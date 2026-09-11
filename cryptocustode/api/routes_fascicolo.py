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

from fastapi import APIRouter, UploadFile

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

    Creare il fascicolo alla creazione dell'app invece che qui legherebbe
    l'esistenza del fascicolo all'avvio del server: chi costruisce l'app per
    interrogarla — i test, e in futuro il ripristino da vault, che il fascicolo
    se lo porta da sé — si troverebbe un fascicolo vuoto già installato.
    """
    try:
        return store.prendi(ID_FASCICOLO_ATTIVO)
    except KeyError:
        # `KeyError` nudo perché è ciò che `SessionStore.prendi` solleva oggi.
        # La issue #16 lo sostituirà con un errore di dominio: quando accadrà,
        # questa clausola va cambiata insieme, altrimenti il nuovo errore
        # scivola nella tabella della spec §13 e il primo caricamento di una
        # sessione risponde con un rifiuto invece di creare il fascicolo.
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

    @router.post("/documenti", status_code=201)
    async def carica_documento(file: UploadFile) -> dict:
        """Aggiunge un documento al fascicolo attivo, o lo rifiuta.

        Il documento entra passando da `aggiungi_documento`, che è la facciata
        dove vivono il tetto dei 10 (spec §1) e il rifiuto degli omonimi
        (spec §8): un `fascicolo.documents.append(...)` li aggirerebbe entrambi.

        Il testo restituito è quello **originale** estratto. Non contraddice
        l'invariante 3 della spec §4: il mascherato esce solo dal gate di
        esportazione, e di anteprime del mascherato qui non ce ne sono.
        """
        contenuto = await file.read()
        documento = costruisci_documento(file.filename, contenuto)
        fascicolo = fascicolo_attivo(store)
        aggiungi_documento(fascicolo, documento)
        return {
            "doc_id": documento.doc_id,
            "filename": documento.filename,
            "testo": documento.text,
            "caratteri": len(documento.text),
            "pagine": len(documento.page_offsets),
            "documenti_nel_fascicolo": len(fascicolo.documents),
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
