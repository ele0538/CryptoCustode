"""Tipi di dominio di CryptoCustode. Solo dati: nessun comportamento, nessuna I/O."""

from dataclasses import dataclass, field
from enum import Enum

class Category(str, Enum):
    PERSONA = "PERSONA"
    AZIENDA = "AZIENDA"
    INDIRIZZO = "INDIRIZZO"
    EMAIL = "EMAIL"
    TELEFONO = "TELEFONO"
    CF = "CF"
    PIVA = "PIVA"
    IBAN = "IBAN"
    DATA = "DATA"
    IMPORTO = "IMPORTO"
    PRATICA = "PRATICA"
    CATASTO = "CATASTO"


class StatoTag(str, Enum):
    """Cosa è successo a un tag nel fascicolo (spec §5 del 2026-09-14)."""

    APPLICATO = "APPLICATO"
    """Sostituito almeno una volta nel testo di almeno un documento."""

    NON_TROVATO = "NON_TROVATO"
    """Il modello ha nominato il valore, ma nel testo non compare alla lettera.

    Non è un caso d'angolo: è il modo in cui il modello sbaglia più spesso,
    perché normalizza (`Mario Rossi` per un documento che scrive `ROSSI Mario`).
    Ignorarlo lascerebbe il dato in chiaro senza che nessuno lo sappia, quindi
    il tag resta visibile nella tabella di revisione (spec §7).
    """

    DISATTIVATO = "DISATTIVATO"
    """L'utente ha deciso che quel dato esce in chiaro."""


class State(str, Enum):
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"


@dataclass(frozen=True)
class Document:
    doc_id: str
    filename: str
    text: str
    page_offsets: list[int]
    sha256: str


@dataclass(frozen=True)
class Rilevazione:
    """Un dato sensibile come il modello lo ha nominato (spec §6).

    `valore` deve essere una sottostringa letterale del documento: è il vincolo
    che il prompt impone e che rende vera l'identità del round-trip (§8). Qui
    non si verifica — se il modello lo viola, `tagga()` non trova occorrenze e
    il tag finisce `NON_TROVATO`.
    """

    valore: str
    categoria: Category


@dataclass(frozen=True)
class Tag:
    """Un segnaposto e il dato che nasconde.

    Sostituisce insieme `Span` ed `Entity`: senza offset dal modello non c'è
    più un'occorrenza da rappresentare a parte dall'entità.
    """

    tag: str
    categoria: Category
    valore: str
    occorrenze: int
    stato: StatoTag


@dataclass(frozen=True)
class Regione:
    """Un'occorrenza che `tagga()` ha davvero rivendicato, nel testo originale.

    Non è uno `Span` risorto: non ha identità, nessuno la modifica, e il
    modello non la vede mai. È il verbale di ciò che la mascheratura ha fatto,
    e serve alla UI per evidenziare esattamente i punti sostituiti invece di
    ricercarli per conto proprio (spec §5).
    """

    start: int
    end: int
    tag: str


@dataclass(frozen=True)
class Mascheratura:
    """Il risultato di `tagga()` su un documento."""

    mascherato: str
    tags: list[Tag]
    regioni: list[Regione]


@dataclass
class Fascicolo:
    MAX_DOCUMENTI = 10

    fascicolo_id: str
    documents: list[Document] = field(default_factory=list)
    category_enabled: dict[Category, bool] = field(default_factory=dict)
    state: State = State.DRAFT
    approval_hash: str | None = None
    counters: dict[Category, int] = field(default_factory=dict)
    tags: dict[str, Tag] = field(default_factory=dict)
    """La tabella dei tag del fascicolo, indicizzata per stringa del tag.

    Per tag e non per valore perché è il tag l'identificativo che la UI
    rimanda indietro quando l'utente spegne una riga, ed è il tag la chiave
    del dizionario di ripristino.
    """
    analizzati: set[str] = field(default_factory=set)
    """I `doc_id` già passati dal rilevatore.

    Prima questa informazione si deduceva dagli span esistenti. Senza span
    serve un campo: rianalizzare un documento significa ripagare una chiamata
    a Gemini per un risultato che si ha già.
    """


def fascicolo_vuoto(fascicolo_id: str) -> Fascicolo:
    """Un fascicolo nuovo: tutte le categorie mascherate, contatori a zero (spec §5)."""
    return Fascicolo(
        fascicolo_id=fascicolo_id,
        category_enabled={c: True for c in Category},
        counters={c: 0 for c in Category},
    )
