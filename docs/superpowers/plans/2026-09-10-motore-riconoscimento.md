# Motore di riconoscimento e mascheratura — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Costruire il motore puro di CryptoCustode: dato un testo italiano, produce gli span dei dati personali, li aggrega in entità con segnaposto stabili, e restituisce il testo mascherato.

**Architecture:** Una libreria `cryptocustode/core/` che non conosce né HTTP né stato di sessione. Pipeline ibrida a priorità decrescente: prima le regole deterministiche con checksum (P1-P3), poi il NER statistico (P4); gli span di priorità superiore consumano il testo. L'aggregazione in entità fonde automaticamente solo su codice fiscale identico e mette tutto il resto in una coda di ambiguità da far decidere all'utente.

**Tech Stack:** Python 3.14.5, spaCy 3.8.16 con `it_core_news_lg`, pytest 9.1.1.

**Spec:** `docs/superpowers/specs/2026-09-10-cryptocustode-design.md`

Questo è il **piano 1 di 3**. Il piano 2 coprirà ingestione documenti, macchina a stati, export, ripristino e vault; il piano 3 le route HTTP, la UI e i materiali di consegna.

## Global Constraints

- **Python 3.14.5**, unico interprete installato sulla macchina. Ambiente isolato in `.venv/` nella radice del repo. Tutti i comandi usano l'interprete del venv: `.venv\Scripts\python`.
- **`cryptocustode/core/` non deve importare** `fastapi`, `uvicorn`, `starlette`, né `cryptocustode.state`. Garantito dal test di architettura del Task 1.
- **Nessuna funzione in `core/mask.py` accede a filesystem, orologio o random.** Il masking deve essere deterministico perché l'hash di approvazione sia riproducibile.
- **Naming:** i nomi dei tipi restano quelli della spec (`Document`, `Span`, `Entity`, `Ambiguity`, `Fascicolo`, `Category`, `Source`, `State`); funzioni, variabili e messaggi sono in italiano. I messaggi d'errore rivolti all'utente sono in italiano.
- **Formato segnaposto:** `[TIPO_INDICE]`, conforme a `\[[A-Z]+_\d+\]`. Indice incrementale per tipo, globale al fascicolo, mai riciclato.
- **Tutti i dati di test sono inventati.** Nessun dato personale reale, in nessun file del repo.
- **Un commit per task**, con il messaggio indicato nell'ultimo step del task.

## File Structure

| File | Responsabilità | Task |
|---|---|---|
| `requirements.txt` | dipendenze di runtime, versioni pinnate | 1 |
| `requirements-dev.txt` | dipendenze di sviluppo e test | 1 |
| `pyproject.toml` | configurazione di pytest e del package | 1 |
| `cryptocustode/__init__.py` | marcatore di package | 1 |
| `cryptocustode/core/__init__.py` | marcatore di package | 1 |
| `tests/test_architettura.py` | fa rispettare l'invariante di purezza di `core/` | 1 |
| `cryptocustode/core/models.py` | tipi di dominio, nessun comportamento | 2 |
| `cryptocustode/core/detect/validators.py` | checksum: CIN del CF, cifra di controllo P.IVA, IBAN MOD-97 | 3 |
| `cryptocustode/core/detect/patterns.py` | le regex e le parole chiave di contesto, una voce per categoria | 4 |
| `cryptocustode/core/detect/rules.py` | applica pattern e validatori, produce span | 4 |
| `cryptocustode/core/spans.py` | priorità, sovrapposizioni, invariante di non sovrapposizione | 5 |
| `cryptocustode/core/detect/ner.py` | carica spaCy, converte le entità NER in span | 6 |
| `cryptocustode/core/entities.py` | normalizzazione, aggregazione, euristiche, coda ambiguità | 7 |
| `cryptocustode/core/mask.py` | masking puro e hash canonico di approvazione | 8 |

---

### Task 1: Ambiente, scaffolding e invariante di purezza

**Files:**
- Create: `requirements.txt`, `requirements-dev.txt`, `pyproject.toml`
- Create: `cryptocustode/__init__.py`, `cryptocustode/core/__init__.py`, `cryptocustode/core/detect/__init__.py`, `cryptocustode/state/__init__.py`
- Test: `tests/test_architettura.py`

**Interfaces:**
- Consumes: nulla, è il primo task.
- Produces: un ambiente `.venv` funzionante con spaCy e `it_core_news_lg` installati; la struttura di package su cui poggiano tutti i task successivi; il test `test_core_non_importa_http_ne_stato`.

- [ ] **Step 1: Creare il virtualenv**

```
python -m venv .venv
```

- [ ] **Step 2: Scrivere `requirements.txt`**

```
fastapi==0.137.1
uvicorn[standard]==0.49.0
pymupdf==1.28.0
cryptography==48.0.0
spacy==3.8.16
python-multipart==0.0.20
```

`python-multipart` serve a FastAPI per gli upload di file: viene usato nel piano 3, ma la dipendenza va dichiarata una volta sola.

- [ ] **Step 3: Scrivere `requirements-dev.txt`**

```
-r requirements.txt
pytest==9.1.1
httpx==0.28.1
```

`httpx` è richiesto dal `TestClient` di FastAPI, usato nel piano 2.

- [ ] **Step 4: Installare le dipendenze**

```
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements-dev.txt
```

- [ ] **Step 5: Installare il modello linguistico**

```
.venv\Scripts\python -m spacy download it_core_news_lg
```

Circa 550 MB, richiede rete. Se il comando fallisce perché il modello non è compatibile con spaCy 3.8.16, installare la release esplicita:

```
.venv\Scripts\python -m pip install https://github.com/explosion/spacy-models/releases/download/it_core_news_lg-3.8.0/it_core_news_lg-3.8.0-py3-none-any.whl
```

- [ ] **Step 6: Verificare che il modello carichi e riconosca una persona**

```
.venv\Scripts\python -c "import spacy; nlp = spacy.load('it_core_news_lg'); print([(e.text, e.label_) for e in nlp('Il contratto è firmato da Mario Rossi a Torino.').ents])"
```

Atteso: una lista contenente una entità con label `PER` per "Mario Rossi". Se la lista è vuota, fermarsi: il resto del piano presuppone un modello funzionante.

- [ ] **Step 7: Scrivere `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "cryptocustode"
version = "0.1.0"
requires-python = ">=3.14"

[tool.setuptools.packages.find]
include = ["cryptocustode*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q --strict-markers"
markers = [
    "lento: test che caricano il modello spaCy",
    "rete: test che richiedono connettività o una API key",
]
```

`--strict-markers` fa fallire un marker scritto male invece di ignorarlo silenziosamente.

- [ ] **Step 8: Creare la struttura di package**

Creare quattro file vuoti: `cryptocustode/__init__.py`, `cryptocustode/core/__init__.py`, `cryptocustode/core/detect/__init__.py`, `cryptocustode/state/__init__.py`.

- [ ] **Step 9: Scrivere il test di architettura**

`tests/test_architettura.py`:

```python
"""Fa rispettare l'invariante 1 della spec: core/ non conosce HTTP né lo stato."""
import ast
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]
CORE = RADICE / "cryptocustode" / "core"

VIETATI = {
    "fastapi",
    "uvicorn",
    "starlette",
    "cryptocustode.state",
}


def moduli_importati(percorso: Path) -> set[str]:
    """Restituisce i nomi dei moduli importati da un file Python."""
    albero = ast.parse(percorso.read_text(encoding="utf-8"))
    nomi: set[str] = set()
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                nomi.add(alias.name)
                nomi.add(alias.name.split(".")[0])
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            nomi.add(nodo.module)
            nomi.add(nodo.module.split(".")[0])
    return nomi


def test_core_non_importa_http_ne_stato():
    violazioni = []
    for percorso in sorted(CORE.rglob("*.py")):
        for modulo in sorted(moduli_importati(percorso) & VIETATI):
            violazioni.append(f"{percorso.relative_to(RADICE)} importa {modulo}")
    assert violazioni == [], "core/ deve restare puro:\n" + "\n".join(violazioni)
```

- [ ] **Step 10: Verificare che il test sappia fallire**

Un test che passa appena scritto non dimostra nulla. Creare temporaneamente `cryptocustode/core/_prova.py` con una sola riga:

```python
import fastapi
```

Poi eseguire:

```
.venv\Scripts\python -m pytest tests/test_architettura.py -v
```

Atteso: FAIL, con il messaggio `cryptocustode\core\_prova.py importa fastapi`.

- [ ] **Step 11: Rimuovere il file di prova e verificare che il test passi**

Cancellare `cryptocustode/core/_prova.py`, poi:

```
.venv\Scripts\python -m pytest tests/test_architettura.py -v
```

Atteso: PASS.

- [ ] **Step 12: Commit**

```
git add requirements.txt requirements-dev.txt pyproject.toml cryptocustode tests
git commit -m "chore: ambiente, scaffolding e test di architettura su core/"
```

---

### Task 2: Modello dati

**Files:**
- Create: `cryptocustode/core/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: la struttura di package del Task 1.
- Produces: `Category`, `Source`, `State`, `AmbiguityKind` (enum); `Document`, `Span`, `Entity`, `Ambiguity`, `Fascicolo` (dataclass); `PRIORITA: dict[Category, int]`; `fascicolo_vuoto(fascicolo_id: str) -> Fascicolo`. Tutti i task successivi importano da qui.

- [ ] **Step 1: Scrivere il test che fissa il contratto dei tipi**

`tests/test_models.py`:

```python
import dataclasses

import pytest

from cryptocustode.core.models import (
    PRIORITA,
    Category,
    Document,
    Entity,
    Fascicolo,
    Source,
    Span,
    State,
    fascicolo_vuoto,
)


def test_span_e_immutabile():
    span = Span(
        span_id="s1", doc_id="d1", start=0, end=4,
        category=Category.PERSONA, source=Source.RULE, entity_id="e1",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        span.start = 5


def test_span_nasce_abilitato():
    span = Span(
        span_id="s1", doc_id="d1", start=0, end=4,
        category=Category.PERSONA, source=Source.RULE, entity_id="e1",
    )
    assert span.enabled is True


def test_document_e_immutabile():
    doc = Document(doc_id="d1", filename="a.txt", text="ciao", page_offsets=[0], sha256="x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        doc.text = "altro"


def test_ogni_categoria_ha_una_priorita():
    assert set(PRIORITA) == set(Category)
    assert all(1 <= p <= 4 for p in PRIORITA.values())


def test_le_priorita_seguono_la_spec():
    assert PRIORITA[Category.CF] == 1
    assert PRIORITA[Category.IBAN] == 1
    assert PRIORITA[Category.PIVA] == 1
    assert PRIORITA[Category.EMAIL] == 2
    assert PRIORITA[Category.DATA] == 3
    assert PRIORITA[Category.PERSONA] == 4


def test_fascicolo_vuoto_parte_in_draft_con_tutte_le_categorie_attive():
    f = fascicolo_vuoto("f1")
    assert f.fascicolo_id == "f1"
    assert f.state is State.DRAFT
    assert f.approval_hash is None
    assert f.documents == []
    assert set(f.category_enabled) == set(Category)
    assert all(f.category_enabled.values()), "di default tutto è mascherato"
    assert all(v == 0 for v in f.counters.values())


def test_entity_tiene_traccia_delle_varianti():
    e = Entity(
        entity_id="e1", category=Category.PERSONA, placeholder="[PERSONA_1]",
        canonical_value="Mario Rossi", variants={"Mario Rossi", "M. Rossi"}, cf=None,
    )
    assert "M. Rossi" in e.variants
    assert e.canonical_value == "Mario Rossi"


def test_fascicolo_accetta_al_massimo_dieci_documenti():
    f = fascicolo_vuoto("f1")
    assert Fascicolo.MAX_DOCUMENTI == 10
```

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

```
.venv\Scripts\python -m pytest tests/test_models.py -v
```

Atteso: FAIL con `ModuleNotFoundError: No module named 'cryptocustode.core.models'`.

- [ ] **Step 3: Scrivere `cryptocustode/core/models.py`**

```python
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
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

```
.venv\Scripts\python -m pytest tests/test_models.py tests/test_architettura.py -v
```

Atteso: PASS su tutti.

- [ ] **Step 5: Commit**

```
git add cryptocustode/core/models.py tests/test_models.py
git commit -m "feat: tipi di dominio con priorità e fascicolo vuoto"
```

---

### Task 3: Validatori deterministici

**Files:**
- Create: `cryptocustode/core/detect/validators.py`
- Test: `tests/test_validators.py`

**Interfaces:**
- Consumes: nulla dai task precedenti (modulo autonomo).
- Produces: `cf_valido(valore: str) -> bool`, `cin_atteso(primi_quindici: str) -> str`, `piva_valida(valore: str) -> bool`, `iban_valido(valore: str) -> bool`. Usate dal Task 4.

**Dati di test, calcolati a mano e verificabili:**

| Valore | Valido | Perché |
|---|---|---|
| `RSSMRA85M01H501Q` | sì | somma dispari 78 + somma pari 42 = 120; 120 mod 26 = 16; la 17ª lettera è `Q` |
| `RSSMRA85M01H501Z` | no | stesso corpo, CIN sbagliato (è il caso TC-02 della consegna) |
| `12345678903` | sì | dispari 1+3+5+7+9 = 25; pari raddoppiati 4+8+3+7+0 = 22; totale 47; cifra di controllo (10 − 7) mod 10 = 3 |
| `12345678900` | no | cifra di controllo errata |
| `IT60X0542811101000000123456` | sì | MOD 97-10 restituisce 1 |
| `IT60X0542811101000000123457` | no | ultima cifra alterata |

- [ ] **Step 1: Scrivere i test**

`tests/test_validators.py`:

```python
import pytest

from cryptocustode.core.detect.validators import (
    cf_valido,
    cin_atteso,
    iban_valido,
    piva_valida,
)


class TestCodiceFiscale:
    def test_cin_calcolato_a_mano(self):
        # dispari 78 + pari 42 = 120; 120 % 26 = 16; chr(65+16) = 'Q'
        assert cin_atteso("RSSMRA85M01H501") == "Q"

    def test_cf_con_cin_corretto(self):
        assert cf_valido("RSSMRA85M01H501Q") is True

    def test_cf_con_cin_errato_e_rifiutato(self):
        # TC-02 della consegna
        assert cf_valido("RSSMRA85M01H501Z") is False

    def test_cf_minuscolo_accettato(self):
        assert cf_valido("rssmra85m01h501q") is True

    @pytest.mark.parametrize("valore", ["", "RSSMRA85M01H501", "RSSMRA85M01H501QQ", "1234567890123456"])
    def test_lunghezza_o_forma_errata(self, valore):
        assert cf_valido(valore) is False

    def test_omocodia_non_fa_esplodere_il_calcolo(self):
        # nell'omocodia alcune cifre diventano lettere: il CIN si calcola
        # sui 15 caratteri così come compaiono
        cin = cin_atteso("RSSMRAURMLNH5L1")
        assert cin.isalpha() and len(cin) == 1


class TestPartitaIva:
    def test_piva_valida(self):
        assert piva_valida("12345678903") is True

    def test_piva_con_cifra_di_controllo_errata(self):
        assert piva_valida("12345678900") is False

    def test_prefisso_it_accettato(self):
        assert piva_valida("IT12345678903") is True

    @pytest.mark.parametrize("valore", ["", "1234567890", "123456789012", "1234567890A"])
    def test_lunghezza_o_forma_errata(self, valore):
        assert piva_valida(valore) is False


class TestIban:
    def test_iban_italiano_valido(self):
        assert iban_valido("IT60X0542811101000000123456") is True

    def test_iban_con_cifra_alterata(self):
        assert iban_valido("IT60X0542811101000000123457") is False

    def test_spazi_ignorati(self):
        assert iban_valido("IT60 X054 2811 1010 0000 0123 456") is True

    @pytest.mark.parametrize("valore", ["", "IT60", "XX00X0542811101000000123456"])
    def test_forma_errata(self, valore):
        assert iban_valido(valore) is False
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

```
.venv\Scripts\python -m pytest tests/test_validators.py -v
```

Atteso: FAIL con `ModuleNotFoundError`.

- [ ] **Step 3: Scrivere `cryptocustode/core/detect/validators.py`**

```python
"""Checksum deterministici. Un valore che non supera il controllo non diventa
uno span della sua categoria: al più resta materiale per il NER (spec §6)."""
from __future__ import annotations

import re

# Tabelle ufficiali del CIN del codice fiscale.
# Posizioni dispari contando da 1 (1ª, 3ª, ... 15ª).
_DISPARI = {
    "0": 1, "1": 0, "2": 5, "3": 7, "4": 9, "5": 13, "6": 15, "7": 17, "8": 19, "9": 21,
    "A": 1, "B": 0, "C": 5, "D": 7, "E": 9, "F": 13, "G": 15, "H": 17, "I": 19, "J": 21,
    "K": 2, "L": 4, "M": 18, "N": 20, "O": 11, "P": 3, "Q": 6, "R": 8, "S": 12, "T": 14,
    "U": 16, "V": 10, "W": 22, "X": 25, "Y": 24, "Z": 23,
}

# Posizioni pari: le cifre valgono se stesse, le lettere la loro posizione (A=0).
_PARI = {str(n): n for n in range(10)} | {chr(65 + n): n for n in range(26)}

_FORMA_CF = re.compile(
    r"\A[A-Z]{6}[0-9LMNPQRSTUV]{2}[ABCDEHLMPRST][0-9LMNPQRSTUV]{2}"
    r"[A-Z][0-9LMNPQRSTUV]{3}[A-Z]\Z"
)


def cin_atteso(primi_quindici: str) -> str:
    """Calcola il carattere di controllo dai primi 15 caratteri del codice fiscale.

    I caratteri sono usati così come compaiono: nell'omocodia alcune cifre sono
    sostituite da lettere, e le tabelle ufficiali le contemplano già.
    """
    corpo = primi_quindici.upper()
    if len(corpo) != 15:
        raise ValueError("il corpo del codice fiscale deve avere 15 caratteri")
    totale = 0
    for indice, carattere in enumerate(corpo, start=1):
        tabella = _DISPARI if indice % 2 == 1 else _PARI
        if carattere not in tabella:
            raise ValueError(f"carattere non ammesso nel codice fiscale: {carattere!r}")
        totale += tabella[carattere]
    return chr(65 + totale % 26)


def cf_valido(valore: str) -> bool:
    codice = valore.strip().upper()
    if not _FORMA_CF.match(codice):
        return False
    try:
        return cin_atteso(codice[:15]) == codice[15]
    except ValueError:
        return False


def piva_valida(valore: str) -> bool:
    """Cifra di controllo della partita IVA italiana: 11 cifre, l'ultima calcolata
    sulle prime 10 raddoppiando le posizioni pari."""
    cifre = valore.strip().upper().removeprefix("IT")
    if len(cifre) != 11 or not cifre.isdigit():
        return False
    totale = 0
    for indice, carattere in enumerate(cifre[:10]):
        n = int(carattere)
        if indice % 2 == 1:  # 2ª, 4ª, ... contando da 1
            n *= 2
            if n > 9:
                n -= 9
        totale += n
    return (10 - totale % 10) % 10 == int(cifre[10])


def iban_valido(valore: str) -> bool:
    """ISO 7064 MOD 97-10: sposta i primi 4 caratteri in coda, converte le lettere
    in numeri (A=10 ... Z=35) e verifica che il resto modulo 97 sia 1."""
    codice = re.sub(r"\s+", "", valore).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[0-9A-Z]{11,30}", codice):
        return False
    riordinato = codice[4:] + codice[:4]
    resto = 0
    for carattere in riordinato:
        if carattere.isdigit():
            pezzo = carattere
        else:
            pezzo = str(ord(carattere) - 55)  # 'A' -> '10'
        for cifra in pezzo:
            resto = (resto * 10 + int(cifra)) % 97
    return resto == 1
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

```
.venv\Scripts\python -m pytest tests/test_validators.py -v
```

Atteso: PASS su tutti. Se `test_cin_calcolato_a_mano` fallisce, l'errore è nelle tabelle: ricontrollare `_DISPARI` carattere per carattere prima di toccare la logica.

- [ ] **Step 5: Commit**

```
git add cryptocustode/core/detect/validators.py tests/test_validators.py
git commit -m "feat: validatori di codice fiscale, partita IVA e IBAN"
```

---

### Task 4: Pattern e motore a regole

**Files:**
- Create: `cryptocustode/core/detect/patterns.py`
- Create: `cryptocustode/core/detect/rules.py`
- Test: `tests/test_rules.py`

**Interfaces:**
- Consumes: `Category`, `Source`, `Span` dal Task 2; i validatori dal Task 3.
- Produces: `PATTERN: dict[Category, Pattern[str]]`, `PAROLE_CONTESTO: dict[Category, tuple[str, ...]]`, `FINESTRA_CONTESTO: int` da `patterns.py`; `trova_per_regole(testo: str, doc_id: str) -> list[Span]` da `rules.py`. Usata dai Task 5 e 7.

**Nota sugli identificativi:** in questo task ogni span riceve `entity_id=""`. L'assegnazione delle entità è responsabilità del Task 7; qui gli span sono ancora anonimi. `span_id` è deterministico — `f"{doc_id}:{start}-{end}:{categoria}"` — così due esecuzioni sullo stesso testo producono gli stessi identificativi, requisito del determinismo dichiarato nei Global Constraints.

- [ ] **Step 1: Scrivere i test**

`tests/test_rules.py`:

```python
import pytest

from cryptocustode.core.detect.rules import trova_per_regole
from cryptocustode.core.models import Category, Source


def categorie(testo: str) -> set[Category]:
    return {s.category for s in trova_per_regole(testo, "d1")}


def valori(testo: str, categoria: Category) -> list[str]:
    return [testo[s.start:s.end] for s in trova_per_regole(testo, "d1") if s.category is categoria]


class TestChecksum:
    def test_cf_valido_riconosciuto(self):
        assert valori("Codice fiscale RSSMRA85M01H501Q.", Category.CF) == ["RSSMRA85M01H501Q"]

    def test_cf_con_cin_errato_ignorato(self):
        # TC-02: la regola non lo prende, resterà eventualmente al NER
        assert Category.CF not in categorie("Codice fiscale RSSMRA85M01H501Z.")

    def test_iban_valido_riconosciuto(self):
        testo = "Bonifico su IT60X0542811101000000123456 entro il termine."
        assert valori(testo, Category.IBAN) == ["IT60X0542811101000000123456"]

    def test_iban_con_cifra_alterata_ignorato(self):
        assert Category.IBAN not in categorie("Bonifico su IT60X0542811101000000123457.")


class TestRequisitoDiContesto:
    def test_piva_con_parola_chiave_riconosciuta(self):
        assert valori("P. IVA 12345678903", Category.PIVA) == ["12345678903"]

    def test_piva_con_prefisso_it_riconosciuta(self):
        assert valori("Fattura a IT12345678903", Category.PIVA) == ["IT12345678903"]

    def test_undici_cifre_nude_non_diventano_piva(self):
        # senza contesto ogni numero lungo diventerebbe un dato personale
        assert Category.PIVA not in categorie("Il totale delle unità è 12345678903 pezzi.")

    def test_cellulare_con_parola_chiave_riconosciuto(self):
        assert valori("Cell. 3401234567", Category.TELEFONO) == ["3401234567"]

    def test_numero_con_prefisso_internazionale_riconosciuto(self):
        assert valori("Chiamare +39 340 1234567", Category.TELEFONO) == ["+39 340 1234567"]

    def test_numero_nudo_senza_contesto_ignorato(self):
        assert Category.TELEFONO not in categorie("La particella misura 3401234567 centimetri.")


class TestAltreCategorie:
    def test_email(self):
        assert valori("Scrivere a mario.rossi@esempio.it subito.", Category.EMAIL) == [
            "mario.rossi@esempio.it"
        ]

    def test_data_numerica(self):
        assert valori("Firmato il 14/03/2024 a Torino.", Category.DATA) == ["14/03/2024"]

    def test_data_testuale_italiana(self):
        assert valori("Firmato il 14 marzo 2024 a Torino.", Category.DATA) == ["14 marzo 2024"]

    def test_data_inesistente_ignorata(self):
        assert Category.DATA not in categorie("Il numero 31/02/2024 non è una data.")

    def test_importo_con_simbolo(self):
        assert valori("Canone di € 1.250,00 mensili.", Category.IMPORTO) == ["€ 1.250,00"]

    def test_importo_con_valuta_dopo(self):
        assert valori("Canone di 1.250,00 EUR mensili.", Category.IMPORTO) == ["1.250,00 EUR"]

    def test_dati_catastali(self):
        trovati = valori("Immobile al foglio 12 particella 345 sub 2.", Category.CATASTO)
        assert len(trovati) == 1
        assert "foglio 12" in trovati[0] and "345" in trovati[0]

    def test_numero_pratica(self):
        trovati = valori("Pratica n. 2024/ABC-77 in corso.", Category.PRATICA)
        assert len(trovati) == 1
        assert "2024/ABC-77" in trovati[0]

    def test_indirizzo_con_civico(self):
        trovati = valori("Residente in Via Giuseppe Garibaldi 42, Torino.", Category.INDIRIZZO)
        assert len(trovati) == 1
        assert trovati[0].startswith("Via Giuseppe Garibaldi")

    def test_cap_da_solo_non_e_un_indirizzo(self):
        assert Category.INDIRIZZO not in categorie("Il codice 10121 non basta.")


class TestFormaDegliSpan:
    def test_gli_span_sono_prodotti_dalle_regole(self):
        for span in trova_per_regole("P. IVA 12345678903", "d1"):
            assert span.source is Source.RULE
            assert span.doc_id == "d1"
            assert span.entity_id == ""

    def test_span_id_deterministico(self):
        testo = "Codice fiscale RSSMRA85M01H501Q."
        primi = [s.span_id for s in trova_per_regole(testo, "d1")]
        secondi = [s.span_id for s in trova_per_regole(testo, "d1")]
        assert primi == secondi

    def test_gli_offset_puntano_al_testo_giusto(self):
        testo = "Codice fiscale RSSMRA85M01H501Q."
        span = trova_per_regole(testo, "d1")[0]
        assert testo[span.start:span.end] == "RSSMRA85M01H501Q"
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

```
.venv\Scripts\python -m pytest tests/test_rules.py -v
```

Atteso: FAIL con `ModuleNotFoundError`.

- [ ] **Step 3: Scrivere `cryptocustode/core/detect/patterns.py`**

```python
"""Le regex per categoria e le parole chiave che fanno da contesto obbligatorio."""
from __future__ import annotations

import re
from re import Pattern

from cryptocustode.core.models import Category

MESI = (
    "gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|"
    "settembre|ottobre|novembre|dicembre"
)

TOPONIMI = (
    r"via|viale|v\.le|piazza|p\.zza|piazzale|corso|c\.so|largo|vicolo|"
    r"strada|contrada|localit[àa]|borgo|salita|lungomare"
)

SUFFISSI_SOCIETARI = (
    r"s\.?r\.?l\.?|s\.?p\.?a\.?|s\.?n\.?c\.?|s\.?a\.?s\.?|s\.?c\.?a\.?r\.?l\.?"
)

PATTERN: dict[Category, Pattern[str]] = {
    Category.CF: re.compile(
        r"\b[A-Z]{6}[0-9LMNPQRSTUV]{2}[ABCDEHLMPRST][0-9LMNPQRSTUV]{2}"
        r"[A-Z][0-9LMNPQRSTUV]{3}[A-Z]\b"
    ),
    Category.IBAN: re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[0-9A-Z]){11,30}\b"),
    Category.PIVA: re.compile(r"\b(?:IT)?\d{11}\b"),
    Category.EMAIL: re.compile(
        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
    ),
    Category.TELEFONO: re.compile(
        r"(?:\+39|0039)[\s.\-/]?\d(?:[\s.\-/]?\d){8,9}"
        r"|\b3\d{2}[\s.\-/]?\d{3}[\s.\-/]?\d{3,4}\b"
        r"|\b0\d{1,3}[\s.\-/]?\d{6,8}\b"
    ),
    Category.CATASTO: re.compile(
        r"(?:f(?:og)?li?o?)[\s.:n°]*\d{1,4}.{0,40}?"
        r"(?:part(?:icella)?|mapp(?:ale)?)[\s.:n°]*\d{1,5}"
        r"(?:[\s,]*sub\.?[\s.:n°]*\d{1,4})?",
        re.IGNORECASE | re.DOTALL,
    ),
    Category.PRATICA: re.compile(
        r"(?:pratica|fascicolo|prot(?:ocollo)?|rif(?:erimento)?)"
        r"[\s.:n°/\-]{0,6}([A-Za-z0-9][A-Za-z0-9/._\-]{2,20})",
        re.IGNORECASE,
    ),
    Category.DATA: re.compile(
        r"\b\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4}\b"
        r"|\b\d{4}-\d{2}-\d{2}\b"
        rf"|\b\d{{1,2}}\s+(?:{MESI})\s+\d{{4}}\b",
        re.IGNORECASE,
    ),
    Category.IMPORTO: re.compile(
        r"(?:€|EUR|euro)\s?\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?"
        r"|\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?\s?(?:€|EUR|euro)\b",
        re.IGNORECASE,
    ),
    Category.INDIRIZZO: re.compile(
        rf"\b(?:{TOPONIMI})\s+(?:[A-Z][\w'À-ÿ]*\s?){{1,4}}"
        r"(?:,?\s*n?\.?\s*\d{1,4}[a-zA-Z]?)?",
        re.IGNORECASE,
    ),
    Category.AZIENDA: re.compile(
        rf"\b(?:[A-Z][\w'À-ÿ&.]*\s+){{1,4}}(?:{SUFFISSI_SOCIETARI})\b",
        re.IGNORECASE,
    ),
}

# Categorie che richiedono una parola chiave vicina per non generare falsi positivi
# a valanga su qualunque numero lungo del documento (spec §6).
PAROLE_CONTESTO: dict[Category, tuple[str, ...]] = {
    Category.PIVA: ("p. iva", "p.iva", "partita iva", "p.i.", "vat"),
    Category.TELEFONO: ("tel", "telefono", "cell", "cellulare", "fax", "mobile"),
}

FINESTRA_CONTESTO = 30
```

Nota su `Category.PERSONA`: non ha una regex. Le persone arrivano solo dal NER (Task 6), come previsto dalla spec.

- [ ] **Step 4: Scrivere `cryptocustode/core/detect/rules.py`**

```python
"""Applica pattern e validatori al testo e produce span di priorità P1-P3.

Gli span nascono con `entity_id` vuoto: l'assegnazione delle entità è compito
di `core/entities.py`.
"""
from __future__ import annotations

import re
from datetime import date

from cryptocustode.core.detect import validators
from cryptocustode.core.detect.patterns import (
    FINESTRA_CONTESTO,
    MESI,
    PAROLE_CONTESTO,
    PATTERN,
)
from cryptocustode.core.models import Category, Source, Span

_NOMI_MESI = {nome: numero for numero, nome in enumerate(MESI.split("|"), start=1)}


def _ha_contesto(testo: str, inizio: int, categoria: Category) -> bool:
    parole = PAROLE_CONTESTO.get(categoria)
    if parole is None:
        return True
    finestra = testo[max(0, inizio - FINESTRA_CONTESTO):inizio].lower()
    return any(parola in finestra for parola in parole)


def _data_esiste(valore: str) -> bool:
    ripulito = valore.strip().lower()
    numerica = re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", ripulito)
    if numerica:
        giorno, mese, anno = (int(g) for g in numerica.groups())
    else:
        iso = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", ripulito)
        if iso:
            anno, mese, giorno = (int(g) for g in iso.groups())
        else:
            testuale = re.fullmatch(r"(\d{1,2})\s+([a-zà-ÿ]+)\s+(\d{4})", ripulito)
            if not testuale:
                return False
            giorno = int(testuale.group(1))
            mese = _NOMI_MESI.get(testuale.group(2), 0)
            anno = int(testuale.group(3))
    try:
        date(anno, mese, giorno)
    except ValueError:
        return False
    return True


_VALIDATORI = {
    Category.CF: validators.cf_valido,
    Category.PIVA: validators.piva_valida,
    Category.IBAN: validators.iban_valido,
    Category.DATA: _data_esiste,
}


def _accettato(categoria: Category, valore: str) -> bool:
    validatore = _VALIDATORI.get(categoria)
    return True if validatore is None else validatore(valore)


def trova_per_regole(testo: str, doc_id: str) -> list[Span]:
    """Tutti gli span ricavabili da regex e checksum, senza risoluzione delle
    sovrapposizioni: quella è responsabilità di `core/spans.py`."""
    trovati: list[Span] = []
    for categoria, pattern in PATTERN.items():
        for corrispondenza in pattern.finditer(testo):
            # PRATICA cattura l'identificativo nel gruppo 1: lo span copre
            # l'intera espressione, parola chiave inclusa, così l'utente vede
            # il contesto che ha giustificato il riconoscimento.
            valore = corrispondenza.group(0)
            if categoria is Category.PRATICA and not any(
                c.isdigit() for c in corrispondenza.group(1)
            ):
                continue
            if not _accettato(categoria, valore):
                continue
            if not _ha_contesto(testo, corrispondenza.start(), categoria):
                continue
            inizio, fine = corrispondenza.start(), corrispondenza.end()
            trovati.append(
                Span(
                    span_id=f"{doc_id}:{inizio}-{fine}:{categoria.value}",
                    doc_id=doc_id,
                    start=inizio,
                    end=fine,
                    category=categoria,
                    source=Source.RULE,
                    entity_id="",
                )
            )
    trovati.sort(key=lambda s: (s.start, -s.lunghezza))
    return trovati
```

- [ ] **Step 5: Eseguire i test**

```
.venv\Scripts\python -m pytest tests/test_rules.py -v
```

Atteso: PASS su tutti. I test che più probabilmente richiedono un aggiustamento della regex sono `test_indirizzo_con_civico`, `test_dati_catastali` e `test_importo_con_valuta_dopo`: correggere il pattern in `patterns.py`, non il test, a meno che il test stesso descriva un comportamento sbagliato.

- [ ] **Step 6: Commit**

```
git add cryptocustode/core/detect/patterns.py cryptocustode/core/detect/rules.py tests/test_rules.py
git commit -m "feat: pattern per categoria e motore a regole con requisito di contesto"
```

---

### Task 5: Risoluzione degli span

**Files:**
- Create: `cryptocustode/core/spans.py`
- Test: `tests/test_spans.py`

**Interfaces:**
- Consumes: `Span`, `Category`, `Source`, `PRIORITA` dal Task 2.
- Produces: `risolvi(spans: list[Span]) -> list[Span]`, `si_sovrappongono(a: Span, b: Span) -> bool`. Usate dai Task 6 e 7.

**Regole (spec §6):** vince la priorità più alta (numero più basso); a parità di priorità vince lo span più lungo; a parità di lunghezza vince quello che inizia prima, così l'esito è deterministico.

- [ ] **Step 1: Scrivere i test**

`tests/test_spans.py`:

```python
import itertools

from cryptocustode.core.models import Category, Source, Span
from cryptocustode.core.spans import risolvi, si_sovrappongono


def span(inizio: int, fine: int, categoria: Category, id_suffisso: str = "") -> Span:
    return Span(
        span_id=f"s{inizio}-{fine}{id_suffisso}", doc_id="d1", start=inizio, end=fine,
        category=categoria, source=Source.RULE, entity_id="",
    )


def test_span_adiacenti_non_si_sovrappongono():
    assert si_sovrappongono(span(0, 5, Category.CF), span(5, 10, Category.EMAIL)) is False


def test_span_che_condividono_un_carattere_si_sovrappongono():
    assert si_sovrappongono(span(0, 6, Category.CF), span(5, 10, Category.EMAIL)) is True


def test_priorita_alta_vince_su_sovrapposizione():
    # il CF (P1) contiene cifre che la DATA (P3) potrebbe interpretare
    vincitori = risolvi([span(0, 16, Category.CF), span(6, 14, Category.DATA)])
    assert [s.category for s in vincitori] == [Category.CF]


def test_a_parita_di_priorita_vince_il_piu_lungo():
    # INDIRIZZO e AZIENDA sono entrambe P4
    vincitori = risolvi([span(0, 10, Category.INDIRIZZO), span(0, 25, Category.AZIENDA)])
    assert [s.category for s in vincitori] == [Category.AZIENDA]


def test_span_disgiunti_sopravvivono_tutti():
    dati = [span(0, 5, Category.CF), span(10, 20, Category.EMAIL), span(30, 35, Category.IBAN)]
    assert len(risolvi(dati)) == 3


def test_risultato_ordinato_per_offset():
    dati = [span(30, 35, Category.IBAN), span(0, 5, Category.CF), span(10, 20, Category.EMAIL)]
    assert [s.start for s in risolvi(dati)] == [0, 10, 30]


def test_invariante_nessuna_sovrapposizione_nel_risultato():
    dati = [
        span(0, 16, Category.CF), span(6, 14, Category.DATA), span(12, 30, Category.INDIRIZZO),
        span(28, 40, Category.EMAIL), span(35, 50, Category.AZIENDA), span(50, 60, Category.IBAN),
    ]
    risolti = risolvi(dati)
    for a, b in itertools.combinations(risolti, 2):
        assert not si_sovrappongono(a, b), f"{a.span_id} e {b.span_id} si sovrappongono"


def test_risoluzione_deterministica():
    dati = [span(0, 10, Category.INDIRIZZO, "a"), span(0, 10, Category.AZIENDA, "b")]
    assert [s.span_id for s in risolvi(dati)] == [s.span_id for s in risolvi(list(reversed(dati)))]


def test_lista_vuota():
    assert risolvi([]) == []
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

```
.venv\Scripts\python -m pytest tests/test_spans.py -v
```

Atteso: FAIL con `ModuleNotFoundError`.

- [ ] **Step 3: Scrivere `cryptocustode/core/spans.py`**

```python
"""Risoluzione delle sovrapposizioni fra span, per priorità decrescente (spec §6)."""
from __future__ import annotations

from cryptocustode.core.models import Span


def si_sovrappongono(a: Span, b: Span) -> bool:
    """Due span si sovrappongono se condividono almeno un carattere.
    Gli span adiacenti (fine dell'uno uguale all'inizio dell'altro) non si
    sovrappongono."""
    return a.start < b.end and b.start < a.end


def _forza(span: Span) -> tuple[int, int, int, str]:
    """Chiave di ordinamento: priorità più alta prima, poi lo span più lungo,
    poi quello che inizia prima, infine lo span_id per rendere l'esito
    indipendente dall'ordine di ingresso."""
    return (span.priorita, -span.lunghezza, span.start, span.span_id)


def risolvi(spans: list[Span]) -> list[Span]:
    """Sceglie gli span vincenti e restituisce una lista senza sovrapposizioni,
    ordinata per offset crescente."""
    vincitori: list[Span] = []
    for candidato in sorted(spans, key=_forza):
        if any(si_sovrappongono(candidato, scelto) for scelto in vincitori):
            continue
        vincitori.append(candidato)
    vincitori.sort(key=lambda s: s.start)
    return vincitori
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

```
.venv\Scripts\python -m pytest tests/test_spans.py -v
```

Atteso: PASS su tutti.

- [ ] **Step 5: Commit**

```
git add cryptocustode/core/spans.py tests/test_spans.py
git commit -m "feat: risoluzione degli span per priorità con invariante di non sovrapposizione"
```

---

### Task 6: Riconoscimento statistico con spaCy

**Files:**
- Create: `cryptocustode/core/detect/ner.py`
- Test: `tests/test_ner.py`

**Interfaces:**
- Consumes: `Category`, `Source`, `Span` dal Task 2.
- Produces: `carica_modello(nome: str = "it_core_news_lg")` (memoizzata), `trova_per_ner(testo: str, doc_id: str) -> list[Span]`, `MAPPA_LABEL: dict[str, Category]`. Usata dal Task 7.

**Avvertenza sulla fragilità dei test:** gli esiti dipendono dal modello, non dal nostro codice. I test asseriscono soltanto che un nome evidente venga trovato, mai il conteggio esatto delle entità. Sono marcati `lento` perché caricano 550 MB.

- [ ] **Step 1: Scrivere i test**

`tests/test_ner.py`:

```python
import pytest

from cryptocustode.core.detect.ner import MAPPA_LABEL, carica_modello, trova_per_ner
from cryptocustode.core.models import Category, Source

pytestmark = pytest.mark.lento


def valori(testo: str, categoria: Category) -> list[str]:
    return [testo[s.start:s.end] for s in trova_per_ner(testo, "d1") if s.category is categoria]


def test_il_modello_si_carica_una_volta_sola():
    assert carica_modello() is carica_modello()


def test_riconosce_una_persona():
    testo = "Il presente contratto è sottoscritto da Mario Rossi in data odierna."
    assert any("Rossi" in v for v in valori(testo, Category.PERSONA))


def test_riconosce_una_azienda():
    testo = "La società Alfa Costruzioni S.r.l. si impegna a consegnare l'opera."
    assert any("Alfa" in v for v in valori(testo, Category.AZIENDA))


def test_le_label_mappate_coprono_le_tre_categorie_previste():
    assert set(MAPPA_LABEL.values()) == {
        Category.PERSONA, Category.AZIENDA, Category.INDIRIZZO,
    }


def test_gli_span_sono_marcati_come_ner():
    testo = "Contratto firmato da Mario Rossi."
    for span in trova_per_ner(testo, "d1"):
        assert span.source is Source.NER
        assert span.entity_id == ""
        assert testo[span.start:span.end].strip() == testo[span.start:span.end]


def test_scarta_token_di_una_sola_lettera():
    for span in trova_per_ner("La lettera A firmata da B.", "d1"):
        assert span.lunghezza > 1


def test_offset_coerenti_con_il_testo():
    testo = "Il signor Mario Rossi abita a Torino."
    for span in trova_per_ner(testo, "d1"):
        assert 0 <= span.start < span.end <= len(testo)
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

```
.venv\Scripts\python -m pytest tests/test_ner.py -v
```

Atteso: FAIL con `ModuleNotFoundError`.

- [ ] **Step 3: Scrivere `cryptocustode/core/detect/ner.py`**

```python
"""Riconoscimento statistico delle entità con spaCy: priorità P4 (spec §6).

Il modello è generalista: non offre garanzie di completezza. Serve ad assistere
la revisione umana, non a sostituirla.
"""
from __future__ import annotations

from functools import lru_cache

import spacy
from spacy.language import Language

from cryptocustode.core.models import Category, Source, Span

MAPPA_LABEL: dict[str, Category] = {
    "PER": Category.PERSONA,
    "ORG": Category.AZIENDA,
    "LOC": Category.INDIRIZZO,
}


@lru_cache(maxsize=2)
def carica_modello(nome: str = "it_core_news_lg") -> Language:
    """Carica il modello una volta sola per processo: sono circa 550 MB."""
    try:
        return spacy.load(nome)
    except OSError as errore:
        raise RuntimeError(
            f"modello spaCy '{nome}' non installato. "
            f"Eseguire: python -m spacy download {nome}"
        ) from errore


def trova_per_ner(testo: str, doc_id: str) -> list[Span]:
    """Span ricavati dal NER, senza risoluzione delle sovrapposizioni."""
    documento = carica_modello()(testo)
    trovati: list[Span] = []
    for entita in documento.ents:
        categoria = MAPPA_LABEL.get(entita.label_)
        if categoria is None:
            continue
        # Gli offset di spaCy possono includere spazi ai bordi: li riduco, così
        # il testo mascherato non resta con spazi doppi.
        inizio = entita.start_char + (len(entita.text) - len(entita.text.lstrip()))
        fine = entita.end_char - (len(entita.text) - len(entita.text.rstrip()))
        if fine - inizio <= 1:
            continue
        trovati.append(
            Span(
                span_id=f"{doc_id}:{inizio}-{fine}:{categoria.value}",
                doc_id=doc_id,
                start=inizio,
                end=fine,
                category=categoria,
                source=Source.NER,
                entity_id="",
            )
        )
    trovati.sort(key=lambda s: (s.start, -s.lunghezza))
    return trovati
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

```
.venv\Scripts\python -m pytest tests/test_ner.py -v
```

Atteso: PASS. Se `test_riconosce_una_azienda` fallisce, non forzare il test: annotarlo tra i limiti noti e verificare che il pattern sui suffissi societari del Task 4 copra il caso, perché è quello il meccanismo di riserva.

- [ ] **Step 5: Commit**

```
git add cryptocustode/core/detect/ner.py tests/test_ner.py
git commit -m "feat: riconoscimento statistico con spaCy per persone, aziende e luoghi"
```

---

### Task 7: Entità, euristiche e coda delle ambiguità

**Files:**
- Create: `cryptocustode/core/entities.py`
- Test: `tests/test_entities.py`

**Interfaces:**
- Consumes: tutti i tipi del Task 2; `risolvi` dal Task 5; `trova_per_regole` dal Task 4; `trova_per_ner` dal Task 6.
- Produces: `normalizza(valore: str) -> str`, `chiavi_equivalenti(a: str, b: str) -> bool`, `prossimo_placeholder(fascicolo: Fascicolo, categoria: Category) -> str`, `analizza_documento(fascicolo: Fascicolo, documento: Document, usa_ner: bool = True) -> None` (muta il fascicolo aggiungendo span ed entità), `aggiungi_span_manuale(fascicolo: Fascicolo, documento: Document, inizio: int, fine: int, categoria: Category) -> Span`, `risolvi_ambiguita_omonimia(fascicolo: Fascicolo) -> None`. Usate dal Task 8 e dal piano 2.

**Regole di aggregazione (spec §7):** CF identico fonde automaticamente; CF diversi separano automaticamente; stessa stringa normalizzata nello stesso documento è la stessa entità; stessa stringa normalizzata in documenti diversi senza CF apre una ambiguità `SAME_NAME_NO_CF`; una corrispondenza per euristica apre una `HEURISTIC_MERGE_SUGGESTION`.

- [ ] **Step 1: Scrivere i test della normalizzazione e delle euristiche**

`tests/test_entities.py`:

```python
from cryptocustode.core.entities import (
    analizza_documento,
    chiavi_equivalenti,
    normalizza,
    prossimo_placeholder,
)
from cryptocustode.core.models import (
    AmbiguityKind,
    Category,
    Document,
    Source,
    Span,
    fascicolo_vuoto,
)


def documento(doc_id: str, testo: str) -> Document:
    return Document(doc_id=doc_id, filename=f"{doc_id}.txt", text=testo,
                    page_offsets=[0], sha256="x")


class TestNormalizzazione:
    def test_rimuove_titoli_e_uniforma(self):
        assert normalizza("Sig. Mario  Rossi") == normalizza("mario rossi")

    def test_rimuove_titoli_femminili_e_professionali(self):
        for titolo in ["Sig.ra", "Dott.ssa", "Avv.", "Ing.", "Geom.", "Rag."]:
            assert normalizza(f"{titolo} Anna Bianchi") == normalizza("anna bianchi")

    def test_uniforma_spazi_multipli(self):
        assert normalizza("Mario   Rossi") == "mario rossi"


class TestEuristiche:
    def test_ordine_dei_token_indifferente(self):
        assert chiavi_equivalenti("Rossi Mario", "Mario Rossi") is True

    def test_iniziale_compatibile(self):
        assert chiavi_equivalenti("M. Rossi", "Mario Rossi") is True

    def test_iniziale_incompatibile(self):
        assert chiavi_equivalenti("G. Rossi", "Mario Rossi") is False

    def test_cognomi_diversi_non_equivalenti(self):
        assert chiavi_equivalenti("Mario Rossi", "Mario Bianchi") is False


class TestSegnaposto:
    def test_indice_incrementale_per_tipo(self):
        f = fascicolo_vuoto("f1")
        assert prossimo_placeholder(f, Category.PERSONA) == "[PERSONA_1]"
        assert prossimo_placeholder(f, Category.PERSONA) == "[PERSONA_2]"
        assert prossimo_placeholder(f, Category.IBAN) == "[IBAN_1]"

    def test_gli_indici_non_vengono_riciclati(self):
        f = fascicolo_vuoto("f1")
        prossimo_placeholder(f, Category.PERSONA)
        prossimo_placeholder(f, Category.PERSONA)
        f.entities.clear()  # come se un'entità fosse stata fusa via
        assert prossimo_placeholder(f, Category.PERSONA) == "[PERSONA_3]"


class TestAggregazione:
    def test_stesso_valore_nello_stesso_documento_e_una_sola_entita(self):
        f = fascicolo_vuoto("f1")
        doc = documento("d1", "IBAN IT60X0542811101000000123456 e ancora "
                              "IT60X0542811101000000123456.")
        analizza_documento(f, doc, usa_ner=False)
        iban = [e for e in f.entities.values() if e.category is Category.IBAN]
        assert len(iban) == 1
        assert len([s for s in f.spans if s.category is Category.IBAN]) == 2

    def test_stesso_valore_in_documenti_diversi_usa_lo_stesso_segnaposto(self):
        f = fascicolo_vuoto("f1")
        for doc_id in ("d1", "d2"):
            analizza_documento(
                f, documento(doc_id, "Bonifico su IT60X0542811101000000123456."),
                usa_ner=False,
            )
        iban = [e for e in f.entities.values() if e.category is Category.IBAN]
        assert len(iban) == 1
        assert iban[0].placeholder == "[IBAN_1]"

    def test_valori_diversi_ottengono_segnaposto_diversi(self):
        f = fascicolo_vuoto("f1")
        analizza_documento(
            f,
            documento("d1", "Email mario@esempio.it e anna@esempio.it."),
            usa_ner=False,
        )
        email = sorted(
            e.placeholder for e in f.entities.values() if e.category is Category.EMAIL
        )
        assert email == ["[EMAIL_1]", "[EMAIL_2]"]

    def test_gli_span_risultanti_non_si_sovrappongono(self):
        f = fascicolo_vuoto("f1")
        analizza_documento(
            f,
            documento("d1", "CF RSSMRA85M01H501Q, P. IVA 12345678903, "
                            "firmato il 14/03/2024 per € 1.250,00."),
            usa_ner=False,
        )
        ordinati = sorted(f.spans, key=lambda s: s.start)
        for precedente, successivo in zip(ordinati, ordinati[1:]):
            assert precedente.end <= successivo.start

    def test_ogni_span_ha_una_entita(self):
        f = fascicolo_vuoto("f1")
        analizza_documento(f, documento("d1", "P. IVA 12345678903."), usa_ner=False)
        for span in f.spans:
            assert span.entity_id in f.entities


class TestOmonimi:
    def _fascicolo_con_omonimo(self):
        f = fascicolo_vuoto("f1")
        for doc_id in ("d1", "d2"):
            doc = documento(doc_id, "Contratto con Giuseppe Verdi.")
            analizza_documento(f, doc, usa_ner=False)
            # simulo l'esito del NER senza caricare il modello
            inizio = doc.text.index("Giuseppe Verdi")
            _registra_manuale(f, doc, inizio, inizio + len("Giuseppe Verdi"))
        return f

    def test_omonimia_senza_cf_apre_una_ambiguita_bloccante(self):
        from cryptocustode.core.entities import risolvi_ambiguita_omonimia
        f = self._fascicolo_con_omonimo()
        risolvi_ambiguita_omonimia(f)
        bloccanti = [a for a in f.ambiguities if a.blocca_approvazione]
        assert len(bloccanti) == 1
        assert bloccanti[0].kind is AmbiguityKind.SAME_NAME_NO_CF


def _registra_manuale(fascicolo, documento, inizio, fine):
    """Aggiunge uno span PERSONA come se l'utente lo avesse selezionato a mano."""
    from cryptocustode.core.entities import aggiungi_span_manuale
    aggiungi_span_manuale(fascicolo, documento, inizio, fine, Category.PERSONA)
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

```
.venv\Scripts\python -m pytest tests/test_entities.py -v
```

Atteso: FAIL con `ModuleNotFoundError`.

- [ ] **Step 3: Scrivere `cryptocustode/core/entities.py`**

```python
"""Aggregazione degli span in entità con segnaposto stabili sul fascicolo.

Principio guida (spec §7): fondere per errore corrompe i dati e rivela il nome
di una persona al posto di un'altra; separare per errore degrada soltanto la
qualità della risposta dell'IA. Quindi separare è il default, e solo il codice
fiscale identico autorizza una fusione automatica.
"""
from __future__ import annotations

import re
import unicodedata
import uuid

from cryptocustode.core.detect.ner import trova_per_ner
from cryptocustode.core.detect.rules import trova_per_regole
from cryptocustode.core.models import (
    Ambiguity,
    AmbiguityKind,
    Category,
    Document,
    Entity,
    Fascicolo,
    Source,
    Span,
)
from cryptocustode.core.spans import risolvi

_TITOLI = (
    "sig.ra", "sig.", "sig", "signora", "signor", "dott.ssa", "dott.", "dottore",
    "dottoressa", "avv.", "avvocato", "ing.", "ingegner", "arch.", "geom.",
    "rag.", "prof.ssa", "prof.", "on.", "spett.le", "spett.",
)

# Categorie per cui ha senso confrontare varianti di nome. Su un IBAN o un CF
# l'uguaglianza è esatta o non è.
_CATEGORIE_CON_VARIANTI = {Category.PERSONA, Category.AZIENDA}


def normalizza(valore: str) -> str:
    """Chiave di confronto: NFKC, minuscolo, senza titoli, spazi collassati."""
    testo = unicodedata.normalize("NFKC", valore).casefold().strip()
    testo = re.sub(r"\s+", " ", testo)
    cambiato = True
    while cambiato:
        cambiato = False
        for titolo in _TITOLI:
            if testo.startswith(titolo + " ") or testo == titolo:
                testo = testo[len(titolo):].strip()
                cambiato = True
    return testo


def _token(valore: str) -> list[str]:
    return [t for t in re.split(r"[\s,]+", normalizza(valore)) if t]


def chiavi_equivalenti(a: str, b: str) -> bool:
    """Vero se le due stringhe possono indicare la stessa entità, a meno
    dell'ordine dei token e delle iniziali abbreviate. È un suggerimento:
    non autorizza da sé alcuna fusione."""
    primi, secondi = _token(a), _token(b)
    if not primi or not secondi or len(primi) != len(secondi):
        return False
    if sorted(primi) == sorted(secondi):
        return True
    rimasti = list(secondi)
    for token in primi:
        accoppiato = None
        for candidato in rimasti:
            if token == candidato or _iniziale_compatibile(token, candidato):
                accoppiato = candidato
                break
        if accoppiato is None:
            return False
        rimasti.remove(accoppiato)
    return True


def _iniziale_compatibile(a: str, b: str) -> bool:
    breve, lungo = sorted((a.rstrip("."), b.rstrip(".")), key=len)
    return len(breve) == 1 and len(lungo) > 1 and lungo.startswith(breve)


def prossimo_placeholder(fascicolo: Fascicolo, categoria: Category) -> str:
    """Assegna il prossimo indice della categoria. I contatori non tornano mai
    indietro: un indice bruciato resta bruciato (spec §5)."""
    fascicolo.counters[categoria] = fascicolo.counters.get(categoria, 0) + 1
    return f"[{categoria.value}_{fascicolo.counters[categoria]}]"


def _entita_per_valore(
    fascicolo: Fascicolo, categoria: Category, valore: str
) -> Entity | None:
    chiave = normalizza(valore)
    for entita in fascicolo.entities.values():
        if entita.category is not categoria:
            continue
        if any(normalizza(v) == chiave for v in entita.variants):
            return entita
    return None


def _crea_entita(fascicolo: Fascicolo, categoria: Category, valore: str) -> Entity:
    entita = Entity(
        entity_id=str(uuid.uuid4()),
        category=categoria,
        placeholder=prossimo_placeholder(fascicolo, categoria),
        canonical_value=valore,
        variants={valore},
    )
    fascicolo.entities[entita.entity_id] = entita
    return entita


def _assegna(fascicolo: Fascicolo, documento: Document, span: Span) -> Span:
    valore = documento.text[span.start:span.end]
    entita = _entita_per_valore(fascicolo, span.category, valore)
    if entita is None:
        entita = _crea_entita(fascicolo, span.category, valore)
    else:
        entita.variants.add(valore)
    return Span(
        span_id=span.span_id, doc_id=span.doc_id, start=span.start, end=span.end,
        category=span.category, source=span.source, entity_id=entita.entity_id,
        enabled=span.enabled,
    )


def analizza_documento(
    fascicolo: Fascicolo, documento: Document, usa_ner: bool = True
) -> None:
    """Analizza un documento e aggiunge al fascicolo span ed entità.

    `usa_ner=False` esiste per i test che non devono caricare 550 MB di modello.
    """
    trovati = trova_per_regole(documento.text, documento.doc_id)
    if usa_ner:
        trovati += trova_per_ner(documento.text, documento.doc_id)
    for span in risolvi(trovati):
        fascicolo.spans.append(_assegna(fascicolo, documento, span))


def aggiungi_span_manuale(
    fascicolo: Fascicolo, documento: Document, inizio: int, fine: int,
    categoria: Category,
) -> Span:
    """Tagging manuale dell'utente sul testo selezionato (punto 5 della consegna)."""
    grezzo = Span(
        span_id=f"{documento.doc_id}:{inizio}-{fine}:{categoria.value}:manuale",
        doc_id=documento.doc_id, start=inizio, end=fine, category=categoria,
        source=Source.MANUAL, entity_id="",
    )
    span = _assegna(fascicolo, documento, grezzo)
    fascicolo.spans.append(span)
    return span


def risolvi_ambiguita_omonimia(fascicolo: Fascicolo) -> None:
    """Apre una ambiguità per ogni entità che compare in più documenti con lo
    stesso nome e senza codice fiscale che la discrimini (spec §7, TC-03)."""
    documenti_per_entita: dict[str, set[str]] = {}
    span_per_entita: dict[str, list[str]] = {}
    for span in fascicolo.spans:
        documenti_per_entita.setdefault(span.entity_id, set()).add(span.doc_id)
        span_per_entita.setdefault(span.entity_id, []).append(span.span_id)

    gia_aperte = {
        tuple(sorted(a.candidate_entity_ids)) for a in fascicolo.ambiguities
    }
    for entity_id, documenti in documenti_per_entita.items():
        entita = fascicolo.entities.get(entity_id)
        if entita is None or entita.category not in _CATEGORIE_CON_VARIANTI:
            continue
        if len(documenti) < 2 or entita.cf is not None:
            continue
        if (entity_id,) in gia_aperte:
            continue
        fascicolo.ambiguities.append(
            Ambiguity(
                ambiguity_id=str(uuid.uuid4()),
                kind=AmbiguityKind.SAME_NAME_NO_CF,
                category=entita.category,
                candidate_entity_ids=[entity_id],
                occurrence_span_ids=span_per_entita[entity_id],
            )
        )
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

```
.venv\Scripts\python -m pytest tests/test_entities.py -v
```

Atteso: PASS su tutti.

- [ ] **Step 5: Eseguire l'intera suite per controllare di non aver rotto nulla**

```
.venv\Scripts\python -m pytest -v -m "not lento"
```

Atteso: PASS su tutto, con i test del Task 6 saltati.

- [ ] **Step 6: Commit**

```
git add cryptocustode/core/entities.py tests/test_entities.py
git commit -m "feat: aggregazione in entità, euristiche sui nomi e coda delle omonimie"
```

---

### Task 8: Masking puro e hash canonico

**Files:**
- Create: `cryptocustode/core/mask.py`
- Test: `tests/test_mask.py`

**Interfaces:**
- Consumes: tutti i tipi del Task 2.
- Produces: `span_attivo(span, fascicolo) -> bool`, `maschera(testo, spans, entities) -> str`, `maschera_documento(fascicolo, documento) -> str`, `hash_approvazione(fascicolo) -> str`. Usate dal piano 2 (macchina a stati ed export).

**Vincolo:** nessuna I/O, nessun orologio, nessun random. Le sostituzioni procedono da destra a sinistra, così gli offset non ancora applicati restano validi (spec §9).

- [ ] **Step 1: Scrivere i test**

`tests/test_mask.py`:

```python
import dataclasses
import re

from cryptocustode.core.mask import (
    hash_approvazione,
    maschera,
    maschera_documento,
    span_attivo,
)
from cryptocustode.core.models import (
    Category,
    Document,
    Entity,
    Source,
    Span,
    State,
    fascicolo_vuoto,
)

FORMATO_SEGNAPOSTO = re.compile(r"\[[A-Z]+_\d+\]")


def scenario():
    """Un fascicolo con un documento, due entità e due span."""
    testo = "Mario Rossi paga a Anna Bianchi la somma dovuta."
    doc = Document(doc_id="d1", filename="contratto.txt", text=testo,
                   page_offsets=[0], sha256="x")
    f = fascicolo_vuoto("f1")
    f.documents.append(doc)
    f.entities["e1"] = Entity(
        entity_id="e1", category=Category.PERSONA, placeholder="[PERSONA_1]",
        canonical_value="Mario Rossi", variants={"Mario Rossi"},
    )
    f.entities["e2"] = Entity(
        entity_id="e2", category=Category.PERSONA, placeholder="[PERSONA_2]",
        canonical_value="Anna Bianchi", variants={"Anna Bianchi"},
    )
    f.spans.append(Span(span_id="s1", doc_id="d1", start=0, end=11,
                        category=Category.PERSONA, source=Source.NER, entity_id="e1"))
    f.spans.append(Span(span_id="s2", doc_id="d1", start=19, end=31,
                        category=Category.PERSONA, source=Source.NER, entity_id="e2"))
    return f, doc


class TestMascheratura:
    def test_sostituisce_tutti_gli_span(self):
        f, doc = scenario()
        assert maschera_documento(f, doc) == (
            "[PERSONA_1] paga a [PERSONA_2] la somma dovuta."
        )

    def test_nessun_valore_originale_sopravvive(self):
        f, doc = scenario()
        mascherato = maschera_documento(f, doc)
        for entita in f.entities.values():
            for variante in entita.variants:
                assert variante not in mascherato

    def test_i_segnaposto_rispettano_il_formato(self):
        f, doc = scenario()
        for trovato in FORMATO_SEGNAPOSTO.finditer(maschera_documento(f, doc)):
            assert trovato.group(0).startswith("[PERSONA_")

    def test_span_disabilitato_non_viene_mascherato(self):
        f, doc = scenario()
        f.spans[0] = dataclasses.replace(f.spans[0], enabled=False)
        mascherato = maschera_documento(f, doc)
        assert "Mario Rossi" in mascherato
        assert "[PERSONA_2]" in mascherato

    def test_categoria_disattivata_non_viene_mascherata(self):
        f, doc = scenario()
        f.category_enabled[Category.PERSONA] = False
        assert maschera_documento(f, doc) == doc.text

    def test_span_attivo_richiede_entrambi_gli_interruttori(self):
        f, _ = scenario()
        span = f.spans[0]
        assert span_attivo(span, f) is True
        f.category_enabled[Category.PERSONA] = False
        assert span_attivo(span, f) is False

    def test_ordine_di_sostituzione_non_corrompe_gli_offset(self):
        # tre span consecutivi: se si sostituisse da sinistra, gli offset
        # successivi slitterebbero
        testo = "AAAA BBBB CCCC"
        doc = Document(doc_id="d1", filename="a.txt", text=testo,
                       page_offsets=[0], sha256="x")
        f = fascicolo_vuoto("f1")
        f.documents.append(doc)
        for indice, (inizio, fine) in enumerate([(0, 4), (5, 9), (10, 14)], start=1):
            f.entities[f"e{indice}"] = Entity(
                entity_id=f"e{indice}", category=Category.PRATICA,
                placeholder=f"[PRATICA_{indice}]",
                canonical_value=testo[inizio:fine], variants={testo[inizio:fine]},
            )
            f.spans.append(Span(span_id=f"s{indice}", doc_id="d1", start=inizio,
                                end=fine, category=Category.PRATICA,
                                source=Source.RULE, entity_id=f"e{indice}"))
        assert maschera_documento(f, doc) == "[PRATICA_1] [PRATICA_2] [PRATICA_3]"

    def test_testo_senza_span_resta_identico(self):
        doc = Document(doc_id="d1", filename="a.txt", text="Nulla da nascondere.",
                       page_offsets=[0], sha256="x")
        f = fascicolo_vuoto("f1")
        assert maschera(doc.text, [], {}) == doc.text


class TestHashDiApprovazione:
    def test_deterministico(self):
        f, _ = scenario()
        assert hash_approvazione(f) == hash_approvazione(f)

    def test_cambia_se_cambia_uno_span(self):
        f, _ = scenario()
        prima = hash_approvazione(f)
        f.spans.pop()
        assert hash_approvazione(f) != prima

    def test_cambia_se_cambia_un_toggle_di_categoria(self):
        f, _ = scenario()
        prima = hash_approvazione(f)
        f.category_enabled[Category.PERSONA] = False
        assert hash_approvazione(f) != prima

    def test_indipendente_dall_ordine_dei_documenti(self):
        f, doc = scenario()
        secondo = Document(doc_id="d2", filename="allegato.txt", text="Testo neutro.",
                           page_offsets=[0], sha256="y")
        f.documents.append(secondo)
        atteso = hash_approvazione(f)
        f.documents.reverse()
        assert hash_approvazione(f) == atteso

    def test_e_uno_sha256_esadecimale(self):
        f, _ = scenario()
        assert re.fullmatch(r"[0-9a-f]{64}", hash_approvazione(f))

    def test_non_dipende_dallo_stato_del_fascicolo(self):
        # l'hash misura il testo, non il ciclo di vita
        f, _ = scenario()
        prima = hash_approvazione(f)
        f.state = State.APPROVED
        assert hash_approvazione(f) == prima
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

```
.venv\Scripts\python -m pytest tests/test_mask.py -v
```

Atteso: FAIL con `ModuleNotFoundError`.

- [ ] **Step 3: Scrivere `cryptocustode/core/mask.py`**

```python
"""Mascheratura e hash canonico di approvazione.

Modulo deliberatamente puro: nessuna I/O, nessun orologio, nessun random. Se
mascherare lo stesso fascicolo due volte producesse output diversi, il
confronto con `approval_hash` fallirebbe a caso e il controllo di integrità
diventerebbe rumore invece di una difesa (spec §4, invariante 2).
"""
from __future__ import annotations

import hashlib

from cryptocustode.core.models import Document, Entity, Fascicolo, Span


def span_attivo(span: Span, fascicolo: Fascicolo) -> bool:
    """Uno span viene mascherato solo se sono chiusi entrambi gli interruttori:
    quello sul singolo span e quello sulla categoria (spec §5)."""
    return span.enabled and fascicolo.category_enabled.get(span.category, True)


def maschera(testo: str, spans: list[Span], entities: dict[str, Entity]) -> str:
    """Sostituisce gli span con i segnaposto delle rispettive entità.

    Procede da destra a sinistra: così ogni sostituzione lascia validi gli
    offset di quelle ancora da applicare (spec §9).
    """
    risultato = testo
    for span in sorted(spans, key=lambda s: s.start, reverse=True):
        entita = entities.get(span.entity_id)
        if entita is None:
            continue
        risultato = risultato[:span.start] + entita.placeholder + risultato[span.end:]
    return risultato


def maschera_documento(fascicolo: Fascicolo, documento: Document) -> str:
    attivi = [
        s for s in fascicolo.spans
        if s.doc_id == documento.doc_id and span_attivo(s, fascicolo)
    ]
    return maschera(documento.text, attivi, fascicolo.entities)


def hash_approvazione(fascicolo: Fascicolo) -> str:
    """SHA-256 su una serializzazione canonica dei testi mascherati.

    I documenti sono ordinati per nome file e ciascuno emette
    `filename\\n<lunghezza>\\n<testo>`. La lunghezza esplicita rende la
    concatenazione non ambigua, così due fascicoli diversi non possono
    produrre lo stesso digest (spec §8).
    """
    digest = hashlib.sha256()
    for documento in sorted(fascicolo.documents, key=lambda d: d.filename):
        mascherato = maschera_documento(fascicolo, documento)
        blocco = f"{documento.filename}\n{len(mascherato)}\n{mascherato}"
        digest.update(blocco.encode("utf-8"))
    return digest.hexdigest()
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

```
.venv\Scripts\python -m pytest tests/test_mask.py -v
```

Atteso: PASS su tutti.

- [ ] **Step 5: Eseguire l'intera suite**

```
.venv\Scripts\python -m pytest -v
```

Atteso: PASS su tutto, compresi i test `lento` del Task 6.

- [ ] **Step 6: Commit**

```
git add cryptocustode/core/mask.py tests/test_mask.py
git commit -m "feat: mascheratura pura e hash canonico di approvazione"
```

---

## Fine del piano 1

Al termine il motore è completo e verificato: dato un testo italiano produce span validati, entità con segnaposto stabili sul fascicolo, una coda di omonimie da far decidere all'utente, e il testo mascherato con il suo hash canonico.

**Cosa resta fuori, e in quale piano:**

- **Piano 2** — caricamento TXT e PDF, verdetto scansione, controllo dei segnaposto preesistenti, tetto di 10 documenti, macchina a stati, gate di esportazione, ripristino della risposta dell'IA, vault cifrato.
- **Piano 3** — route HTTP, interfaccia web di revisione, test anti-fuga end-to-end, documenti di verifica distinti da quelli di sviluppo, README con istruzioni di avvio e limiti noti, script `tools/e2e_gemini.py`.

**Limite noto introdotto da questo piano:** `analizza_documento` accetta il parametro `usa_ner` per permettere ai test di evitare il caricamento del modello. È una comodità di test che compare nella firma di produzione; se nel piano 3 diventasse un'opzione esposta all'utente, va rimossa e sostituita con una iniezione della funzione di riconoscimento.
