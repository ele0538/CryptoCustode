"""Route del vault: salvataggio e riapertura cifrata del fascicolo (spec §10, issue #9).

`api/` può importare `core/` e `state/`; l'invariante 1 della spec §4 vieta il
verso opposto. Il server non scrive mai il blob su disco: lo riceve o lo
restituisce, e la RAM del processo è l'unico posto in cui il fascicolo vive
fuori dal vault cifrato.

Il motore crittografico e la serializzazione stanno in `core/vault.py` e ci
sono da prima: questo modulo è solo il cablaggio che mancava. Vale la pena
dirlo perché è la diagnosi della issue #51 — il vault funzionava e
dall'applicazione non ci si arrivava, quindi le sue issue risultavano chiuse
mentre l'utente vedeva un pulsante spento.
"""

from fastapi import APIRouter, Form, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from cryptocustode.api.routes_fascicolo import (
    ID_FASCICOLO_ATTIVO,
    fascicolo_attivo,
    revisione,
)
from cryptocustode.config.stato import Configurazione
from cryptocustode.core.vault import carica, salva
from cryptocustode.state.session import SessionStore

NOME_FILE_VAULT = "fascicolo.vault"

SENZA_PASSPHRASE = (
    "non c'è nessuna passphrase aperta in questa sessione: il fascicolo si "
    "cifra con la stessa passphrase che protegge la chiave API. Aprila dalla "
    "configurazione, oppure scegline una per questo vault soltanto."
)


class Password(BaseModel):
    """La password del vault, facoltativa dal 2026-09-14.

    Assente significa «usa la passphrase della configurazione», che è il flusso
    normale: il fascicolo si salva a ogni esportazione, e un segreto nuovo da
    inventare ogni volta è un segreto che finisce su un foglietto. Resta
    accettata perché chi vuole chiudere *questo* vault con un segreto proprio
    deve poterlo fare — e perché i vault salvati prima si riaprono solo così.
    """

    password: str | None = None


def crea_router(
    store: SessionStore, configurazione: Configurazione | None = None
) -> APIRouter:
    """Le rotte del vault.

    `configurazione` è facoltativa perché il vault sa funzionare senza: chi
    manda una password esplicita non ha bisogno di nessuna sessione sbloccata.
    Assente, il ripiego non esiste e la rotta lo dice invece di cifrare con una
    stringa vuota.
    """
    router = APIRouter(prefix="/api/vault", tags=["vault"])

    def segreto(esplicita: str | None) -> str | None:
        """La password da usare: quella mandata, o la passphrase di sessione.

        L'ordine non è arbitrario. Una password esplicita è una scelta
        dell'utente su *questo* file, e una scelta esplicita non si scavalca
        mai con un valore implicito — altrimenti chi chiede un vault separato
        si ritrova un vault che si apre col segreto di tutti gli altri.
        """
        if esplicita:
            return esplicita
        if configurazione is None:
            return None
        return configurazione.passphrase_corrente

    @router.post("/salva", response_model=None)
    async def salva_vault(comando: Password) -> Response:
        """Il fascicolo esce cifrato, come allegato da scaricare.

        La password arriva nel corpo e non come parametro di query: una query
        finisce nei log del server e nella cronologia del browser, e questa è
        l'unica cosa che sta fra il fascicolo e chi trova il file `.vault`.
        """
        password = segreto(comando.password)
        if password is None:
            return JSONResponse(status_code=409, content={"errore": SENZA_PASSPHRASE})
        blob = salva(fascicolo_attivo(store), password)
        return Response(
            content=blob,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{NOME_FILE_VAULT}"'
            },
        )

    @router.post("/apri", response_model=None)
    async def apri_vault(
        file: UploadFile, password: str | None = Form(default=None)
    ) -> dict | JSONResponse:
        """Il vault torna a essere il fascicolo attivo, e la pagina si ridisegna.

        `carica` ricostruisce il `fascicolo_id` con cui era stato salvato, e
        per il fascicolo attivo è sempre lo stesso: forzarlo qui è la difesa
        esplicita che `fascicolo_attivo` chiede a chi ripristina da vault. Senza
        questa riga il fascicolo riaperto resterebbe nello store sotto un id che
        nessuna route interroga, e il primo caricamento successivo ne creerebbe
        uno vuoto facendo sparire il lavoro in silenzio.

        `store.salva` **sostituisce**, non fonde: chi apre un vault avendo già
        un fascicolo in corso si ritrova quello del vault e basta, invece dei
        documenti di due fascicoli diversi mescolati senza alcun errore.

        La risposta è `revisione(fascicolo)`, la stessa che rendono i toggle:
        la pagina si ridisegna con il codice che ha già, invece di un secondo
        percorso di disegno che diverge al primo campo aggiunto.

        Password errata e file manomesso passano entrambi per `VaultUnreadable`,
        che il gestore d'errore dell'app traduce in 422 con un messaggio solo
        (spec §13): distinguerli direbbe a chi ci prova che la password è
        l'unico ostacolo rimasto.
        """
        segreta = segreto(password)
        if segreta is None:
            return JSONResponse(status_code=409, content={"errore": SENZA_PASSPHRASE})
        blob = await file.read()
        fascicolo = carica(blob, segreta)
        fascicolo.fascicolo_id = ID_FASCICOLO_ATTIVO
        store.salva(fascicolo)
        return revisione(fascicolo)

    return router
