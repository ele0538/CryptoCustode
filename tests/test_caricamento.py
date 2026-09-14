"""Caricamento dei documenti dalla UI, coi rifiuti visibili all'utente (issue #3).

Questi test difendono due cose distinte:

1. che TXT e PDF digitali entrino davvero nel fascicolo col testo estratto;
2. che i rifiuti del motore — tetto dei 10, PDF scansionato, TXT non UTF-8,
   omonimia — arrivino allo schermo come messaggi in italiano con il dettaglio
   che serve a rimediare (pagina, offset, nome del file), invece di morire come
   500 con un traceback.

Il fascicolo è ispezionato **attraverso lo store**, non solo attraverso la
risposta HTTP: un rifiuto deve lasciare il fascicolo esattamente com'era, e la
risposta da sola non lo dimostra.
"""

import inspect
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cryptocustode.api.app import STATO_HTTP, UI, crea_app, stato_http_di
from cryptocustode.api.routes_fascicolo import ID_FASCICOLO_ATTIVO, crea_router
from cryptocustode.core.errors import (
    AIKeyMissing,
    AIResponseInvalid,
    AIUnavailable,
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
from cryptocustode.state.session import SessionStore
from tests.doppi import RilevatoreFinto
from tests.pdf_di_prova import pdf_di_prova

ROTTA = "/api/fascicolo/documenti"
INDIRIZZO_DI_PROVA = "http://127.0.0.1:8765"
HARNESS = Path(__file__).parent / "ui_harness.mjs"
"""L'app accetta solo il loopback nell'intestazione `Host`, quindi il
`base_url` di default del TestClient (`http://testserver`) prenderebbe un
400. Il valore di prova sta qui e non fra gli host consentiti in
produzione."""


def documenti_del(store: SessionStore):
    """I nomi dei documenti entrati nel fascicolo attivo, in ordine di arrivo.

    Restituisce `[]` anche quando il fascicolo non esiste ancora: la creazione
    è pigra (vedi `fascicolo_attivo`), quindi un rifiuto al primo
    caricamento lascia lo store vuoto. Per chi guarda da fuori i due casi sono
    lo stesso — nessun documento è entrato — e distinguerli qui renderebbe
    i test dei rifiuti dipendenti dall'ordine dei controlli dentro la route.

    L'esistenza si chiede con `contiene`: prima passava da un `except KeyError`,
    che legava il test a *quale* eccezione lo store solleva. Dalla issue #16 è
    `FascicoloNotFound`, e un test che dipendeva da quel dettaglio si sarebbe
    rotto per un cambio che non riguarda il caricamento.

    Resta falsificabile: se la route smettesse di salvare il fascicolo, i test
    del percorso felice vedrebbero `[]` al posto dei nomi attesi.
    """
    if not store.contiene(ID_FASCICOLO_ATTIVO):
        return []
    return [documento.filename for documento in store.prendi(ID_FASCICOLO_ATTIVO).documents]


def carica(client: TestClient, nome: str, contenuto: bytes):
    """Un caricamento multipart, come lo fa la UI: un file per richiesta."""
    return client.post(ROTTA, files={"file": (nome, contenuto)})


@pytest.fixture
def store() -> SessionStore:
    """Lo store del test, passato all'app come seme.

    Senza il seme lo store sarebbe interno all'app e i test dovrebbero credere
    alla risposta HTTP sulla parola; con un `SessionStore` globale di modulo si
    passerebbero invece i fascicoli l'uno all'altro.
    """
    return SessionStore()


@pytest.fixture
def client(store):
    with TestClient(crea_app(store=store), base_url=INDIRIZZO_DI_PROVA) as client:
        yield client


def test_un_txt_utf8_entra_nel_fascicolo_col_testo_estratto(client, store):
    """Il primo criterio della issue #3. Se la route non salva il documento nel
    fascicolo attivo, la risposta può comunque dire 201 e l'utente crede di aver
    caricato: al momento dell'analisi il fascicolo è vuoto."""
    risposta = carica(client, "contratto.txt", "Il sig. Rossi è a Torino.".encode("utf-8"))

    assert risposta.status_code == 201
    assert documenti_del(store) == ["contratto.txt"]
    assert store.prendi(ID_FASCICOLO_ATTIVO).documents[0].text == "Il sig. Rossi è a Torino."


def test_un_pdf_digitale_entra_nel_fascicolo_col_testo_estratto(client, store):
    """Il PDF passa da un estrattore diverso dal TXT: una route che decodificasse
    tutto come testo supererebbe il test sul TXT e fallirebbe qui, perché i byte
    di un PDF non sono UTF-8 valido."""
    risposta = carica(client, "contratto.pdf", pdf_di_prova(["testo", "testo"]))

    assert risposta.status_code == 201
    assert documenti_del(store) == ["contratto.pdf"]
    assert risposta.json()["pagine"] == 2, (
        "il conteggio delle pagine deve venire dal documento: un 1 costante "
        "passerebbe su un PDF di una pagina sola"
    )
    assert "Contratto di locazione" in store.prendi(ID_FASCICOLO_ATTIVO).documents[0].text


def test_la_risposta_restituisce_il_testo_originale_estratto(client):
    """L'utente deve poter leggere che cosa è stato estratto dal file: è il solo
    modo di accorgersi che un PDF ha reso testo sbagliato o vuoto. È il testo
    **originale**, non il mascherato: l'invariante 3 della spec §4 vuole che il
    mascherato esca solo dal gate di esportazione.

    Il conteggio dei caratteri è contato a mano sulla frase, non chiesto al
    codice sotto test."""
    risposta = carica(client, "nota.txt", "Torino, 12 marzo.".encode("utf-8"))

    esito = risposta.json()
    assert esito["testo"] == "Torino, 12 marzo."
    assert esito["caratteri"] == 17
    assert esito["pagine"] == 1
    assert esito["documenti_nel_fascicolo"] == 1
    assert esito["massimo_documenti"] == 10, "il tetto della spec §1, servito e non riscritto nella UI"


def test_il_testo_mascherato_non_compare_nella_risposta_del_caricamento(client):
    """Invariante 3 della spec §4 e §4 «nessuna anteprima del mascherato prima
    dell'approvazione»: se la route servisse anche il mascherato, l'anteprima
    sarebbe copiabile e il gate di approvazione una formalità aggirabile."""
    risposta = carica(client, "nota.txt", "Il sig. Rossi è a Torino.".encode("utf-8"))

    corpo = risposta.text
    assert not re.search(r"\[[A-Z]+_\d+\]", corpo), (
        "nessun segnaposto deve comparire: il caricamento non maschera e non "
        f"mostra anteprime — {corpo[:200]}"
    )


# --- I rifiuti, che sono il titolo della issue ------------------------------
#
# La spec §13 mappa tutti e quattro a **422**, con un messaggio che dice cosa
# rimediare. Ogni test verifica due cose insieme, perché separate non dicono
# niente: che l'utente legga la ragione, e che il fascicolo sia rimasto com'era.
# Una route che rifiutasse dopo aver mutato il fascicolo darebbe un messaggio
# giusto e un fascicolo sbagliato.


def test_l_undicesimo_documento_e_rifiutato_e_il_fascicolo_resta_di_dieci(client, store):
    """Tetto di 10 documenti per fascicolo (spec §1). Il tetto vive in
    `aggiungi_documento`: una route che facesse `documents.append(...)` da sé
    lo aggirerebbe, e l'undicesimo entrerebbe in silenzio."""
    for numero in range(10):
        accettato = carica(client, f"doc{numero}.txt", b"testo")
        assert accettato.status_code == 201

    # Il contatore che la UI stampa deve **salire**: una costante `1` passerebbe
    # tutti gli altri test e la pagina direbbe "1 di 10" dopo dieci caricamenti.
    assert accettato.json()["documenti_nel_fascicolo"] == 10

    risposta = carica(client, "undicesimo.txt", b"testo")

    assert risposta.status_code == 422
    assert "10" in risposta.json()["errore"]
    assert len(documenti_del(store)) == 10
    assert "undicesimo.txt" not in documenti_del(store)


def test_un_pdf_scansionato_e_rifiutato_per_intero_con_la_pagina_colpevole(client, store):
    """Rifiuto dell'intero file, mai di una parte (spec §12), e l'utente deve
    sapere **quale** pagina: senza il numero non può né rifare la scansione né
    togliere la pagina. Qui la scansione è la terza di tre."""
    risposta = carica(client, "scansionato.pdf", pdf_di_prova(["testo", "testo", "immagine"]))

    assert risposta.status_code == 422
    assert "pagina 3" in risposta.json()["errore"]
    assert documenti_del(store) == [], "un rifiuto non deve lasciare traccia nel fascicolo"


def test_un_txt_non_utf8_e_rifiutato_con_la_posizione_del_byte_invalido(client, store):
    """La posizione serve a rimediare: dice dove guardare nel file. L'offset
    atteso è contato a mano — `Via Roma 1` sono dieci caratteri ASCII, indici da
    0 a 9, quindi il byte `0xff` sta all'offset 10 — e non chiesto al codice."""
    risposta = carica(client, "latino1.txt", "Via Roma 1".encode("ascii") + b"\xff")

    assert risposta.status_code == 422
    assert "offset 10" in risposta.json()["errore"]
    assert documenti_del(store) == []


def test_il_secondo_file_con_lo_stesso_nome_e_rifiutato_col_nome_nel_messaggio(client, store):
    """Due omonimi collasserebbero in una sola chiave del payload di export e
    l'utente riceverebbe un documento in meno senza errori (spec §8, issue #19).
    Il nome nel messaggio è ciò che gli permette di capire quale rinominare."""
    assert carica(client, "contratto.txt", b"primo").status_code == 201

    risposta = carica(client, "contratto.txt", b"secondo")

    assert risposta.status_code == 422
    assert "contratto.txt" in risposta.json()["errore"]
    assert documenti_del(store) == ["contratto.txt"]
    assert store.prendi(ID_FASCICOLO_ATTIVO).documents[0].text == "primo", (
        "il primo documento non deve essere sovrascritto dal secondo"
    )


def test_i_segnaposto_gia_presenti_sono_un_avviso_con_la_posizione_non_un_rifiuto(
    client, store
):
    """Spec §12: il documento entra, ma l'utente viene avvisato. Al ripristino
    quella stringa verrebbe interpretata come segnaposto e sostituita con dati
    veri, corrompendo il testo — e se qui fosse un rifiuto, un documento
    legittimo che cita un segnaposto non si potrebbe caricare affatto.

    La posizione attesa è contata a mano: `Il sig. ` sono otto caratteri, indici
    da 0 a 7, quindi la parentesi quadra sta all'offset 8."""
    risposta = carica(client, "citazione.txt", "Il sig. [PERSONA_1] è a Torino.".encode("utf-8"))

    assert risposta.status_code == 201
    assert documenti_del(store) == ["citazione.txt"], "l'avviso non è un rifiuto"
    assert risposta.json()["segnaposto_preesistenti"] == [
        {"posizione": 8, "segnaposto": "[PERSONA_1]"}
    ]


def test_un_documento_pulito_non_porta_avvisi_di_segnaposto(client):
    """Il controllo del controllo: senza questo, un avviso restituito sempre —
    anche a vuoto — passerebbe per un rilevamento funzionante, e la UI
    mostrerebbe un allarme a ogni caricamento finché nessuno ci crede più."""
    risposta = carica(client, "pulito.txt", "Nessun segnaposto qui.".encode("utf-8"))

    assert risposta.json()["segnaposto_preesistenti"] == []


def test_ogni_errore_di_dominio_ha_uno_stato_http_dichiarato():
    """La tabella della spec §13 vive in un posto solo, `STATO_HTTP`. Questo
    test è il guardiano di quel posto: un errore di dominio aggiunto senza la
    sua riga arriverebbe all'utente come 500 con un traceback, che è esattamente
    ciò che la §13 esiste per impedire.

    Il confronto è sulle sottoclassi vive di `CryptoCustodeError`, non su
    un elenco scritto a mano che si sgancerebbe dal codice. Conta solo la
    discendenza definita dentro `cryptocustode.`: una sottoclasse creata
    dentro un test non è un errore di produzione e non ha bisogno di una
    riga — e senza questo filtro il test diventerebbe rosso, o verde, a
    seconda dell'ordine in cui i test girano."""
    from cryptocustode.api.app import STATO_HTTP
    from cryptocustode.core.errors import CryptoCustodeError

    def discendenti(classe):
        for figlia in classe.__subclasses__():
            yield figlia
            yield from discendenti(figlia)

    senza_stato = {
        errore.__name__
        for errore in discendenti(CryptoCustodeError)
        if errore.__module__.startswith("cryptocustode.") and errore not in STATO_HTTP
    }
    assert senza_stato == set(), (
        "errori di dominio senza stato HTTP nella tabella della spec §13: "
        + ", ".join(sorted(senza_stato))
    )


# --- La tabella della spec, la UI e il disco --------------------------------


def test_la_tabella_degli_stati_trascrive_la_spec():
    """`STATO_HTTP` non è una scelta dell'API: è la trascrizione delle
    tabelle della §13 della spec del 2026-09-10 e della §12 della spec del
    2026-09-14, che sono l'autorità.

    Il confronto con un letterale scritto a mano è un rilevatore di
    cambiamenti, e qui è esattamente quello che serve: sei di queste righe
    non hanno ancora una route che le solleva, quindi il loro *valore* non è
    esercitato da nessun test di comportamento. Cambiare il 409 dell'export in
    un 500 non romperebbe niente fino al giorno in cui quella route esiste — e
    quel giorno il difetto sembrerebbe suo.
    """
    assert STATO_HTTP == {
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


def test_una_richiesta_con_un_host_diverso_dal_loopback_non_viene_servita(store):
    """Il bind sul loopback non impedisce a una pagina ostile aperta nel
    browser dell'utente di parlare con l'app: un form cross-origin in
    `multipart/form-data` è una richiesta "semplice", quindi il browser la
    manda senza preflight. Col DNS rebinding — un nome che risolve a
    127.0.0.1 — anche la risposta diventerebbe leggibile, e lo sarà davvero
    appena esisterà una route che restituisce il testo originale.

    Il controllo dell'`Host` è ciò che chiude quella strada.
    """
    with TestClient(crea_app(store=store), base_url="http://cattivo.example") as client:
        assert client.get("/").status_code == 400
        assert carica(client, "contratto.txt", b"testo").status_code == 400

    assert documenti_del(store) == []


def test_gli_identificativi_cercati_dallo_script_esistono_nella_pagina():
    """Nessun test esegue `app.js` — in questo repo non c'è infrastruttura
    JavaScript — e un `getElementById` con un nome sbagliato fa morire la
    pagina al caricamento senza che la suite se ne accorga: l'`app.js` viene
    comunque servito, e il test che lo verifica guarda solo che risponda 200.

    Questo test non esegue lo script: controlla che i due file si riferiscano
    agli stessi nomi, che è la rottura che nessun altro vedrebbe.
    """
    script = (UI / "app.js").read_text(encoding="utf-8")
    pagina = (UI / "index.html").read_text(encoding="utf-8")

    cercati = set(re.findall(r'getElementById\("([^"]+)"\)', script))

    assert cercati, "atteso che lo script cerchi almeno un elemento della pagina"
    mancanti = sorted(nome for nome in cercati if f'id="{nome}"' not in pagina)
    assert mancanti == [], f"lo script cerca elementi che la pagina non ha: {mancanti}"


def test_il_campo_multipart_dello_script_e_quello_che_la_route_aspetta():
    """Se il nome del campo divergesse, ogni caricamento risponderebbe 422 di
    validazione e la riga nella pagina direbbe soltanto "richiesta non valida":
    un guasto totale con un messaggio che non indica la causa.

    Il nome atteso è chiesto alla firma della route, non riscritto a mano.
    """
    script = (UI / "app.js").read_text(encoding="utf-8")
    [campo] = re.findall(r'corpo\.append\("([^"]+)"', script)

    router = crea_router(SessionStore(), RilevatoreFinto())
    [rotta] = [r for r in router.routes if getattr(r, "path", "") == ROTTA]
    parametri = set(inspect.signature(rotta.endpoint).parameters)

    assert campo in parametri, (
        f'lo script manda la parte "{campo}", la route aspetta {sorted(parametri)}'
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node non installato")
def test_lo_script_della_ui_e_sintatticamente_valido():
    """Un errore di sintassi in `app.js` non fa fallire nulla nella suite: la
    pagina viene servita, il browser scarta lo script e la UI è morta senza
    un solo test rosso. `node --check` non lo esegue, lo compila: è il
    controllo più debole che intercetta comunque quella rottura.
    """
    esito = subprocess.run(
        ["node", "--check", str(UI / "app.js")], capture_output=True, text=True
    )

    assert esito.returncode == 0, esito.stderr


def test_un_documento_di_tre_megabyte_non_viene_scritto_su_disco(client, monkeypatch):
    """Spec §10: fuori dal vault il fascicolo vive **solo** nella RAM del
    processo. Col valore predefinito di starlette ogni parte oltre 1 MiB rotola
    in un file in chiaro nella cartella temporanea del sistema — cioè il PDF
    normale, non il caso limite. La §16.9 concede lo swap del sistema
    operativo, che è un fatto del sistema; quella sarebbe una scrittura
    scelta dall'applicazione.

    Il test non guarda la costante, che potrebbe esserci e non essere usata:
    sorveglia `rollover`, il metodo che sposta i byte su disco, e pretende che
    nessuno lo chiami.
    """
    rotolamenti = []
    rollover_vero = tempfile.SpooledTemporaryFile.rollover

    def rollover_sorvegliato(self):
        rotolamenti.append(True)
        return rollover_vero(self)

    monkeypatch.setattr(tempfile.SpooledTemporaryFile, "rollover", rollover_sorvegliato)

    risposta = carica(client, "grande.txt", b"x" * (3 * 1024 * 1024))

    assert risposta.status_code == 201
    assert rotolamenti == [], "i byte del documento sono stati scritti su disco in chiaro"


def test_due_file_nella_stessa_richiesta_sono_rifiutati_e_nessuno_entra(client, store):
    """Due parti con lo stesso nome: prima vinceva la seconda e la prima
    spariva in silenzio, con un 201 a dire che era andato tutto bene. È lo
    stesso guasto per cui esiste `DuplicateFilename` (spec §8) — un
    documento in meno senza alcun errore — e un rifiuto è la sola risposta
    che non mente. Dalla UI non è raggiungibile: la route non deve dipendere
    da questo.
    """
    risposta = client.post(
        ROTTA,
        files=[("file", ("primo.txt", b"primo")), ("file", ("secondo.txt", b"secondo"))],
    )

    assert risposta.status_code == 422
    assert "2" in risposta.json()["errore"]
    assert documenti_del(store) == []


def test_il_nome_del_file_perde_il_percorso(client, store):
    """Il nome arriva dal client e diventa una chiave del payload di export
    (spec §8). Oggi nessuno scrive su disco, quindi `../../etc/passwd.txt`
    non è sfruttabile; il giorno in cui quelle chiavi diventano nomi di file
    lo sarebbe, e allora accorgersene costerebbe molto di più.
    """
    risposta = carica(client, "../../etc/passwd.txt", b"testo")

    assert risposta.status_code == 201
    assert risposta.json()["filename"] == "passwd.txt"
    assert documenti_del(store) == ["passwd.txt"]


# --- La risalita della gerarchia e la UI eseguita per davvero ---------------

senza_node = pytest.mark.skipif(
    shutil.which("node") is None, reason="node non installato: la UI non viene eseguita"
)


def test_un_errore_nuovo_sotto_una_classe_mappata_eredita_il_suo_stato():
    """La tabella si legge **risalendo** la gerarchia dell'errore, non
    confrontando il tipo esatto: un discendente senza riga propria esce col
    codice del genitore invece che con un 500. Un 500 è un difetto del
    server, e qui il server ha capito benissimo la richiesta.

    La sottoclasse è definita qui, e non in `core/errors.py`, proprio
    perché non deve avere una riga: è il caso che il test di
    esaustività non può coprire, visto che `__subclasses__` vede solo
    le classi già importate.
    """

    class ExportNegatoSperimentale(ExportNotAllowed):
        pass

    assert stato_http_di(ExportNegatoSperimentale("x")) == 409


def esito_della_ui(scenario: str) -> dict:
    """Esegue il vero `cryptocustode/ui/app.js` e restituisce quello che
    l'utente avrebbe visto: le righe dell'elenco, il contatore, e quali file
    sono stati davvero tentati.

    L'harness (`tests/ui_harness.mjs`) carica il file di produzione — non una
    copia — dentro un DOM finto, con una `fetch` programmata. Non prova il
    rendering né il CSS: quello resta un controllo umano. Prova la logica,
    che è la metà che nessun test toccava.
    """
    esecuzione = subprocess.run(
        ["node", str(HARNESS), scenario],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert esecuzione.returncode == 0, esecuzione.stderr
    return json.loads(esecuzione.stdout)


@senza_node
def test_una_risposta_senza_corpo_json_non_interrompe_la_fila_dei_file():
    """Il guasto che questa riga difende è stato misurato, non immaginato:
    con `await risposta.json()` fuori dal `try`, un 500 servito come testo
    rigettava la promessa, il ciclo dei file moriva su quel file, i successivi
    non venivano nemmeno tentati e nessuna riga compariva in pagina. Cioè
    esattamente il "morire come 500 senza spiegazione" che questa slice esiste
    per impedire, spostato di un livello.
    """
    esito = esito_della_ui("corpo-non-json")

    assert [riga["classe"] for riga in esito["righe"]] == ["caricato", "rifiutato", "caricato"]
    assert [tentativo["file"] for tentativo in esito["tentativi"]] == [
        "uno.txt",
        "due.txt",
        "tre.txt",
    ], "i file dopo quello fallito devono essere tentati comunque"
    assert esito["scelta_svuotata"], "la selezione va svuotata anche dopo un errore"


@senza_node
def test_un_errore_di_validazione_arriva_in_pagina_col_suo_messaggio():
    """FastAPI risponde alle richieste malformate con `detail`, non con
    `errore`: leggendo solo `errore` la riga diceva `undefined`, cioè un
    guasto totale con un messaggio che non indica niente.
    """
    esito = esito_della_ui("dettaglio-di-validazione")

    [riga] = esito["righe"]
    assert riga["classe"] == "rifiutato"
    assert "campo mancante: file" in riga["testo"]
    assert "undefined" not in riga["testo"]


@senza_node
def test_il_contatore_usa_il_tetto_servito_dal_payload():
    """Il "di 10" era scritto a mano nello script: al primo cambio di
    `MAX_DOCUMENTI` la pagina avrebbe mentito. Lo scenario serve 3 documenti su
    un tetto di 7, quindi un 10 nella riga vorrebbe dire che il numero viene
    ancora da una costante del JavaScript.
    """
    esito = esito_della_ui("tetto-dal-payload")

    assert "3" in esito["conteggio"]
    assert "7" in esito["conteggio"]
    assert "10" not in esito["conteggio"]


@senza_node
def test_gli_avvisi_sono_limitati_e_il_resto_viene_riassunto():
    """Un documento che cita legittimamente molti segnaposto produceva una riga
    di tre frasi per ciascuno: l'avviso che conta finiva sepolto sotto gli
    altri. Lo scenario ne serve otto.
    """
    esito = esito_della_ui("avvisi-molti")

    avvisi = [riga for riga in esito["righe"] if riga["classe"] == "avviso"]
    assert len(avvisi) == 6, "cinque avvisi più una riga di riassunto"
    assert "altri 3" in avvisi[-1]["testo"]


@senza_node
def test_col_server_chiuso_la_pagina_lo_dice_invece_di_restare_muta():
    """L'app è locale: la `fetch` che non parte significa che il server è
    stato chiuso, non che il file è sbagliato. Senza il `catch` intorno alla
    `fetch` la pagina resterebbe zitta.
    """
    esito = esito_della_ui("server-chiuso")

    [riga] = esito["righe"]
    assert riga["classe"] == "rifiutato"
    assert "non risponde" in riga["testo"]


@senza_node
def test_l_estratto_del_testo_arriva_in_pagina():
    """Il payload serve il testo estratto perché l'utente possa accorgersi
    che un PDF ha reso testo sbagliato o vuoto (spec §4 lo autorizza
    esplicitamente). Finché lo script non lo mostrava, quel campo era
    servito e mai usato: la giustificazione esisteva solo nei test.
    """
    esito = esito_della_ui("corpo-non-json")

    [prima] = [riga for riga in esito["righe"] if riga["classe"] == "caricato"][:1]
    assert prima["dettaglio"] is not None
    assert "Rossi" in prima["dettaglio"]


# --- Il restyle: le due aggiunte di comportamento, prima del codice -----------


@senza_node
def test_le_metriche_del_fascicolo_si_aggiornano_con_i_caricamenti():
    """La card del fascicolo mostra quattro numeri grandi — documenti, pagine,
    caratteri, avvisi — e li aggiorna a ogni caricamento. I documenti vengono
    dal payload (è il server a sapere quanti sono), pagine e caratteri si
    sommano, gli avvisi si contano. Lo scenario serve 61 caratteri e 1 pagina,
    poi 40 e 3 con due segnaposto: i totali attesi sono contati a mano.
    """
    esito = esito_della_ui("metriche")

    assert esito["metriche"] == {
        "documenti": "2",
        "pagine": "4",
        "caratteri": "101",
        "avvisi": "2",
    }


@senza_node
def test_i_file_lasciati_cadere_sulla_card_vengono_caricati():
    """Il trascinamento è la stessa strada del modulo, non una seconda:
    un file lasciato cadere sulla card deve produrre la stessa richiesta e la
    stessa riga di verdetto di un file scelto col pulsante."""
    esito = esito_della_ui("trascinamento")

    assert [tentativo["file"] for tentativo in esito["tentativi"]] == ["uno.txt"]
    assert [riga["classe"] for riga in esito["righe"]] == ["caricato"]


@senza_node
def test_la_pagina_dice_quanti_file_sono_stati_scelti():
    """L'input dei file è nascosto dietro un pulsante a pillola, quindi il
    browser non mostra più da sé i nomi scelti: senza questo conteggio
    l'utente clicca «Carica» senza sapere se la scelta è andata a buon fine.
    Lo scenario sceglie tre file."""
    esito = esito_della_ui("corpo-non-json")

    assert "3" in esito["file_scelti"]
