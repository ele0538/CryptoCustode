# Fase 1 — Il motore passa a Gemini: piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sostituire il motore di riconoscimento a regex e NER con una chiamata a Gemini che restituisce l'elenco dei dati sensibili, e far costruire all'applicazione il testo mascherato a partire da quell'elenco.

**Architecture:** Gemini riceve il testo e risponde con `[{valore, categoria}]` vincolato da JSON Schema. `core/tagga.py`, funzione pura, cerca ogni valore alla lettera nel testo e lo sostituisce con `[CATEGORIA_N]`: il modello non scrive mai testo, quindi non può riscrivere il documento. Il confine con la rete è un `Protocol` dichiarato in `core/rilevatore.py` e implementato in `ai/gemini.py`, fuori da `core/`, così l'invariante di purezza regge e nessun test della suite predefinita tocca la rete. A fine fase la UI di revisione funziona come prima: le posizioni evidenziate non vengono più dal modello ma dalle regioni che `tagga()` ha davvero rivendicato.

**Tech Stack:** Python 3.14, `google-genai`, FastAPI, pytest. Esce `spacy` con il modello `it_core_news_lg`.

**Spec:** `docs/superpowers/specs/2026-09-14-motore-ia-esporta-importa.md` (che a sua volta emenda `docs/superpowers/specs/2026-09-10-cryptocustode-design.md`: vanno letti insieme).

## Global Constraints

- Python `>=3.14`. **Mai** `from __future__ import annotations`: un test lo vieta in tutto il package e in `tests/` (issue #18).
- `core/` non può importare `fastapi`, `uvicorn`, `starlette`, `cryptocustode.state`, e da questa fase nemmeno `httpx`, `requests`, `google`, `google.genai`.
- `core/mask.py` e `core/tagga.py` non possono importare `os`, `pathlib`, `random`, `secrets`, `time`, `datetime`, `uuid`, `io`: devono essere deterministici perché `approval_hash` va ricalcolato identico in esportazione.
- **Additivo prima, sottrattivo dopo.** Nessun commit può lasciare la suite rossa. I tipi e i moduli nuovi si aggiungono accanto ai vecchi (task 1-12); `core/detect/`, `core/spans.py` e `core/entities.py` si cancellano solo nel task 13, quando nessuno li importa più.
- Nomi dei tipi e delle eccezioni in inglese; messaggi d'errore, docstring e commenti in italiano, come tutto il repo.
- Suite: `python -m pytest -q` dalla radice del repo. Un singolo file: `python -m pytest tests/test_tagga.py -q`.
- Il repo è condiviso con altre sessioni: `git add` solo i file elencati nel task, mai `git add -A`.

---

### Task 1: I tipi del tagging

Aggiunge a `core/models.py` i tipi che tutta la fase usa. Puramente additivo: `Span`, `Entity`, `Ambiguity` restano al loro posto e verranno rimossi nel task 13.

**Files:**
- Modify: `cryptocustode/core/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: `Category` (già esistente in `core/models.py`).
- Produces: `Rilevazione(valore, categoria)`, `StatoTag.{APPLICATO,NON_TROVATO,DISATTIVATO}`, `Tag(tag, categoria, valore, occorrenze, stato)`, `Regione(start, end, tag)`, `Mascheratura(mascherato, tags, regioni)`. Il campo `Fascicolo.tags: dict[str, Tag]` è **indicizzato per stringa del tag** (`"[PERSONA_1]"`), non per valore.

- [ ] **Step 1: Scrivi i test che falliscono**

In fondo a `tests/test_models.py`:

```python
from cryptocustode.core.models import (
    Mascheratura,
    Regione,
    Rilevazione,
    StatoTag,
    Tag,
)


class TestITipiDelTagging:
    """I tipi della spec §5 del 2026-09-14. Solo dati: nessun comportamento."""

    def test_la_rilevazione_tiene_valore_e_categoria(self):
        r = Rilevazione(valore="Mario Rossi", categoria=Category.PERSONA)
        assert r.valore == "Mario Rossi"
        assert r.categoria is Category.PERSONA

    def test_il_tag_nasce_non_trovato_e_a_zero_occorrenze(self):
        """`assegna_tag` crea i tag prima di sapere se il testo li contiene:
        lo stato vero lo decide `conta_occorrenze` (task 5)."""
        t = Tag(
            tag="[PERSONA_1]",
            categoria=Category.PERSONA,
            valore="Mario Rossi",
            occorrenze=0,
            stato=StatoTag.NON_TROVATO,
        )
        assert t.tag == "[PERSONA_1]"
        assert t.occorrenze == 0
        assert t.stato is StatoTag.NON_TROVATO

    def test_la_regione_si_riferisce_al_testo_originale(self):
        regione = Regione(start=8, end=19, tag="[PERSONA_1]")
        assert "Il sig. Mario Rossi paga."[regione.start:regione.end] == "Mario Rossi"

    def test_la_mascheratura_tiene_testo_tag_e_regioni(self):
        m = Mascheratura(mascherato="ciao", tags=[], regioni=[])
        assert m.mascherato == "ciao"
        assert m.tags == []
        assert m.regioni == []

    def test_il_fascicolo_vuoto_ha_la_tabella_dei_tag_vuota(self):
        fascicolo = fascicolo_vuoto("f1")
        assert fascicolo.tags == {}

    def test_i_tipi_del_tagging_sono_congelati(self):
        """Congelati come `Span` lo era: la tabella dei tag attraversa
        `hash_approvazione`, e un tipo mutabile permetterebbe di cambiare un
        valore dopo l'approvazione senza passare da `registra_mutazione`."""
        t = Tag(
            tag="[CF_1]",
            categoria=Category.CF,
            valore="RSSMRA80A01H501U",
            occorrenze=1,
            stato=StatoTag.APPLICATO,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            t.valore = "altro"
```

In testa al file, se non ci sono già: `import dataclasses`, `import pytest`, e l'import di `fascicolo_vuoto` e `Category` da `cryptocustode.core.models`.

- [ ] **Step 2: Esegui i test e verifica che falliscano**

Run: `python -m pytest tests/test_models.py -q`
Expected: FAIL con `ImportError: cannot import name 'Rilevazione'`.

- [ ] **Step 3: Aggiungi i tipi**

In `cryptocustode/core/models.py`, dopo `class Source` e prima di `PRIORITA`:

```python
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
```

E dopo `class Document`:

```python
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
```

In `class Fascicolo` aggiungi il campo, lasciando gli altri dove sono:

```python
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
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `python -m pytest tests/test_models.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cryptocustode/core/models.py tests/test_models.py
git commit -m "feat: i tipi del tagging, accanto a quelli che sostituiranno"
```

---

### Task 2: Il confine con il modello

Dichiara il `Protocol` che `core/` usa per parlare con un rilevatore, senza sapere che esiste una rete. È ciò che permette a tutta la suite di girare contro un doppio.

**Files:**
- Create: `cryptocustode/core/rilevatore.py`
- Create: `tests/doppi.py`
- Test: `tests/test_rilevatore.py`

**Interfaces:**
- Consumes: `Rilevazione` dal task 1.
- Produces: `Rilevatore` (Protocol con `rileva(self, testo: str) -> list[Rilevazione]`), e `RilevatoreFinto(rilevazioni_per_testo: dict[str, list[Rilevazione]] | None, sempre: list[Rilevazione] | None)` in `tests/doppi.py`, con l'attributo `chiamate: list[str]`.

- [ ] **Step 1: Scrivi il test che fallisce**

Crea `tests/test_rilevatore.py`:

```python
"""Il confine fra `core/` e il modello (spec §4, invariante 1)."""

from cryptocustode.core.models import Category, Rilevazione
from cryptocustode.core.rilevatore import Rilevatore

from tests.doppi import RilevatoreFinto


def test_il_doppio_soddisfa_il_protocollo():
    """`Protocol` è runtime-checkable: senza questo test la conformità del
    doppio resterebbe un'opinione, e un cambio di firma la romperebbe in
    silenzio in tutti i test che lo usano."""
    assert isinstance(RilevatoreFinto(sempre=[]), Rilevatore)


def test_il_doppio_risponde_per_testo():
    finto = RilevatoreFinto(
        rilevazioni_per_testo={
            "Mario Rossi paga.": [
                Rilevazione(valore="Mario Rossi", categoria=Category.PERSONA)
            ]
        }
    )
    assert finto.rileva("Mario Rossi paga.") == [
        Rilevazione(valore="Mario Rossi", categoria=Category.PERSONA)
    ]


def test_il_doppio_su_un_testo_non_previsto_non_trova_niente():
    assert RilevatoreFinto(rilevazioni_per_testo={}).rileva("qualunque cosa") == []


def test_il_doppio_registra_le_chiamate():
    """Serve ai test di rianalisi: dimostrare che un documento già analizzato
    non ripaga una seconda chiamata."""
    finto = RilevatoreFinto(sempre=[])
    finto.rileva("a")
    finto.rileva("b")
    assert finto.chiamate == ["a", "b"]
```

- [ ] **Step 2: Esegui il test e verifica che fallisca**

Run: `python -m pytest tests/test_rilevatore.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'cryptocustode.core.rilevatore'`.

- [ ] **Step 3: Scrivi il modulo e il doppio**

Crea `cryptocustode/core/rilevatore.py`:

```python
"""Il confine fra il dominio e il modello linguistico (spec §4, invariante 1).

Qui vive la sola cosa che `core/` deve sapere del rilevamento: che esiste
qualcuno capace di guardare un testo e dire quali dati sensibili contiene.
Chi sia — Gemini, un doppio di test, un domani un modello locale — non entra in
`core/`, e il test di architettura lo fa rispettare vietando sotto `core/` gli
import di `httpx`, `requests` e `google`.

`runtime_checkable` esiste perché i test possano affermare la conformità di un
doppio con un `isinstance`: senza, la conformità sarebbe un'opinione, e un
cambio di firma la romperebbe in silenzio ovunque il doppio è usato.
"""

from typing import Protocol, runtime_checkable

from cryptocustode.core.models import Rilevazione


@runtime_checkable
class Rilevatore(Protocol):
    """Guarda un testo, dice quali dati sensibili contiene."""

    def rileva(self, testo: str) -> list[Rilevazione]:
        """Le rilevazioni trovate nel testo.

        Ogni `valore` deve essere una sottostringa letterale di `testo`.
        Un'implementazione che non riesce a garantirlo non è in errore: i
        valori che non si trovano diventano tag `NON_TROVATO` (spec §7).

        Solleva `AIUnavailable` se il servizio non risponde e
        `AIResponseInvalid` se risponde male: in entrambi i casi il fascicolo
        del chiamante deve restare intatto.
        """
        ...
```

Crea `tests/doppi.py`:

```python
"""I doppi condivisi dalla suite.

Vivono in un modulo e non in `conftest.py` perché sono classi importabili per
nome, non fixture: un test che ne vuole uno lo costruisce con gli argomenti che
gli servono, invece di ricevere quello che la fixture ha deciso.
"""

from cryptocustode.core.models import Rilevazione


class RilevatoreFinto:
    """Un `Rilevatore` che risponde quello che il test gli ha detto.

    `rilevazioni_per_testo` risponde in base al testo ricevuto; `sempre`
    risponde la stessa cosa a chiunque. Passarli entrambi è legittimo: vince la
    voce per testo, e `sempre` fa da risposta predefinita.
    """

    def __init__(
        self,
        rilevazioni_per_testo: dict[str, list[Rilevazione]] | None = None,
        sempre: list[Rilevazione] | None = None,
    ) -> None:
        self._per_testo = rilevazioni_per_testo or {}
        self._sempre = sempre
        self.chiamate: list[str] = []

    def rileva(self, testo: str) -> list[Rilevazione]:
        self.chiamate.append(testo)
        if testo in self._per_testo:
            return list(self._per_testo[testo])
        return list(self._sempre) if self._sempre is not None else []
```

- [ ] **Step 4: Esegui il test e verifica che passi**

Run: `python -m pytest tests/test_rilevatore.py -q`
Expected: PASS, 4 test.

- [ ] **Step 5: Commit**

```bash
git add cryptocustode/core/rilevatore.py tests/doppi.py tests/test_rilevatore.py
git commit -m "feat: il confine con il modello e' un Protocol, non un client"
```

---

### Task 3: `assegna_tag`

Dalle rilevazioni di tutto il fascicolo alla tabella dei tag. Gira **una volta per fascicolo**, non per documento: è ciò che fa sì che lo stesso nome riceva lo stesso tag in tutti i file.

**Files:**
- Create: `cryptocustode/core/tagga.py`
- Test: `tests/test_tagga.py`

**Interfaces:**
- Consumes: `Rilevazione`, `Tag`, `StatoTag`, `Category` dal task 1; `costruisci_segnaposto(categoria: str, indice: int) -> str` da `core/placeholders.py`.
- Produces: `assegna_tag(rilevazioni: list[Rilevazione], tabella: dict[str, Tag], contatori: dict[Category, int]) -> tuple[dict[str, Tag], dict[Category, int]]`. Non muta gli argomenti: restituisce copie nuove.

- [ ] **Step 1: Scrivi i test che falliscono**

Crea `tests/test_tagga.py`:

```python
"""`assegna_tag` e `tagga`: dai valori del modello al testo mascherato (spec §7)."""

from cryptocustode.core.models import Category, Rilevazione, StatoTag
from cryptocustode.core.tagga import assegna_tag

VUOTI: dict[Category, int] = {}


def _rilevazione(valore: str, categoria: Category = Category.PERSONA) -> Rilevazione:
    return Rilevazione(valore=valore, categoria=categoria)


class TestAssegnaTag:
    def test_un_valore_riceve_un_tag_della_sua_categoria(self):
        tabella, contatori = assegna_tag([_rilevazione("Mario Rossi")], {}, VUOTI)
        assert list(tabella) == ["[PERSONA_1]"]
        assert tabella["[PERSONA_1]"].valore == "Mario Rossi"
        assert tabella["[PERSONA_1]"].categoria is Category.PERSONA
        assert contatori[Category.PERSONA] == 1

    def test_il_tag_nasce_non_trovato(self):
        """Se il valore compaia davvero nel testo lo sa solo `tagga`."""
        tabella, _ = assegna_tag([_rilevazione("Mario Rossi")], {}, VUOTI)
        assert tabella["[PERSONA_1]"].stato is StatoTag.NON_TROVATO
        assert tabella["[PERSONA_1]"].occorrenze == 0

    def test_lo_stesso_valore_nominato_due_volte_e_un_tag_solo(self):
        tabella, contatori = assegna_tag(
            [_rilevazione("Mario Rossi"), _rilevazione("Mario Rossi")], {}, VUOTI
        )
        assert list(tabella) == ["[PERSONA_1]"]
        assert contatori[Category.PERSONA] == 1

    def test_un_valore_gia_in_tabella_non_consuma_un_indice_nuovo(self):
        """La stabilità fra documenti: il secondo file che nomina Mario Rossi
        riceve il tag che aveva il primo (spec §5)."""
        tabella, contatori = assegna_tag([_rilevazione("Mario Rossi")], {}, VUOTI)
        tabella, contatori = assegna_tag(
            [_rilevazione("Mario Rossi"), _rilevazione("Luigi Bianchi")],
            tabella,
            contatori,
        )
        assert sorted(tabella) == ["[PERSONA_1]", "[PERSONA_2]"]
        assert tabella["[PERSONA_1]"].valore == "Mario Rossi"
        assert tabella["[PERSONA_2]"].valore == "Luigi Bianchi"

    def test_categorie_diverse_hanno_contatori_indipendenti(self):
        tabella, _ = assegna_tag(
            [
                _rilevazione("Mario Rossi", Category.PERSONA),
                _rilevazione("ACME s.r.l.", Category.AZIENDA),
            ],
            {},
            VUOTI,
        )
        assert sorted(tabella) == ["[AZIENDA_1]", "[PERSONA_1]"]

    def test_la_numerazione_non_dipende_dall_ordine_di_arrivo(self):
        """Il modello elenca in un ordine suo, che può cambiare fra due
        chiamate: la numerazione no, altrimenti l'hash di approvazione
        cambierebbe senza che sia cambiato niente."""
        avanti, _ = assegna_tag(
            [_rilevazione("Mario Rossi"), _rilevazione("Bianchi")], {}, VUOTI
        )
        indietro, _ = assegna_tag(
            [_rilevazione("Bianchi"), _rilevazione("Mario Rossi")], {}, VUOTI
        )
        assert {t.tag: t.valore for t in avanti.values()} == {
            t.tag: t.valore for t in indietro.values()
        }

    def test_a_parita_di_lunghezza_decide_l_alfabeto(self):
        avanti, _ = assegna_tag(
            [_rilevazione("Bianchi"), _rilevazione("Azzurri")], {}, VUOTI
        )
        assert avanti["[PERSONA_1]"].valore == "Azzurri"
        assert avanti["[PERSONA_2]"].valore == "Bianchi"

    def test_gli_indici_non_si_riciclano(self):
        """`counters` cresce e non torna indietro: un testo esportato ieri non
        deve contenere un tag che oggi significa un'altra persona (spec §5)."""
        _, contatori = assegna_tag([_rilevazione("Mario Rossi")], {}, VUOTI)
        tabella, contatori = assegna_tag([_rilevazione("Luigi Bianchi")], {}, contatori)
        assert list(tabella) == ["[PERSONA_2]"]

    def test_il_valore_vuoto_viene_scartato(self):
        """Un valore vuoto troverebbe un'occorrenza a ogni offset del testo."""
        tabella, _ = assegna_tag([_rilevazione("")], {}, VUOTI)
        assert tabella == {}

    def test_non_muta_gli_argomenti(self):
        tabella_iniziale: dict = {}
        contatori_iniziali: dict = {}
        assegna_tag([_rilevazione("Mario Rossi")], tabella_iniziale, contatori_iniziali)
        assert tabella_iniziale == {}
        assert contatori_iniziali == {}
```

- [ ] **Step 2: Esegui i test e verifica che falliscano**

Run: `python -m pytest tests/test_tagga.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'cryptocustode.core.tagga'`.

- [ ] **Step 3: Scrivi `assegna_tag`**

Crea `cryptocustode/core/tagga.py`:

```python
"""Dai valori rilevati al testo mascherato (spec §7 del 2026-09-14).

Modulo puro come `mask.py`, e per la stessa ragione: `hash_approvazione` lo
attraversa, quindi un tagging non deterministico farebbe fallire a caso il
confronto con `approval_hash` e il controllo d'integrità diventerebbe rumore.
Il non determinismo del modello sta a monte e non entra qui: queste funzioni
ricevono una lista di valori, non un documento da interpretare.

La divisione in due funzioni non è cosmetica. I tag sono **di fascicolo** —
lo stesso nome deve avere lo stesso segnaposto in tutti i documenti, altrimenti
il testo che l'utente consegna a un'IA di terze parti non è coerente con sé
stesso — mentre il testo mascherato è **di documento**.
"""

from dataclasses import replace

from cryptocustode.core.models import (
    Category,
    Mascheratura,
    Regione,
    Rilevazione,
    StatoTag,
    Tag,
)
from cryptocustode.core.placeholders import costruisci_segnaposto


def _ordine_totale(valore: str) -> tuple[int, str]:
    """Lunghezza decrescente, poi alfabetico crescente.

    La lunghezza serve alla correttezza: `Rossi` non deve prendersi il posto
    dentro `Mario Rossi`. L'alfabetico serve alla riproducibilità: due valori
    lunghi uguali devono ordinarsi sempre allo stesso modo, qualunque sia
    l'ordine in cui il modello li ha elencati.
    """
    return (-len(valore), valore)


def assegna_tag(
    rilevazioni: list[Rilevazione],
    tabella: dict[str, Tag],
    contatori: dict[Category, int],
) -> tuple[dict[str, Tag], dict[Category, int]]:
    """Estende la tabella dei tag con i valori che non ci sono ancora.

    Restituisce copie nuove e non muta gli argomenti: chi chiama decide quando
    scrivere il risultato nel fascicolo, e un fallimento a metà non lascia la
    tabella in uno stato intermedio.

    I nuovi valori vengono numerati in ordine totale (`_ordine_totale`), non
    nell'ordine in cui il modello li ha elencati.
    """
    nuova = dict(tabella)
    contati = dict(contatori)
    gia_presenti = {tag.valore for tag in nuova.values()}

    inediti: list[Rilevazione] = []
    for rilevazione in rilevazioni:
        if not rilevazione.valore or rilevazione.valore in gia_presenti:
            continue
        gia_presenti.add(rilevazione.valore)
        inediti.append(rilevazione)

    for rilevazione in sorted(inediti, key=lambda r: _ordine_totale(r.valore)):
        indice = contati.get(rilevazione.categoria, 0) + 1
        contati[rilevazione.categoria] = indice
        segnaposto = costruisci_segnaposto(rilevazione.categoria.value, indice)
        nuova[segnaposto] = Tag(
            tag=segnaposto,
            categoria=rilevazione.categoria,
            valore=rilevazione.valore,
            occorrenze=0,
            stato=StatoTag.NON_TROVATO,
        )
    return nuova, contati
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `python -m pytest tests/test_tagga.py -q`
Expected: PASS, 10 test.

- [ ] **Step 5: Commit**

```bash
git add cryptocustode/core/tagga.py tests/test_tagga.py
git commit -m "feat: assegna_tag numera i valori in un ordine totale, non in quello del modello"
```

---

### Task 4: `tagga`

Il cuore della fase: cerca i valori alla lettera, rivendica le occorrenze, costruisce il testo mascherato e verbalizza le regioni.

**Files:**
- Modify: `cryptocustode/core/tagga.py`
- Test: `tests/test_tagga.py`

**Interfaces:**
- Consumes: `assegna_tag` dal task 3; `Mascheratura`, `Regione` dal task 1.
- Produces: `tagga(testo: str, tabella: dict[str, Tag]) -> Mascheratura`. `regioni` è ordinata per `start` crescente e riferita al testo **originale**; `tags` è `list(tabella.values())`.

- [ ] **Step 1: Scrivi i test che falliscono**

Aggiungi a `tests/test_tagga.py` (e all'import in testa: `from cryptocustode.core.tagga import assegna_tag, tagga`):

```python
def _tabella(*valori_e_categorie) -> dict:
    rilevazioni = [Rilevazione(valore=v, categoria=c) for v, c in valori_e_categorie]
    tabella, _ = assegna_tag(rilevazioni, {}, VUOTI)
    return tabella


class TestTagga:
    def test_sostituisce_il_valore_col_suo_tag(self):
        tabella = _tabella(("Mario Rossi", Category.PERSONA))
        assert tagga("Il sig. Mario Rossi paga.", tabella).mascherato == (
            "Il sig. [PERSONA_1] paga."
        )

    def test_sostituisce_tutte_le_occorrenze(self):
        tabella = _tabella(("Mario Rossi", Category.PERSONA))
        risultato = tagga("Mario Rossi e ancora Mario Rossi.", tabella)
        assert risultato.mascherato == "[PERSONA_1] e ancora [PERSONA_1]."
        assert len(risultato.regioni) == 2

    def test_il_valore_piu_lungo_rivendica_per_primo(self):
        """Senza l'ordinamento per lunghezza, `Rossi` verrebbe taggato dentro
        `Mario Rossi` e produrrebbe `Mario [PERSONA_2]`."""
        tabella = _tabella(
            ("Mario Rossi", Category.PERSONA), ("Rossi", Category.PERSONA)
        )
        assert tagga("Mario Rossi.", tabella).mascherato == "[PERSONA_1]."

    def test_il_valore_corto_prende_solo_le_occorrenze_che_restano(self):
        tabella = _tabella(
            ("Mario Rossi", Category.PERSONA), ("Rossi", Category.PERSONA)
        )
        mascherato = tagga("Mario Rossi e il dott. Rossi.", tabella).mascherato
        assert mascherato == "[PERSONA_1] e il dott. [PERSONA_2]."

    def test_una_sottostringa_dentro_una_parola_piu_lunga_viene_comunque_presa(self):
        """`Rossi` dentro `Rossini` è un falso positivo del modello, non di
        `tagga`: la ricerca è letterale e non conosce i confini di parola. Il
        test fissa il comportamento perché sia una scelta visibile e non una
        sorpresa — chi vorrà cambiarlo saprà cosa sta cambiando."""
        tabella = _tabella(("Rossi", Category.PERSONA))
        assert tagga("Rossini canta.", tabella).mascherato == "[PERSONA_1]ni canta."

    def test_la_ricerca_e_sensibile_alle_maiuscole(self):
        """La controparte del vincolo di letteralità imposto al modello: senza
        confronto esatto l'identità del round-trip non varrebbe, perché al
        ripristino tornerebbe il valore con la grafia sbagliata."""
        tabella = _tabella(("Mario Rossi", Category.PERSONA))
        assert tagga("ROSSI MARIO paga.", tabella).mascherato == "ROSSI MARIO paga."

    def test_un_valore_assente_lascia_il_testo_intatto(self):
        tabella = _tabella(("Luigi Bianchi", Category.PERSONA))
        risultato = tagga("Mario Rossi paga.", tabella)
        assert risultato.mascherato == "Mario Rossi paga."
        assert risultato.regioni == []

    def test_le_regioni_si_riferiscono_al_testo_originale(self):
        tabella = _tabella(("Mario Rossi", Category.PERSONA))
        testo = "Il sig. Mario Rossi paga."
        regione = tagga(testo, tabella).regioni[0]
        assert testo[regione.start:regione.end] == "Mario Rossi"
        assert regione.tag == "[PERSONA_1]"

    def test_le_regioni_sono_ordinate_per_inizio(self):
        tabella = _tabella(
            ("Mario Rossi", Category.PERSONA), ("ACME s.r.l.", Category.AZIENDA)
        )
        regioni = tagga("ACME s.r.l. paga a Mario Rossi.", tabella).regioni
        assert [r.start for r in regioni] == sorted(r.start for r in regioni)

    def test_e_deterministica(self):
        tabella = _tabella(
            ("Mario Rossi", Category.PERSONA), ("Rossi", Category.PERSONA)
        )
        testo = "Mario Rossi, poi Rossi, poi Mario Rossi."
        assert tagga(testo, tabella).mascherato == tagga(testo, tabella).mascherato

    def test_il_testo_vuoto_non_esplode(self):
        assert tagga("", _tabella(("Mario Rossi", Category.PERSONA))).mascherato == ""
```

- [ ] **Step 2: Esegui i test e verifica che falliscano**

Run: `python -m pytest tests/test_tagga.py -q`
Expected: FAIL con `ImportError: cannot import name 'tagga'`.

- [ ] **Step 3: Scrivi `tagga`**

In fondo a `cryptocustode/core/tagga.py`:

```python
def tagga(testo: str, tabella: dict[str, Tag]) -> Mascheratura:
    """Sostituisce nel testo i valori della tabella con i rispettivi tag.

    La ricerca è **esatta**: sensibile a maiuscole, accenti, punteggiatura e
    spaziatura, senza alcuna normalizzazione. È la controparte del vincolo di
    letteralità imposto al modello nella §6, e ciò che rende vera l'identità
    `unmask(tagga(testo, tabella).mascherato, mappa) == testo` della §8: se qui
    si accettasse una corrispondenza approssimata, al ripristino tornerebbe un
    valore diverso da quello che c'era, e il round-trip non sarebbe più
    un'identità ma una somiglianza.

    Un valore più lungo rivendica prima di uno più corto, e un valore corto non
    può rivendicare dentro una regione già presa: è ciò che impedisce a `Rossi`
    di finire dentro `Mario Rossi`.
    """
    rivendicate: list[Regione] = []
    occupato = [False] * len(testo)

    for tag in sorted(tabella.values(), key=lambda t: _ordine_totale(t.valore)):
        if not tag.valore:
            continue
        inizio = 0
        while True:
            trovato = testo.find(tag.valore, inizio)
            if trovato == -1:
                break
            fine = trovato + len(tag.valore)
            if any(occupato[trovato:fine]):
                # Sovrapposta a una regione già presa da un valore più lungo:
                # si riparte dal carattere successivo, perché l'occorrenza
                # buona potrebbe cominciare dentro quella scartata.
                inizio = trovato + 1
                continue
            occupato[trovato:fine] = [True] * (fine - trovato)
            rivendicate.append(Regione(start=trovato, end=fine, tag=tag.tag))
            inizio = fine

    rivendicate.sort(key=lambda regione: regione.start)

    # Da destra a sinistra: così ogni sostituzione lascia validi gli offset di
    # quelle ancora da applicare (spec §9 del 2026-09-10).
    mascherato = testo
    for regione in reversed(rivendicate):
        mascherato = mascherato[: regione.start] + regione.tag + mascherato[regione.end :]

    return Mascheratura(
        mascherato=mascherato,
        tags=list(tabella.values()),
        regioni=rivendicate,
    )
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `python -m pytest tests/test_tagga.py -q`
Expected: PASS, 21 test.

- [ ] **Step 5: Commit**

```bash
git add cryptocustode/core/tagga.py tests/test_tagga.py
git commit -m "feat: tagga rivendica le occorrenze, il valore piu' lungo per primo"
```

---

### Task 5: `conta_occorrenze`

Occorrenze e stato di un tag sono proprietà del **fascicolo**, non di un documento: si sanno solo dopo aver mascherato tutti i file.

**Files:**
- Modify: `cryptocustode/core/tagga.py`
- Test: `tests/test_tagga.py`

**Interfaces:**
- Consumes: `tagga` dal task 4.
- Produces: `conta_occorrenze(tabella: dict[str, Tag], mascherature: list[Mascheratura]) -> dict[str, Tag]`. Non tocca i tag `DISATTIVATO`.

- [ ] **Step 1: Scrivi i test che falliscono**

Aggiungi a `tests/test_tagga.py` (import: `from cryptocustode.core.tagga import assegna_tag, conta_occorrenze, tagga`, e `from dataclasses import replace`):

```python
class TestContaOccorrenze:
    def test_un_tag_trovato_diventa_applicato(self):
        tabella = _tabella(("Mario Rossi", Category.PERSONA))
        aggiornata = conta_occorrenze(tabella, [tagga("Mario Rossi.", tabella)])
        assert aggiornata["[PERSONA_1]"].stato is StatoTag.APPLICATO
        assert aggiornata["[PERSONA_1]"].occorrenze == 1

    def test_somma_le_occorrenze_di_tutti_i_documenti(self):
        tabella = _tabella(("Mario Rossi", Category.PERSONA))
        mascherature = [
            tagga("Mario Rossi e Mario Rossi.", tabella),
            tagga("Ancora Mario Rossi.", tabella),
        ]
        assert conta_occorrenze(tabella, mascherature)["[PERSONA_1]"].occorrenze == 3

    def test_un_tag_che_nessun_documento_contiene_resta_non_trovato(self):
        """Il caso della §7: il modello ha normalizzato il valore. Il tag resta
        visibile, perché ignorarlo lascerebbe il dato in chiaro in silenzio."""
        tabella = _tabella(("Mario Rossi", Category.PERSONA))
        aggiornata = conta_occorrenze(tabella, [tagga("ROSSI MARIO.", tabella)])
        assert aggiornata["[PERSONA_1]"].stato is StatoTag.NON_TROVATO
        assert aggiornata["[PERSONA_1]"].occorrenze == 0

    def test_non_riaccende_un_tag_spento_dall_utente(self):
        """Spegnere un tag è una decisione dell'utente sulla riservatezza: un
        conteggio non può revocarla. Senza questa guardia, ricalcolare le
        occorrenze dopo un toggle rimetterebbe in maschera un dato che l'utente
        ha chiesto di lasciare in chiaro."""
        tabella = _tabella(("Mario Rossi", Category.PERSONA))
        spenta = {
            chiave: replace(tag, stato=StatoTag.DISATTIVATO)
            for chiave, tag in tabella.items()
        }
        aggiornata = conta_occorrenze(spenta, [tagga("Mario Rossi.", spenta)])
        assert aggiornata["[PERSONA_1]"].stato is StatoTag.DISATTIVATO

    def test_non_muta_la_tabella_ricevuta(self):
        tabella = _tabella(("Mario Rossi", Category.PERSONA))
        conta_occorrenze(tabella, [tagga("Mario Rossi.", tabella)])
        assert tabella["[PERSONA_1]"].occorrenze == 0
```

- [ ] **Step 2: Esegui i test e verifica che falliscano**

Run: `python -m pytest tests/test_tagga.py -q`
Expected: FAIL con `ImportError: cannot import name 'conta_occorrenze'`.

- [ ] **Step 3: Scrivi `conta_occorrenze`**

In fondo a `cryptocustode/core/tagga.py`:

```python
def conta_occorrenze(
    tabella: dict[str, Tag], mascherature: list[Mascheratura]
) -> dict[str, Tag]:
    """Aggiorna occorrenze e stato sull'insieme dei documenti del fascicolo.

    Quante volte un dato compaia, e se compaia affatto, è una proprietà del
    fascicolo: `tagga` lavora su un documento per volta e non può saperlo.

    I tag `DISATTIVATO` restano tali. Spegnere un tag è una decisione
    dell'utente sulla riservatezza, e un conteggio non ha titolo per revocarla:
    senza questa guardia, il primo ricalcolo dopo un toggle rimetterebbe in
    maschera un dato che l'utente ha chiesto di lasciare in chiaro.
    """
    quante: dict[str, int] = {}
    for mascheratura in mascherature:
        for regione in mascheratura.regioni:
            quante[regione.tag] = quante.get(regione.tag, 0) + 1

    aggiornata: dict[str, Tag] = {}
    for chiave, tag in tabella.items():
        if tag.stato is StatoTag.DISATTIVATO:
            aggiornata[chiave] = tag
            continue
        totale = quante.get(tag.tag, 0)
        aggiornata[chiave] = replace(
            tag,
            occorrenze=totale,
            stato=StatoTag.APPLICATO if totale else StatoTag.NON_TROVATO,
        )
    return aggiornata
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `python -m pytest tests/test_tagga.py -q`
Expected: PASS, 26 test.

- [ ] **Step 5: Commit**

```bash
git add cryptocustode/core/tagga.py tests/test_tagga.py
git commit -m "feat: occorrenze e stato di un tag sono proprieta' del fascicolo"
```

---

### Task 6: Il ripristino su un dizionario, e l'identità del round-trip

`ripristina` prende oggi `dict[str, Entity]`, un tipo che il task 13 cancella. La logica non cambia: cambia il parametro, che diventa la mappa `tag → valore` e basta. Qui nasce anche il test centrale della suite.

**Files:**
- Modify: `cryptocustode/core/unmask.py`
- Modify: `tests/test_unmask.py`
- Create: `tests/test_round_trip.py`

**Interfaces:**
- Consumes: `tagga`, `assegna_tag` dai task 3-4.
- Produces: `ripristina(risposta: str, dizionario: dict[str, str]) -> str` e `dizionario_di(tabella: dict[str, Tag]) -> dict[str, str]` in `core/tagga.py`.

- [ ] **Step 1: Scrivi il test dell'identità**

Crea `tests/test_round_trip.py`:

```python
"""L'identità della spec §8: mascherare e ripristinare riporta all'originale.

È il test più importante della suite. Se `tagga` sbagliasse un offset, o
`unmask` cambiasse la forma del segnaposto, o i due divergessero su cosa sia un
tag, questo test cade prima di qualunque altro — e cade in memoria, senza rete
e senza costo.
"""

import pytest

from cryptocustode.core.models import Category, Rilevazione
from cryptocustode.core.tagga import assegna_tag, dizionario_di, tagga
from cryptocustode.core.unmask import ripristina

# Testi senza segnaposto preesistenti: uno `[PERSONA_1]` già scritto nel
# documento originale verrebbe risolto dal ripristino, ed è il caso che
# `segnaposto_preesistenti` avvisa al caricamento (spec §12 del 2026-09-10).
CASI = [
    (
        "Il sig. Mario Rossi, C.F. RSSMRA80A01H501U, paga 1.200,00 euro.",
        [
            ("Mario Rossi", Category.PERSONA),
            ("RSSMRA80A01H501U", Category.CF),
            ("1.200,00 euro", Category.IMPORTO),
        ],
    ),
    (
        "Mario Rossi e il dott. Rossi firmano per ACME s.r.l.",
        [
            ("Mario Rossi", Category.PERSONA),
            ("Rossi", Category.PERSONA),
            ("ACME s.r.l.", Category.AZIENDA),
        ],
    ),
    ("Nessun dato personale in questo testo.", []),
    ("", [("Mario Rossi", Category.PERSONA)]),
    (
        "Mario Rossi\nMario Rossi\nMario Rossi\n",
        [("Mario Rossi", Category.PERSONA)],
    ),
]


@pytest.mark.parametrize("testo, valori", CASI)
def test_mascherare_e_ripristinare_riporta_all_originale(testo, valori):
    rilevazioni = [Rilevazione(valore=v, categoria=c) for v, c in valori]
    tabella, _ = assegna_tag(rilevazioni, {}, {})
    mascherato = tagga(testo, tabella).mascherato
    assert ripristina(mascherato, dizionario_di(tabella)) == testo


@pytest.mark.parametrize("testo, valori", CASI)
def test_nessun_valore_applicato_sopravvive_nel_mascherato(testo, valori):
    """Il test anti-fuga della §14, nella forma che la §8 gli dà ora."""
    rilevazioni = [Rilevazione(valore=v, categoria=c) for v, c in valori]
    tabella, _ = assegna_tag(rilevazioni, {}, {})
    risultato = tagga(testo, tabella)
    taggati = {regione.tag for regione in risultato.regioni}
    for tag in tabella.values():
        if tag.tag in taggati:
            assert tag.valore not in risultato.mascherato
```

- [ ] **Step 2: Esegui il test e verifica che fallisca**

Run: `python -m pytest tests/test_round_trip.py -q`
Expected: FAIL con `ImportError: cannot import name 'dizionario_di'`.

- [ ] **Step 3: Aggiungi `dizionario_di` e cambia il parametro di `ripristina`**

In fondo a `cryptocustode/core/tagga.py`:

```python
def dizionario_di(tabella: dict[str, Tag]) -> dict[str, str]:
    """La mappa `tag → valore` che il ripristino consuma.

    Sta qui e non in `unmask.py` perché è una proiezione della tabella dei tag,
    e `unmask` non deve conoscere `Tag`: riceve un dizionario di stringhe, e
    così resta usabile anche quando la mappa arriva da un vault invece che da
    un fascicolo vivo.
    """
    return {tag.tag: tag.valore for tag in tabella.values()}
```

In `cryptocustode/core/unmask.py`, sostituisci l'import di `Entity` e il corpo che lo usa:

```python
# era: from cryptocustode.core.models import Entity
# (nessun import di modelli: questo modulo lavora su stringhe)
```

e dentro `ripristina` cambia la firma e la riga del dizionario:

```python
def ripristina(risposta: str, dizionario: dict[str, str]) -> str:
    """Sostituisce i segnaposto della risposta con i valori reali.

    `dizionario` è la mappa `tag → valore`, non più un dizionario di entità:
    questo modulo non ha bisogno di conoscere i tipi del dominio, e ricevendo
    stringhe resta identico sia che la mappa venga da un fascicolo vivo sia che
    venga da un vault riaperto (`core/tagga.dizionario_di`).

    Nessun ripristino parziale, in nessun caso: se anche un solo segnaposto è
    alterato o sconosciuto la funzione solleva e non restituisce nulla. Un
    testo in cui l'utente non sa quali segnaposto siano stati risolti e quali
    no è peggio di un errore (spec §11).
    """
    alterati = _alterazioni(risposta)
    if alterati:
        elenco = ", ".join(repr(frammento) for frammento in alterati)
        raise MalformedPlaceholder(
            f"segnaposto alterati, ripristino interrotto: {elenco}"
        )

    trovati = [trovato.group(0) for trovato in SEGNAPOSTO.finditer(risposta)]
    sconosciuti = sorted({t for t in trovati if t not in dizionario})
    ...
```

Il resto del corpo (la parte da `sconosciuti` in poi) resta identico: cambia solo che `dizionario` arriva per parametro invece di essere costruito dalle entità.

In `tests/test_unmask.py`, sostituisci ogni costruzione di `Entity` con il dizionario corrispondente. Esempio della trasformazione da applicare a tutti i casi:

```python
# prima
entities = {"e1": Entity(entity_id="e1", category=Category.PERSONA,
                         placeholder="[PERSONA_1]", canonical_value="Mario Rossi",
                         variants=set())}
assert ripristina("Caro [PERSONA_1],", entities) == "Caro Mario Rossi,"

# dopo
assert ripristina("Caro [PERSONA_1],", {"[PERSONA_1]": "Mario Rossi"}) == "Caro Mario Rossi,"
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `python -m pytest tests/test_round_trip.py tests/test_unmask.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cryptocustode/core/tagga.py cryptocustode/core/unmask.py tests/test_unmask.py tests/test_round_trip.py
git commit -m "feat: il ripristino lavora su un dizionario, e il round-trip e' un'identita'"
```

---

### Task 7: I quattro errori nuovi

**Files:**
- Modify: `cryptocustode/core/errors.py`
- Modify: `cryptocustode/api/app.py` (`STATO_HTTP`)
- Modify: `tests/test_errori.py`

**Interfaces:**
- Produces: `AIKeyMissing`, `AIUnavailable`, `AIResponseInvalid`, `VaultNotFound`, tutti sottoclassi di `CryptoCustodeError`.

- [ ] **Step 1: Insegna al test a leggere due spec**

`tests/test_errori.py` legge oggi la tabella della §13 dalla spec del 2026-09-10. La §12 della spec nuova ne aggiunge quattro righe e ne ritira una. Sostituisci le costanti e la funzione di lettura:

```python
SPEC_BASE = RADICE / "docs" / "superpowers" / "specs" / "2026-09-10-cryptocustode-design.md"
SPEC_IA = RADICE / "docs" / "superpowers" / "specs" / "2026-09-14-motore-ia-esporta-importa.md"

# La colonna cambia nome fra le due tabelle: la §13 dice "Errore nel core", la
# §12 dice "Errore". Si cerca per nome e non per posizione, perché riordinare
# le colonne è il modo più probabile in cui quelle tabelle verranno toccate.
TABELLE = ((SPEC_BASE, "13", "Errore nel core"), (SPEC_IA, "12", "Errore"))

RITIRATI = {"UnresolvedAmbiguities"}
"""Errori che la spec del 2026-09-14 §5 manda in pensione insieme al
sottosistema che li generava. Restano nominati dalla §13 della spec vecchia,
che resta in vigore per tutto il resto: senza questo insieme il test
pretenderebbe una classe che non deve più esistere."""
```

Cambia `_errori_dichiarati_dalla_spec()` perché prenda i tre parametri e la funzione che aggrega:

```python
def _errori_di_tabella(percorso: Path, sezione_numero: str, colonna: str) -> set[str]:
    """Le eccezioni nominate dalla tabella di una sezione di una spec."""
    testo = percorso.read_text(encoding="utf-8")
    sezione = re.search(
        rf"^## {sezione_numero}\..*?(?=^## |\Z)", testo, re.MULTILINE | re.DOTALL
    )
    assert sezione is not None, f"sezione §{sezione_numero} non trovata in {percorso}"
    # ...il resto del corpo attuale, invariato, con `colonna` al posto di
    # COLONNA_ERRORE...


def _errori_dichiarati_dalle_spec() -> set[str]:
    dichiarati: set[str] = set()
    for percorso, sezione, colonna in TABELLE:
        dichiarati |= _errori_di_tabella(percorso, sezione, colonna)
    return dichiarati - RITIRATI
```

Aggiorna tutte le chiamate nel file, incluso `test_la_tabella_della_spec_resta_leggibile`, che deve verificare che **entrambe** le tabelle si leggano:

```python
@pytest.mark.parametrize("percorso, sezione, colonna", TABELLE)
def test_la_tabella_della_spec_resta_leggibile(percorso, sezione, colonna):
    """Se un giorno una di queste tabelle cambia forma, questo test fallisce
    per primo e dice che è cambiato il documento, non il codice."""
    assert _errori_di_tabella(percorso, sezione, colonna)
```

- [ ] **Step 2: Esegui il test e verifica che fallisca**

Run: `python -m pytest tests/test_errori.py -q`
Expected: FAIL — la §12 dichiara quattro classi che `errors.py` non ha.

- [ ] **Step 3: Aggiungi le classi e le righe HTTP**

In fondo a `cryptocustode/core/errors.py`:

```python
class AIKeyMissing(CryptoCustodeError):
    """Chiave di Gemini assente, o piano non attestato come a pagamento.

    È un 503 e non un 500: non è un difetto del server, è una dipendenza non
    configurata, cioè un servizio indisponibile per una ragione che l'utente
    può rimuovere. Il messaggio deve dire come.

    L'attestazione del piano a pagamento è la decisione D8 della spec del
    2026-09-14: sul piano gratuito i termini di Gemini vietano l'invio di dati
    personali, e questa applicazione non manda altro.
    """


class AIUnavailable(CryptoCustodeError):
    """Gemini irraggiungibile, in timeout, o in errore di trasporto.

    Chi la solleva deve aver lasciato il fascicolo esattamente com'era: niente
    analisi parziale, niente tag a metà (spec §6).
    """


class AIResponseInvalid(CryptoCustodeError):
    """Risposta che lo schema non accetta, o categoria fuori dall'enum.

    È un 502 e non un 503 perché la reazione dell'utente è diversa: sul 503
    riprova, sul 502 riprova e, se si ripete, c'è qualcosa da segnalare.
    """


class VaultNotFound(CryptoCustodeError):
    """Nessun vault corrisponde al file che l'utente sta importando.

    Dichiarato qui in fase 1 benché lo sollevi solo la fase 3: la tabella degli
    errori è un contratto dell'applicazione, e il test di esaustività la
    pretende completa. Il repo lo fa già per le righe 409 dell'esportazione.
    """
```

In `cryptocustode/api/app.py`, aggiungi le quattro righe a `STATO_HTTP` e i quattro nomi all'import da `cryptocustode.core.errors`:

```python
    AIKeyMissing: 503,
    AIUnavailable: 503,
    AIResponseInvalid: 502,
    VaultNotFound: 404,
```

- [ ] **Step 4: Esegui la suite e verifica che passi**

Run: `python -m pytest tests/test_errori.py tests/test_caricamento.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cryptocustode/core/errors.py cryptocustode/api/app.py tests/test_errori.py
git commit -m "feat: i quattro errori dell'IA, e il test legge entrambe le spec"
```

---

### Task 8: Il prompt e lo schema

**Files:**
- Create: `cryptocustode/ai/__init__.py` (vuoto)
- Create: `cryptocustode/ai/prompt.py`
- Test: `tests/test_prompt.py`

**Interfaces:**
- Produces: `MODELLO: str`, `SCHEMA_RILEVAZIONI: dict`, `istruzioni() -> str` in `cryptocustode/ai/prompt.py`.

- [ ] **Step 1: Scrivi i test che falliscono**

Crea `tests/test_prompt.py`:

```python
"""Lo schema imposto a Gemini (spec §6)."""

from cryptocustode.ai.prompt import MODELLO, SCHEMA_RILEVAZIONI, istruzioni
from cryptocustode.core.models import Category


def test_il_modello_e_quello_della_spec():
    assert MODELLO == "gemini-3.8-flash"


def test_l_enum_dello_schema_copre_esattamente_le_categorie():
    """Se una categoria venisse aggiunta a `Category` senza entrare qui, il
    modello non potrebbe mai nominarla e nessuno se ne accorgerebbe."""
    ammesse = SCHEMA_RILEVAZIONI["items"]["properties"]["categoria"]["enum"]
    assert sorted(ammesse) == sorted(c.value for c in Category)


def test_lo_schema_pretende_entrambi_i_campi():
    assert sorted(SCHEMA_RILEVAZIONI["items"]["required"]) == ["categoria", "valore"]


def test_lo_schema_e_una_lista_di_oggetti():
    assert SCHEMA_RILEVAZIONI["type"] == "array"
    assert SCHEMA_RILEVAZIONI["items"]["type"] == "object"


def test_le_istruzioni_pretendono_la_sottostringa_letterale():
    """È il vincolo da cui dipende tutto il resto: senza, i valori tornano
    normalizzati, `tagga` non li trova e i dati restano in chiaro."""
    testo = istruzioni().lower()
    assert "letteral" in testo
    assert "non normalizzare" in testo


def test_le_istruzioni_elencano_le_categorie():
    testo = istruzioni()
    for categoria in Category:
        assert categoria.value in testo
```

- [ ] **Step 2: Esegui i test e verifica che falliscano**

Run: `python -m pytest tests/test_prompt.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'cryptocustode.ai'`.

- [ ] **Step 3: Scrivi il modulo**

Crea `cryptocustode/ai/__init__.py` vuoto, e `cryptocustode/ai/prompt.py`:

```python
"""Le istruzioni e lo schema con cui si interroga Gemini (spec §6).

Sta in `ai/` e non in `core/` perché è la forma di una richiesta a un
fornitore, non una regola del dominio: `core/` non deve sapere che esista un
prompt. Le categorie però vengono da `core/models.py`, perché una seconda
lista scritta a mano divergerebbe al primo cambiamento.
"""

from cryptocustode.core.models import Category

MODELLO = "gemini-3.8-flash"
"""Il Flash di punta, stabile, con structured output vincolato da JSON Schema."""

CATEGORIE = [categoria.value for categoria in Category]

SCHEMA_RILEVAZIONI: dict = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "valore": {"type": "string"},
            "categoria": {"type": "string", "enum": CATEGORIE},
        },
        "required": ["valore", "categoria"],
        "propertyOrdering": ["valore", "categoria"],
    },
}


def istruzioni() -> str:
    """Il testo di sistema, con il vincolo di letteralità in primo piano.

    Il vincolo non è una preferenza di stile: `tagga()` cerca ogni valore alla
    lettera nel documento, quindi un valore normalizzato non viene trovato e il
    dato resta in chiaro nel file esportato. La motivazione sta nel prompt e
    non solo qui, perché un modello che capisce *perché* una regola esiste la
    rispetta più spesso di uno che la legge come un capriccio.
    """
    elenco = "\n".join(f"- {categoria}" for categoria in CATEGORIE)
    return (
        "Sei un revisore che individua i dati personali in documenti italiani.\n"
        "Elenca ogni dato personale presente nel testo che ti viene dato.\n\n"
        "REGOLA PIÙ IMPORTANTE: ogni `valore` che restituisci deve essere una "
        "sottostringa letterale del documento, copiata carattere per carattere "
        "esattamente come vi compare. Non normalizzare, non correggere, non "
        "riordinare, non aggiungere né togliere titoli, non cambiare "
        "maiuscole, spaziatura o punteggiatura.\n"
        "Il motivo: chi riceve la tua risposta cerca quella stringa nel "
        "documento per sostituirla. Se la stringa non combacia, il dato "
        "personale resta visibile.\n\n"
        "Esempio: se il documento scrive `ROSSI Mario`, rispondi `ROSSI Mario` "
        "e non `Mario Rossi`.\n\n"
        "Se lo stesso dato compare più volte, elencalo una volta sola.\n"
        "Se non trovi nessun dato personale, restituisci una lista vuota.\n\n"
        f"Categorie ammesse:\n{elenco}\n"
    )
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `python -m pytest tests/test_prompt.py -q`
Expected: PASS, 6 test.

- [ ] **Step 5: Commit**

```bash
git add cryptocustode/ai/__init__.py cryptocustode/ai/prompt.py tests/test_prompt.py
git commit -m "feat: lo schema e il prompt, col vincolo di letteralita' motivato"
```

---

### Task 9: Il client Gemini

Il client si testa senza rete perché la chiamata vera è un parametro: il test inietta una funzione che restituisce una stringa JSON, la produzione inietta quella che parla con `google.genai`.

**Files:**
- Create: `cryptocustode/ai/gemini.py`
- Test: `tests/test_gemini.py`
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: `Rilevazione`, `Category`; `MODELLO`, `SCHEMA_RILEVAZIONI`, `istruzioni` dal task 8; `AIKeyMissing`, `AIUnavailable`, `AIResponseInvalid` dal task 7.
- Produces: `RilevatoreGemini(chiave: str | None = None, modello: str = MODELLO, chiama: Chiamata | None = None)` con `rileva(testo) -> list[Rilevazione]`, dove `Chiamata = Callable[[str, str, str, dict], str]` riceve `(modello, istruzioni, testo, schema)` e restituisce il JSON grezzo.

- [ ] **Step 1: Scrivi i test che falliscono**

Crea `tests/test_gemini.py`:

```python
"""Il client Gemini, provato senza toccare la rete (spec §4, invariante 5)."""

import json

import pytest

from cryptocustode.ai.gemini import RilevatoreGemini
from cryptocustode.core.errors import AIKeyMissing, AIResponseInvalid, AIUnavailable
from cryptocustode.core.models import Category, Rilevazione
from cryptocustode.core.rilevatore import Rilevatore


def _chiamata(risposta: str):
    """Una `Chiamata` che restituisce sempre lo stesso JSON grezzo."""
    def chiama(modello, istruzioni, testo, schema):
        return risposta
    return chiama


def _rilevatore(risposta: str) -> RilevatoreGemini:
    return RilevatoreGemini(chiave="finta", chiama=_chiamata(risposta))


def test_soddisfa_il_protocollo():
    assert isinstance(_rilevatore("[]"), Rilevatore)


def test_traduce_la_risposta_in_rilevazioni():
    risposta = json.dumps(
        [{"valore": "Mario Rossi", "categoria": "PERSONA"},
         {"valore": "ACME s.r.l.", "categoria": "AZIENDA"}]
    )
    assert _rilevatore(risposta).rileva("qualunque") == [
        Rilevazione(valore="Mario Rossi", categoria=Category.PERSONA),
        Rilevazione(valore="ACME s.r.l.", categoria=Category.AZIENDA),
    ]


def test_una_lista_vuota_e_una_risposta_legittima():
    assert _rilevatore("[]").rileva("niente di personale") == []


def test_senza_chiave_solleva_prima_di_chiamare():
    """Il controllo precede la chiamata: chiedere a Gemini per poi scoprire che
    manca la chiave manderebbe il documento in rete per niente."""
    chiamate = []

    def chiama(modello, istruzioni, testo, schema):
        chiamate.append(testo)
        return "[]"

    with pytest.raises(AIKeyMissing):
        RilevatoreGemini(chiave=None, chiama=chiama).rileva("Mario Rossi")
    assert chiamate == []


def test_un_errore_di_trasporto_diventa_AIUnavailable():
    def chiama(modello, istruzioni, testo, schema):
        raise TimeoutError("connessione scaduta")

    with pytest.raises(AIUnavailable):
        RilevatoreGemini(chiave="finta", chiama=chiama).rileva("Mario Rossi")


def test_json_malformato_diventa_AIResponseInvalid():
    with pytest.raises(AIResponseInvalid):
        _rilevatore("non sono json").rileva("Mario Rossi")


def test_una_risposta_che_non_e_una_lista_diventa_AIResponseInvalid():
    with pytest.raises(AIResponseInvalid):
        _rilevatore('{"valore": "Mario Rossi"}').rileva("Mario Rossi")


def test_una_categoria_inventata_diventa_AIResponseInvalid():
    """`PERSONE` non è un valore di `Category`: lo schema dovrebbe averlo
    impedito, ma lo schema è una richiesta al fornitore, non una garanzia."""
    risposta = json.dumps([{"valore": "Mario Rossi", "categoria": "PERSONE"}])
    with pytest.raises(AIResponseInvalid):
        _rilevatore(risposta).rileva("Mario Rossi")


def test_una_voce_senza_valore_diventa_AIResponseInvalid():
    with pytest.raises(AIResponseInvalid):
        _rilevatore(json.dumps([{"categoria": "PERSONA"}])).rileva("Mario Rossi")


def test_un_valore_non_stringa_diventa_AIResponseInvalid():
    risposta = json.dumps([{"valore": 42, "categoria": "PERSONA"}])
    with pytest.raises(AIResponseInvalid):
        _rilevatore(risposta).rileva("Mario Rossi")


def test_passa_al_fornitore_modello_istruzioni_e_schema():
    visti = {}

    def chiama(modello, istruzioni, testo, schema):
        visti.update(modello=modello, istruzioni=istruzioni, testo=testo, schema=schema)
        return "[]"

    RilevatoreGemini(chiave="finta", chiama=chiama).rileva("Mario Rossi paga.")
    assert visti["modello"] == "gemini-3.8-flash"
    assert visti["testo"] == "Mario Rossi paga."
    assert "letteral" in visti["istruzioni"].lower()
    assert visti["schema"]["type"] == "array"
```

- [ ] **Step 2: Esegui i test e verifica che falliscano**

Run: `python -m pytest tests/test_gemini.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'cryptocustode.ai.gemini'`.

- [ ] **Step 3: Scrivi il client**

Crea `cryptocustode/ai/gemini.py`:

```python
"""L'unico punto dell'applicazione che parla con la rete (spec §4).

La chiamata vera è un **parametro**, non un import nascosto nel corpo: il test
inietta una funzione che restituisce una stringa, la produzione inietta quella
che costruisce il client di `google.genai`. Non serve una libreria di mock, e
soprattutto nessun test della suite predefinita può finire in rete per
distrazione — l'invariante 5 della §4 diventa una proprietà della struttura
invece di una promessa.
"""

import json
import os
from typing import Callable

from cryptocustode.ai.prompt import MODELLO, SCHEMA_RILEVAZIONI, istruzioni
from cryptocustode.core.errors import (
    AIKeyMissing,
    AIResponseInvalid,
    AIUnavailable,
)
from cryptocustode.core.models import Category, Rilevazione

VARIABILE_CHIAVE = "CRYPTOCUSTODE_GEMINI_API_KEY"

Chiamata = Callable[[str, str, str, dict], str]
"""`(modello, istruzioni, testo, schema) -> JSON grezzo`."""


def chiamata_reale(modello: str, sistema: str, testo: str, schema: dict) -> str:
    """La chiamata di produzione. Importa `google.genai` qui dentro e non in
    testa al modulo, così chi costruisce un `RilevatoreGemini` con una
    `chiama` propria — cioè ogni test — non ha bisogno che l'SDK sia
    installato."""
    from google import genai
    from google.genai import types

    cliente = genai.Client(api_key=os.environ[VARIABILE_CHIAVE])
    risposta = cliente.models.generate_content(
        model=modello,
        contents=testo,
        config=types.GenerateContentConfig(
            system_instruction=sistema,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0,
        ),
    )
    return risposta.text


class RilevatoreGemini:
    """Il `Rilevatore` di produzione (spec §6)."""

    def __init__(
        self,
        chiave: str | None = None,
        modello: str = MODELLO,
        chiama: Chiamata | None = None,
    ) -> None:
        self._chiave = chiave if chiave is not None else os.environ.get(VARIABILE_CHIAVE)
        self._modello = modello
        self._chiama = chiama if chiama is not None else chiamata_reale

    def rileva(self, testo: str) -> list[Rilevazione]:
        """Le rilevazioni di Gemini su questo testo.

        Il controllo sulla chiave precede la chiamata: scoprire che manca dopo
        aver spedito significherebbe aver mandato il documento in rete per
        niente.
        """
        if not self._chiave:
            raise AIKeyMissing(
                f"la variabile d'ambiente {VARIABILE_CHIAVE} non è impostata: "
                "senza chiave di Gemini l'analisi non può partire. La chiave "
                "deve appartenere a un progetto con fatturazione attiva, "
                "perché sul piano gratuito i termini di Gemini vietano l'invio "
                "di dati personali."
            )
        try:
            grezza = self._chiama(
                self._modello, istruzioni(), testo, SCHEMA_RILEVAZIONI
            )
        except Exception as errore:
            raise AIUnavailable(
                "il servizio di analisi non è raggiungibile, il fascicolo è "
                f"intatto: riprova. Dettaglio: {errore}"
            ) from errore
        return _traduci(grezza)


def _traduci(grezza: str) -> list[Rilevazione]:
    """Dal JSON grezzo alle rilevazioni, rifiutando tutto ciò che non torna.

    Lo schema è una *richiesta* al fornitore, non una garanzia: se la risposta
    lo viola, accettarla significherebbe far entrare nel fascicolo una
    categoria che non esiste, o un valore che non è una stringa, e scoprirlo
    più tardi sotto forma di eccezione in un punto che non c'entra.
    """
    try:
        dati = json.loads(grezza)
    except (json.JSONDecodeError, TypeError) as errore:
        raise AIResponseInvalid(
            "il modello ha risposto in un formato non valido, il fascicolo è "
            f"intatto: {errore}"
        ) from errore

    if not isinstance(dati, list):
        raise AIResponseInvalid(
            "il modello doveva rispondere con una lista di rilevazioni e ha "
            f"risposto con {type(dati).__name__}, il fascicolo è intatto"
        )

    rilevazioni: list[Rilevazione] = []
    for indice, voce in enumerate(dati):
        if not isinstance(voce, dict):
            raise AIResponseInvalid(
                f"la voce {indice} della risposta non è un oggetto, il "
                "fascicolo è intatto"
            )
        valore = voce.get("valore")
        categoria = voce.get("categoria")
        if not isinstance(valore, str) or not isinstance(categoria, str):
            raise AIResponseInvalid(
                f"la voce {indice} della risposta non ha `valore` e "
                "`categoria` come stringhe, il fascicolo è intatto"
            )
        try:
            rilevazioni.append(
                Rilevazione(valore=valore, categoria=Category(categoria))
            )
        except ValueError as errore:
            raise AIResponseInvalid(
                f"la voce {indice} della risposta dichiara la categoria "
                f"{categoria!r}, che non esiste: il fascicolo è intatto"
            ) from errore
    return rilevazioni
```

In `requirements.txt`, aggiungi sotto `python-multipart`:

```
google-genai==1.52.0
```

(Verifica la versione disponibile con `pip index versions google-genai` e pinna quella, come fa il resto del file.)

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `python -m pytest tests/test_gemini.py -q`
Expected: PASS, 11 test.

- [ ] **Step 5: Commit**

```bash
git add cryptocustode/ai/gemini.py tests/test_gemini.py requirements.txt
git commit -m "feat: il client Gemini, con la chiamata iniettata invece che importata"
```

---

### Task 10: `mask.py` e `session.py` sui tag

**Files:**
- Modify: `cryptocustode/core/mask.py`
- Modify: `cryptocustode/state/session.py`
- Modify: `tests/test_mask.py`, `tests/test_session.py`

**Interfaces:**
- Consumes: `tagga`, `conta_occorrenze` dai task 4-5.
- Produces: `tabella_attiva(fascicolo) -> dict[str, Tag]`, `maschera_documento(fascicolo, documento) -> str`, `hash_approvazione(fascicolo) -> str` in `core/mask.py`. `analisi_completata(fascicolo)` non popola più code; `approva(fascicolo)` non ha più ambiguità da controllare.

- [ ] **Step 1: Scrivi i test che falliscono**

Sostituisci il contenuto di `tests/test_mask.py` con test costruiti sui tag (i vecchi, basati su `Span` ed `Entity`, vanno rimossi in questo stesso passo):

```python
"""Mascheratura di un documento del fascicolo e hash di approvazione (spec §9)."""

from dataclasses import replace

from cryptocustode.core.mask import hash_approvazione, maschera_documento, tabella_attiva
from cryptocustode.core.models import Category, Document, Rilevazione, StatoTag, fascicolo_vuoto
from cryptocustode.core.tagga import assegna_tag


def _documento(doc_id: str, filename: str, testo: str) -> Document:
    return Document(
        doc_id=doc_id, filename=filename, text=testo, page_offsets=[0], sha256="x"
    )


def _fascicolo(testo="Il sig. Mario Rossi paga.", valori=(("Mario Rossi", Category.PERSONA),)):
    fascicolo = fascicolo_vuoto("f1")
    fascicolo.documents.append(_documento("d1", "a.txt", testo))
    rilevazioni = [Rilevazione(valore=v, categoria=c) for v, c in valori]
    fascicolo.tags, fascicolo.counters = assegna_tag(
        rilevazioni, fascicolo.tags, fascicolo.counters
    )
    return fascicolo


def test_maschera_il_documento():
    fascicolo = _fascicolo()
    assert maschera_documento(fascicolo, fascicolo.documents[0]) == (
        "Il sig. [PERSONA_1] paga."
    )


def test_un_tag_spento_lascia_il_dato_in_chiaro():
    fascicolo = _fascicolo()
    fascicolo.tags["[PERSONA_1]"] = replace(
        fascicolo.tags["[PERSONA_1]"], stato=StatoTag.DISATTIVATO
    )
    assert maschera_documento(fascicolo, fascicolo.documents[0]) == (
        "Il sig. Mario Rossi paga."
    )


def test_una_categoria_spenta_lascia_il_dato_in_chiaro():
    fascicolo = _fascicolo()
    fascicolo.category_enabled[Category.PERSONA] = False
    assert maschera_documento(fascicolo, fascicolo.documents[0]) == (
        "Il sig. Mario Rossi paga."
    )


def test_i_due_interruttori_sono_indipendenti():
    """Riaccendere la categoria non riaccende i tag spenti a mano: le due
    decisioni si leggono in `and`, come `span_attivo` faceva prima (spec §5)."""
    fascicolo = _fascicolo()
    fascicolo.tags["[PERSONA_1]"] = replace(
        fascicolo.tags["[PERSONA_1]"], stato=StatoTag.DISATTIVATO
    )
    fascicolo.category_enabled[Category.PERSONA] = False
    fascicolo.category_enabled[Category.PERSONA] = True
    assert "[PERSONA_1]" not in tabella_attiva(fascicolo)


def test_l_hash_e_deterministico():
    assert hash_approvazione(_fascicolo()) == hash_approvazione(_fascicolo())


def test_l_hash_cambia_se_cambia_il_mascherato():
    prima = hash_approvazione(_fascicolo())
    dopo_fascicolo = _fascicolo()
    dopo_fascicolo.category_enabled[Category.PERSONA] = False
    assert hash_approvazione(dopo_fascicolo) != prima
```

In `tests/test_session.py`, rimuovi i test che costruiscono ambiguità (`TestApprovaConAmbiguita` o equivalenti) e aggiungi:

```python
def test_approva_senza_ambiguita_da_controllare():
    """La coda delle ambiguità non esiste più: con il contratto B due
    occorrenze della stessa stringa sono lo stesso tag per costruzione, quindi
    non c'è più un momento in cui due entità distinte esistano (spec §5)."""
    fascicolo = _fascicolo_analizzato()
    approva(fascicolo)
    assert fascicolo.state is State.APPROVED
    assert fascicolo.approval_hash is not None
```

- [ ] **Step 2: Esegui i test e verifica che falliscano**

Run: `python -m pytest tests/test_mask.py tests/test_session.py -q`
Expected: FAIL con `ImportError: cannot import name 'tabella_attiva'`.

- [ ] **Step 3: Riscrivi `mask.py` e sfoltisci `session.py`**

Sostituisci il corpo di `cryptocustode/core/mask.py` (docstring del modulo invariata) con:

```python
import hashlib

from cryptocustode.core.models import Document, Fascicolo, StatoTag, Tag
from cryptocustode.core.tagga import tagga


def tabella_attiva(fascicolo: Fascicolo) -> dict[str, Tag]:
    """I tag che verranno davvero sostituiti.

    Due interruttori indipendenti, letti in `and`: lo stato del singolo tag e
    quello della sua categoria (spec §5 del 2026-09-10). Tenerli distinti dà
    una risposta ovvia alla domanda "spengo la categoria e poi la riaccendo:
    che fine fanno i tag che avevo spento a mano?" — restano spenti.

    È l'erede di `span_attivo`, e vive qui per la stessa ragione per cui
    viveva qui quello: chiunque debba sapere se un dato esce in chiaro deve
    leggerlo da un posto solo, altrimenti la UI mostra acceso ciò che
    l'esportazione lascia spento.
    """
    return {
        chiave: tag
        for chiave, tag in fascicolo.tags.items()
        if tag.stato is not StatoTag.DISATTIVATO
        and fascicolo.category_enabled.get(tag.categoria, True)
    }


def maschera_documento(fascicolo: Fascicolo, documento: Document) -> str:
    return tagga(documento.text, tabella_attiva(fascicolo)).mascherato


def hash_approvazione(fascicolo: Fascicolo) -> str:
    """SHA-256 su una serializzazione canonica dei testi mascherati.

    I documenti sono ordinati per nome file e ciascuno emette
    `filename\\n<lunghezza>\\n<testo>`. La lunghezza esplicita rende la
    concatenazione non ambigua, così due fascicoli diversi non possono
    produrre lo stesso digest (spec §8 del 2026-09-10).
    """
    digest = hashlib.sha256()
    for documento in sorted(fascicolo.documents, key=lambda d: (d.filename, d.doc_id)):
        mascherato = maschera_documento(fascicolo, documento)
        blocco = f"{documento.filename}\n{len(mascherato)}\n{mascherato}"
        digest.update(blocco.encode("utf-8"))
    return digest.hexdigest()
```

In `cryptocustode/state/session.py`: togli l'import di `cryptocustode.core.entities` e quello di `UnresolvedAmbiguities`, e riscrivi le due funzioni:

```python
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
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `python -m pytest tests/test_mask.py tests/test_session.py tests/test_export.py -q`
Expected: PASS. `test_export.py` va adattato allo stesso modo se costruisce fascicoli con `Span`/`Entity`: sostituisci quelle costruzioni con `assegna_tag`, come in `_fascicolo()` qui sopra.

- [ ] **Step 5: Commit**

```bash
git add cryptocustode/core/mask.py cryptocustode/state/session.py tests/test_mask.py tests/test_session.py tests/test_export.py
git commit -m "feat: la mascheratura legge la tabella dei tag, e le ambiguita' non bloccano piu'"
```

---

### Task 11: Il vault versione 3

Il payload cifrato contiene oggi `spans`, `entities` e `ambiguities`, tre campi che il task 13 cancella.

**Files:**
- Modify: `cryptocustode/core/vault.py`
- Modify: `tests/test_vault.py`

**Interfaces:**
- Produces: `VAULT_VERSION = 3`; il payload serializza `tags` (lista di oggetti `{tag, categoria, valore, occorrenze, stato}`) e `analizzati` al posto di `spans`, `entities`, `ambiguities`.

- [ ] **Step 1: Scrivi i test che falliscono**

In `tests/test_vault.py`, sostituisci le costruzioni di `Span`/`Entity`/`Ambiguity` con la tabella dei tag e aggiungi:

```python
def test_il_round_trip_conserva_la_tabella_dei_tag():
    fascicolo = fascicolo_vuoto("f1")
    fascicolo.tags, fascicolo.counters = assegna_tag(
        [Rilevazione(valore="Mario Rossi", categoria=Category.PERSONA)],
        fascicolo.tags,
        fascicolo.counters,
    )
    fascicolo.analizzati.add("d1")
    riletto = carica(salva(fascicolo, "password lunga"), "password lunga")
    assert riletto.tags == fascicolo.tags
    assert riletto.counters == fascicolo.counters
    assert riletto.analizzati == {"d1"}


def test_un_vault_di_formato_precedente_non_e_leggibile():
    """La §10 del 2026-09-10 prometteva che un formato più vecchio restasse
    leggibile. La promessa cade qui, ed è una rottura deliberata: leggere un
    vault v2 richiederebbe di tenere in vita `Span`, `Entity` e `Ambiguity`
    solo per tradurli, e non esiste alcun vault v2 reale — l'esportazione che
    li avrebbe scritti arriva in fase 2. Il messaggio lo dice all'utente invece
    di fallire con una diagnosi incomprensibile."""
    with pytest.raises(VaultVersionNotSupported):
        _verifica_versione(2)
```

- [ ] **Step 2: Esegui i test e verifica che falliscano**

Run: `python -m pytest tests/test_vault.py -q`
Expected: FAIL.

- [ ] **Step 3: Porta il vault alla versione 3**

In `cryptocustode/core/vault.py`: porta `VAULT_VERSION` a `3`; sostituisci nell'import `Ambiguity`, `AmbiguityKind`, `Entity`, `Span` con `StatoTag`, `Tag`.

In `_a_dizionario`, sostituisci i tre blocchi `spans`, `entities`, `ambiguities` con:

```python
        "tags": [
            {
                "tag": t.tag,
                "categoria": t.categoria.value,
                "valore": t.valore,
                "occorrenze": t.occorrenze,
                "stato": t.stato.value,
            }
            for t in fascicolo.tags.values()
        ],
        "analizzati": sorted(fascicolo.analizzati),
```

In `_da_dizionario`, gli stessi tre blocchi diventano:

```python
        tags={
            t["tag"]: Tag(
                tag=t["tag"],
                categoria=Category(t["categoria"]),
                valore=t["valore"],
                occorrenze=t["occorrenze"],
                stato=StatoTag(t["stato"]),
            )
            for t in dati["tags"]
        },
        analizzati=set(dati["analizzati"]),
```

In `_verifica_versione`, aggiungi il rifiuto all'indietro accanto a quello in avanti che c'è già:

```python
    if versione < VAULT_VERSION:
        raise VaultVersionNotSupported(
            f"questo vault è in formato {versione} e CryptoCustode legge solo "
            f"il formato {VAULT_VERSION}: il formato è cambiato quando il "
            "motore è passato all'IA, e i fascicoli vecchi vanno rianalizzati."
        )
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `python -m pytest tests/test_vault.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cryptocustode/core/vault.py tests/test_vault.py
git commit -m "feat: il vault v3 cifra la tabella dei tag, e non legge piu' il v2"
```

---

### Task 12: Le route, l'iniezione del rilevatore e la UI

**Files:**
- Modify: `cryptocustode/api/routes_fascicolo.py`
- Modify: `cryptocustode/api/app.py`
- Modify: `cryptocustode/ui/app.js`, `cryptocustode/ui/index.html`
- Modify: `tests/test_app.py`, `tests/test_revisione.py`, `tests/ui_harness.mjs`

**Interfaces:**
- Consumes: tutto ciò che precede.
- Produces: `crea_router(store, rilevatore)`, `crea_app(..., rilevatore: Rilevatore | None = None)`. Route `POST /api/fascicolo/tag` con corpo `{"tag": str, "attivo": bool}` al posto di `POST /api/fascicolo/span`. Nel payload di revisione ogni segmento porta `tag` al posto di `span_id`, e la chiave `ambiguita` sparisce.

- [ ] **Step 1: Scrivi i test che falliscono**

In `tests/test_revisione.py`, adatta i test esistenti alla nuova forma e aggiungi:

```python
def test_l_analisi_usa_il_rilevatore_iniettato(client_con_rilevatore):
    client, finto = client_con_rilevatore(
        sempre=[Rilevazione(valore="Mario Rossi", categoria=Category.PERSONA)]
    )
    client.post("/api/fascicolo/documenti", files=_file("a.txt", "Mario Rossi paga."))
    revisione = client.post("/api/fascicolo/analisi").json()
    segmenti = revisione["documenti"][0]["segmenti"]
    assert [s["testo"] for s in segmenti] == ["Mario Rossi", " paga."]
    assert segmenti[0]["tag"] == "[PERSONA_1]"
    assert segmenti[0]["mascherato"] is True


def test_un_documento_gia_analizzato_non_ripaga_una_chiamata(client_con_rilevatore):
    """Ogni chiamata costa e manda il documento in rete: rianalizzare ciò che
    si è già analizzato è una spesa e un'esposizione senza contropartita."""
    client, finto = client_con_rilevatore(sempre=[])
    client.post("/api/fascicolo/documenti", files=_file("a.txt", "Mario Rossi paga."))
    client.post("/api/fascicolo/analisi")
    client.post("/api/fascicolo/analisi")
    assert finto.chiamate == ["Mario Rossi paga."]


def test_spegnere_un_tag_lo_lascia_in_chiaro(client_con_rilevatore):
    client, _ = client_con_rilevatore(
        sempre=[Rilevazione(valore="Mario Rossi", categoria=Category.PERSONA)]
    )
    client.post("/api/fascicolo/documenti", files=_file("a.txt", "Mario Rossi paga."))
    client.post("/api/fascicolo/analisi")
    revisione = client.post(
        "/api/fascicolo/tag", json={"tag": "[PERSONA_1]", "attivo": False}
    ).json()
    assert revisione["documenti"][0]["segmenti"][0]["mascherato"] is False


def test_un_tag_inesistente_e_un_404(client_con_rilevatore):
    client, _ = client_con_rilevatore(sempre=[])
    client.post("/api/fascicolo/documenti", files=_file("a.txt", "niente."))
    client.post("/api/fascicolo/analisi")
    risposta = client.post(
        "/api/fascicolo/tag", json={"tag": "[PERSONA_99]", "attivo": False}
    )
    assert risposta.status_code == 404


def test_la_revisione_non_parla_piu_di_ambiguita(client_con_rilevatore):
    client, _ = client_con_rilevatore(sempre=[])
    client.post("/api/fascicolo/documenti", files=_file("a.txt", "niente."))
    assert "ambiguita" not in client.post("/api/fascicolo/analisi").json()
```

Il repo non ha un `tests/conftest.py`: le fixture `store` e `client` vivono in `tests/test_revisione.py` (righe 56-97). La nuova fixture va lí accanto, e deve passare `base_url=INDIRIZZO_DI_PROVA` come fa `client`, altrimenti il middleware del tetto risponde 400 a ogni richiesta:

```python
@pytest.fixture
def client_con_rilevatore(store):
    """Un `TestClient` e il `RilevatoreFinto` che l'app userà.

    Il rilevatore arriva per parametro come già fa lo store: costruirlo dentro
    `crea_app` significherebbe che ogni test fa partire il client Gemini vero,
    cioè che la suite tocca la rete (spec §4, invariante 5).

    Restituisce una funzione e non una coppia già fatta perché ogni test ha
    bisogno di un doppio programmato diversamente: una fixture che decidesse
    lei le rilevazioni costringerebbe i test ad accettare le sue.
    """
    def costruisci(**kwargs):
        finto = RilevatoreFinto(**kwargs)
        app = crea_app(store=store, rilevatore=finto)
        return TestClient(app, base_url=INDIRIZZO_DI_PROVA), finto

    return costruisci
```

I test che la usano vanno scritti con il `with`, come fa la fixture `client` esistente, oppure la funzione `costruisci` va avvolta in un `contextlib.ExitStack` della fixture: senza entrare nel contesto, il `lifespan` dell'app non parte.

- [ ] **Step 2: Esegui i test e verifica che falliscano**

Run: `python -m pytest tests/test_revisione.py -q`
Expected: FAIL — `crea_app()` non accetta `rilevatore`.

- [ ] **Step 3: Ricabla le route**

In `cryptocustode/api/routes_fascicolo.py`: togli l'import di `analizza_documento` e di `span_attivo`, aggiungi

```python
from cryptocustode.core.mask import tabella_attiva
from cryptocustode.core.rilevatore import Rilevatore
from cryptocustode.core.tagga import assegna_tag, conta_occorrenze, tagga
```

Sostituisci `segmenti_di`:

```python
def segmenti_di(fascicolo: Fascicolo, documento: Document) -> list[dict]:
    """Il testo originale spezzato sulle regioni che la mascheratura rivendica.

    Le regioni si calcolano sulla tabella **intera** e non su quella attiva,
    perché la pagina deve mostrare anche i tag spenti — spenti, ma visibili,
    altrimenti l'utente non avrebbe modo di riaccenderli. Quale sia acceso lo
    dice `tabella_attiva`, letta da un posto solo così la pagina non può
    mostrare acceso un dato che l'esportazione lascia in chiaro.
    """
    attivi = tabella_attiva(fascicolo)
    regioni = tagga(documento.text, fascicolo.tags).regioni
    segmenti: list[dict] = []
    cursore = 0
    for regione in regioni:
        if regione.start > cursore:
            segmenti.append(_segmento_nudo(documento.text[cursore:regione.start]))
        tag = fascicolo.tags[regione.tag]
        segmenti.append(
            {
                "testo": documento.text[regione.start:regione.end],
                "tag": tag.tag,
                "categoria": tag.categoria.value,
                "mascherato": tag.tag in attivi,
                "segnaposto": tag.tag,
            }
        )
        cursore = regione.end
    if cursore < len(documento.text):
        segmenti.append(_segmento_nudo(documento.text[cursore:]))
    return segmenti


def _segmento_nudo(testo: str) -> dict:
    return {
        "testo": testo,
        "tag": None,
        "categoria": None,
        "mascherato": False,
        "segnaposto": None,
    }
```

In `revisione()`, conta le categorie dai tag e togli la chiave `ambiguita`:

```python
    quanti: dict[Category, int] = {}
    for tag in fascicolo.tags.values():
        quanti[tag.categoria] = quanti.get(tag.categoria, 0) + 1
```

`crea_router` prende il rilevatore, e `analizza` lo usa:

```python
def crea_router(store: SessionStore, rilevatore: Rilevatore) -> APIRouter:
    ...
    @router.post("/analisi", response_model=None)
    async def analizza() -> dict | JSONResponse:
        """Fa rilevare i dati sensibili e chiude l'analisi.

        Rieseguibile, come prima: chi aggiunge un documento dopo una prima
        analisi ripreme lo stesso bottone. I documenti già passati dal
        rilevatore vengono saltati, e qui la ragione è più forte di prima —
        ogni chiamata costa e manda il documento in rete.

        Se il rilevatore solleva, il fascicolo resta esattamente com'era:
        `assegna_tag` non muta i suoi argomenti, e la scrittura avviene solo
        dopo che tutte le chiamate sono andate a buon fine (spec §6).
        """
        fascicolo = fascicolo_attivo(store)
        if not fascicolo.documents:
            return JSONResponse(
                status_code=422,
                content={"errore": "non c'è nessun documento da analizzare: "
                                   "caricane almeno uno"},
            )
        da_analizzare = [
            d for d in fascicolo.documents if d.doc_id not in fascicolo.analizzati
        ]
        rilevazioni = []
        for documento in da_analizzare:
            rilevazioni.extend(rilevatore.rileva(documento.text))

        tabella, contatori = assegna_tag(
            rilevazioni, fascicolo.tags, fascicolo.counters
        )
        mascherature = [tagga(d.text, tabella) for d in fascicolo.documents]
        fascicolo.tags = conta_occorrenze(tabella, mascherature)
        fascicolo.counters = contatori
        fascicolo.analizzati.update(d.doc_id for d in da_analizzare)
        analisi_completata(fascicolo)
        return revisione(fascicolo)
```

Sostituisci il modello e la route degli span:

```python
class ToggleTag(BaseModel):
    tag: str
    attivo: bool


    @router.post("/tag", response_model=None)
    async def cambia_tag(comando: ToggleTag) -> dict | JSONResponse:
        """Accende o spegne il mascheramento di un dato.

        Un tag che non esiste è un 404 e non un 200 silenzioso: senza il
        controllo la route non muterebbe niente e risponderebbe come se avesse
        funzionato, e la pagina continuerebbe a mostrare acceso un tag che
        l'utente crede di aver spento — cioè un dato che esce in chiaro contro
        la sua volontà esplicita.
        """
        fascicolo = fascicolo_attivo(store)
        tag = fascicolo.tags.get(comando.tag)
        if tag is None:
            return JSONResponse(
                status_code=404,
                content={"errore": f"nessun tag {comando.tag!r} nel fascicolo: "
                                   "ricarica la revisione"},
            )
        nuovo_stato = (
            StatoTag.APPLICATO if comando.attivo else StatoTag.DISATTIVATO
        )
        fascicolo.tags[comando.tag] = replace(tag, stato=nuovo_stato)
        return revisione(fascicolo)
```

In `cryptocustode/api/app.py`, `crea_app` prende il rilevatore e lo passa al router:

```python
def crea_app(
    *,
    al_pronto: AlPronto | None = None,
    store: SessionStore | None = None,
    rilevatore: Rilevatore | None = None,
    tetto_richiesta: int = TETTO_RICHIESTA,
) -> FastAPI:
    ...
    app.include_router(crea_router(store, rilevatore or RilevatoreGemini()))
```

`RilevatoreGemini()` costruito qui non chiama nessuno: la chiave si legge alla
prima `rileva`, quindi costruire l'app senza chiave resta possibile e i test
che non analizzano non ne hanno bisogno.

In `avvia()`, prima di aprire la porta, il controllo della decisione D8:

```python
PIANO_ATTESTATO = "CRYPTOCUSTODE_GEMINI_PIANO"


def verifica_configurazione_ia(ambiente: dict[str, str]) -> None:
    """Rifiuta l'avvio se la chiave manca o il piano non è attestato (D8).

    L'attestazione è una dichiarazione dell'utente, non una verifica: l'API non
    espone il piano di fatturazione, quindi l'applicazione non ha modo di
    controllarlo. Serve comunque, e non è teatro: costringe chi avvia a leggere
    perché il piano gratuito non va bene, prima che il primo documento parta.
    """
    if not ambiente.get(VARIABILE_CHIAVE):
        raise SystemExit(
            f"{VARIABILE_CHIAVE} non è impostata. CryptoCustode manda i tuoi "
            "documenti a Gemini per farli analizzare: senza chiave non può "
            "partire."
        )
    if ambiente.get(PIANO_ATTESTATO) != "pagamento":
        raise SystemExit(
            f"Imposta {PIANO_ATTESTATO}=pagamento per confermare che la chiave "
            "appartiene a un progetto con fatturazione attiva.\n"
            "Sul piano gratuito i termini di Gemini dicono di non inviare dati "
            "personali, e Google usa i contenuti per sviluppare i propri "
            "prodotti: CryptoCustode non invia altro che documenti con dati "
            "personali dentro."
        )
```

- [ ] **Step 4: Adatta la UI e i suoi test**

In `cryptocustode/ui/app.js`: `ROTTA_SPAN` diventa `ROTTA_TAG = "/api/fascicolo/tag"`; `segmento.span_id` diventa `segmento.tag`; `pezzo.dataset.spanId` diventa `pezzo.dataset.tag`; il corpo inviato diventa `{ tag, attivo }`; togli il blocco che legge `revisione.ambiguita` (intorno alla riga 321) e l'elemento corrispondente in `index.html`.

In `tests/ui_harness.mjs`: togli `ambiguita` dal payload di prova, e rinomina `span_id` in `tag` e `SPAN_PERSONA`/`SPAN_IMPORTO` in `TAG_PERSONA = "[PERSONA_1]"` / `TAG_IMPORTO = "[IMPORTO_1]"`, incluso l'uso a riga 393 (`nodo.dataset.tag`).

Run: `python -m pytest -q` e `node tests/ui_harness.mjs`
Expected: PASS entrambi.

- [ ] **Step 5: Commit**

```bash
git add cryptocustode/api/routes_fascicolo.py cryptocustode/api/app.py cryptocustode/ui/app.js cryptocustode/ui/index.html tests/test_revisione.py tests/test_app.py tests/conftest.py tests/ui_harness.mjs
git commit -m "feat: l'analisi chiama il rilevatore iniettato, e la revisione parla di tag"
```

---

### Task 13: La cancellazione

Ultimo per necessità: finché una route importava `analizza_documento`, cancellare `entities.py` avrebbe lasciato la suite rossa.

**Files:**
- Delete: `cryptocustode/core/detect/` (intera cartella), `cryptocustode/core/spans.py`, `cryptocustode/core/entities.py`
- Delete: `tests/test_patterns.py`, `tests/test_rules.py`, `tests/test_ner.py`, `tests/test_validators.py`, `tests/test_spans.py`, `tests/test_entities.py`
- Modify: `cryptocustode/core/models.py`, `tests/test_architettura.py`, `requirements.txt`, `pyproject.toml`

- [ ] **Step 1: Estendi il test di architettura**

In `tests/test_architettura.py`, aggiungi ai divieti e sostituisci il caso di prova che cita `entities.py`:

```python
VIETATI = {
    "fastapi",
    "uvicorn",
    "starlette",
    "cryptocustode.state",
    # Dalla spec del 2026-09-14: il fornitore IA è fuori da `core/`, che ne
    # conosce solo il `Protocol` di `core/rilevatore.py`. Senza queste righe il
    # primo client scritto dentro `core/` passerebbe senza che nessuno se ne
    # accorga, e l'invariante resterebbe vero solo per abitudine.
    "httpx",
    "requests",
    "google",
    "cryptocustode.ai",
}

VIETATI_IN_MASK = {...}  # invariato


def test_il_divieto_di_determinismo_copre_anche_tagga():
    """`tagga.py` è attraversata da `hash_approvazione` come `mask.py`: se non
    fosse deterministica, il confronto con `approval_hash` fallirebbe a caso."""
    for nome in ("mask.py", "tagga.py"):
        percorso = CORE / nome
        trovati = nomi_vietati_in(
            percorso.read_text(encoding="utf-8"),
            pacchetto_del_file(percorso),
            VIETATI | VIETATI_IN_MASK,
        )
        assert trovati == set(), f"core/{nome} deve restare deterministica: {trovati}"


def test_rileva_un_client_http_dentro_core():
    assert nomi_vietati_in("from google import genai\n", PACCHETTO_DI_PROVA) == {
        "google", "google.genai"
    }
```

Sostituisci `test_il_divieto_su_mask_non_riguarda_gli_altri_moduli_di_core`, la cui docstring cita `entities.py`, con una che cita `vault.py` (che usa `os` per il salt):

```python
def test_il_divieto_di_determinismo_non_riguarda_tutto_core():
    """`vault.py` usa `os` per salt e nonce e `datetime` per `created_at`, ed
    è legittimo: il divieto è di `mask.py` e `tagga.py`, non di tutto `core/`."""
    assert nomi_vietati_in("import os\n", PACCHETTO_DI_PROVA) == set()
    assert nomi_vietati_in("from datetime import timezone\n", PACCHETTO_DI_PROVA) == set()
```

Rimuovi `test_mask_non_importa_filesystem_orologio_ne_random`, assorbito dal test parametrico qui sopra.

- [ ] **Step 2: Esegui e verifica che passi già**

Run: `python -m pytest tests/test_architettura.py -q`
Expected: PASS — nessun modulo di `core/` importa quei nomi, ed è il punto.

- [ ] **Step 3: Cancella**

```bash
git rm -r cryptocustode/core/detect
git rm cryptocustode/core/spans.py cryptocustode/core/entities.py
git rm tests/test_patterns.py tests/test_rules.py tests/test_ner.py \
       tests/test_validators.py tests/test_spans.py tests/test_entities.py
```

In `cryptocustode/core/models.py` togli `Span`, `Entity`, `Ambiguity`, `AmbiguityKind`, `Source`, `PRIORITA`, e i campi `spans`, `entities`, `ambiguities` da `Fascicolo`. In `fascicolo_vuoto` non cambia niente: `tags` e `analizzati` hanno già il loro default.

In `requirements.txt` togli la riga `spacy==3.8.16` e l'intero blocco di commento sul modello `it_core_news_lg` e sul parallelismo delle worktree, che non descrive più niente di vero.

In `pyproject.toml` togli il marcatore `lento` da `markers` (nessun test carica più spaCy) e lascia `rete`, che ora serve davvero.

- [ ] **Step 4: Esegui la suite intera**

Run: `python -m pytest -q`
Expected: PASS, nessun test saltato per modello mancante. Verifica anche che nulla citi più i moduli cancellati:

```bash
grep -rn "core.detect\|core.spans\|core.entities\|it_core_news\|spacy" \
  --include="*.py" --include="*.toml" --include="*.txt" . | grep -v "^./docs/"
```

Expected: nessuna riga.

- [ ] **Step 5: Commit e chiudi la #47**

```bash
git add -u cryptocustode/core/models.py requirements.txt pyproject.toml tests/test_architettura.py
git commit -m "refactor: via il motore a regex, spaCy e il modello da 550 MB"
```

```bash
glab issue note 47 --message "Chiusa da obsolescenza: la regex del CAP viveva in core/detect/patterns.py, cancellato nella fase 1 del passaggio a Gemini (spec docs/superpowers/specs/2026-09-14-motore-ia-esporta-importa.md, §15). Il caso 'Via Roma 12, Torino (TO) 10121' ora dipende dal modello, non da un pattern: se si ripresenta va riaperto come qualità del rilevamento, con il testo che lo riproduce."
glab issue close 47
```

---

## Self-review

**Copertura della spec.** §4 architettura → task 2, 8, 9, 13; §5 modello dati → task 1, 11, 13; §6 contratto Gemini → task 8, 9; §7 tagging → task 3, 4, 5; §8 garanzie → task 6; §9 stato → task 10; §12 errori → task 7; §13 test → distribuito, con i property test nei task 3-5 e l'identità nel task 6; §14 fase 1 → l'intero piano; §15 cancellazione → task 13.

**Fuori dalla fase 1, per costruzione:** §10 (vault automatico e indice) e §11 (importazione) sono fase 2 e 3. Il task 11 tocca il vault solo per il formato del payload, non per il salvataggio automatico. I `TC-07` e `TC-08` della §13 sono coperti dai test del task 9 (`test_una_categoria_inventata_diventa_AIResponseInvalid`) e del task 5 (`test_un_tag_che_nessun_documento_contiene_resta_non_trovato`); `TC-09` appartiene alla fase 3.

**Nomi.** `tagga`, `assegna_tag`, `conta_occorrenze`, `dizionario_di`, `tabella_attiva`, `maschera_documento`, `hash_approvazione`, `ripristina`, `rileva`, `crea_router(store, rilevatore)`, `crea_app(rilevatore=...)`. La tabella dei tag è sempre `dict[str, Tag]` indicizzata per stringa del tag, in tutti i task.
