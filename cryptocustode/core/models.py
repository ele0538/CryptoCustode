"""Tipi di dominio di CryptoCustode. Solo dati: nessun comportamento, nessuna I/O."""
from __future__ import annotations

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


class Source(str, Enum):
    RULE = "RULE"
    NER = "NER"
    MANUAL = "MANUAL"


class State(str, Enum):
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"


class AmbiguityKind(str, Enum):
    SAME_NAME_NO_CF = "SAME_NAME_NO_CF"
    HEURISTIC_MERGE_SUGGESTION = "HEURISTIC_MERGE_SUGGESTION"


# Priorità decrescente: 1 consuma il testo prima di 2, e così via (spec §6).
PRIORITA: dict[Category, int] = {
    Category.CF: 1,
    Category.IBAN: 1,
    Category.PIVA: 1,
    Category.EMAIL: 2,
    Category.TELEFONO: 2,
    Category.CATASTO: 2,
    Category.PRATICA: 2,
    Category.DATA: 3,
    Category.IMPORTO: 3,
    Category.PERSONA: 4,
    Category.AZIENDA: 4,
    Category.INDIRIZZO: 4,
}


@dataclass(frozen=True)
class Document:
    doc_id: str
    filename: str
    text: str
    page_offsets: list[int]
    sha256: str


@dataclass(frozen=True)
class Span:
    span_id: str
    doc_id: str
    start: int
    end: int
    category: Category
    source: Source
    entity_id: str
    enabled: bool = True

    @property
    def priorita(self) -> int:
        return PRIORITA[self.category]

    @property
    def lunghezza(self) -> int:
        return self.end - self.start


@dataclass
class Entity:
    entity_id: str
    category: Category
    placeholder: str
    canonical_value: str
    variants: set[str] = field(default_factory=set)
    # LIMITE NOTO: nessun codice in produzione assegna `cf`, quindi le due
    # righe della spec §7 che dipendono da questo campo — "CF identico:
    # fusione automatica" e "CF diversi, stesso nome: entità distinte
    # automaticamente" — non esistono ancora. La spec non dice *come* un
    # codice fiscale si lega a una persona (vicinanza nel testo? stessa
    # riga? stessa frase?), e inventare la regola qui sarebbe peggio che
    # dichiararla mancante: legare il CF alla persona sbagliata fonde due
    # persone diverse. Conseguenza attuale: due omonimi nello stesso
    # documento condividono `[PERSONA_1]`, e al ripristino uno dei due
    # riceve il nome dell'altro. Richiede un emendamento della spec.
    cf: str | None = None


@dataclass
class Ambiguity:
    ambiguity_id: str
    kind: AmbiguityKind
    category: Category
    candidate_entity_ids: list[str]
    occurrence_span_ids: list[str]
    resolved: bool = False

    @property
    def blocca_approvazione(self) -> bool:
        """Solo le omonimie reali bloccano: ignorare un suggerimento significa
        tenere le entità separate, che è il default sicuro (spec §7)."""
        return self.kind is AmbiguityKind.SAME_NAME_NO_CF and not self.resolved


@dataclass
class Fascicolo:
    MAX_DOCUMENTI = 10

    fascicolo_id: str
    documents: list[Document] = field(default_factory=list)
    spans: list[Span] = field(default_factory=list)
    entities: dict[str, Entity] = field(default_factory=dict)
    category_enabled: dict[Category, bool] = field(default_factory=dict)
    ambiguities: list[Ambiguity] = field(default_factory=list)
    state: State = State.DRAFT
    approval_hash: str | None = None
    counters: dict[Category, int] = field(default_factory=dict)


def fascicolo_vuoto(fascicolo_id: str) -> Fascicolo:
    """Un fascicolo nuovo: tutte le categorie mascherate, contatori a zero (spec §5)."""
    return Fascicolo(
        fascicolo_id=fascicolo_id,
        category_enabled={c: True for c in Category},
        counters={c: 0 for c in Category},
    )
