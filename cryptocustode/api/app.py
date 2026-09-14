"""Ossatura HTTP dell'applicazione locale (spec §2 decisione 1, spec §4).

`api/` può importare `core/` e `state/`; l'invariante 1 della spec §4 vieta il
verso opposto ed è sorvegliato da `tests/test_architettura.py`.

Il server e l'apertura del browser entrano in `avvia` come parametri con un
default di produzione. Non è un'astrazione per i test: sono le due sole cose di
questo modulo che non si possono osservare da dentro il processo — una blocca
il thread, l'altra lancia un programma esterno — e il vincolo di sicurezza da
dimostrare (l'ascolto sul solo loopback) vive proprio negli argomenti che il
server riceve.

Due superfici restano esposte di proposito, e conviene dirlo perché nessuna
delle due è stata chiesta: `/static` serve l'intera cartella `ui/`, quindi
`/static/index.html` è la stessa pagina di `/`; e `/docs` con `/openapi.json`
restano attivi, perché lo schema è comodo per provare le route del gate di
esportazione. Entrambe sono accettabili soltanto perché l'ascolto è sul solo
loopback: il giorno in cui questa app venisse esposta, vanno chiuse.
"""


import os
import socket
import webbrowser
from collections.abc import Callable, Mapping
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.formparsers import MultiPartParser

from cryptocustode.ai.gemini import VARIABILE_CHIAVE, RilevatoreGemini
from cryptocustode.api.routes_config import crea_router_config
from cryptocustode.api.routes_fascicolo import crea_router
from cryptocustode.api.routes_restore import crea_router_ripristino
from cryptocustode.api.routes_fusioni import crea_router as crea_router_fusioni
from cryptocustode.api.routes_vault import crea_router as crea_router_vault
from cryptocustode.config.stato import Configurazione
from cryptocustode.core.errors import (
    AIKeyMissing,
    AIResponseInvalid,
    AIUnavailable,
    CryptoCustodeError,
    DuplicateFilename,
    ExportNotAllowed,
    FascicoloFull,
    FascicoloNotFound,
    IntegrityError,
    InvalidEncoding,
    MalformedPlaceholder,
    ScannedDocumentRejected,
    UnknownPlaceholder,
    UploadTooLarge,
    VaultNotFound,
    VaultUnreadable,
    VaultVersionNotSupported,
)
from cryptocustode.core.rilevatore import Rilevatore
from cryptocustode.state.session import SessionStore

HOST = "127.0.0.1"
PORTA = 8765
INDIRIZZO = f"http://{HOST}:{PORTA}/"

UI = Path(__file__).resolve().parents[1] / "ui"

PAGINE = {
    "/": "home.html",
    "/nascondi": "nascondi.html",
    "/rimetti": "rimetti.html",
}
"""Le tre pagine dell'interfaccia, e i tre indirizzi da cui si raggiungono.

Erano una sola, con tutto impilato dentro: la configurazione, il caricamento,
la revisione, l'esportazione, il ripristino e il vault. Il proprietario del
prodotto l'ha riassunta così — «non tutto in una pagina» — e la divisione
segue i mestieri, non le schermate: si entra (`/`), si nasconde (`/nascondi`),
si rimette (`/rimetti`).

Tre documenti e non un router nel JavaScript perché i due mestieri non
condividono stato: tutto quello che conta vive nel `SessionStore`, quindi
cambiare pagina non perde niente, e un guasto in uno dei due non può portare
giù l'altro. I due *passi* dentro `/nascondi` stanno invece nello stesso
documento, perché quelli una conversazione sola la sono davvero.

`PAGINA` resta come nome del punto d'ingresso per chi lo importa.
"""

PAGINA = UI / PAGINE["/"]

HOST_CONSENTITI = ("127.0.0.1", "localhost")
"""Gli unici valori accettati nell'intestazione `Host`.

Il bind sul loopback impedisce che l'app sia raggiungibile dalla rete, non che
una pagina ostile aperta nel browser dell'utente le parli: un form cross-origin
in `multipart/form-data` è una richiesta "semplice", quindi il browser la
manda senza preflight. La risposta resta opaca a chi attacca, ma col DNS
rebinding — un nome che risolve a 127.0.0.1 — smetterebbe di esserlo, e
diventerebbe leggibile appena esisterà una route che restituisce il testo
originale. Controllare l'`Host` chiude il rebinding, e costa una riga adesso
contro una riprogettazione dopo. L'autenticazione resta fuori ambito
(spec §17): questo non la sostituisce, chiude solo la strada che il bind sul
loopback lascia aperta.
"""

DIMENSIONE_MASSIMA_IN_MEMORIA = 64 * 1024 * 1024
"""Quanto di un caricamento resta in RAM prima che starlette lo scriva su disco.

Il valore predefinito di `MultiPartParser.spool_max_size` è 1 MiB: oltre
quella soglia il `SpooledTemporaryFile` che regge il file caricato rotola in un
file vero nella cartella temporanea del sistema, **in chiaro**. Per un PDF di
qualche megabyte — il caso normale, non il limite — vorrebbe dire scrivere su
disco il documento che la spec §10 promette di tenere solo nella RAM del
processo. La §16.9 concede lo swap del sistema operativo, che è un
fatto del sistema; questa sarebbe una scrittura scelta dall'applicazione.

**Alzare la soglia non chiude l'invariante della §10, la sposta.** I
documenti reali non toccano più il disco, ma un caricamento oltre questa
soglia rotola ancora in un file in chiaro nella cartella temporanea, e niente
lo rifiuta: la promessa «fuori dal vault il fascicolo vive solo nella RAM del
processo» resta violabile con un input più grande, e quel file sopravvive al
processo in un posto che nessuno pulisce.

Chiuderla davvero vuole un tetto, cioè un rifiuto, cioè un errore di
dominio e una riga nella tabella della §13: è la issue #27. Due vincoli
per chi la prenderà, verificati qui:

- il tetto deve stare **sotto** questa soglia, altrimenti il rifiuto arriva
  dopo la scrittura e non serve a niente;
- il controllo non può stare nel corpo della route. Starlette applica
  `max_part_size` solo alle parti che **non** sono file
  (`formparsers.on_part_data`), quindi un file caricato non ha alcun limite, e
  quando la route riceve il suo `UploadFile` i byte sono già stati scritti.
  L'unico punto utile precede la lettura: `Content-Length`, o un conteggio
  sullo stream in ingresso.
"""

TETTO_RICHIESTA = 32 * 1024 * 1024
"""Quanto può pesare al massimo una richiesta di caricamento, in byte.

Sta **sotto** `DIMENSIONE_MASSIMA_IN_MEMORIA`, e il rapporto fra i due numeri è
la ragione per cui il rifiuto arriva in tempo: una richiesta ammessa resta per
costruzione sotto la soglia oltre la quale starlette scriverebbe su disco, e
nessuna parte può essere più grande della richiesta che la contiene. Se questo
tetto superasse quella soglia, una richiesta ammessa potrebbe comunque rotolare
in chiaro nella cartella temporanea: il rifiuto arriverebbe dopo la scrittura,
cioè troppo tardi. Un test sorveglia la disuguaglianza.

Limita la **richiesta**, non il singolo documento né il fascicolo, perché è
l'unica quantità nota nel solo momento utile — prima che la form venga letta.
Il fascicolo ha già il suo tetto di dieci documenti (§1); un tetto sui byte
complessivi del fascicolo richiederebbe di sommare fra richieste diverse e non
salverebbe dal caso che questo chiude, che è il singolo caricamento enorme.
"""

AlPronto = Callable[[], None]
"""Cosa fare quando l'app entra in servizio. In produzione apre il browser."""

Apri = Callable[[str], object]
"""Apre un indirizzo nel browser dell'utente. In produzione `webbrowser.open`."""

Esegui = Callable[[FastAPI, str, int], None]
"""Serve l'app bloccando il chiamante. In produzione `esegui_uvicorn`."""


class PortaOccupata(RuntimeError):
    """La porta locale è già in uso: un altro programma, o un'altra istanza."""


STATO_HTTP: dict[type[CryptoCustodeError], int] = {
    InvalidEncoding: 422,
    ScannedDocumentRejected: 422,
    FascicoloFull: 422,
    DuplicateFilename: 422,
    FascicoloNotFound: 404,
    ExportNotAllowed: 409,
    IntegrityError: 409,
    UnknownPlaceholder: 422,
    MalformedPlaceholder: 422,
    VaultUnreadable: 422,
    VaultVersionNotSupported: 422,
    UploadTooLarge: 413,
    AIKeyMissing: 503,
    AIUnavailable: 503,
    AIResponseInvalid: 502,
    VaultNotFound: 404,
}
"""La tabella della §13 della spec del 2026-09-10 e della §12 della spec del
2026-09-14, trascritte una volta sola.

Sta qui e non dentro le route perché è un contratto dell'applicazione, non di
un endpoint: ripetuta in ogni handler divergerebbe al primo che dimentica una
riga. `tests/test_caricamento.py` fa rispettare che ogni errore di dominio
abbia la sua riga, così un errore nuovo non può arrivare all'utente come 500.

Il 409 al posto del 403 per l'export negato è lo scostamento consapevole
dichiarato dalla §13: la risorsa è nello stato sbagliato, non manca un
permesso. Le righe del 409 non hanno ancora una route che le solleva — sono il
contratto che le issue dell'approvazione e dell'esportazione erediteranno.
"""


def stato_http_di(errore: BaseException) -> int | None:
    """Il primo stato dichiarato risalendo la gerarchia dell'errore.

    Risalire invece di guardare il tipo esatto serve a un caso che esiste
    già: `VaultVersionNotSupported` è sottoclasse di `VaultUnreadable`
    perché la §13 vuole che chi cattura il genitore continui a
    funzionare. Col confronto esatto un discendente senza riga propria
    diventerebbe un 500 — un difetto del server per una richiesta che il server
    ha capito benissimo.

    Il test di esaustività pretende comunque una riga per ogni discendente,
    e le due difese coprono cose diverse: il test impedisce che una riga
    mancante arrivi fino a un utente, la risalita impedisce che, se ci
    arrivasse, il danno sia un 500. E la risalita copre il buco del test:
    `__subclasses__` vede solo le classi già importate, quindi un errore
    definito in un modulo che nessun test importa gli sfuggirebbe.
    """
    # Attenzione a chi tocca il test di esaustività: questa risalita
    # **sposta** la rete, non la aggiunge. Col confronto sul tipo esatto
    # una riga mancante era rumorosa a runtime (un 500); risalendo, un
    # errore nuovo sotto una classe già mappata eredita in silenzio il
    # codice del padre, che potrebbe non essere il suo. Ciò che rende
    # sicura questa scelta è soltanto quel test: la protezione è
    # passata dal runtime al tempo di test, e indebolire il test riapre la
    # classe di difetto in silenzio.
    for classe in type(errore).__mro__:
        if classe in STATO_HTTP:
            return STATO_HTTP[classe]
    return None


def rispondi_all_errore_di_dominio(richiesta: Request, errore: Exception) -> JSONResponse:
    """Traduce un errore di dominio nella sua risposta HTTP (spec §13).

    Il messaggio dell'errore arriva all'utente così com'è: i messaggi del core
    sono già in italiano e già portano il dettaglio che serve a rimediare — il
    numero di pagina della scansione, l'offset del byte invalido, il nome del
    file duplicato. Riscriverli qui significherebbe averne due versioni che
    divergono.

    Se nemmeno la gerarchia dichiara uno stato, l'errore viene
    **rilanciato**: finisce in `ServerErrorMiddleware`, che lo registra col
    suo traceback. Servirlo come 500 col messaggio di dominio lo renderebbe
    invisibile nei log e indistinguibile, per chi guarda, da una risposta
    voluta.
    """
    stato = stato_http_di(errore)
    if stato is None:
        raise errore
    return JSONResponse(status_code=stato, content={"errore": str(errore)})


def servi_pagina(percorso: Path) -> Callable[[], FileResponse]:
    """Un endpoint che serve **quel** file, e nient'altro.

    Il percorso è deciso qui, a costruzione dell'app, e non può essere
    influenzato dalla richiesta: è la differenza fra servire tre pagine e
    offrire al browser di scegliere quale file leggere dal disco.
    """

    def servi() -> FileResponse:
        return FileResponse(percorso, media_type="text/html")

    return servi


def crea_app(
    *,
    al_pronto: AlPronto | None = None,
    store: SessionStore | None = None,
    rilevatore: Rilevatore | None = None,
    configurazione: Configurazione | None = None,
    tetto_richiesta: int = TETTO_RICHIESTA,
) -> FastAPI:
    """L'app HTTP: serve la pagina della UI, i suoi statici e le route del fascicolo.

    `al_pronto` viene chiamato quando l'app entra in servizio, non quando viene
    creata: è l'aggancio con cui `avvia` apre la scheda del browser soltanto a
    server pronto. Chi crea l'app per interrogarla — i test, e in futuro altre
    route — lo lascia assente e non apre nulla.

    `store` è il secondo seme: in produzione ogni avvio parte da uno store
    vuoto, e chi costruisce l'app per interrogarla passa il proprio così da
    poter guardare il fascicolo invece di credere alla risposta HTTP sulla
    parola. Non è un singleton di modulo di proposito: due app dello stesso
    processo non devono condividere il fascicolo.

    `rilevatore` è il terzo seme, per la stessa ragione: chi inietta un doppio
    evita che i suoi test facciano partire il client Gemini vero (spec §4,
    invariante 5). Il default `RilevatoreGemini()` non chiama nessuno alla
    costruzione — la chiave si legge alla prima `rileva` — quindi creare
    l'app senza chiave resta possibile, ed è ciò che permette a ogni test che
    non analizza di ignorare questo parametro.
    """
    if store is None:
        store = SessionStore()
    if configurazione is None:
        configurazione = Configurazione()
    # Dopo la configurazione, e non prima: il rilevatore di produzione ne legge
    # modello e chiave a ogni chiamata, quindi costruirlo senza vuol dire
    # inchiodarlo ai valori dell'ambiente e rendere inefficace la pagina di
    # configurazione, che continuerebbe a salvare senza che nulla cambi.
    if rilevatore is None:
        rilevatore = RilevatoreGemini(configurazione=configurazione)

    @asynccontextmanager
    async def ciclo_di_vita(app: FastAPI):
        if al_pronto is not None:
            al_pronto()
        yield

    # Soglia di processo, non dell'app: `spool_max_size` è un attributo
    # di classe che starlette legge a ogni parsing. Sta qui e non a livello
    # di modulo perché l'import di `api.app` non deve avere effetti
    # collaterali su una libreria di terze parti; creare l'app sì, è
    # il momento in cui questo processo diventa l'applicazione.
    MultiPartParser.spool_max_size = DIMENSIONE_MASSIMA_IN_MEMORIA

    app = FastAPI(title="CryptoCustode", lifespan=ciclo_di_vita)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(HOST_CONSENTITI))

    @app.middleware("http")
    async def rifiuta_i_caricamenti_troppo_grandi(richiesta: Request, chiama):
        """Chiude la richiesta troppo grande prima che qualcuno ne legga il corpo.

        È un middleware e non un controllo nella route perché quando la route
        riceve il suo `UploadFile` i byte sono già stati scritti: starlette
        verifica `max_part_size` solo nel ramo delle parti che non sono file
        (`formparsers.py`, `on_part_data`), e una parte-file finisce in
        `_file_parts_to_write` senza alcun controllo di dimensione. Qui invece
        non è ancora stato letto niente.

        `Content-Length` assente significa rifiuto, non passaggio libero: senza
        quel numero l'unico modo di sapere quanto pesa è leggerlo, che è
        esattamente ciò che si sta cercando di evitare. Davanti a
        un'invariante di riservatezza il dubbio si chiude.
        """
        if richiesta.method == "POST" and richiesta.url.path.startswith("/api/"):
            dichiarata = richiesta.headers.get("content-length")
            if dichiarata is None or not dichiarata.isdigit():
                return rispondi_all_errore_di_dominio(
                    richiesta,
                    UploadTooLarge(
                        "dimensione del caricamento non dichiarata: "
                        f"il massimo accettato e' {tetto_richiesta} byte"
                    ),
                )
            if int(dichiarata) > tetto_richiesta:
                return rispondi_all_errore_di_dominio(
                    richiesta,
                    UploadTooLarge(
                        "il caricamento e' troppo grande: "
                        f"il massimo accettato e' {tetto_richiesta} byte"
                    ),
                )
        return await chiama(richiesta)
    @app.middleware("http")
    async def non_conservare_gli_statici(richiesta: Request, chiama):
        """Gli statici non si mettono in cache.

        Un'applicazione locale si aggiorna sostituendo i file sul posto, e il
        browser non ha modo di accorgersene: dopo un aggiornamento la pagina
        continua a usare il CSS e il JavaScript vecchi, e l'utente vede un
        difetto gia' corretto — o peggio, uno script nuovo contro un foglio di
        stile vecchio. E' successo qui durante lo sviluppo, con una regola
        `[hidden]` nuova ignorata per un quarto d'ora.

        Non costa niente: i file arrivano da questo stesso computer, e il
        risparmio di banda che la cache offre non esiste sul loopback.
        """
        risposta = await chiama(richiesta)
        if richiesta.url.path.startswith("/static/"):
            risposta.headers["Cache-Control"] = "no-store"
        return risposta

    app.mount("/static", StaticFiles(directory=UI), name="static")
    app.include_router(crea_router(store, rilevatore))
    # Il vault ha un router suo perche' ha un file suo: le sue due rotte non
    # toccano il fascicolo attivo per id come fanno quelle di `routes_fascicolo`,
    # lo sostituiscono per intero. Riceve lo **stesso** store, altrimenti
    # salverebbe un fascicolo diverso da quello che l'utente sta revisionando.
    app.include_router(crea_router_vault(store, configurazione))
    # I suggerimenti di fusione hanno un router loro perche' non sono un passo
    # della revisione: non bloccano niente e il fascicolo che li ignora e'
    # esattamente quello di prima (spec 7).
    app.include_router(crea_router_fusioni(store))
    app.include_router(crea_router_config(configurazione))
    app.include_router(crea_router_ripristino(store))
    app.add_exception_handler(CryptoCustodeError, rispondi_all_errore_di_dominio)

    # Una rotta per pagina, registrate dal dizionario invece che scritte tre
    # volte: aggiungere una schermata non deve poter significare aggiungerla
    # all'elenco e dimenticare la rotta, o il contrario — due elenchi che
    # dicono la stessa cosa sono due elenchi che divergono.
    #
    # Il gestore si costruisce in una funzione a parte e non dentro il ciclo:
    # una funzione definita nel ciclo cattura la variabile, non il suo valore,
    # e tutte e tre servirebbero l'ultima pagina. Il percorso arriva per
    # chiusura e non come parametro, perché un parametro di un endpoint FastAPI
    # è un parametro della richiesta — cioè qualcosa che il browser potrebbe
    # scegliere, e qui sceglierebbe quale file leggere dal disco.
    for indirizzo, nome_file in PAGINE.items():
        app.add_api_route(
            indirizzo,
            servi_pagina(UI / nome_file),
            methods=["GET"],
            include_in_schema=False,
        )

    return app


def apri_ascolto(host: str, porta: int) -> socket.socket:
    """Mette in ascolto il socket del server, o solleva `PortaOccupata`.

    Nessun `SO_REUSEADDR`: su Windows permette di legare una porta già in uso,
    e accorgersi che è occupata è metà del lavoro di questa funzione.
    """
    presa = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        presa.bind((host, porta))
    except OSError as errore:
        presa.close()
        raise PortaOccupata(
            f"la porta {porta} di {host} è già occupata: chiudi il programma "
            "che la usa — o l'altra istanza di CryptoCustode — e riprova"
        ) from errore
    presa.listen()
    return presa


def esegui_uvicorn(app: FastAPI, host: str, porta: int) -> None:
    """Il default di produzione di `Esegui`. Blocca finché il server vive.

    Il socket viene legato qui e non da uvicorn, e la ragione riguarda entrambe
    le volte in cui la scheda del browser può arrivare nel momento sbagliato:

    - uvicorn esegue il ciclo di vita dell'app **prima** di legare la porta
      (`Server.startup` fa `await self.lifespan.startup()` e solo dopo
      `loop.create_server`), quindi l'aggancio che apre la scheda scatterebbe
      su un socket non ancora in ascolto;
    - con la porta occupata, il bind fallirebbe **dopo** quell'apertura:
      l'utente vedrebbe la pagina di un altro programma — o un errore di
      connessione — mentre CryptoCustode è già terminato.

    Legando prima, la scheda non può precedere il server, e `PortaOccupata`
    arriva prima che si apra qualsiasi cosa.
    """
    with apri_ascolto(host, porta) as presa:
        # Ricevendo un socket già legato, uvicorn salta la sua riga «Uvicorn
        # running on ...» (`Server.startup` la stampa solo quando lega da sé,
        # dando per scontato che chi passa i socket abbia già informato). Senza
        # questa stampa, chi non vede aprirsi la scheda — nessun browser
        # predefinito, per esempio — non saprebbe dove andare.
        print(
            f"CryptoCustode è in ascolto su http://{host}:{porta}/ — CTRL+C per chiudere",
            flush=True,
        )
        uvicorn.Server(uvicorn.Config(app, host=host, port=porta)).run(sockets=[presa])


PIANO_ATTESTATO = "CRYPTOCUSTODE_GEMINI_PIANO"


def verifica_configurazione_ia(
    ambiente: Mapping[str, str], configurazione: "Configurazione | None" = None
) -> None:
    """Rifiuta l'avvio se la chiave manca o il piano non è attestato (D8).

    L'attestazione è una dichiarazione dell'utente, non una verifica: l'API non
    espone il piano di fatturazione, quindi l'applicazione non ha modo di
    controllarlo. Serve comunque, e non è teatro: costringe chi avvia a leggere
    perché il piano gratuito non va bene, prima che il primo documento parta.
    """
    # Una chiave salvata sul disco basta per partire, anche se e' ancora
    # cifrata: la passphrase si chiede nella pagina. Uccidere qui il processo
    # perche' la variabile d'ambiente non c'e' impedirebbe di **arrivare** alla
    # pagina in cui la chiave si scrive, cioe' renderebbe la configurazione
    # raggiungibile solo a chi e' gia' configurato.
    # Con una configurazione, l'avvio non si blocca **mai**: chiave e
    # attestazione si raccolgono nella pagina, e il rifiuto vive dove serve
    # davvero, in `RilevatoreGemini.rileva`, subito prima che un documento
    # parta. Bloccare qui rendeva irraggiungibile proprio la pagina in cui si
    # configura — cioe' impediva di rimediare all'unica condizione che il
    # blocco denunciava.
    #
    # Senza configurazione il comportamento resta quello di prima, ed e' il
    # contratto che i test di questo modulo verificano.
    if configurazione is not None:
        return
    if not ambiente.get(VARIABILE_CHIAVE):
        raise SystemExit(
            "Non c'è nessuna chiave di Gemini: né salvata nella configurazione, "
            f"né nella variabile d'ambiente {VARIABILE_CHIAVE}. CryptoCustode "
            "manda i tuoi documenti a Gemini per farli analizzare, quindi senza "
            "chiave non può partire.\n"
            f"Imposta {VARIABILE_CHIAVE} per questo avvio: dalla pagina potrai "
            "poi salvarne una cifrata, e da lì in avanti basterà la passphrase."
        )
    if ambiente.get(PIANO_ATTESTATO) != "pagamento":
        raise SystemExit(
            f"Imposta {PIANO_ATTESTATO}=pagamento per confermare che la chiave "
            "appartiene a un progetto con fatturazione attiva.\n"
            "Sul piano gratuito i termini di Gemini dicono di non inviare dati "
            "personali, e Google usa i contenuti per sviluppare i propri "
            "prodotti: CryptoCustode non invia altro che documenti con dati "
            "personali dentro."
        )


def avvia(*, esegui: Esegui = esegui_uvicorn, apri: Apri = webbrowser.open) -> None:
    """Avvia l'applicazione: ascolto sul solo loopback e scheda del browser.

    `HOST` non è configurabile dall'esterno di proposito. Un fascicolo contiene
    dati personali di terzi e l'applicazione non ha autenticazione: legarla a
    `0.0.0.0` li offrirebbe a chiunque sia sulla stessa rete.

    Il controllo della decisione D8 precede l'apertura della porta: scoprire
    che la chiave manca o il piano non è attestato **dopo** aver aperto la
    scheda del browser mostrerebbe all'utente una pagina che si romperà al
    primo «Analizza», invece di un messaggio chiaro in console.
    """
    configurazione = Configurazione()
    verifica_configurazione_ia(os.environ, configurazione)
    app = crea_app(al_pronto=lambda: apri(INDIRIZZO), configurazione=configurazione)
    esegui(app, HOST, PORTA)
