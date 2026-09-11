"""Transizioni di stato e approvazione (spec §8).

`state/` può importare `core/`; l'invariante 1 vieta il verso opposto.
"""

from __future__ import annotations

from cryptocustode.core.entities import risolvi_ambiguita_omonimia, suggerisci_fusioni
from cryptocustode.core.errors import (
    ExportNotAllowed,
    FascicoloNotFound,
    IntegrityError,
    UnresolvedAmbiguities,
)
from cryptocustode.core.mask import hash_approvazione, maschera_documento
from cryptocustode.core.models import Fascicolo, State


def analisi_completata(fascicolo: Fascicolo) -> None:
    """DRAFT -> PENDING_REVIEW, popolando le code delle ambiguità.

    Le due code si calcolano qui e non dentro `analizza_documento` perché le
    omonimie sono una proprietà del fascicolo intero: hanno senso solo quando
    tutti i documenti sono stati analizzati. Senza queste due chiamate la coda
    resterebbe vuota e `approva` non troverebbe mai nulla da bloccare.
    """
    risolvi_ambiguita_omonimia(fascicolo)
    suggerisci_fusioni(fascicolo)
    fascicolo.state = State.PENDING_REVIEW


def approva(fascicolo: Fascicolo) -> None:
    """PENDING_REVIEW -> APPROVED, calcolando l'hash del testo mascherato.

    Rifiutata se lo stato non è PENDING_REVIEW: la macchina a stati della
    spec §8 autorizza solo questa transizione. Un DRAFT non ha ancora
    attraversato `analisi_completata`, quindi approvarlo firmerebbe
    l'hash del testo non ancora mascherato.

    Rifiutata anche se restano ambiguità bloccanti non risolte: sono le
    omonimie reali, quelle in cui approvare significherebbe fondere o
    separare due persone senza che nessuno abbia deciso quale delle due
    (spec §7).
    """
    if fascicolo.state is not State.PENDING_REVIEW:
        raise ValueError(
            f"impossibile approvare un fascicolo nello stato {fascicolo.state.value!r}: "
            "serve PENDING_REVIEW"
        )
    bloccanti = [a for a in fascicolo.ambiguities if a.blocca_approvazione]
    if bloccanti:
        elenco = ", ".join(a.ambiguity_id for a in bloccanti)
        raise UnresolvedAmbiguities(
            f"il fascicolo ha ambiguità da risolvere prima dell'approvazione: {elenco}"
        )
    fascicolo.approval_hash = hash_approvazione(fascicolo)
    fascicolo.state = State.APPROVED


def registra_mutazione(fascicolo: Fascicolo) -> None:
    """Qualsiasi mutazione dopo l'approvazione la annulla.

    L'hash va cancellato insieme allo stato: tenerlo significherebbe conservare
    la prova di un'approvazione che non vale più.
    """
    if fascicolo.state is State.APPROVED:
        fascicolo.state = State.PENDING_REVIEW
        fascicolo.approval_hash = None


class SessionStore:
    """I fascicoli vivi del processo, indicizzati per id.

    Fuori di qui e dal vault cifrato un fascicolo non esiste: niente database,
    niente file temporanei (spec §10).
    """

    def __init__(self) -> None:
        self._fascicoli: dict[str, Fascicolo] = {}

    def salva(self, fascicolo: Fascicolo) -> None:
        self._fascicoli[fascicolo.fascicolo_id] = fascicolo

    def prendi(self, fascicolo_id: str) -> Fascicolo:
        """Il fascicolo con quell'id, o `FascicoloNotFound` se non c'è.

        Il `KeyError` del dizionario non esce di qui. Non è un
        `CryptoCustodeError`, quindi attraverserebbe il gate di
        `export_sanitized_text` prima dei suoi due controlli senza che nessuno
        lo riconosca, e il layer HTTP lo tradurrebbe in un 500 — un difetto del
        server — invece del 404 della spec §13 (issue #16).
        """
        try:
            return self._fascicoli[fascicolo_id]
        except KeyError as errore:
            raise FascicoloNotFound(
                f"il fascicolo richiesto non esiste: {fascicolo_id}"
            ) from errore


def export_sanitized_text(fascicolo_id: str, store: SessionStore) -> dict[str, str]:
    """L'unico punto da cui esce il testo mascherato (spec §8).

    Due controlli, in ordine: lo stato deve essere APPROVED, e il testo
    mascherato corrente deve ancora produrre l'hash approvato. Il secondo
    intercetta le mutazioni che non sono passate da `registra_mutazione`.

    Il payload contiene esclusivamente `{nome_file: testo_mascherato}`: nessun
    testo originale, nessun dizionario, nessuno span.
    """
    fascicolo = store.prendi(fascicolo_id)
    if fascicolo.state is not State.APPROVED:
        raise ExportNotAllowed("il fascicolo non è approvato")
    if hash_approvazione(fascicolo) != fascicolo.approval_hash:
        raise IntegrityError("il testo è cambiato dopo l'approvazione")
    return {
        documento.filename: maschera_documento(fascicolo, documento)
        for documento in fascicolo.documents
    }
