"""Le route della configurazione: modello, prezzi, chiave e conto speso.

Stanno in un modulo proprio e non dentro `routes_fascicolo.py` perché non
parlano del fascicolo: vivono quando il fascicolo non esiste ancora — anzi,
sono le uniche che devono funzionare prima che ci sia una chiave, altrimenti
non ci sarebbe modo di inserirla.

**La chiave API non esce mai da qui.** `GET /api/config` dice se c'è e se è
sbloccata, non quanto vale. Rimandarla alla pagina per «ricompilare il campo»
la metterebbe nel corpo di una risposta HTTP, nella cronologia del browser e
negli strumenti di sviluppo, che è esattamente ciò che cifrarla su disco serve
a evitare: il segreto viaggia in una sola direzione.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from cryptocustode.config.impostazioni import ConfigurazioneIlleggibile
from cryptocustode.config.stato import Configurazione


class ImpostazioniInEntrata(BaseModel):
    """Cosa la pagina manda quando si preme Salva.

    I prezzi sono `float` e non stringhe: un prezzo scritto male deve diventare
    un 422 di validazione con il suo messaggio, non uno zero silenzioso che
    farebbe mostrare all'utente un costo di zero per sempre.
    """

    modello: str
    prezzo_input: float = 0.0
    prezzo_output: float = 0.0
    valuta: str = "USD"
    chiave: str | None = None
    passphrase: str | None = None


class Passphrase(BaseModel):
    passphrase: str


def riassunto(configurazione: Configurazione) -> dict:
    impostazioni = configurazione.impostazioni
    return {
        "modello": impostazioni.modello,
        "prezzo_input": impostazioni.prezzo_input,
        "prezzo_output": impostazioni.prezzo_output,
        "valuta": impostazioni.valuta,
        # Due booleani e non uno: «c'è una chiave salvata sul disco» e «la
        # chiave è utilizzabile adesso» sono stati diversi, ed è la differenza
        # fra chiedere la passphrase e chiedere la chiave. Riassumerli in uno
        # solo obbligherebbe la pagina a indovinare quale dei due schermi
        # mostrare al riavvio.
        "chiave_salvata": impostazioni.chiave_cifrata is not None,
        "pronta": impostazioni.pronta,
        "consumo": configurazione.consumo(),
    }


def crea_router_config(configurazione: Configurazione) -> APIRouter:
    """Le route della configurazione, legate all'oggetto che ricevono."""
    router = APIRouter(prefix="/api", tags=["configurazione"])

    @router.get("/config", response_model=None)
    async def leggi_config() -> dict:
        """Cosa mostrare nella pagina di configurazione. Mai la chiave."""
        return riassunto(configurazione)

    @router.post("/config", response_model=None)
    async def salva_config(nuove: ImpostazioniInEntrata) -> dict | JSONResponse:
        """Salva modello, prezzi e — se ne arriva una — la chiave.

        La chiave è facoltativa di proposito: cambiare solo il prezzo non deve
        costringere a riscrivere la chiave, che l'utente non ha sottomano e che
        dovrebbe andare a ripescare dalla console di Google ogni volta.
        """
        try:
            configurazione.aggiorna(
                modello=nuove.modello,
                prezzo_input=nuove.prezzo_input,
                prezzo_output=nuove.prezzo_output,
                valuta=nuove.valuta,
                chiave=nuove.chiave,
                passphrase=nuove.passphrase,
            )
        except ValueError as errore:
            return JSONResponse(status_code=422, content={"errore": str(errore)})
        return riassunto(configurazione)

    @router.post("/config/sblocca", response_model=None)
    async def sblocca(comando: Passphrase) -> dict | JSONResponse:
        """Decifra la chiave salvata, per questa sessione.

        Serve a ogni avvio quando una chiave esiste: sta cifrata sul disco, e
        senza passphrase l'applicazione non può usarla. È il prezzo della
        scelta di non tenerla in chiaro, ed è meglio dirlo che aggirarlo.
        """
        try:
            configurazione.sblocca(comando.passphrase)
        except ConfigurazioneIlleggibile as errore:
            return JSONResponse(status_code=422, content={"errore": str(errore)})
        return riassunto(configurazione)

    @router.get("/consumo", response_model=None)
    async def consumo() -> dict:
        """Quanto è costato: da quando l'app è aperta, e da sempre."""
        return configurazione.consumo()

    return router
