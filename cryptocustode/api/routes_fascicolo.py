"""Le route del fascicolo: il caricamento dei documenti e la revisione (spec §4).

`api/` può importare `core/` e `state/`; l'invariante 1 della spec §4 vieta il
verso opposto.

Il caricamento è **un file per richiesta**, e non un multipart con dieci parti.
La ragione è la tabella della spec §13: ogni rifiuto è uno stato HTTP con un
messaggio: con più file nella stessa richiesta l'esito sarebbe misto e un solo
stato non potrebbe dirlo. La UI cicla sui file scelti e mostra un verdetto per
ciascuno.

La revisione serve il testo **originale già spezzato in segmenti** sugli offset
degli span, non il testo più una lista di offset che il JavaScript ricompone.
L'aritmetica sugli offset è dominio, e duplicata nella UI diverge alla prima
differenza fra il modo in cui Python e JavaScript contano i caratteri: un
carattere fuori dai piani BMP vale uno in Python e due in JavaScript, quindi
una UI che tagliasse da sé evidenzierebbe il pezzo sbagliato senza un errore.
Qui i segmenti arrivano già tagliati, e la UI si limita a dipingerli.
"""


from dataclasses import replace
from pathlib import PurePosixPath, PureWindowsPath

from fastapi import APIRouter, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from cryptocustode.core.entities import analizza_documento
from cryptocustode.core.ingest.loader import (
    aggiungi_documento,
    costruisci_documento,
    segnaposto_preesistenti,
)
from cryptocustode.core.mask import span_attivo
from cryptocustode.core.models import Category, Document, Fascicolo, fascicolo_vuoto
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


class ToggleSpan(BaseModel):
    span_id: str
    attivo: bool


def segmenti_di(fascicolo: Fascicolo, documento: Document) -> list[dict]:
    """Il testo originale del documento spezzato sugli offset dei suoi span.

    Concatenare i `testo` dei segmenti restituisce il testo originale carattere
    per carattere: è la decisione 2 della spec §2 resa osservabile — il testo è
    immutabile e l'utente agisce solo sugli span, quindi la revisione non può
    mostrare un testo diverso da quello che verrà mascherato.

    `mascherato` è `span_attivo`, cioè **entrambi** gli interruttori: quello
    del singolo span e quello della sua categoria (spec §5). Ricalcolarlo qui
    con un `and` scritto a mano lo farebbe divergere da ciò che `maschera`
    applica davvero, e la pagina mostrerebbe acceso un dato che esce in chiaro.
    """
    spans = sorted(
        (span for span in fascicolo.spans if span.doc_id == documento.doc_id),
        key=lambda span: span.start,
    )
    segmenti: list[dict] = []
    cursore = 0
    for span in spans:
        if span.start > cursore:
            segmenti.append(
                {
                    "testo": documento.text[cursore:span.start],
                    "span_id": None,
                    "categoria": None,
                    "mascherato": False,
                    "segnaposto": None,
                }
            )
        entita = fascicolo.entities.get(span.entity_id)
        segmenti.append(
            {
                "testo": documento.text[span.start:span.end],
                "span_id": span.span_id,
                "categoria": span.category.value,
                "mascherato": span_attivo(span, fascicolo),
                "segnaposto": None if entita is None else entita.placeholder,
            }
        )
        cursore = span.end
    if cursore < len(documento.text):
        segmenti.append(
            {
                "testo": documento.text[cursore:],
                "span_id": None,
                "categoria": None,
                "mascherato": False,
                "segnaposto": None,
            }
        )
    return segmenti


def revisione(fascicolo: Fascicolo) -> dict:
    """Tutto quello che serve alla pagina di revisione, in un payload solo.

    Ogni toggle restituisce questo stesso payload e la pagina si ridisegna da
    capo. Applicare la modifica anche nel JavaScript significherebbe tenere due
    copie dello stato del fascicolo — quella del server e quella della pagina —
    che divergono al primo caso che una delle due non prevede; e quella che
    l'utente vede sarebbe la copia sbagliata.

    Le categorie servite sono soltanto quelle che hanno almeno uno span: un
    interruttore per una categoria assente dal fascicolo prometterebbe un
    effetto che non può avere.
    """
    quanti: dict[Category, int] = {}
    for span in fascicolo.spans:
        quanti[span.category] = quanti.get(span.category, 0) + 1
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
        "ambiguita": {
            "totale": len(fascicolo.ambiguities),
            "bloccanti": sum(1 for a in fascicolo.ambiguities if a.blocca_approvazione),
        },
        "documenti": [
            {
                "doc_id": documento.doc_id,
                "filename": documento.filename,
                "segmenti": segmenti_di(fascicolo, documento),
            }
            for documento in fascicolo.documents
        ],
    }


def crea_router(store: SessionStore) -> APIRouter:
    """Le route del fascicolo, legate allo store che ricevono.

    Lo store arriva per parametro e non come singleton di modulo, come già fa
    `export_sanitized_text` (spec §8): un singleton renderebbe ogni app del
    processo compartecipe dello stesso fascicolo.
    """
    router = APIRouter(prefix="/api/fascicolo", tags=["fascicolo"])

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
        """Analizza i documenti non ancora analizzati e chiude l'analisi.

        Rieseguibile di proposito, ed è il criterio 5 della issue #4: chi
        aggiunge un documento dopo una prima analisi ripreme lo stesso bottone,
        e la coda delle ambiguità viene ricalcolata. `analisi_completata` è
        l'**unico** punto che popola le code — l'omonimia è una proprietà del
        fascicolo intero, non del singolo documento — quindi saltarla al
        secondo giro lascerebbe in coda le ambiguità del primo, senza quelle
        che il documento appena entrato ha creato: stantie, e in silenzio.

        I documenti già analizzati vengono saltati perché `analizza_documento`
        li rifiuta: una seconda copia di ogni span farebbe applicare a
        `maschera` due sostituzioni sovrapposte allo stesso intervallo,
        troncando il testo dal primo segnaposto in poi. Il filtro è sugli span
        e non su una lista di doc_id già visti: un documento che non ha
        prodotto nemmeno uno span viene ripassato, e ripassarlo non costa
        niente perché il risultato è di nuovo vuoto.

        Il fascicolo vuoto è un rifiuto e non un'analisi a vuoto: promuoverlo a
        `PENDING_REVIEW` lo renderebbe approvabile, e un fascicolo approvato
        senza documenti esporta zero documenti senza che nulla lo segnali.
        """
        fascicolo = fascicolo_attivo(store)
        if not fascicolo.documents:
            return JSONResponse(
                status_code=422,
                content={
                    "errore": "non c'è nessun documento da analizzare: "
                    "caricane almeno uno"
                },
            )
        analizzati = {span.doc_id for span in fascicolo.spans}
        for documento in fascicolo.documents:
            if documento.doc_id not in analizzati:
                analizza_documento(fascicolo, documento)
        analisi_completata(fascicolo)
        return revisione(fascicolo)

    @router.post("/categoria", response_model=None)
    async def cambia_categoria(comando: ToggleCategoria) -> dict:
        """Accende o spegne il mascheramento di un'intera categoria (spec §5).

        Non tocca il flag dei singoli span: le due decisioni sono indipendenti
        e `span_attivo` le legge in `and`, quindi riaccendere la categoria
        rimette esattamente com'erano gli span spenti uno per uno. Scriverle
        entrambe qui perderebbe quelle scelte senza poterle recuperare.
        """
        fascicolo = fascicolo_attivo(store)
        fascicolo.category_enabled[comando.categoria] = comando.attiva
        return revisione(fascicolo)

    @router.post("/span", response_model=None)
    async def cambia_span(comando: ToggleSpan) -> dict | JSONResponse:
        """Accende o spegne il mascheramento di una singola occorrenza.

        Uno `span_id` che non esiste è un 404 e non un 200 silenzioso: senza il
        controllo la route non muterebbe niente e risponderebbe come se avesse
        funzionato, e la pagina continuerebbe a mostrare acceso uno span che
        l'utente crede di aver spento — cioè un dato che esce in chiaro
        dall'export contro la sua volontà esplicita.
        """
        fascicolo = fascicolo_attivo(store)
        for indice, span in enumerate(fascicolo.spans):
            if span.span_id == comando.span_id:
                # `Span` è congelato: la sostituzione in posizione è l'unico
                # modo di cambiarne il flag senza perdere l'ordine, da cui
                # dipende la stabilità dell'hash di approvazione.
                fascicolo.spans[indice] = replace(span, enabled=comando.attivo)
                return revisione(fascicolo)
        return JSONResponse(
            status_code=404,
            content={
                "errore": f"nessuno span con identificativo {comando.span_id!r} "
                "nel fascicolo: ricarica la revisione"
            },
        )

    return router
