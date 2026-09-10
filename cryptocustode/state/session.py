"""Transizioni di stato e approvazione (spec §8).

`state/` può importare `core/`; l'invariante 1 vieta il verso opposto.
"""

from __future__ import annotations

from cryptocustode.core.entities import risolvi_ambiguita_omonimia, suggerisci_fusioni
from cryptocustode.core.errors import UnresolvedAmbiguities
from cryptocustode.core.mask import hash_approvazione
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

    Rifiutata se restano ambiguità bloccanti non risolte: sono le omonimie
    reali, quelle in cui approvare significherebbe fondere o separare due
    persone senza che nessuno abbia deciso quale delle due (spec §7).
    """
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
