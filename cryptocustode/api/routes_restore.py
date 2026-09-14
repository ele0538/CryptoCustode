"""Il ripristino della risposta dell'IA, dietro HTTP (spec §4, spec §11).

L'altra metà del prodotto: senza, il mascheramento è a senso unico. L'utente
incolla la risposta che l'IA gli ha restituito — piena di segnaposto — e
riottiene il testo con i dati veri al loro posto.

**Perché sta in un file suo.** Lo dice la spec §4, che gli assegna un modulo
proprio; ma la ragione è la stessa che vale per l'esportazione: questa è
l'unica rotta che **riporta in chiaro** i valori del dizionario, e un punto
solo si sorveglia leggendo un file di quaranta righe. Sparso fra le rotte del
fascicolo, lo stesso controllo andrebbe rifatto a ogni modifica di
`routes_fascicolo.py`.

**Perché non passa da `fascicolo_attivo`.** Quella funzione crea il fascicolo
se manca, ed è giusto per una rotta che carica o revisiona. Qui sarebbe un
danno: un fascicolo appena creato ha il dizionario vuoto, quindi ogni
segnaposto diventerebbe uno sconosciuto e l'utente riceverebbe un 422
«segnaposto non riconosciuto» che lo manda a cercare l'errore nella risposta
dell'IA invece che nel fascicolo che non ha caricato. Il ripristino legge e
basta: `prendi` dà il 404 della spec §13, che è la risposta vera.

**Perché non c'è alcun gate di stato.** Il ripristino non fa uscire il testo
mascherato — lo riceve già mascherato dalle mani dell'utente — quindi
l'invariante 3 della §4 e i tre controlli della §8 non lo riguardano. Legarlo
all'approvazione impedirebbe di ripristinare una risposta dopo una qualsiasi
correzione in revisione, cioè proprio quando serve.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from cryptocustode.api.routes_fascicolo import ID_FASCICOLO_ATTIVO
from cryptocustode.core.tagga import dizionario_di
from cryptocustode.core.unmask import ripristina
from cryptocustode.state.session import SessionStore


class RispostaDaRipristinare(BaseModel):
    """Quello che l'utente incolla: la risposta dell'IA, e nient'altro.

    Il campo si chiama `risposta` e non `testo` di proposito. Non è cosmetica:
    un test fa rispettare che nessuna rotta del fascicolo accetti *il testo di
    un documento*, perché il testo può cambiare solo caricando un file (spec §2,
    decisione 2). Questo testo non entra nel fascicolo in nessun modo: viene
    letto, sostituito e restituito, e il fascicolo non lo vede passare.
    """

    risposta: str


def crea_router_ripristino(store: SessionStore) -> APIRouter:
    """La rotta del ripristino, legata allo store che riceve.

    Lo store arriva per parametro come in `crea_router`: un singleton di modulo
    renderebbe ogni app del processo compartecipe dello stesso fascicolo, e il
    dizionario con cui si ripristina è esattamente ciò che non deve essere
    condiviso per sbaglio.
    """
    router = APIRouter(prefix="/api/fascicolo", tags=["ripristino"])

    @router.post("/ripristino", response_model=None)
    async def ripristina_risposta(corpo: RispostaDaRipristinare) -> dict[str, str]:
        """Il testo con i valori veri al posto dei segnaposto (spec §11).

        Il dizionario si costruisce da `fascicolo.tags` e comprende **tutti** i
        tag, anche i disattivati. Un tag spento non ha mai sostituito niente,
        quindi il suo segnaposto non può comparire nella risposta dell'IA —
        ma può comparire in una risposta ottenuta *prima* che l'utente lo
        spegnesse, e quella va ripristinata lo stesso: il contrario
        trasformerebbe un cambio di idea in revisione in un errore su un testo
        che era corretto quando è stato generato.

        `UnknownPlaceholder` e `MalformedPlaceholder` non vengono catturati:
        salgono al gestore registrato in `crea_app`, che li traduce entrambi
        nel 422 della §13 con il messaggio del dominio — già in italiano, e già
        completo dei segnaposto che hanno fermato il ripristino. Catturarli qui
        vorrebbe dire riscrivere quella tabella una seconda volta, e riscrivere
        quei messaggi una seconda volta: due copie che divergono.

        Il corpo della risposta ha **una sola chiave**. Rimandare indietro anche
        i segnaposto risolti, o il dizionario che li ha risolti, rifarebbe
        uscire dal processo la mappa che l'invariante 4 della §4 tiene dentro —
        e la rifarebbe uscire proprio dalla rotta che ha già i valori in chiaro
        sotto mano.
        """
        fascicolo = store.prendi(ID_FASCICOLO_ATTIVO)
        return {
            "ripristinato": ripristina(corpo.risposta, dizionario_di(fascicolo.tags))
        }

    return router
