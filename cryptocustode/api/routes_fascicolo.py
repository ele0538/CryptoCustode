"""Le route del fascicolo: per ora il caricamento dei documenti (spec §4).

`api/` può importare `core/` e `state/`; l'invariante 1 della spec §4 vieta il
verso opposto.

Il caricamento è **un file per richiesta**, e non un multipart con dieci parti.
La ragione è la tabella della spec §13: ogni rifiuto è uno stato HTTP con un
messaggio: con più file nella stessa richiesta l'esito sarebbe misto e un solo
stato non potrebbe dirlo. La UI cicla sui file scelti e mostra un verdetto per
ciascuno.
"""

from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath

from fastapi import APIRouter, UploadFile
from fastapi.responses import JSONResponse

from cryptocustode.core.ingest.loader import (
    aggiungi_documento,
    costruisci_documento,
    segnaposto_preesistenti,
)
from cryptocustode.core.models import Fascicolo, fascicolo_vuoto
from cryptocustode.state.session import SessionStore

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

    return router
