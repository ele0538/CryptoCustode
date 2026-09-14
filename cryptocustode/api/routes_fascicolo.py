"""Le route del fascicolo: il caricamento dei documenti e la revisione (spec §4).

`api/` può importare `core/` e `state/`; l'invariante 1 della spec §4 vieta il
verso opposto.

Il caricamento è **un file per richiesta**, e non un multipart con dieci parti.
La ragione è la tabella della spec §13: ogni rifiuto è uno stato HTTP con un
messaggio: con più file nella stessa richiesta l'esito sarebbe misto e un solo
stato non potrebbe dirlo. La UI cicla sui file scelti e mostra un verdetto per
ciascuno.

La revisione serve il testo **originale già spezzato in segmenti** sulle
regioni che la mascheratura rivendica, non il testo più una lista di offset
che il JavaScript ricompone. L'aritmetica sugli offset è dominio, e duplicata
nella UI diverge alla prima differenza fra il modo in cui Python e JavaScript
contano i caratteri: un carattere fuori dai piani BMP vale uno in Python e due
in JavaScript, quindi una UI che tagliasse da sé evidenzierebbe il pezzo
sbagliato senza un errore. Qui i segmenti arrivano già tagliati, e la UI si
limita a dipingerli.
"""


from dataclasses import replace
from pathlib import PurePosixPath, PureWindowsPath

from fastapi import APIRouter, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from cryptocustode.core.ingest.loader import (
    aggiungi_documento,
    costruisci_documento,
    segnaposto_preesistenti,
)
from cryptocustode.core.mask import tabella_attiva
from cryptocustode.core.models import Category, Document, Fascicolo, StatoTag, fascicolo_vuoto
from cryptocustode.core.rilevatore import Rilevatore
from cryptocustode.core.tagga import assegna_tag, conta_occorrenze, tagga
from cryptocustode.state.session import SessionStore, analisi_completata

ID_FASCICOLO_ATTIVO = "f_attivo"
"""Un fascicolo attivo per volta (spec §1), quindi un identificativo fisso.

Un id generato a ogni avvio costringerebbe la UI a ricordarselo per poi
rimandarlo indietro a ogni richiesta, senza che nessuno possa scegliere fra più
fascicoli: sarebbe un parametro con un solo valore possibile.
"""


def fascicolo_attivo(store: SessionStore) -> Fascicolo:
    """Il fascicolo su cui si lavora, creato vuoto al primo caricamento.

    Crearlo alla creazione dell'app, invece che qui, legherebbe l'esistenza del
    fascicolo all'avvio del server: chi costruisce l'app per interrogarla — i
    test, e in futuro il ripristino da vault, che il fascicolo se lo porta da
    sé — si troverebbe un fascicolo vuoto già installato.

    L'esistenza si chiede con `contiene` e non catturando un'eccezione: prima
    passava da un `except KeyError`, che faceva fare a un errore il mestiere di
    un segnale di controllo e legava questa funzione a *quale* eccezione lo
    store solleva — dalla issue #16 è `FascicoloNotFound` e non più un
    `KeyError` nudo. Con `contiene` il prossimo cambio nella gerarchia degli
    errori non tocca questa riga.

    **Vincolo da portare avanti**: chi ripristinerà un fascicolo da vault
    deve salvarlo **sotto questo id**. `vault.carica` restituisce un fascicolo
    col proprio `fascicolo_id`, che qui non verrebbe trovato: il primo
    caricamento dopo un ripristino creerebbe un fascicolo nuovo e vuoto, e il
    lavoro ripristinato sembrerebbe svanito senza alcun errore.
    """
    if store.contiene(ID_FASCICOLO_ATTIVO):
        return store.prendi(ID_FASCICOLO_ATTIVO)
    fascicolo = fascicolo_vuoto(ID_FASCICOLO_ATTIVO)
    store.salva(fascicolo)
    return fascicolo


class ToggleCategoria(BaseModel):
    """Il corpo del toggle per categoria.

    `categoria` è tipizzata sull'enum, non su `str`: una categoria inventata
    diventa un 422 di validazione con il suo `detail`, che la UI sa già
    mostrare, invece di una chiave nuova in `category_enabled` che nessuno
    leggerebbe mai e di un interruttore che sembra funzionare e non fa niente.
    """

    categoria: Category
    attiva: bool


class ToggleTag(BaseModel):
    tag: str
    attivo: bool


def _segmento_nudo(testo: str) -> dict:
    return {
        "testo": testo,
        "tag": None,
        "categoria": None,
        "mascherato": False,
        "segnaposto": None,
    }


def segmenti_di(fascicolo: Fascicolo, documento: Document) -> list[dict]:
    """Il testo originale spezzato sulle regioni che la mascheratura rivendica.

    Le regioni si calcolano sulla tabella **intera** e non su quella attiva,
    perché la pagina deve mostrare anche i tag spenti — spenti, ma visibili,
    altrimenti l'utente non avrebbe modo di riaccenderli. Quale sia acceso lo
    dice `tabella_attiva`, letta da un posto solo così la pagina non può
    mostrare acceso un dato che l'esportazione lascia in chiaro.

    Questa scelta apre una divergenza nota e accettata (issue #48): con un
    valore lungo spento che ne contiene uno corto acceso, la pagina mostra in
    chiaro più di quanto l'esportazione lasci davvero in chiaro. L'errore
    corre nella direzione sicura — la pagina mostra sempre più esposizione di
    quella reale, mai meno — e la tabella della fase 2 sostituirà questa vista
    evidenziata: non si ricalcolano le regioni due volte per chiuderla qui.
    """
    attivi = tabella_attiva(fascicolo)
    regioni = tagga(documento.text, fascicolo.tags).regioni
    segmenti: list[dict] = []
    cursore = 0
    for regione in regioni:
        if regione.start > cursore:
            segmenti.append(_segmento_nudo(documento.text[cursore:regione.start]))
        tag = fascicolo.tags[regione.tag]
        segmenti.append(
            {
                "testo": documento.text[regione.start:regione.end],
                "tag": tag.tag,
                "categoria": tag.categoria.value,
                "mascherato": tag.tag in attivi,
                "segnaposto": tag.tag,
            }
        )
        cursore = regione.end
    if cursore < len(documento.text):
        segmenti.append(_segmento_nudo(documento.text[cursore:]))
    return segmenti


def totali_di(fascicolo: Fascicolo) -> dict:
    """Le quattro cifre grandi della scheda, calcolate dal fascicolo.

    Prima vivevano in un accumulatore del JavaScript, sommato a ogni
    caricamento. Un accumulatore non è una copia innocua dello stato: non
    sopravvive al refresh, e soprattutto non ha modo di **diminuire** — dopo
    lo svuotamento del fascicolo continuerebbe a dichiarare i caratteri di
    documenti che non ci sono più. Calcolarle qui le rende una funzione del
    fascicolo, cioè giuste per costruzione in entrambi i casi (issue #50).
    """
    return {
        "documenti": len(fascicolo.documents),
        "massimo_documenti": Fascicolo.MAX_DOCUMENTI,
        "pagine": sum(len(documento.page_offsets) for documento in fascicolo.documents),
        "caratteri": sum(len(documento.text) for documento in fascicolo.documents),
        "avvisi": sum(
            len(segnaposto_preesistenti(documento.text))
            for documento in fascicolo.documents
        ),
    }


def revisione(fascicolo: Fascicolo) -> dict:
    """Tutto quello che serve alla pagina di revisione, in un payload solo.

    Ogni toggle restituisce questo stesso payload e la pagina si ridisegna da
    capo. Applicare la modifica anche nel JavaScript significherebbe tenere due
    copie dello stato del fascicolo — quella del server e quella della pagina —
    che divergono al primo caso che una delle due non prevede; e quella che
    l'utente vede sarebbe la copia sbagliata.

    Le categorie servite sono soltanto quelle che hanno almeno un tag: un
    interruttore per una categoria assente dal fascicolo prometterebbe un
    effetto che non può avere.
    """
    quanti: dict[Category, int] = {}
    for tag in fascicolo.tags.values():
        quanti[tag.categoria] = quanti.get(tag.categoria, 0) + 1
    return {
        "stato": fascicolo.state.value,
        "categorie": [
            {
                "categoria": categoria.value,
                "attiva": fascicolo.category_enabled.get(categoria, True),
                "quanti": quanti[categoria],
            }
            for categoria in Category
            if categoria in quanti
        ],
        "documenti": [
            {
                "doc_id": documento.doc_id,
                "filename": documento.filename,
                "segmenti": segmenti_di(fascicolo, documento),
            }
            for documento in fascicolo.documents
        ],
    }


def crea_router(store: SessionStore, rilevatore: Rilevatore) -> APIRouter:
    """Le route del fascicolo, legate allo store e al rilevatore che ricevono.

    Entrambi arrivano per parametro e non come singleton di modulo, come già
    fa `export_sanitized_text` (spec §8): un singleton renderebbe ogni app del
    processo compartecipe dello stesso fascicolo, o costringerebbe ogni test a
    far partire il client Gemini vero.
    """
    router = APIRouter(prefix="/api/fascicolo", tags=["fascicolo"])

    @router.get("", response_model=None)
    async def stato() -> dict:
        """Tutto ciò che serve a ridisegnare la pagina da zero (issue #50).

        Esiste perché la pagina non aveva **nessun** posto da cui rileggere il
        fascicolo: i quattro POST rispondevano solo a chi li premeva, quindi un
        F5 azzerava la UI mentre `SessionStore` teneva il fascicolo per tutta la
        vita del processo. Da lì i tre sintomi che sembravano bug distinti —
        la scheda a zero, il duplicato rifiutato a ragione, i documenti vecchi
        che riaffioravano in revisione — ed erano lo stesso: la pagina e il
        server non erano più d'accordo su cosa fosse caricato.

        È una `GET` e non un `POST` perché non muta niente: chi ricarica la
        pagina non deve poter cambiare il fascicolo per il fatto di guardarlo.
        Serve anche alla riapertura del vault, che ha lo stesso bisogno di
        ridisegnare tutto dopo aver sostituito il fascicolo.

        Il fascicolo vuoto **non** è un errore qui, al contrario di `/analisi`:
        è la risposta giusta alla domanda «cosa c'è dentro?» quando non c'è
        ancora niente, ed è lo stato in cui la pagina si trova al primo avvio.
        """
        fascicolo = fascicolo_attivo(store)
        return revisione(fascicolo) | {"totali": totali_di(fascicolo)}

    @router.delete("", response_model=None)
    async def svuota() -> dict:
        """Butta via il fascicolo attivo e ne mette uno vuoto al suo posto.

        Senza questa rotta l'utente che incontra il rifiuto dell'omonimo non
        aveva **nessuna** via d'uscita dentro l'applicazione: il solo modo di
        ricominciare era chiudere il programma e riaprirlo, cioè buttare via
        davvero tutto il lavoro invece di quel documento. Il rifiuto era
        corretto e restava senza rimedio, che è il difetto vero della #50.

        Sostituisce il fascicolo invece di svuotare quello che c'è: `state`,
        `approval_hash`, `counters`, `tags` e `analizzati` devono tornare tutti
        al valore iniziale insieme, e ripulirli campo per campo è il genere di
        elenco a cui si dimentica una riga il giorno che il fascicolo ne
        guadagna una.
        """
        store.salva(fascicolo_vuoto(ID_FASCICOLO_ATTIVO))
        fascicolo = fascicolo_attivo(store)
        return revisione(fascicolo) | {"totali": totali_di(fascicolo)}

    @router.post("/documenti", status_code=201, response_model=None)
    async def carica_documento(file: list[UploadFile]) -> dict | JSONResponse:
        """Aggiunge un documento al fascicolo attivo, o lo rifiuta.

        La firma accetta una lista per poter **rifiutare** più di un
        file, non per servirlo: due parti con lo stesso nome lasciavano
        vincere la seconda, e la prima spariva in silenzio — lo stesso
        guasto per cui esiste `DuplicateFilename` (spec §8). Non è
        un errore di dominio ma una richiesta malformata, quindi risponde
        qui e non passa dalla tabella della §13.

        Il documento entra passando da `aggiungi_documento`, che è la facciata
        dove vivono il tetto dei 10 (spec §1) e il rifiuto degli omonimi
        (spec §8): un `fascicolo.documents.append(...)` li aggirerebbe entrambi.

        Il testo restituito è quello **originale** estratto. Non contraddice
        l'invariante 3 della spec §4: il mascherato esce solo dal gate di
        esportazione, e di anteprime del mascherato qui non ce ne sono.
        """
        if len(file) != 1:
            return JSONResponse(
                status_code=422,
                content={
                    "errore": "una richiesta, un file: in questa ne sono "
                    f"arrivati {len(file)} e nessuno è stato caricato"
                },
            )
        [parte] = file

        # Il nome arriva dal client e finisce nel payload dell'export come
        # chiave (spec §8): `PurePosixPath` e `PureWindowsPath` in fila
        # togliono il percorso in entrambe le convenzioni, così
        # `../../etc/passwd.txt` diventa `passwd.txt` su ogni sistema. Oggi
        # nessuno scrive su disco e non è sfruttabile; il giorno in cui
        # quelle chiavi diventano nomi di file, lo sarebbe.
        nome = PureWindowsPath(PurePosixPath(parte.filename or "").name).name
        contenuto = await parte.read()
        documento = costruisci_documento(nome, contenuto)
        fascicolo = fascicolo_attivo(store)

        # L'unico `await` della route sta sopra questa riga. Dal controllo
        # del tetto dentro `aggiungi_documento` fino al suo `append` non ci
        # sono punti di sospensione, quindi due richieste non possono
        # interleavare fra controllo e mutazione. Chi inserisse un `await`
        # qui, o spostasse il parsing in un threadpool, riaprirebbe una
        # corsa sul tetto dei dieci che nessun test intercetta.
        aggiungi_documento(fascicolo, documento)
        return {
            "doc_id": documento.doc_id,
            "filename": documento.filename,
            "testo": documento.text,
            "caratteri": len(documento.text),
            "pagine": len(documento.page_offsets),
            # Gli stessi totali della `GET`, così la pagina si ridisegna dopo
            # un caricamento senza doverli sommare da sé: l'accumulatore nel
            # JavaScript era la metà della #50 che sopravviveva anche al
            # ridisegno, perché nessuno lo faceva mai scendere.
            "totali": totali_di(fascicolo),
            "documenti_nel_fascicolo": len(fascicolo.documents),
            # Servito, non duplicato nel JavaScript: il "di 10" della UI
            # veniva da una costante scritta a mano, che avrebbe mentito al
            # primo cambio di `MAX_DOCUMENTI`.
            "massimo_documenti": Fascicolo.MAX_DOCUMENTI,
            # Avviso, non rifiuto (spec §12): il documento è già entrato. Al
            # ripristino una di queste stringhe verrebbe presa per un segnaposto
            # e sostituita con dati veri, corrompendo il testo — ma un documento
            # legittimo che ne cita uno deve poter essere caricato.
            "segnaposto_preesistenti": [
                {"posizione": posizione, "segnaposto": testo}
                for posizione, testo in segnaposto_preesistenti(documento.text)
            ],
        }

    @router.post("/analisi", response_model=None)
    async def analizza() -> dict | JSONResponse:
        """Fa rilevare i dati sensibili e chiude l'analisi.

        Rieseguibile, come prima: chi aggiunge un documento dopo una prima
        analisi ripreme lo stesso bottone. I documenti già passati dal
        rilevatore vengono saltati, e qui la ragione è più forte di prima —
        ogni chiamata costa e manda il documento in rete.

        Se il rilevatore solleva, il fascicolo resta esattamente com'era:
        `assegna_tag` non muta i suoi argomenti, e la scrittura avviene solo
        dopo che tutte le chiamate sono andate a buon fine (spec §6).
        """
        fascicolo = fascicolo_attivo(store)
        if not fascicolo.documents:
            return JSONResponse(
                status_code=422,
                content={"errore": "non c'è nessun documento da analizzare: "
                                   "caricane almeno uno"},
            )
        da_analizzare = [
            d for d in fascicolo.documents if d.doc_id not in fascicolo.analizzati
        ]
        rilevazioni = []
        for documento in da_analizzare:
            rilevazioni.extend(rilevatore.rileva(documento.text))

        tabella, contatori = assegna_tag(
            rilevazioni, fascicolo.tags, fascicolo.counters
        )
        mascherature = [tagga(d.text, tabella) for d in fascicolo.documents]
        fascicolo.tags = conta_occorrenze(tabella, mascherature)
        fascicolo.counters = contatori
        fascicolo.analizzati.update(d.doc_id for d in da_analizzare)
        analisi_completata(fascicolo)
        return revisione(fascicolo)

    @router.post("/categoria", response_model=None)
    async def cambia_categoria(comando: ToggleCategoria) -> dict:
        """Accende o spegne il mascheramento di un'intera categoria (spec §5).

        Non tocca il flag dei singoli tag: le due decisioni sono indipendenti
        e `tabella_attiva` le legge in `and`, quindi riaccendere la categoria
        rimette esattamente com'erano i tag spenti uno per uno. Scriverle
        entrambe qui perderebbe quelle scelte senza poterle recuperare.
        """
        fascicolo = fascicolo_attivo(store)
        fascicolo.category_enabled[comando.categoria] = comando.attiva
        return revisione(fascicolo)

    @router.post("/tag", response_model=None)
    async def cambia_tag(comando: ToggleTag) -> dict | JSONResponse:
        """Accende o spegne il mascheramento di un dato.

        Un tag che non esiste è un 404 e non un 200 silenzioso: senza il
        controllo la route non muterebbe niente e risponderebbe come se avesse
        funzionato, e la pagina continuerebbe a mostrare acceso un tag che
        l'utente crede di aver spento — cioè un dato che esce in chiaro contro
        la sua volontà esplicita.
        """
        fascicolo = fascicolo_attivo(store)
        tag = fascicolo.tags.get(comando.tag)
        if tag is None:
            return JSONResponse(
                status_code=404,
                content={"errore": f"nessun tag {comando.tag!r} nel fascicolo: "
                                   "ricarica la revisione"},
            )
        # Riaccendere un tag non lo rende `APPLICATO` a occhi chiusi: un tag
        # `NON_TROVATO` ha zero occorrenze nel testo (il modello lo ha
        # nominato, ma non compare alla lettera), e marcarlo `APPLICATO`
        # dichiarerebbe una sostituzione mai avvenuta — nella direzione
        # sbagliata, quella che fa credere mascherato un dato che è rimasto in
        # chiaro. Spegnerlo resta incondizionato: `DISATTIVATO` è una scelta
        # dell'utente, non un fatto sul testo.
        nuovo_stato = (
            (StatoTag.APPLICATO if tag.occorrenze else StatoTag.NON_TROVATO)
            if comando.attivo
            else StatoTag.DISATTIVATO
        )
        fascicolo.tags[comando.tag] = replace(tag, stato=nuovo_stato)
        return revisione(fascicolo)

    return router
