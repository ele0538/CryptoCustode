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
    varianti: tuple[str, ...] = ()
    """Le altre scritture che questo segnaposto copre, dopo una fusione accettata.

    Nascono vuote e restano vuote finché l'utente non accetta un suggerimento:
    l'euristica sui nomi non fonde niente da sé (spec §7). `valore` resta il
    valore **canonico**, cioè quello che il ripristino rimette al posto del
    segnaposto; le varianti vengono sostituite nel testo ma non tornano indietro
    come erano scritte, ed è il senso stesso di aver detto che sono la stessa
    cosa.

    Una tupla e non un insieme: `Tag` è congelato, viene confrontato nei test e
    serializzato nel vault, e un insieme darebbe un ordine — quindi un JSON —
    diverso a ogni esecuzione.
    """


@dataclass
class FusioneSuggerita:
    """Due tag che l'euristica sui nomi giudica la stessa cosa (spec §7).

    È un suggerimento e **non blocca niente**. La coda bloccante di
    `feat/p6-disambiguazione` — `SAME_NAME_NO_CF`, due persone diverse con lo
    stesso nome — non è portata e non è portabile: `assegna_tag` deduplica per
    valore esatto e il modello non restituisce offset, quindi due omonimi sono
    un tag solo per costruzione e non c'è niente da separare. Resta il limite
    noto 2 della spec §16.

    `fusione_id` è deterministico (`tag_a+tag_b`) e non un UUID: l'analisi è
    rieseguibile, e un identificativo nuovo a ogni giro farebbe mandare alla
    pagina già aperta un id che non esiste più.
    """

    fusione_id: str
    categoria: Category
    tag_a: str
    """Il segnaposto più vecchio dei due: è quello che sopravvive alla fusione."""
    tag_b: str
    risolta: bool = False


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
    fusioni: list[FusioneSuggerita] = field(default_factory=list)
    """La coda dei suggerimenti di fusione, decisi e non.

    I decisi restano in coda invece di essere cancellati: è ciò che impedisce
    all'analisi successiva di riproporre una coppia che l'utente ha già
    guardato e lasciato separata.
    """
    analizzati: set[str] = field(default_factory=set)
    """I `doc_id` già passati dal rilevatore.

    Prima questa informazione si deduceva dagli span esistenti. Senza span
    serve un campo: rianalizzare un documento significa ripagare una chiamata
    a Gemini per un risultato che si ha già.
    """


def fascicolo_vuoto(fascicolo_id: str) -> Fascicolo:
    """Un fascicolo nuovo: nessuna categoria mascherata, contatori a zero (spec §5).

    Si parte da zero e si accende ciò che serve. È l'opposto della decisione 4
    della spec del 2026-09-10, che mascherava tutto per prudenza, ed è una
    scelta del proprietario del prodotto presa dopo aver visto il default
    prudente all'opera: chi conosce il documento decide cosa nascondere, invece
    di trovarsi un testo già svuotato da riaprire pezzo per pezzo.

    **Il rischio è reale e va detto qui, perché è qui che si decide.** Chi
    carica un documento, non tocca nessun interruttore e preme Esporta,
    esporta il documento in chiaro. L'analisi mostra comunque tutto ciò che ha
    trovato, evidenziato e con il suo segnaposto accanto, quindi il dato non è
    nascosto all'utente — ma spento resta, finché non lo accende lui.

    `category_enabled` elenca comunque tutte e dodici le categorie, anche se
    partono tutte a `False`: la UI le deve poter mostrare, e
    `mask.tabella_attiva` non deve indovinare un valore mancante.
    """
    return Fascicolo(
        fascicolo_id=fascicolo_id,
        category_enabled={c: False for c in Category},
        counters={c: 0 for c in Category},
    )
