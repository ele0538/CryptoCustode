"""Transizioni di stato e approvazione (spec §8).

`state/` può importare `core/`; l'invariante 1 vieta il verso opposto.
"""

from cryptocustode.core.errors import ExportNotAllowed, FascicoloNotFound, IntegrityError
from cryptocustode.core.mask import hash_approvazione, maschera_documento
from cryptocustode.core.models import Fascicolo, State


def analisi_completata(fascicolo: Fascicolo) -> None:
    """DRAFT -> PENDING_REVIEW.

    Prima popolava anche le due code delle ambiguità. Non esistono più: con il
    contratto B (spec §2 del 2026-09-14) due occorrenze della stessa stringa
    sono lo stesso tag per costruzione, quindi non c'è più un momento in cui
    due entità distinte esistano e si possa chiedere all'utente quale sia
    quale. Il costo è dichiarato al limite noto 2 della §16: l'omonimia fra
    documenti, che prima era intercettata e bloccante, ora è silenziosa.
    """
    fascicolo.state = State.PENDING_REVIEW


def approva(fascicolo: Fascicolo) -> None:
    """PENDING_REVIEW -> APPROVED, calcolando l'hash del testo mascherato.

    Rifiutata se lo stato non è PENDING_REVIEW: un DRAFT non ha ancora
    attraversato `analisi_completata`, quindi approvarlo firmerebbe l'hash di
    un testo non ancora mascherato.
    """
    if fascicolo.state is not State.PENDING_REVIEW:
        raise ValueError(
            f"impossibile approvare un fascicolo nello stato {fascicolo.state.value!r}: "
            "serve PENDING_REVIEW"
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

    def contiene(self, fascicolo_id: str) -> bool:
        """Se lo store ha quel fascicolo, senza sollevare nulla.

        Esiste perché "crealo se manca" sia una domanda esplicita e non un
        `except` sull'errore di `prendi`: un'eccezione usata come segnale di
        controllo si rompe in silenzio ogni volta che cambia la gerarchia degli
        errori, e il chiamante non ha modo di accorgersene (issue #3).

        Lo store resta l'indice e basta: quale sia il fascicolo attivo, e con
        quale id crearlo, resta una decisione di chi chiama.
        """
        return fascicolo_id in self._fascicoli

    def prendi(self, fascicolo_id: str) -> Fascicolo:
        """Il fascicolo con quell'id, o `FascicoloNotFound` se non c'è.

        Il `KeyError` del dizionario non esce di qui. Non è un
        `CryptoCustodeError`, quindi attraverserebbe il gate di
        `export_sanitized_text`, di cui questa risoluzione è il primo dei tre
        controlli, senza che nessuno lo riconosca, e il layer HTTP lo
        tradurrebbe in un 500 — un difetto del server — invece del 404 della
        spec §13 (issue #16).
        """
        try:
            return self._fascicoli[fascicolo_id]
        except KeyError as errore:
            raise FascicoloNotFound(
                f"il fascicolo richiesto non esiste: {fascicolo_id}"
            ) from errore


def export_sanitized_text(fascicolo_id: str, store: SessionStore) -> dict[str, str]:
    """L'unico punto da cui esce il testo mascherato (spec §8).

    Tre controlli, in ordine: `fascicolo_id` deve risolversi contro lo store,
    lo stato deve essere APPROVED, e il testo mascherato corrente deve ancora
    produrre l'hash approvato. Il primo lo esegue `prendi`, ed è la prima cosa
    che può fallire; il terzo intercetta le mutazioni che non sono passate da
    `registra_mutazione`.

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
