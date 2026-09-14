"""Route dei suggerimenti di fusione (spec §7, issue #51).

`api/` può importare `core/` e `state/`; l'invariante 1 della spec §4 vieta il
verso opposto.

Un file suo e non tre rotte dentro `routes_fascicolo.py`, per due ragioni che
si sommano: il suggerimento non è un passo della revisione — non blocca niente,
si può ignorare per sempre, e il fascicolo che lo ignora è esattamente quello
di prima — e tenerlo separato lascia libero un file su cui un'altra corsia sta
lavorando.

Il ricalcolo è una rotta esplicita e non un effetto dell'analisi. Costa zero
chiamate al modello, quindi il motivo non è il costo: è che `POST /analisi`
scrive la tabella dei tag e basta, e infilarci dentro una seconda scrittura su
una seconda coda significherebbe che un errore nell'euristica può far fallire
un'analisi già pagata.
"""

from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from cryptocustode.api.routes_fascicolo import fascicolo_attivo, revisione
from cryptocustode.core.fusioni import fondi, suggerisci
from cryptocustode.core.models import Fascicolo, FusioneSuggerita
from cryptocustode.core.tagga import conta_occorrenze, tagga
from cryptocustode.state.session import SessionStore, registra_mutazione


class Decisione(BaseModel):
    """Il corpo della decisione.

    `decisione` è tipizzata su due sole stringhe: una terza parola diventa un
    422 di validazione con il suo `detail`, invece di una richiesta che passa,
    non corrisponde a nessun ramo e chiude la proposta senza fare niente.
    """

    fusione_id: str
    decisione: Literal["fondi", "separa"]


def _proposta(fascicolo: Fascicolo, fusione: FusioneSuggerita) -> dict:
    """La proposta come la vede la pagina.

    I valori viaggiano accanto ai segnaposto perché la domanda da fare
    all'utente è «`Mario Rossi` e `M. Rossi` sono la stessa persona?». Chiedergli
    se `[PERSONA_1]` e `[PERSONA_2]` lo sono è una domanda a cui nessuno può
    rispondere.

    Un tag può essere sparito dalla tabella — è quello assorbito da una fusione
    già accettata — e allora il valore non c'è più: `None` invece di un `KeyError`
    che farebbe cadere la lettura dell'intera coda.
    """
    tabella = fascicolo.tags
    return {
        "fusione_id": fusione.fusione_id,
        "categoria": fusione.categoria.value,
        "tag_a": fusione.tag_a,
        "tag_b": fusione.tag_b,
        "valore_a": tabella[fusione.tag_a].valore if fusione.tag_a in tabella else None,
        "valore_b": tabella[fusione.tag_b].valore if fusione.tag_b in tabella else None,
        "risolta": fusione.risolta,
    }


def _coda(fascicolo: Fascicolo) -> dict:
    return {"fusioni": [_proposta(fascicolo, f) for f in fascicolo.fusioni]}


def crea_router(store: SessionStore) -> APIRouter:
    router = APIRouter(prefix="/api/fusioni", tags=["fusioni"])

    @router.get("", response_model=None)
    async def leggi() -> dict:
        """La coda com'è, decisi compresi. Nessun effetto: ricalcolare da una
        GET vorrebbe dire che aprire la pagina cambia il fascicolo."""
        return _coda(fascicolo_attivo(store))

    @router.post("/ricalcolo", response_model=None)
    async def ricalcola() -> dict:
        """Cerca coppie nuove e le accoda, senza fondere niente.

        Rieseguibile: `suggerisci` riceve la coda esistente e non ripropone ciò
        che c'è già, deciso o no. Senza quella guardia ogni clic su «Analizza»
        riaprirebbe le coppie che l'utente ha appena guardato e lasciato
        separate.
        """
        fascicolo = fascicolo_attivo(store)
        fascicolo.fusioni.extend(suggerisci(fascicolo.tags, fascicolo.fusioni))
        return _coda(fascicolo)

    @router.post("/decisione", response_model=None)
    async def decidi(comando: Decisione) -> dict | JSONResponse:
        """L'utente fonde o lascia separati, e la proposta esce dalla coda.

        Le due decisioni non sono simmetriche, e non lo sono per costruzione:
        «fondi» unisce i due tag sotto il segnaposto più vecchio, «separa» non
        tocca niente — accetta il default sicuro della spec §7. Entrambe però
        chiudono la proposta, perché entrambe sono una risposta.

        È la decisione a chiudere, e solo dopo che la fusione è riuscita:
        marcarla risolta prima lascerebbe l'utente convinto di aver unito due
        nomi che sono ancora due.

        Una seconda decisione sulla stessa proposta è un 409 e non un 200
        silenzioso: arriva da una pagina che mostra un fascicolo che non esiste
        più — i due tag che nominava sono già stati uniti, o già lasciati stare.
        """
        fascicolo = fascicolo_attivo(store)
        trovata = next(
            (f for f in fascicolo.fusioni if f.fusione_id == comando.fusione_id), None
        )
        if trovata is None:
            return JSONResponse(
                status_code=404,
                content={
                    "errore": "nessun suggerimento di fusione con identificativo "
                    f"{comando.fusione_id!r} nel fascicolo: ricarica la revisione"
                },
            )
        if trovata.risolta:
            return JSONResponse(
                status_code=409,
                content={
                    "errore": f"il suggerimento {comando.fusione_id!r} è già stato "
                    "deciso: ricarica la revisione per vedere com'è adesso il "
                    "fascicolo"
                },
            )

        if comando.decisione == "fondi":
            try:
                tabella = fondi(fascicolo.tags, trovata.tag_a, trovata.tag_b)
            except ValueError as errore:
                return JSONResponse(status_code=422, content={"errore": str(errore)})
            # Il segnaposto sopravvissuto copre ora anche le occorrenze della
            # variante: senza il ricalcolo la revisione mostrerebbe un conteggio
            # che il testo mascherato smentisce.
            mascherature = [tagga(d.text, tabella) for d in fascicolo.documents]
            fascicolo.tags = conta_occorrenze(tabella, mascherature)
            # Spec §5: il testo mascherato è cambiato, quindi l'hash approvato
            # non vale più. Senza questa riga si esporterebbe un testo diverso
            # da quello che l'utente ha firmato.
            registra_mutazione(fascicolo)

        trovata.risolta = True
        return revisione(fascicolo)

    return router
