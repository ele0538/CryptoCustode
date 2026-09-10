# Ingresso documenti, stato e persistenza — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Portare un fascicolo dal file caricato fino al testo mascherato esportabile, con la macchina a stati, il vault cifrato e il ripristino della risposta dell'IA.

**Architecture:** Il piano 1 ha costruito il motore di riconoscimento puro sotto `core/`. Questo piano aggiunge i due bordi che gli mancano: l'ingresso (`core/ingest/`, che trasforma byte in `Document` e respinge ciò che non si può trattare) e la persistenza con il ciclo di vita (`core/vault.py`, `core/unmask.py`, `state/session.py`). Resta fuori tutto ciò che è HTTP: il piano 3 costruirà le route sopra le funzioni che questo piano espone.

**Tech Stack:** Python 3.14.5, PyMuPDF 1.28 (estrazione PDF), `cryptography` 48 (AES-256-GCM, PBKDF2-HMAC-SHA256), pytest 9.1. Nessuna dipendenza nuova.

**Spec:** `docs/superpowers/specs/2026-09-10-cryptocustode-design.md` — autorità vincolante. Il piano argomenta dalla spec; chi esegue legge entrambi.

## Global Constraints

- **Python 3.14.5**, unico interprete installato. Ambiente isolato in `.venv/` nella radice del repo. Tutti i comandi usano l'interprete del venv: `.venv\Scripts\python`.
- **`cryptocustode/core/` non deve importare** `fastapi`, `uvicorn`, `starlette`, né `cryptocustode.state`. Garantito dal test di architettura di `tests/test_architettura.py`.
- **Nessuna funzione in `core/mask.py` accede a filesystem, orologio o random.** Il vincolo riguarda `mask.py` soltanto: `core/vault.py` usa deliberatamente random (salt, nonce) e orologio (`created_at`).
- **Solo il gate di esportazione fa uscire il testo mascherato.** In questo piano il gate è `state/session.py::export_sanitized_text`; nel piano 3 `api/export.py` sarà l'unico chiamante HTTP.
- **Il dizionario delle corrispondenze non lascia mai il processo** se non come blob cifrato dentro il `.vault`.
- **Naming:** i nomi dei tipi restano quelli della spec (`Document`, `Span`, `Entity`, `Ambiguity`, `Fascicolo`, `Category`, `Source`, `State`); i nomi delle eccezioni restano quelli della spec §13, in inglese; funzioni, variabili e messaggi sono in italiano. I messaggi d'errore rivolti all'utente sono in italiano.
- **Formato segnaposto:** `[TIPO_INDICE]`, conforme a `\[[A-Z]+_\d+\]`. Indice incrementale per tipo, globale al fascicolo, **mai riciclato**.
- **Tutti i dati di test sono inventati.** Nessun dato personale reale, in nessun file del repo.
- **Un commit per task**, con il messaggio indicato nell'ultimo step del task.
- I marker `lento` (carica il modello spaCy) e `rete` (richiede connettività) sono già dichiarati in `pyproject.toml`. Nessun test di questo piano ha bisogno di entrambi.

## Scostamenti dalla spec, decisi in questo piano

Tre punti in cui il piano si discosta dalla lettera della spec. Ognuno è reversibile e va segnalato al revisore finale.

1. **`counters` entra nel vault.** La spec §10 elenca il contenuto cifrato senza `counters`, ma `Fascicolo.counters` è ciò che rende gli indici dei segnaposto non riciclabili (spec §7). Senza persisterlo, riaprire un vault e aggiungere un'entità riassegnerebbe `[PERSONA_1]` a una persona diversa da quella che l'aveva prima della chiusura, e un testo ripristinato con il vecchio dizionario diventerebbe silenziosamente sbagliato. È una lacuna della spec, non una comodità: il campo va salvato.
2. **`export_sanitized_text` riceve lo store come parametro.** La spec §8 scrive `export_sanitized_text(fascicolo_id: str) -> dict[str, str]`, che presuppone uno store globale di processo. Passarlo esplicitamente mantiene la funzione testabile senza stato globale; sarà `api/export.py` nel piano 3 a legare lo store dell'applicazione. La firma della spec resta realizzabile con una riga di adattamento.
3. **`[PERSON_1]` è un segnaposto sconosciuto, non malformato.** La spec §11 lo elenca al passo 3 fra i quasi-segnaposto "con un tipo inesistente", ma la regex severa `\[[A-Z]+_\d+\]` lo accetta: è ben formato, e il fatto che `PERSON` non esista è una questione di dizionario, non di forma. Lo classifichiamo al passo 4, `UnknownPlaceholder`. Per l'utente l'esito non cambia — il ripristino si interrompe comunque — cambia solo l'errore sollevato. Restano `MalformedPlaceholder` i casi che la regex severa davvero non accetta: `[PERSONA_1` senza chiusura e `[persona_1]` in minuscolo.

## File Structure

| File | Responsabilità | Task |
|---|---|---|
| `cryptocustode/core/errors.py` | la tassonomia degli errori di dominio della spec §13 | 1 |
| `cryptocustode/core/ingest/__init__.py` | marcatore di package | 1 |
| `cryptocustode/core/ingest/config.py` | le due soglie del verdetto di scansione | 1 |
| `cryptocustode/core/ingest/txt_loader.py` | decodifica UTF-8 strict | 2 |
| `cryptocustode/core/ingest/pdf_loader.py` | PyMuPDF: estrazione, offset di pagina, verdetto di scansione | 3 |
| `cryptocustode/core/ingest/loader.py` | facciata: dispatch per estensione, tetto dei 10, segnaposto preesistenti | 4 |
| `cryptocustode/core/vault.py` | AES-256-GCM + PBKDF2, header versionato e autenticato | 5 |
| `cryptocustode/core/unmask.py` | ripristino della risposta dell'IA | 6 |
| `cryptocustode/state/session.py` | transizioni, approvazione, `SessionStore`, gate di esportazione | 7, 8 |
| `tests/pdf_di_prova.py` | costruisce i PDF di test con PyMuPDF, niente binari nel repo | 3 |

Un file di test per ciascun modulo, più `tests/test_matrice_consegna.py` per il Task 9.

## Grafo delle dipendenze

Il Task 1 precede tutto. Poi i Task 2, 3, 5, 6 e 7 sono indipendenti fra loro; il 4 richiede 2 e 3; l'8 richiede il 7; il 9 richiede tutto.

```
1 ──┬─> 2 ──┐
    ├─> 3 ──┴─> 4 ──┐
    ├─> 5 ──────────┤
    ├─> 6 ──────────┼─> 9
    └─> 7 ──> 8 ────┘
```

---

### Task 1: Errori di dominio e configurazione

**Files:**
- Create: `cryptocustode/core/errors.py`
- Create: `cryptocustode/core/ingest/__init__.py`
- Create: `cryptocustode/core/ingest/config.py`
- Test: `tests/test_errori.py`

**Interfaces:**
- Consumes: niente.
- Produces: da `errors.py` la base `CryptoCustodeError` e le nove sottoclassi `InvalidEncoding`, `ScannedDocumentRejected`, `FascicoloFull`, `ExportNotAllowed`, `IntegrityError`, `UnresolvedAmbiguities`, `UnknownPlaceholder`, `MalformedPlaceholder`, `VaultUnreadable`; da `ingest/config.py` le costanti `CARATTERI_MINIMI_PAGINA: int` e `FRAZIONE_IMMAGINE_MASSIMA: float`. Usate da tutti i task successivi.

Questo task esiste per una ragione pratica: otto task successivi sollevano questi errori, e se ciascuno creasse il proprio file gli ultimi arrivati troverebbero conflitti. Definirli una volta all'inizio rende il resto del piano parallelizzabile.

- [ ] **Step 1: Scrivere i test**

`tests/test_errori.py`:

```python
import inspect

import pytest

from cryptocustode.core import errors
from cryptocustode.core.errors import CryptoCustodeError
from cryptocustode.core.ingest import config

# I nomi sono quelli della tabella della spec §13, in inglese come i tipi di dominio.
NOMI_ATTESI = {
    "InvalidEncoding",
    "ScannedDocumentRejected",
    "FascicoloFull",
    "ExportNotAllowed",
    "IntegrityError",
    "UnresolvedAmbiguities",
    "UnknownPlaceholder",
    "MalformedPlaceholder",
    "VaultUnreadable",
}


def test_esistono_tutti_gli_errori_della_spec():
    definiti = {
        nome
        for nome, oggetto in inspect.getmembers(errors, inspect.isclass)
        if issubclass(oggetto, CryptoCustodeError) and oggetto is not CryptoCustodeError
    }
    assert definiti == NOMI_ATTESI


@pytest.mark.parametrize("nome", sorted(NOMI_ATTESI))
def test_ogni_errore_deriva_dalla_base(nome):
    assert issubclass(getattr(errors, nome), CryptoCustodeError)


def test_la_base_deriva_da_exception():
    assert issubclass(CryptoCustodeError, Exception)


def test_un_errore_conserva_il_messaggio():
    errore = errors.FascicoloFull("massimo 10 documenti per fascicolo")
    assert str(errore) == "massimo 10 documenti per fascicolo"


def test_soglie_del_verdetto_di_scansione():
    # Valori della tabella della spec §12. Vivono in un modulo di configurazione
    # perché siano ritoccabili senza toccare la logica.
    assert config.CARATTERI_MINIMI_PAGINA == 40
    assert config.FRAZIONE_IMMAGINE_MASSIMA == 0.5
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

Run: `.venv\Scripts\python -m pytest tests/test_errori.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'cryptocustode.core.errors'`.

- [ ] **Step 3: Scrivere `cryptocustode/core/errors.py`**

```python
"""Gli errori di dominio della spec §13.

I nomi restano in inglese come i tipi di dominio; i messaggi che li accompagnano
sono in italiano perché arrivano all'utente.
"""


class CryptoCustodeError(Exception):
    """Base di tutti gli errori di dominio, così un chiamante può catturarli
    tutti insieme senza elencarli."""


class InvalidEncoding(CryptoCustodeError):
    """TXT che non è UTF-8 valido."""


class ScannedDocumentRejected(CryptoCustodeError):
    """PDF con almeno una pagina che è una scansione."""


class FascicoloFull(CryptoCustodeError):
    """Undicesimo documento in un fascicolo."""


class ExportNotAllowed(CryptoCustodeError):
    """Esportazione richiesta con il fascicolo in uno stato diverso da APPROVED."""


class IntegrityError(CryptoCustodeError):
    """Il testo mascherato è cambiato dopo l'approvazione."""


class UnresolvedAmbiguities(CryptoCustodeError):
    """Approvazione richiesta con ambiguità bloccanti ancora aperte."""


class UnknownPlaceholder(CryptoCustodeError):
    """Segnaposto ben formato ma estraneo al dizionario del fascicolo."""


class MalformedPlaceholder(CryptoCustodeError):
    """Frammento che somiglia a un segnaposto senza esserlo."""


class VaultUnreadable(CryptoCustodeError):
    """Password errata o file danneggiato: i due casi non si distinguono."""
```

- [ ] **Step 4: Scrivere `cryptocustode/core/ingest/__init__.py`**

```python
"""Ingresso dei documenti: da byte a `Document`, con i rifiuti del caso."""
```

- [ ] **Step 5: Scrivere `cryptocustode/core/ingest/config.py`**

```python
"""Le soglie del verdetto di scansione (spec §12).

Stanno qui perché siano ritoccabili e testabili senza toccare la logica che le usa.
"""

# Sotto questa soglia una pagina si considera priva di testo utile.
CARATTERI_MINIMI_PAGINA = 40

# Frazione dell'area di pagina coperta da immagini oltre la quale la pagina
# si considera prevalentemente raster.
FRAZIONE_IMMAGINE_MASSIMA = 0.5
```

- [ ] **Step 6: Eseguire i test e verificare che passino**

Run: `.venv\Scripts\python -m pytest tests/test_errori.py -v`
Expected: PASS, 13 test.

- [ ] **Step 7: Eseguire l'intera suite**

Run: `.venv\Scripts\python -m pytest -m "not lento"`
Expected: nessuna regressione; il test di architettura resta verde.

- [ ] **Step 8: Commit**

```bash
git add cryptocustode/core/errors.py cryptocustode/core/ingest/ tests/test_errori.py
git commit -m "feat: tassonomia degli errori di dominio e soglie del verdetto di scansione"
```

---

### Task 2: Caricatore TXT

**Files:**
- Create: `cryptocustode/core/ingest/txt_loader.py`
- Test: `tests/test_txt_loader.py`

**Interfaces:**
- Consumes: `InvalidEncoding` dal Task 1.
- Produces: `carica_txt(contenuto: bytes) -> str`. Usata dal Task 4.

**Regola (spec §12):** decodifica UTF-8 *strict*, nessun fallback ad altre codifiche. Una decodifica errata altera i caratteri, i checksum di CF e IBAN smettono di tornare e i dati sensibili passano inosservati in silenzio. L'errore cita l'offset del byte incriminato.

- [ ] **Step 1: Scrivere i test**

`tests/test_txt_loader.py`:

```python
import pytest

from cryptocustode.core.errors import InvalidEncoding
from cryptocustode.core.ingest.txt_loader import carica_txt


def test_utf8_valido_viene_decodificato():
    assert carica_txt("Contratto firmato a Torino.".encode("utf-8")) == (
        "Contratto firmato a Torino."
    )


def test_accenti_e_simboli_sopravvivono():
    testo = "Società à è ì ò ù — € 1.200,00"
    assert carica_txt(testo.encode("utf-8")) == testo


def test_testo_vuoto_e_lecito():
    assert carica_txt(b"") == ""


def test_byte_non_utf8_solleva_invalid_encoding():
    # 0xE8 è "è" in latin-1: da solo non è una sequenza UTF-8 valida.
    with pytest.raises(InvalidEncoding):
        carica_txt("perch\xe8".encode("latin-1"))


def test_il_messaggio_cita_l_offset_del_byte():
    # "abc" occupa gli offset 0,1,2; il byte invalido sta all'offset 3.
    with pytest.raises(InvalidEncoding, match="3"):
        carica_txt(b"abc\xe8def")


def test_nessun_fallback_silenzioso_ad_altre_codifiche():
    # Con un fallback a latin-1 questa chiamata restituirebbe "perchè no"
    # invece di sollevare: è esattamente il comportamento che la spec vieta.
    with pytest.raises(InvalidEncoding):
        carica_txt("perch\xe8 no".encode("latin-1"))
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

Run: `.venv\Scripts\python -m pytest tests/test_txt_loader.py -v`
Expected: FAIL con `ModuleNotFoundError`.

- [ ] **Step 3: Scrivere `cryptocustode/core/ingest/txt_loader.py`**

```python
"""Decodifica dei TXT: UTF-8 strict e nient'altro (spec §12)."""

from __future__ import annotations

from cryptocustode.core.errors import InvalidEncoding


def carica_txt(contenuto: bytes) -> str:
    """Decodifica `contenuto` come UTF-8 strict.

    Nessun fallback ad altre codifiche: una decodifica errata altera i caratteri,
    i checksum di CF e IBAN smettono di tornare, e i dati sensibili passerebbero
    inosservati in silenzio (spec §12).
    """
    try:
        return contenuto.decode("utf-8")
    except UnicodeDecodeError as errore:
        raise InvalidEncoding(
            f"codifica non valida: il byte all'offset {errore.start} "
            "non fa parte di una sequenza UTF-8 valida"
        ) from errore
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

Run: `.venv\Scripts\python -m pytest tests/test_txt_loader.py -v`
Expected: PASS, 6 test.

- [ ] **Step 5: Commit**

```bash
git add cryptocustode/core/ingest/txt_loader.py tests/test_txt_loader.py
git commit -m "feat: caricatore TXT con decodifica UTF-8 strict"
```

---

### Task 3: Caricatore PDF e verdetto di scansione

**Files:**
- Create: `cryptocustode/core/ingest/pdf_loader.py`
- Create: `tests/pdf_di_prova.py`
- Test: `tests/test_pdf_loader.py`

**Interfaces:**
- Consumes: `ScannedDocumentRejected` dal Task 1; `CARATTERI_MINIMI_PAGINA` e `FRAZIONE_IMMAGINE_MASSIMA` da `ingest/config.py`.
- Produces: `carica_pdf(contenuto: bytes) -> tuple[str, list[int]]`, che restituisce il testo concatenato e gli offset di inizio di ogni pagina. Usata dal Task 4.

**La tabella del verdetto (spec §12).** Per ogni pagina, con `caratteri = len(pagina.get_text("text").strip())` e `frazione_immagini` uguale all'area coperta dalle immagini diviso l'area della pagina:

| Condizione | Verdetto |
|---|---|
| `caratteri == 0` e la pagina ha immagini | **respinto** — immagine senza testo: è una scansione |
| `caratteri == 0` e nessuna immagine | accettato — pagina bianca, non contiene nulla da proteggere |
| `caratteri < 40` e `frazione_immagini > 0.5` | **respinto** — pagina prevalentemente raster con testo residuo |
| altrimenti | accettato |

Il rifiuto riguarda **l'intero file**, che non entra nel fascicolo, con un messaggio che indica il numero di pagina. Nessuna elaborazione parziale. I PDF cifrati o protetti da password sono trattati come non leggibili e respinti (spec §16 limite 10).

**Sui PDF di test.** La spec §14 vieta di committare binari: i PDF si costruiscono al volo con PyMuPDF. `tests/pdf_di_prova.py` è un modulo di supporto, non un file di test — non contiene funzioni `test_`.

- [ ] **Step 1: Scrivere il costruttore dei PDF di prova**

`tests/pdf_di_prova.py`:

```python
"""Costruisce PDF di prova con PyMuPDF.

La spec §14 vieta di committare binari nel repo: ogni PDF usato dai test nasce
qui, riproducibile e ispezionabile.
"""

from __future__ import annotations

import fitz

# Testo abbondante: supera comodamente CARATTERI_MINIMI_PAGINA.
TESTO_DI_PAGINA = (
    "Contratto di locazione stipulato fra le parti in data odierna. "
    "Il conduttore dichiara di aver preso visione dell'immobile."
)


def _pagina_di_testo(documento: fitz.Document, testo: str = TESTO_DI_PAGINA) -> None:
    pagina = documento.new_page()
    pagina.insert_textbox(fitz.Rect(50, 50, 545, 400), testo, fontsize=11)


def _pagina_immagine(documento: fitz.Document, copertura: float = 1.0) -> None:
    """Pagina senza testo, coperta da un'immagine grigia: è una scansione."""
    pagina = documento.new_page()
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 200), False)
    pixmap.clear_with(128)
    riquadro = fitz.Rect(
        0, 0, pagina.rect.width * copertura, pagina.rect.height * copertura
    )
    pagina.insert_image(riquadro, pixmap=pixmap)


def _pagina_bianca(documento: fitz.Document) -> None:
    documento.new_page()


def _pagina_raster_con_testo_residuo(documento: fitz.Document) -> None:
    """Poco testo e immagine su gran parte della pagina: terza riga della tabella."""
    pagina = documento.new_page()
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 200), False)
    pixmap.clear_with(200)
    pagina.insert_image(pagina.rect, pixmap=pixmap)
    pagina.insert_textbox(fitz.Rect(50, 700, 545, 780), "Pag. 1", fontsize=9)


COSTRUTTORI = {
    "testo": _pagina_di_testo,
    "immagine": _pagina_immagine,
    "bianca": _pagina_bianca,
    "raster": _pagina_raster_con_testo_residuo,
}


def pdf_di_prova(pagine: list[str]) -> bytes:
    """Costruisce un PDF con una pagina per ogni voce di `pagine`.

    Le voci ammesse sono le chiavi di COSTRUTTORI.
    """
    documento = fitz.open()
    for tipo in pagine:
        COSTRUTTORI[tipo](documento)
    contenuto = documento.tobytes()
    documento.close()
    return contenuto
```

- [ ] **Step 2: Scrivere i test**

`tests/test_pdf_loader.py`:

```python
import pytest

from cryptocustode.core.errors import ScannedDocumentRejected
from cryptocustode.core.ingest.pdf_loader import carica_pdf
from tests.pdf_di_prova import TESTO_DI_PAGINA, pdf_di_prova


def test_pdf_di_solo_testo_viene_estratto():
    testo, _ = carica_pdf(pdf_di_prova(["testo", "testo"]))
    assert "Contratto di locazione" in testo
    assert testo.count("Contratto di locazione") == 2


def test_gli_offset_segnano_l_inizio_di_ogni_pagina():
    testo, offsets = carica_pdf(pdf_di_prova(["testo", "testo", "testo"]))
    assert len(offsets) == 3
    assert offsets[0] == 0
    # Ogni offset cade dentro il testo e in ordine crescente.
    assert offsets == sorted(offsets)
    assert offsets[-1] < len(testo)


def test_l_offset_della_seconda_pagina_punta_al_suo_testo():
    testo, offsets = carica_pdf(pdf_di_prova(["testo", "testo"]))
    assert testo[offsets[1]:].startswith(TESTO_DI_PAGINA[:20])


def test_pagina_immagine_senza_testo_viene_respinta():
    with pytest.raises(ScannedDocumentRejected):
        carica_pdf(pdf_di_prova(["immagine"]))


def test_il_rifiuto_indica_il_numero_di_pagina():
    # Quattro pagine di testo e una scansione in quinta posizione (TC-01).
    with pytest.raises(ScannedDocumentRejected, match="5"):
        carica_pdf(pdf_di_prova(["testo", "testo", "testo", "testo", "immagine"]))


def test_il_rifiuto_riguarda_l_intero_file():
    # Nessuna elaborazione parziale: anche con quattro pagine buone su cinque
    # la funzione solleva invece di restituire il testo delle pagine accettate.
    with pytest.raises(ScannedDocumentRejected):
        carica_pdf(pdf_di_prova(["testo", "immagine", "testo"]))


def test_pagina_bianca_senza_immagini_e_accettata():
    testo, offsets = carica_pdf(pdf_di_prova(["testo", "bianca"]))
    assert "Contratto di locazione" in testo
    assert len(offsets) == 2


def test_pagina_raster_con_testo_residuo_viene_respinta():
    with pytest.raises(ScannedDocumentRejected):
        carica_pdf(pdf_di_prova(["raster"]))


def test_pdf_illeggibile_viene_respinto():
    with pytest.raises(ScannedDocumentRejected):
        carica_pdf(b"questi non sono i byte di un PDF")
```

- [ ] **Step 3: Eseguire i test e verificare che falliscano**

Run: `.venv\Scripts\python -m pytest tests/test_pdf_loader.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'cryptocustode.core.ingest.pdf_loader'`.

- [ ] **Step 4: Scrivere `cryptocustode/core/ingest/pdf_loader.py`**

```python
"""Estrazione dei PDF con PyMuPDF e verdetto di scansione (spec §12)."""

from __future__ import annotations

import fitz

from cryptocustode.core.errors import ScannedDocumentRejected
from cryptocustode.core.ingest.config import (
    CARATTERI_MINIMI_PAGINA,
    FRAZIONE_IMMAGINE_MASSIMA,
)


def _frazione_coperta_da_immagini(pagina: fitz.Page) -> float:
    """Area delle immagini della pagina diviso l'area della pagina.

    I blocchi di tipo 1 del dizionario sono le immagini; il loro bbox è già in
    coordinate di pagina, quindi le aree sono confrontabili senza conversioni.
    """
    area_pagina = pagina.rect.get_area()
    if area_pagina == 0:
        return 0.0
    area_immagini = sum(
        fitz.Rect(blocco["bbox"]).get_area()
        for blocco in pagina.get_text("dict")["blocks"]
        if blocco["type"] == 1
    )
    return area_immagini / area_pagina


def _e_scansione(pagina: fitz.Page) -> bool:
    """La tabella del verdetto della spec §12, riga per riga."""
    caratteri = len(pagina.get_text("text").strip())
    frazione = _frazione_coperta_da_immagini(pagina)
    if caratteri == 0:
        # Immagine senza testo: è una scansione. Pagina bianca senza immagini:
        # non contiene nulla da proteggere, quindi passa.
        return frazione > 0
    return caratteri < CARATTERI_MINIMI_PAGINA and frazione > FRAZIONE_IMMAGINE_MASSIMA


def carica_pdf(contenuto: bytes) -> tuple[str, list[int]]:
    """Estrae il testo di un PDF e gli offset di inizio di ogni pagina.

    Solleva `ScannedDocumentRejected` se anche una sola pagina è una scansione,
    o se il file non è leggibile: il rifiuto riguarda l'intero file, mai una
    parte (spec §12). I PDF cifrati rientrano fra i non leggibili (spec §16.10).
    """
    try:
        documento = fitz.open(stream=contenuto, filetype="pdf")
    except Exception as errore:
        raise ScannedDocumentRejected(
            "documento bloccato: il PDF non è leggibile o è protetto da password"
        ) from errore

    try:
        if documento.needs_pass:
            raise ScannedDocumentRejected(
                "documento bloccato: il PDF è protetto da password"
            )
        pezzi: list[str] = []
        offsets: list[int] = []
        lunghezza = 0
        for numero, pagina in enumerate(documento, start=1):
            if _e_scansione(pagina):
                raise ScannedDocumentRejected(
                    f"documento bloccato: la pagina {numero} è una scansione, "
                    "il file non è stato caricato"
                )
            testo_pagina = pagina.get_text("text")
            offsets.append(lunghezza)
            pezzi.append(testo_pagina)
            lunghezza += len(testo_pagina)
        return "".join(pezzi), offsets
    finally:
        documento.close()
```

- [ ] **Step 5: Eseguire i test e verificare che passino**

Run: `.venv\Scripts\python -m pytest tests/test_pdf_loader.py -v`
Expected: PASS, 9 test.

- [ ] **Step 6: Eseguire l'intera suite**

Run: `.venv\Scripts\python -m pytest -m "not lento"`
Expected: nessuna regressione.

- [ ] **Step 7: Commit**

```bash
git add cryptocustode/core/ingest/pdf_loader.py tests/pdf_di_prova.py tests/test_pdf_loader.py
git commit -m "feat: estrazione PDF con verdetto di scansione per pagina"
```

---

### Task 4: Ingresso nel fascicolo — tetto e segnaposto preesistenti

**Files:**
- Create: `cryptocustode/core/ingest/loader.py`
- Test: `tests/test_loader.py`

**Interfaces:**
- Consumes: `carica_txt` dal Task 2; `carica_pdf` dal Task 3; `FascicoloFull` dal Task 1; `Document`, `Fascicolo`, `MAX_DOCUMENTI` da `core/models.py`.
- Produces: `segnaposto_preesistenti(testo: str) -> list[tuple[int, str]]`, `costruisci_documento(filename: str, contenuto: bytes) -> Document`, `aggiungi_documento(fascicolo: Fascicolo, documento: Document) -> None`. Usate dal piano 3.

**Il tetto dei 10.** `Fascicolo.MAX_DOCUMENTI` esiste dal piano 1 ma nessuno lo fa rispettare: il test di quel task verificava solo che la costante valesse 10, e la revisione lo annotò come rilievo differito proprio a questo piano. L'undicesimo documento solleva `FascicoloFull`.

**I segnaposto preesistenti (spec §12).** Se il testo estratto contiene già una stringa nella forma `\[[A-Z]+_\d+\]`, l'utente va avvisato con la posizione: al ripristino quella stringa verrebbe interpretata come un segnaposto e sostituita con dati veri, corrompendo il testo. È un **avviso**, non un rifiuto: la funzione restituisce l'elenco e chi la chiama decide come mostrarlo.

**`sha256`.** È il digest esadecimale dei byte originali del file, non del testo estratto: serve a riconoscere che due caricamenti sono lo stesso file anche quando l'estrazione cambia.

- [ ] **Step 1: Scrivere i test**

`tests/test_loader.py`:

```python
import hashlib

import pytest

from cryptocustode.core.errors import FascicoloFull, InvalidEncoding
from cryptocustode.core.ingest.loader import (
    aggiungi_documento,
    costruisci_documento,
    segnaposto_preesistenti,
)
from cryptocustode.core.models import Fascicolo, fascicolo_vuoto
from tests.pdf_di_prova import pdf_di_prova


def documento(indice: int):
    return costruisci_documento(f"doc{indice}.txt", b"Testo di prova.")


def test_txt_viene_riconosciuto_dall_estensione():
    doc = costruisci_documento("contratto.txt", "Torino".encode("utf-8"))
    assert doc.text == "Torino"
    assert doc.filename == "contratto.txt"


def test_pdf_viene_riconosciuto_dall_estensione():
    doc = costruisci_documento("contratto.pdf", pdf_di_prova(["testo"]))
    assert "Contratto di locazione" in doc.text


def test_l_estensione_e_insensibile_alle_maiuscole():
    doc = costruisci_documento("CONTRATTO.TXT", b"Torino")
    assert doc.text == "Torino"


def test_estensione_sconosciuta_viene_trattata_come_txt():
    # Un file senza estensione nota è tentato come testo: se non è UTF-8
    # l'errore arriva dal caricatore TXT, che è il comportamento voluto.
    with pytest.raises(InvalidEncoding):
        costruisci_documento("appunti", "perch\xe8".encode("latin-1"))


def test_sha256_e_dei_byte_originali():
    contenuto = "Torino".encode("utf-8")
    doc = costruisci_documento("a.txt", contenuto)
    assert doc.sha256 == hashlib.sha256(contenuto).hexdigest()


def test_i_doc_id_sono_distinti():
    primo = costruisci_documento("a.txt", b"uno")
    secondo = costruisci_documento("b.txt", b"due")
    assert primo.doc_id != secondo.doc_id


def test_il_txt_ha_un_solo_offset_di_pagina():
    doc = costruisci_documento("a.txt", b"Torino")
    assert doc.page_offsets == [0]


def test_dieci_documenti_entrano():
    fascicolo = fascicolo_vuoto("f1")
    for indice in range(Fascicolo.MAX_DOCUMENTI):
        aggiungi_documento(fascicolo, documento(indice))
    assert len(fascicolo.documents) == 10


def test_l_undicesimo_documento_viene_rifiutato():
    fascicolo = fascicolo_vuoto("f1")
    for indice in range(Fascicolo.MAX_DOCUMENTI):
        aggiungi_documento(fascicolo, documento(indice))
    with pytest.raises(FascicoloFull, match="10"):
        aggiungi_documento(fascicolo, documento(99))


def test_il_rifiuto_non_lascia_il_fascicolo_alterato():
    fascicolo = fascicolo_vuoto("f1")
    for indice in range(Fascicolo.MAX_DOCUMENTI):
        aggiungi_documento(fascicolo, documento(indice))
    with pytest.raises(FascicoloFull):
        aggiungi_documento(fascicolo, documento(99))
    assert len(fascicolo.documents) == 10


def test_nessun_segnaposto_preesistente_in_un_testo_normale():
    assert segnaposto_preesistenti("Il conduttore firma il contratto.") == []


def test_segnaposto_preesistente_viene_segnalato_con_la_posizione():
    testo = "Il conduttore [PERSONA_1] firma."
    assert segnaposto_preesistenti(testo) == [(14, "[PERSONA_1]")]


def test_piu_segnaposto_preesistenti_in_ordine():
    testo = "[IBAN_2] e poi [PERSONA_10]"
    assert segnaposto_preesistenti(testo) == [(0, "[IBAN_2]"), (15, "[PERSONA_10]")]


def test_un_quasi_segnaposto_non_viene_segnalato():
    # La forma canonica è [MAIUSCOLE_CIFRE]: queste non lo sono.
    assert segnaposto_preesistenti("[persona_1] e [PERSONA] e [1_PERSONA]") == []
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

Run: `.venv\Scripts\python -m pytest tests/test_loader.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'cryptocustode.core.ingest.loader'`.

- [ ] **Step 3: Scrivere `cryptocustode/core/ingest/loader.py`**

```python
"""Facciata dell'ingresso: da byte a `Document`, e da `Document` a fascicolo."""

from __future__ import annotations

import hashlib
import re
import uuid

from cryptocustode.core.errors import FascicoloFull
from cryptocustode.core.ingest.pdf_loader import carica_pdf
from cryptocustode.core.ingest.txt_loader import carica_txt
from cryptocustode.core.models import Document, Fascicolo

# La forma canonica di un segnaposto (spec §7). La stessa regex vive in
# core/unmask.py per il verso opposto: qui serve ad avvisare che il testo in
# ingresso ne contiene già uno.
SEGNAPOSTO = re.compile(r"\[[A-Z]+_\d+\]")


def segnaposto_preesistenti(testo: str) -> list[tuple[int, str]]:
    """Le occorrenze di segnaposto già presenti nel testo caricato.

    Non è un rifiuto: è un avviso. Al ripristino una di queste stringhe verrebbe
    interpretata come segnaposto e sostituita con dati veri, corrompendo il testo
    (spec §12), quindi l'utente deve saperlo prima di approvare.
    """
    return [(trovato.start(), trovato.group(0)) for trovato in SEGNAPOSTO.finditer(testo)]


def costruisci_documento(filename: str, contenuto: bytes) -> Document:
    """Trasforma i byte di un file in un `Document`.

    Il dispatch è per estensione: `.pdf` passa da PyMuPDF, tutto il resto è
    tentato come testo UTF-8. `sha256` è il digest dei byte originali, non del
    testo estratto, così due caricamenti dello stesso file si riconoscono anche
    se l'estrazione cambiasse.
    """
    if filename.lower().endswith(".pdf"):
        testo, page_offsets = carica_pdf(contenuto)
    else:
        testo, page_offsets = carica_txt(contenuto), [0]
    return Document(
        doc_id=f"d_{uuid.uuid4().hex[:12]}",
        filename=filename,
        text=testo,
        page_offsets=page_offsets,
        sha256=hashlib.sha256(contenuto).hexdigest(),
    )


def aggiungi_documento(fascicolo: Fascicolo, documento: Document) -> None:
    """Aggiunge il documento al fascicolo, se c'è posto.

    Il controllo precede la mutazione: un rifiuto lascia il fascicolo esattamente
    com'era.
    """
    if len(fascicolo.documents) >= Fascicolo.MAX_DOCUMENTI:
        raise FascicoloFull(
            f"massimo {Fascicolo.MAX_DOCUMENTI} documenti per fascicolo"
        )
    fascicolo.documents.append(documento)
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

Run: `.venv\Scripts\python -m pytest tests/test_loader.py -v`
Expected: PASS, 14 test.

- [ ] **Step 5: Commit**

```bash
git add cryptocustode/core/ingest/loader.py tests/test_loader.py
git commit -m "feat: ingresso nel fascicolo con tetto di dieci documenti e avviso segnaposto"
```

---

### Task 5: Vault cifrato

**Files:**
- Create: `cryptocustode/core/vault.py`
- Test: `tests/test_vault.py`

**Interfaces:**
- Consumes: `VaultUnreadable` dal Task 1; tutti i tipi di `core/models.py`.
- Produces: `salva(fascicolo: Fascicolo, password: str) -> bytes`, `carica(blob: bytes, password: str) -> Fascicolo`, e le costanti `MAGIC: bytes`, `ITERAZIONI_KDF: int`, `VAULT_VERSION: int`. Usate dal piano 3.

**Struttura del file (spec §10):**

```
[MAGIC "CCV1"        4 byte]
[ITERAZIONI KDF      4 byte, uint32 big-endian]
[SALT               16 byte, casuale]
[NONCE              12 byte, casuale]
[CIPHERTEXT || TAG   n byte]
```

PBKDF2-HMAC-SHA256, 600.000 iterazioni, salt casuale di 16 byte, chiave di 32 byte. AES-256-GCM. **I primi 24 byte — magic, iterazioni, salt — sono passati come associated data**, così l'intestazione è autenticata e nessuno può abbassare il numero di iterazioni di un file esistente senza far fallire la verifica. Il tag non è un campo separato: `AESGCM.encrypt()` restituisce già `ciphertext || tag`.

**Contenuto cifrato** (JSON, UTF-8): `vault_version`, `fascicolo_id`, `created_at`, `documents`, `spans`, `entities`, `category_enabled`, `ambiguities`, `state`, `approval_hash`, **`counters`**. L'ultimo campo non è nell'elenco della spec: vedi lo scostamento 1 in testa al piano.

**Password errata e file manomesso non si distinguono**, deliberatamente: la verifica del tag GCM fallisce identicamente, e distinguerli comunicherebbe a chi ci prova che la password è l'unico ostacolo rimasto (spec §13).

- [ ] **Step 1: Scrivere i test**

`tests/test_vault.py`:

```python
import pytest

from cryptocustode.core import vault
from cryptocustode.core.errors import VaultUnreadable
from cryptocustode.core.models import (
    Ambiguity,
    AmbiguityKind,
    Category,
    Document,
    Entity,
    Source,
    Span,
    State,
    fascicolo_vuoto,
)

PASSWORD = "una password di prova"


def fascicolo_popolato():
    fascicolo = fascicolo_vuoto("f1")
    fascicolo.documents.append(
        Document(
            doc_id="d1",
            filename="contratto.txt",
            text="Mario Rossi abita a Torino.",
            page_offsets=[0],
            sha256="a" * 64,
        )
    )
    fascicolo.spans.append(
        Span(
            span_id="d1:0-11:PERSONA",
            doc_id="d1",
            start=0,
            end=11,
            category=Category.PERSONA,
            source=Source.NER,
            entity_id="e1",
        )
    )
    fascicolo.entities["e1"] = Entity(
        entity_id="e1",
        category=Category.PERSONA,
        placeholder="[PERSONA_1]",
        canonical_value="Mario Rossi",
        variants={"Mario Rossi", "M. Rossi"},
        cf=None,
    )
    fascicolo.ambiguities.append(
        Ambiguity(
            ambiguity_id="a1",
            kind=AmbiguityKind.SAME_NAME_NO_CF,
            category=Category.PERSONA,
            candidate_entity_ids=["e1"],
            occurrence_span_ids=["d1:0-11:PERSONA"],
        )
    )
    fascicolo.counters[Category.PERSONA] = 1
    fascicolo.category_enabled[Category.DATA] = False
    fascicolo.state = State.PENDING_REVIEW
    return fascicolo


def test_round_trip_conserva_il_fascicolo():
    originale = fascicolo_popolato()
    ricaricato = vault.carica(vault.salva(originale, PASSWORD), PASSWORD)
    assert ricaricato.fascicolo_id == originale.fascicolo_id
    assert ricaricato.documents == originale.documents
    assert ricaricato.spans == originale.spans
    assert ricaricato.state == originale.state


def test_round_trip_conserva_le_entita_con_le_varianti():
    originale = fascicolo_popolato()
    ricaricato = vault.carica(vault.salva(originale, PASSWORD), PASSWORD)
    entita = ricaricato.entities["e1"]
    assert entita.canonical_value == "Mario Rossi"
    assert entita.variants == {"Mario Rossi", "M. Rossi"}
    assert entita.category is Category.PERSONA


def test_round_trip_conserva_le_ambiguita():
    ricaricato = vault.carica(vault.salva(fascicolo_popolato(), PASSWORD), PASSWORD)
    assert len(ricaricato.ambiguities) == 1
    assert ricaricato.ambiguities[0].kind is AmbiguityKind.SAME_NAME_NO_CF
    assert ricaricato.ambiguities[0].blocca_approvazione is True


def test_round_trip_conserva_i_contatori():
    # Senza i contatori gli indici dei segnaposto verrebbero riciclati dopo una
    # riapertura, e [PERSONA_1] finirebbe a una persona diversa (spec §7).
    ricaricato = vault.carica(vault.salva(fascicolo_popolato(), PASSWORD), PASSWORD)
    assert ricaricato.counters[Category.PERSONA] == 1


def test_round_trip_conserva_gli_interruttori_di_categoria():
    ricaricato = vault.carica(vault.salva(fascicolo_popolato(), PASSWORD), PASSWORD)
    assert ricaricato.category_enabled[Category.DATA] is False
    assert ricaricato.category_enabled[Category.PERSONA] is True


def test_l_intestazione_ha_la_forma_della_spec():
    blob = vault.salva(fascicolo_popolato(), PASSWORD)
    assert blob[:4] == vault.MAGIC
    assert int.from_bytes(blob[4:8], "big") == vault.ITERAZIONI_KDF
    # magic 4 + iterazioni 4 + salt 16 + nonce 12 = 36 byte di intestazione.
    assert len(blob) > 36


def test_due_salvataggi_usano_salt_e_nonce_diversi():
    fascicolo = fascicolo_popolato()
    primo = vault.salva(fascicolo, PASSWORD)
    secondo = vault.salva(fascicolo, PASSWORD)
    assert primo[8:36] != secondo[8:36]
    assert primo != secondo


def test_il_testo_in_chiaro_non_compare_nel_blob():
    blob = vault.salva(fascicolo_popolato(), PASSWORD)
    assert b"Mario Rossi" not in blob
    assert b"Torino" not in blob


def test_password_errata_non_apre_il_vault():
    blob = vault.salva(fascicolo_popolato(), PASSWORD)
    with pytest.raises(VaultUnreadable):
        vault.carica(blob, "password sbagliata")


def test_ciphertext_manomesso_non_apre_il_vault():
    blob = bytearray(vault.salva(fascicolo_popolato(), PASSWORD))
    blob[-1] ^= 0xFF
    with pytest.raises(VaultUnreadable):
        vault.carica(bytes(blob), PASSWORD)


def test_abbassare_le_iterazioni_nell_intestazione_non_apre_il_vault():
    # L'intestazione è associated data: modificarla fa fallire la verifica del tag.
    blob = bytearray(vault.salva(fascicolo_popolato(), PASSWORD))
    blob[4:8] = (1000).to_bytes(4, "big")
    with pytest.raises(VaultUnreadable):
        vault.carica(bytes(blob), PASSWORD)


def test_magic_sbagliato_viene_respinto():
    blob = bytearray(vault.salva(fascicolo_popolato(), PASSWORD))
    blob[:4] = b"XXXX"
    with pytest.raises(VaultUnreadable):
        vault.carica(bytes(blob), PASSWORD)


def test_blob_troncato_viene_respinto():
    with pytest.raises(VaultUnreadable):
        vault.carica(b"CCV1", PASSWORD)


def test_il_messaggio_non_distingue_password_da_manomissione():
    blob = vault.salva(fascicolo_popolato(), PASSWORD)
    with pytest.raises(VaultUnreadable) as errata:
        vault.carica(blob, "password sbagliata")
    manomesso = bytearray(blob)
    manomesso[-1] ^= 0xFF
    with pytest.raises(VaultUnreadable) as corrotto:
        vault.carica(bytes(manomesso), PASSWORD)
    assert str(errata.value) == str(corrotto.value)
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

Run: `.venv\Scripts\python -m pytest tests/test_vault.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'cryptocustode.core.vault'`.

- [ ] **Step 3: Scrivere `cryptocustode/core/vault.py`**

```python
"""Vault cifrato: AES-256-GCM con chiave derivata via PBKDF2 (spec §10).

Fuori dal vault il fascicolo vive solo nella RAM del processo.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from cryptocustode.core.errors import VaultUnreadable
from cryptocustode.core.models import (
    Ambiguity,
    AmbiguityKind,
    Category,
    Document,
    Entity,
    Fascicolo,
    Source,
    Span,
    State,
)

MAGIC = b"CCV1"
ITERAZIONI_KDF = 600_000
VAULT_VERSION = 1

_LUNGHEZZA_SALT = 16
_LUNGHEZZA_NONCE = 12
_LUNGHEZZA_CHIAVE = 32
# magic 4 + iterazioni 4 + salt 16: sono i byte autenticati come associated data.
_FINE_INTESTAZIONE_AUTENTICATA = 24
_FINE_INTESTAZIONE = _FINE_INTESTAZIONE_AUTENTICATA + _LUNGHEZZA_NONCE

# Un solo messaggio per password errata e file danneggiato: distinguerli direbbe
# a chi ci prova che la password è l'unico ostacolo rimasto (spec §13).
_MESSAGGIO_ILLEGGIBILE = "password errata o file danneggiato"


def _deriva_chiave(password: str, salt: bytes, iterazioni: int) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=_LUNGHEZZA_CHIAVE,
        salt=salt,
        iterations=iterazioni,
    )
    return kdf.derive(password.encode("utf-8"))


def _a_dizionario(fascicolo: Fascicolo) -> dict:
    return {
        "vault_version": VAULT_VERSION,
        "fascicolo_id": fascicolo.fascicolo_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "documents": [
            {
                "doc_id": d.doc_id,
                "filename": d.filename,
                "text": d.text,
                "page_offsets": list(d.page_offsets),
                "sha256": d.sha256,
            }
            for d in fascicolo.documents
        ],
        "spans": [
            {
                "span_id": s.span_id,
                "doc_id": s.doc_id,
                "start": s.start,
                "end": s.end,
                "category": s.category.value,
                "source": s.source.value,
                "entity_id": s.entity_id,
                "enabled": s.enabled,
            }
            for s in fascicolo.spans
        ],
        "entities": {
            chiave: {
                "entity_id": e.entity_id,
                "category": e.category.value,
                "placeholder": e.placeholder,
                "canonical_value": e.canonical_value,
                # I set non sono serializzabili in JSON: ordinati per rendere il
                # blob riproducibile a parità di contenuto.
                "variants": sorted(e.variants),
                "cf": e.cf,
            }
            for chiave, e in fascicolo.entities.items()
        },
        "category_enabled": {
            categoria.value: attiva for categoria, attiva in fascicolo.category_enabled.items()
        },
        "ambiguities": [
            {
                "ambiguity_id": a.ambiguity_id,
                "kind": a.kind.value,
                "category": a.category.value,
                "candidate_entity_ids": list(a.candidate_entity_ids),
                "occurrence_span_ids": list(a.occurrence_span_ids),
                "resolved": a.resolved,
            }
            for a in fascicolo.ambiguities
        ],
        "state": fascicolo.state.value,
        "approval_hash": fascicolo.approval_hash,
        # Fuori dall'elenco della spec §10: senza i contatori gli indici dei
        # segnaposto verrebbero riciclati dopo una riapertura (spec §7).
        "counters": {
            categoria.value: valore for categoria, valore in fascicolo.counters.items()
        },
    }


def _da_dizionario(dati: dict) -> Fascicolo:
    return Fascicolo(
        fascicolo_id=dati["fascicolo_id"],
        documents=[
            Document(
                doc_id=d["doc_id"],
                filename=d["filename"],
                text=d["text"],
                page_offsets=list(d["page_offsets"]),
                sha256=d["sha256"],
            )
            for d in dati["documents"]
        ],
        spans=[
            Span(
                span_id=s["span_id"],
                doc_id=s["doc_id"],
                start=s["start"],
                end=s["end"],
                category=Category(s["category"]),
                source=Source(s["source"]),
                entity_id=s["entity_id"],
                enabled=s["enabled"],
            )
            for s in dati["spans"]
        ],
        entities={
            chiave: Entity(
                entity_id=e["entity_id"],
                category=Category(e["category"]),
                placeholder=e["placeholder"],
                canonical_value=e["canonical_value"],
                variants=set(e["variants"]),
                cf=e["cf"],
            )
            for chiave, e in dati["entities"].items()
        },
        category_enabled={
            Category(nome): attiva for nome, attiva in dati["category_enabled"].items()
        },
        ambiguities=[
            Ambiguity(
                ambiguity_id=a["ambiguity_id"],
                kind=AmbiguityKind(a["kind"]),
                category=Category(a["category"]),
                candidate_entity_ids=list(a["candidate_entity_ids"]),
                occurrence_span_ids=list(a["occurrence_span_ids"]),
                resolved=a["resolved"],
            )
            for a in dati["ambiguities"]
        ],
        state=State(dati["state"]),
        approval_hash=dati["approval_hash"],
        counters={Category(nome): valore for nome, valore in dati["counters"].items()},
    )


def salva(fascicolo: Fascicolo, password: str) -> bytes:
    """Serializza e cifra l'intero fascicolo.

    Salt e nonce sono casuali a ogni salvataggio, quindi due salvataggi dello
    stesso fascicolo producono blob diversi: è voluto.
    """
    salt = os.urandom(_LUNGHEZZA_SALT)
    nonce = os.urandom(_LUNGHEZZA_NONCE)
    intestazione_autenticata = (
        MAGIC + ITERAZIONI_KDF.to_bytes(4, "big") + salt
    )
    chiave = _deriva_chiave(password, salt, ITERAZIONI_KDF)
    testo_in_chiaro = json.dumps(_a_dizionario(fascicolo), ensure_ascii=False).encode(
        "utf-8"
    )
    cifrato = AESGCM(chiave).encrypt(nonce, testo_in_chiaro, intestazione_autenticata)
    return intestazione_autenticata + nonce + cifrato


def carica(blob: bytes, password: str) -> Fascicolo:
    """Decifra un vault e ricostruisce il fascicolo.

    Solleva `VaultUnreadable` per qualunque motivo di fallimento, con lo stesso
    messaggio in tutti i casi.
    """
    if len(blob) <= _FINE_INTESTAZIONE or blob[:4] != MAGIC:
        raise VaultUnreadable(_MESSAGGIO_ILLEGGIBILE)
    intestazione_autenticata = blob[:_FINE_INTESTAZIONE_AUTENTICATA]
    iterazioni = int.from_bytes(blob[4:8], "big")
    salt = blob[8:_FINE_INTESTAZIONE_AUTENTICATA]
    nonce = blob[_FINE_INTESTAZIONE_AUTENTICATA:_FINE_INTESTAZIONE]
    cifrato = blob[_FINE_INTESTAZIONE:]
    try:
        chiave = _deriva_chiave(password, salt, iterazioni)
        testo_in_chiaro = AESGCM(chiave).decrypt(
            nonce, cifrato, intestazione_autenticata
        )
        return _da_dizionario(json.loads(testo_in_chiaro.decode("utf-8")))
    except (InvalidTag, ValueError, KeyError, UnicodeDecodeError) as errore:
        raise VaultUnreadable(_MESSAGGIO_ILLEGGIBILE) from errore
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

Run: `.venv\Scripts\python -m pytest tests/test_vault.py -v`
Expected: PASS, 14 test. Ogni test che salva paga 600.000 iterazioni di PBKDF2, quindi il file impiega qualche secondo: è il costo voluto del KDF, non un problema da ottimizzare.

- [ ] **Step 5: Commit**

```bash
git add cryptocustode/core/vault.py tests/test_vault.py
git commit -m "feat: vault cifrato AES-256-GCM con intestazione autenticata"
```

---

### Task 6: Ripristino della risposta dell'IA

**Files:**
- Create: `cryptocustode/core/unmask.py`
- Test: `tests/test_unmask.py`

**Interfaces:**
- Consumes: `UnknownPlaceholder` e `MalformedPlaceholder` dal Task 1; `Entity` da `core/models.py`.
- Produces: `ripristina(risposta: str, entities: dict[str, Entity]) -> str`, `SEGNAPOSTO: re.Pattern`, `QUASI_SEGNAPOSTO: re.Pattern`. Usate dal piano 3.

**I cinque passi (spec §11).**

1. **Associazione** — responsabilità del chiamante: `ripristina` riceve già il dizionario del fascicolo attivo.
2. **Estrazione** — tutti i token che corrispondono a `\[[A-Z]+_\d+\]`.
3. **Rilevamento delle alterazioni** — una seconda regex più permissiva, `\[[A-Za-z]+[_\-\s]?\d*\]?`, individua i quasi-segnaposto che non hanno superato la prima. Ognuno viene segnalato letteralmente all'utente.
4. **Validazione** — un segnaposto ben formato ma assente dal dizionario produce `UnknownPlaceholder`.
5. **Sostituzione** — solo se i passi 3 e 4 non hanno prodotto errori. Chiavi ordinate per lunghezza decrescente, così `[PERSONA_10]` viene sostituito prima di `[PERSONA_1]` e non resta uno `0` orfano.

**Nessun ripristino parziale, in nessun caso.** Un testo in cui l'utente non sa quali segnaposto siano stati risolti e quali no è peggio di un errore.

**Una conseguenza della regex permissiva, da tenere e non da "correggere".** `\[[A-Za-z]+[_\-\s]?\d*\]?` rende opzionali sia il separatore sia le cifre, quindi cattura anche parentesi quadre del tutto innocenti: una risposta che contiene `[Nota]` o `[sic]` viene fermata come alterazione. È un falso positivo reale, ed è il verso giusto in cui sbagliare — l'alternativa è un ripristino che procede su un testo in cui un segnaposto storpiato è passato inosservato. L'ultimo test della lista lo fissa come comportamento voluto: chi lo troverà fra sei mesi deve sapere che è una scelta, non una svista. Se un giorno darà fastidio, la correzione è restringere la regex permissiva pretendendo almeno una cifra, non allentare il blocco.

- [ ] **Step 1: Scrivere i test**

`tests/test_unmask.py`:

```python
import pytest

from cryptocustode.core.errors import MalformedPlaceholder, UnknownPlaceholder
from cryptocustode.core.models import Category, Entity
from cryptocustode.core.unmask import ripristina


def dizionario():
    return {
        "e1": Entity(
            entity_id="e1",
            category=Category.PERSONA,
            placeholder="[PERSONA_1]",
            canonical_value="Mario Rossi",
        ),
        "e2": Entity(
            entity_id="e2",
            category=Category.PERSONA,
            placeholder="[PERSONA_10]",
            canonical_value="Luisa Bianchi",
        ),
        "e3": Entity(
            entity_id="e3",
            category=Category.IBAN,
            placeholder="[IBAN_1]",
            canonical_value="IT60X0542811101000000123456",
        ),
    }


def test_un_segnaposto_viene_sostituito():
    assert ripristina("Il contratto è di [PERSONA_1].", dizionario()) == (
        "Il contratto è di Mario Rossi."
    )


def test_piu_segnaposto_di_categorie_diverse():
    testo = "[PERSONA_1] versa su [IBAN_1]."
    assert ripristina(testo, dizionario()) == (
        "Mario Rossi versa su IT60X0542811101000000123456."
    )


def test_lo_stesso_segnaposto_ripetuto_viene_sostituito_ovunque():
    testo = "[PERSONA_1] e ancora [PERSONA_1]"
    assert ripristina(testo, dizionario()) == "Mario Rossi e ancora Mario Rossi"


def test_indice_a_due_cifre_non_lascia_uno_zero_orfano():
    # Il caso che impone l'ordinamento per lunghezza decrescente: sostituendo
    # prima [PERSONA_1] resterebbe "Mario Rossi0".
    assert ripristina("[PERSONA_10] firma.", dizionario()) == "Luisa Bianchi firma."


def test_testo_senza_segnaposto_torna_identico():
    assert ripristina("Nessun segnaposto qui.", dizionario()) == (
        "Nessun segnaposto qui."
    )


def test_segnaposto_sconosciuto_interrompe_il_ripristino():
    # TC-05: [PERSONA_99] non è nel dizionario del fascicolo attivo.
    with pytest.raises(UnknownPlaceholder, match=r"\[PERSONA_99\]"):
        ripristina("Il contratto è di [PERSONA_99].", dizionario())


def test_tipo_inesistente_ma_ben_formato_e_uno_sconosciuto():
    # [PERSON_1] supera la regex severa: è ben formato, e il fatto che PERSON
    # non esista è una questione di dizionario (scostamento 3 in testa al piano).
    with pytest.raises(UnknownPlaceholder, match=r"\[PERSON_1\]"):
        ripristina("Firmato da [PERSON_1].", dizionario())


def test_segnaposto_senza_chiusura_e_malformato():
    with pytest.raises(MalformedPlaceholder, match=r"\[PERSONA_1"):
        ripristina("Firmato da [PERSONA_1 oggi.", dizionario())


def test_segnaposto_in_minuscolo_e_malformato():
    with pytest.raises(MalformedPlaceholder, match=r"\[persona_1\]"):
        ripristina("Firmato da [persona_1].", dizionario())


def test_il_messaggio_cita_i_frammenti_letteralmente():
    with pytest.raises(MalformedPlaceholder) as errore:
        ripristina("[persona_1] e [PERSONA_2", dizionario())
    messaggio = str(errore.value)
    assert "[persona_1]" in messaggio
    assert "[PERSONA_2" in messaggio


def test_nessun_ripristino_parziale_con_un_segnaposto_sconosciuto():
    # Un solo segnaposto ignoto basta a fermare tutto: gli altri, validi,
    # non vengono sostituiti.
    with pytest.raises(UnknownPlaceholder):
        ripristina("[PERSONA_1] e [PERSONA_99]", dizionario())


def test_nessun_ripristino_parziale_con_un_frammento_malformato():
    with pytest.raises(MalformedPlaceholder):
        ripristina("[PERSONA_1] e [persona_2]", dizionario())


def test_le_alterazioni_hanno_la_precedenza_sugli_sconosciuti():
    # Quando ci sono entrambi si segnala prima la forma: è l'errore che
    # l'utente può correggere leggendo il proprio testo.
    with pytest.raises(MalformedPlaceholder):
        ripristina("[persona_1] e [PERSONA_99]", dizionario())


def test_una_parentesi_quadra_innocente_blocca_comunque_il_ripristino():
    # Falso positivo noto e voluto: la regex permissiva della spec §11 rende
    # opzionali separatore e cifre, quindi "[Nota]" le somiglia abbastanza.
    # Fermarsi è il verso giusto in cui sbagliare — l'alternativa è procedere
    # su un testo in cui un segnaposto storpiato è passato inosservato.
    with pytest.raises(MalformedPlaceholder, match=r"\[Nota\]"):
        ripristina("[PERSONA_1] firma. [Nota] a margine.", dizionario())
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

Run: `.venv\Scripts\python -m pytest tests/test_unmask.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'cryptocustode.core.unmask'`.

- [ ] **Step 3: Scrivere `cryptocustode/core/unmask.py`**

```python
"""Ripristino della risposta dell'IA: dai segnaposto ai valori veri (spec §11)."""

from __future__ import annotations

import re

from cryptocustode.core.errors import MalformedPlaceholder, UnknownPlaceholder
from cryptocustode.core.models import Entity

# Passo 2: la forma canonica.
SEGNAPOSTO = re.compile(r"\[[A-Z]+_\d+\]")

# Passo 3: la forma permissiva, che cattura anche i quasi-segnaposto storpiati
# dall'IA. Tutto ciò che questa trova e la severa no è un'alterazione.
QUASI_SEGNAPOSTO = re.compile(r"\[[A-Za-z]+[_\-\s]?\d*\]?")


def _alterazioni(risposta: str) -> list[str]:
    """I frammenti che somigliano a un segnaposto senza esserlo.

    Il confronto è per posizione: un frammento è un'alterazione se la regex
    severa non produce, allo stesso offset, esattamente la stessa stringa.
    """
    canonici = {
        trovato.start(): trovato.group(0) for trovato in SEGNAPOSTO.finditer(risposta)
    }
    return [
        trovato.group(0)
        for trovato in QUASI_SEGNAPOSTO.finditer(risposta)
        if canonici.get(trovato.start()) != trovato.group(0)
    ]


def ripristina(risposta: str, entities: dict[str, Entity]) -> str:
    """Sostituisce i segnaposto della risposta con i valori canonici.

    Nessun ripristino parziale, in nessun caso: se anche un solo segnaposto è
    alterato o sconosciuto la funzione solleva e non restituisce nulla. Un testo
    in cui l'utente non sa quali segnaposto siano stati risolti e quali no è
    peggio di un errore (spec §11).
    """
    alterati = _alterazioni(risposta)
    if alterati:
        elenco = ", ".join(repr(frammento) for frammento in alterati)
        raise MalformedPlaceholder(
            f"segnaposto alterati, ripristino interrotto: {elenco}"
        )

    dizionario = {entita.placeholder: entita.canonical_value for entita in entities.values()}
    trovati = [trovato.group(0) for trovato in SEGNAPOSTO.finditer(risposta)]
    sconosciuti = sorted({t for t in trovati if t not in dizionario})
    if sconosciuti:
        elenco = ", ".join(sconosciuti)
        raise UnknownPlaceholder(
            "segnaposto non riconosciuto o appartenente a un'altra sessione, "
            f"ripristino interrotto: {elenco}"
        )

    ripristinato = risposta
    # Lunghezza decrescente: [PERSONA_10] prima di [PERSONA_1], altrimenti
    # resterebbe uno 0 orfano.
    for segnaposto in sorted(dizionario, key=len, reverse=True):
        ripristinato = ripristinato.replace(segnaposto, dizionario[segnaposto])
    return ripristinato
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

Run: `.venv\Scripts\python -m pytest tests/test_unmask.py -v`
Expected: PASS, 14 test.

- [ ] **Step 5: Commit**

```bash
git add cryptocustode/core/unmask.py tests/test_unmask.py
git commit -m "feat: ripristino della risposta dell'IA senza esiti parziali"
```

---

### Task 7: Macchina a stati e approvazione

**Files:**
- Create: `cryptocustode/state/session.py`
- Test: `tests/test_session.py`

**Interfaces:**
- Consumes: `UnresolvedAmbiguities` dal Task 1; `hash_approvazione` da `core/mask.py`; `risolvi_ambiguita_omonimia` e `suggerisci_fusioni` da `core/entities.py`; `Fascicolo`, `State` da `core/models.py`.
- Produces: `analisi_completata(fascicolo) -> None`, `approva(fascicolo) -> None`, `registra_mutazione(fascicolo) -> None`. Usate dal Task 8 e dal piano 3.

**`analisi_completata` deve popolare le code delle ambiguità.** Il piano 1 costruisce `risolvi_ambiguita_omonimia` e `suggerisci_fusioni` ma **nessuno le chiama**: `analizza_documento` aggrega gli span in entità e si ferma lì. Verificato leggendo il codice consegnato, non a memoria. Se `analisi_completata` non le invoca, la coda resta vuota per sempre, `approva` non trova mai nulla da bloccare e il gate delle omonimie della spec §7 non esiste in produzione. Le due chiamate vanno qui e non dentro `analizza_documento` per una ragione precisa: le omonimie sono una proprietà del **fascicolo intero**, quindi si possono calcolare solo quando tutti i documenti sono stati analizzati, non a metà del caricamento. `state/` può importare `core/`: l'invariante 1 vieta solo il verso opposto.

**La macchina (spec §8):**

```
DRAFT --(analisi completata)--> PENDING_REVIEW --(approvazione)--> APPROVED
                                      ^                                |
                                      +------(qualsiasi mutazione)------+
```

**Approvazione.** Rifiutata se esistono ambiguità bloccanti non risolte. Calcola l'hash del testo mascherato e lo salva in `approval_hash`.

`state/session.py` può importare `core/`: l'invariante 1 vieta il verso opposto.

- [ ] **Step 1: Scrivere i test**

`tests/test_session.py`:

```python
import pytest

from cryptocustode.core.errors import UnresolvedAmbiguities
from cryptocustode.core.models import (
    Ambiguity,
    AmbiguityKind,
    Category,
    Document,
    Entity,
    Source,
    Span,
    State,
    fascicolo_vuoto,
)
from cryptocustode.state.session import (
    analisi_completata,
    approva,
    registra_mutazione,
)


def fascicolo_analizzato():
    """Un fascicolo con un documento, uno span e la sua entità, pronto da approvare."""
    fascicolo = fascicolo_vuoto("f1")
    fascicolo.documents.append(
        Document(
            doc_id="d1",
            filename="contratto.txt",
            text="Mario Rossi abita a Torino.",
            page_offsets=[0],
            sha256="a" * 64,
        )
    )
    fascicolo.spans.append(
        Span(
            span_id="s1",
            doc_id="d1",
            start=0,
            end=11,
            category=Category.PERSONA,
            source=Source.NER,
            entity_id="e1",
        )
    )
    fascicolo.entities["e1"] = Entity(
        entity_id="e1",
        category=Category.PERSONA,
        placeholder="[PERSONA_1]",
        canonical_value="Mario Rossi",
    )
    analisi_completata(fascicolo)
    return fascicolo


def ambiguita_bloccante():
    return Ambiguity(
        ambiguity_id="a1",
        kind=AmbiguityKind.SAME_NAME_NO_CF,
        category=Category.PERSONA,
        candidate_entity_ids=["e1", "e2"],
        occurrence_span_ids=["s1"],
    )


def ambiguita_non_bloccante():
    return Ambiguity(
        ambiguity_id="a2",
        kind=AmbiguityKind.HEURISTIC_MERGE_SUGGESTION,
        category=Category.PERSONA,
        candidate_entity_ids=["e1", "e2"],
        occurrence_span_ids=["s1"],
    )


def test_un_fascicolo_nuovo_e_in_draft():
    assert fascicolo_vuoto("f1").state is State.DRAFT


def test_l_analisi_porta_in_pending_review():
    fascicolo = fascicolo_vuoto("f1")
    analisi_completata(fascicolo)
    assert fascicolo.state is State.PENDING_REVIEW


def test_l_approvazione_porta_in_approved():
    fascicolo = fascicolo_analizzato()
    approva(fascicolo)
    assert fascicolo.state is State.APPROVED


def test_l_approvazione_salva_l_hash():
    fascicolo = fascicolo_analizzato()
    approva(fascicolo)
    assert fascicolo.approval_hash is not None
    assert len(fascicolo.approval_hash) == 64


def test_l_approvazione_e_deterministica():
    primo, secondo = fascicolo_analizzato(), fascicolo_analizzato()
    approva(primo)
    approva(secondo)
    assert primo.approval_hash == secondo.approval_hash


def test_un_ambiguita_bloccante_impedisce_l_approvazione():
    fascicolo = fascicolo_analizzato()
    fascicolo.ambiguities.append(ambiguita_bloccante())
    with pytest.raises(UnresolvedAmbiguities, match="a1"):
        approva(fascicolo)


def test_il_rifiuto_lascia_lo_stato_invariato():
    fascicolo = fascicolo_analizzato()
    fascicolo.ambiguities.append(ambiguita_bloccante())
    with pytest.raises(UnresolvedAmbiguities):
        approva(fascicolo)
    assert fascicolo.state is State.PENDING_REVIEW
    assert fascicolo.approval_hash is None


def test_un_ambiguita_bloccante_risolta_non_impedisce_l_approvazione():
    fascicolo = fascicolo_analizzato()
    ambiguita = ambiguita_bloccante()
    ambiguita.resolved = True
    fascicolo.ambiguities.append(ambiguita)
    approva(fascicolo)
    assert fascicolo.state is State.APPROVED


def test_un_suggerimento_euristico_non_impedisce_l_approvazione():
    fascicolo = fascicolo_analizzato()
    fascicolo.ambiguities.append(ambiguita_non_bloccante())
    approva(fascicolo)
    assert fascicolo.state is State.APPROVED


def test_una_mutazione_dopo_l_approvazione_riporta_in_pending_review():
    # TC-06.
    fascicolo = fascicolo_analizzato()
    approva(fascicolo)
    registra_mutazione(fascicolo)
    assert fascicolo.state is State.PENDING_REVIEW


def test_una_mutazione_dopo_l_approvazione_cancella_l_hash():
    fascicolo = fascicolo_analizzato()
    approva(fascicolo)
    registra_mutazione(fascicolo)
    assert fascicolo.approval_hash is None


def test_una_mutazione_in_pending_review_non_cambia_nulla():
    fascicolo = fascicolo_analizzato()
    registra_mutazione(fascicolo)
    assert fascicolo.state is State.PENDING_REVIEW


def test_una_mutazione_in_draft_non_cambia_nulla():
    fascicolo = fascicolo_vuoto("f1")
    registra_mutazione(fascicolo)
    assert fascicolo.state is State.DRAFT


def test_l_analisi_popola_la_coda_delle_omonimie():
    # Senza le due chiamate dentro analisi_completata questa coda resterebbe
    # vuota per sempre e `approva` non avrebbe mai nulla da bloccare.
    fascicolo = fascicolo_vuoto("f1")
    for indice, testo in enumerate(["Il conduttore Mario Rossi.", "Il garante Mario Rossi."]):
        documento = Document(
            doc_id=f"d{indice}",
            filename=f"doc{indice}.txt",
            text=testo,
            page_offsets=[0],
            sha256=f"{indice}" * 64,
        )
        fascicolo.documents.append(documento)
        aggiungi_span_manuale(
            fascicolo, documento, testo.index("Mario Rossi"),
            testo.index("Mario Rossi") + 11, Category.PERSONA,
        )
    analisi_completata(fascicolo)
    assert any(a.blocca_approvazione for a in fascicolo.ambiguities)


def test_l_analisi_popola_anche_i_suggerimenti_euristici():
    fascicolo = fascicolo_vuoto("f1")
    for indice, (testo, nome) in enumerate(
        [("Il conduttore M. Rossi.", "M. Rossi"), ("Il garante Mario Rossi.", "Mario Rossi")]
    ):
        documento = Document(
            doc_id=f"d{indice}",
            filename=f"doc{indice}.txt",
            text=testo,
            page_offsets=[0],
            sha256=f"{indice}" * 64,
        )
        fascicolo.documents.append(documento)
        aggiungi_span_manuale(
            fascicolo, documento, testo.index(nome),
            testo.index(nome) + len(nome), Category.PERSONA,
        )
    analisi_completata(fascicolo)
    suggerimenti = [
        a
        for a in fascicolo.ambiguities
        if a.kind is AmbiguityKind.HEURISTIC_MERGE_SUGGESTION
    ]
    assert len(suggerimenti) == 1
    assert suggerimenti[0].blocca_approvazione is False
```

I due test nuovi importano anche `AmbiguityKind` e `aggiungi_span_manuale`: aggiungi
`AmbiguityKind` alla lista di import da `cryptocustode.core.models` e
`from cryptocustode.core.entities import aggiungi_span_manuale` in testa al file di test.
Il tagging manuale è la via più corta per costruire due entità omonime senza dipendere dal
NER, e `aggiungi_span_manuale` pretende che il documento sia già in `fascicolo.documents`
— per questo l'append precede la chiamata.

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

Run: `.venv\Scripts\python -m pytest tests/test_session.py -v`
Expected: FAIL con `ImportError` su `cryptocustode.state.session`.

- [ ] **Step 3: Scrivere `cryptocustode/state/session.py`**

```python
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
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

Run: `.venv\Scripts\python -m pytest tests/test_session.py -v`
Expected: PASS, 15 test.

- [ ] **Step 5: Eseguire l'intera suite**

Run: `.venv\Scripts\python -m pytest -m "not lento"`
Expected: nessuna regressione, e in particolare il test di architettura resta verde: `core/` non ha imparato a importare `state/`.

- [ ] **Step 6: Commit**

```bash
git add cryptocustode/state/session.py tests/test_session.py
git commit -m "feat: macchina a stati con approvazione e invalidazione su mutazione"
```

---

### Task 8: Gate di esportazione e SessionStore

**Files:**
- Modify: `cryptocustode/state/session.py`
- Test: `tests/test_export.py`

**Interfaces:**
- Consumes: `ExportNotAllowed`, `IntegrityError` dal Task 1; `hash_approvazione`, `maschera_documento` da `core/mask.py`; le transizioni del Task 7.
- Produces: `SessionStore` con `salva(fascicolo) -> None` e `prendi(fascicolo_id) -> Fascicolo`, e `export_sanitized_text(fascicolo_id: str, store: SessionStore) -> dict[str, str]`. Usate dal piano 3.

**Il contratto (spec §8).** Controlli, in ordine:

1. `fascicolo.state == APPROVED`, altrimenti `ExportNotAllowed`.
2. Ricalcolo dell'hash sul testo mascherato corrente e confronto con `approval_hash`; se differisce, `IntegrityError`.

**Payload:** esclusivamente `{nome_file: testo_mascherato}`. Nessun testo originale, nessun dizionario, nessun metadato sensibile, nessuno span.

Sul passaggio esplicito dello store, vedi lo scostamento 2 in testa al piano.

- [ ] **Step 1: Scrivere i test**

`tests/test_export.py`:

```python
import pytest

from cryptocustode.core.errors import ExportNotAllowed, IntegrityError
from cryptocustode.core.models import (
    Category,
    Document,
    Entity,
    Source,
    Span,
    State,
    fascicolo_vuoto,
)
from cryptocustode.state.session import (
    SessionStore,
    analisi_completata,
    approva,
    export_sanitized_text,
)


def fascicolo_approvato():
    fascicolo = fascicolo_vuoto("f1")
    fascicolo.documents.append(
        Document(
            doc_id="d1",
            filename="contratto.txt",
            text="Mario Rossi abita a Torino.",
            page_offsets=[0],
            sha256="a" * 64,
        )
    )
    fascicolo.spans.append(
        Span(
            span_id="s1",
            doc_id="d1",
            start=0,
            end=11,
            category=Category.PERSONA,
            source=Source.NER,
            entity_id="e1",
        )
    )
    fascicolo.entities["e1"] = Entity(
        entity_id="e1",
        category=Category.PERSONA,
        placeholder="[PERSONA_1]",
        canonical_value="Mario Rossi",
    )
    analisi_completata(fascicolo)
    approva(fascicolo)
    return fascicolo


def store_con(fascicolo):
    store = SessionStore()
    store.salva(fascicolo)
    return store


def test_lo_store_restituisce_quello_che_ha_salvato():
    fascicolo = fascicolo_approvato()
    assert store_con(fascicolo).prendi("f1") is fascicolo


def test_lo_store_solleva_su_un_id_sconosciuto():
    with pytest.raises(KeyError):
        SessionStore().prendi("inesistente")


def test_export_in_stato_approved_restituisce_il_testo_mascherato():
    fascicolo = fascicolo_approvato()
    payload = export_sanitized_text("f1", store_con(fascicolo))
    assert payload == {"contratto.txt": "[PERSONA_1] abita a Torino."}


def test_export_in_draft_e_negato():
    # TC-04.
    fascicolo = fascicolo_vuoto("f1")
    with pytest.raises(ExportNotAllowed):
        export_sanitized_text("f1", store_con(fascicolo))


def test_export_in_pending_review_e_negato():
    fascicolo = fascicolo_vuoto("f1")
    analisi_completata(fascicolo)
    with pytest.raises(ExportNotAllowed):
        export_sanitized_text("f1", store_con(fascicolo))


def test_testo_cambiato_dopo_l_approvazione_solleva_integrity_error():
    fascicolo = fascicolo_approvato()
    # Lo stato resta APPROVED perché nessuno ha chiamato registra_mutazione:
    # è precisamente il caso che il secondo controllo esiste per intercettare.
    fascicolo.entities["e1"].placeholder = "[PERSONA_2]"
    with pytest.raises(IntegrityError):
        export_sanitized_text("f1", store_con(fascicolo))


def test_il_payload_non_contiene_il_testo_originale():
    fascicolo = fascicolo_approvato()
    payload = export_sanitized_text("f1", store_con(fascicolo))
    assert "Mario Rossi" not in payload["contratto.txt"]


def test_il_payload_ha_solo_i_nomi_dei_file_come_chiavi():
    fascicolo = fascicolo_approvato()
    payload = export_sanitized_text("f1", store_con(fascicolo))
    assert set(payload) == {"contratto.txt"}
    assert all(isinstance(valore, str) for valore in payload.values())


def test_lo_stato_resta_approved_dopo_un_export():
    fascicolo = fascicolo_approvato()
    export_sanitized_text("f1", store_con(fascicolo))
    assert fascicolo.state is State.APPROVED
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

Run: `.venv\Scripts\python -m pytest tests/test_export.py -v`
Expected: FAIL con `ImportError: cannot import name 'SessionStore'`.

- [ ] **Step 3: Aggiungere a `cryptocustode/state/session.py`**

Aggiungere gli import mancanti in testa al file:

```python
from cryptocustode.core.errors import (
    ExportNotAllowed,
    IntegrityError,
    UnresolvedAmbiguities,
)
from cryptocustode.core.mask import hash_approvazione, maschera_documento
```

e in coda al file:

```python
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
        return self._fascicoli[fascicolo_id]


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
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

Run: `.venv\Scripts\python -m pytest tests/test_export.py -v`
Expected: PASS, 9 test.

- [ ] **Step 5: Commit**

```bash
git add cryptocustode/state/session.py tests/test_export.py
git commit -m "feat: gate di esportazione con controllo di stato e integrità"
```

---

### Task 9: La matrice della consegna e il test anti-fuga

**Files:**
- Test: `tests/test_matrice_consegna.py`

**Interfaces:**
- Consumes: tutto quanto costruito dai Task 1-8 e dal piano 1.
- Produces: niente codice di produzione. Questo task è la rete che tiene insieme il resto.

**Il test più importante della suite è generico e anti-fuga (spec §14):** per ogni valore del dizionario, quel valore non compare nel testo esportato. Non verifica che il masking abbia fatto la cosa giusta in un caso particolare, verifica che non ne abbia dimenticato nessuno, e continuerà a valere quando verranno aggiunte categorie.

**I sei casi della matrice**, come test che portano quei nomi. TC-02 e TC-03 attraversano il motore del piano 1, quindi caricano il modello spaCy e portano il marker `lento`; gli altri quattro no.

- [ ] **Step 1: Scrivere i test**

`tests/test_matrice_consegna.py`:

```python
"""I sei casi della matrice della consegna e il test anti-fuga generico (spec §14)."""

import pytest

from cryptocustode.core.entities import analizza_documento
from cryptocustode.core.errors import (
    ExportNotAllowed,
    ScannedDocumentRejected,
    UnknownPlaceholder,
)
from cryptocustode.core.ingest.loader import aggiungi_documento, costruisci_documento
from cryptocustode.core.models import Category, State, fascicolo_vuoto
from cryptocustode.core.unmask import ripristina
from cryptocustode.state.session import (
    SessionStore,
    analisi_completata,
    approva,
    export_sanitized_text,
    registra_mutazione,
)
from tests.pdf_di_prova import pdf_di_prova

TESTO_RICCO = (
    "Il contratto è firmato da Mario Rossi, codice fiscale RSSMRA85M01H501Z, "
    "con IBAN IT60X0542811101000000123456 e P. IVA 12345678903. "
    "Recapito: Cell. 3401234567, mario.rossi@esempio.it."
)


def fascicolo_con(testo: str, nome: str = "contratto.txt", usa_ner: bool = False):
    fascicolo = fascicolo_vuoto("f1")
    documento = costruisci_documento(nome, testo.encode("utf-8"))
    aggiungi_documento(fascicolo, documento)
    analizza_documento(fascicolo, documento, usa_ner=usa_ner)
    analisi_completata(fascicolo)
    return fascicolo


def store_con(fascicolo):
    store = SessionStore()
    store.salva(fascicolo)
    return store


def test_anti_fuga_nessun_valore_del_dizionario_compare_nell_esportato():
    """Il test più importante della suite: nessun valore sopravvive all'export."""
    fascicolo = fascicolo_con(TESTO_RICCO)
    approva(fascicolo)
    esportato = export_sanitized_text("f1", store_con(fascicolo))
    testo_esportato = "\n".join(esportato.values())
    assert fascicolo.entities, "il fascicolo deve avere almeno un'entità, altrimenti il test non prova nulla"
    for entita in fascicolo.entities.values():
        assert entita.canonical_value not in testo_esportato
        for variante in entita.variants:
            assert variante not in testo_esportato


def test_TC_01_pdf_con_una_pagina_scansionata_su_cinque_viene_rifiutato():
    contenuto = pdf_di_prova(["testo", "testo", "testo", "testo", "immagine"])
    with pytest.raises(ScannedDocumentRejected, match="5"):
        costruisci_documento("scansione.pdf", contenuto)


@pytest.mark.lento
def test_TC_02_cf_con_cin_errato_non_diventa_un_codice_fiscale():
    # RSSMRA85M01H501A ha il CIN sbagliato: la regola lo scarta. Può restare
    # un'entità NER se il modello lo interpreta come nome, ma non un CF.
    fascicolo = fascicolo_con(
        "Il codice fiscale è RSSMRA85M01H501A.", usa_ner=True
    )
    categorie = {entita.category for entita in fascicolo.entities.values()}
    assert Category.CF not in categorie


@pytest.mark.lento
def test_TC_03_due_documenti_con_lo_stesso_nome_e_nessun_cf_bloccano_l_approvazione():
    fascicolo = fascicolo_vuoto("f1")
    for indice, testo in enumerate(
        ["Il conduttore Mario Rossi firma.", "Il garante Mario Rossi firma."]
    ):
        documento = costruisci_documento(f"doc{indice}.txt", testo.encode("utf-8"))
        aggiungi_documento(fascicolo, documento)
        analizza_documento(fascicolo, documento, usa_ner=True)
    analisi_completata(fascicolo)
    assert any(a.blocca_approvazione for a in fascicolo.ambiguities)


def test_TC_04_export_in_stato_draft_e_negato():
    fascicolo = fascicolo_vuoto("f1")
    assert fascicolo.state is State.DRAFT
    with pytest.raises(ExportNotAllowed):
        export_sanitized_text("f1", store_con(fascicolo))


def test_TC_05_risposta_con_un_segnaposto_inesistente_interrompe_il_ripristino():
    fascicolo = fascicolo_con(TESTO_RICCO)
    with pytest.raises(UnknownPlaceholder, match=r"\[PERSONA_99\]"):
        ripristina("Rispondo a [PERSONA_99].", fascicolo.entities)


def test_TC_06_una_mutazione_dopo_l_approvazione_riporta_in_pending_e_nega_l_export():
    fascicolo = fascicolo_con(TESTO_RICCO)
    approva(fascicolo)
    assert fascicolo.state is State.APPROVED
    registra_mutazione(fascicolo)
    assert fascicolo.state is State.PENDING_REVIEW
    with pytest.raises(ExportNotAllowed):
        export_sanitized_text("f1", store_con(fascicolo))
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano o passino, e capire perché**

Run: `.venv\Scripts\python -m pytest tests/test_matrice_consegna.py -v`

Questo è l'unico task del piano in cui alcuni test possono passare al primo colpo: il codice che verificano esiste già, e questi test lo mettono alla prova insieme per la prima volta. Il valore del task è proprio qui. **Se un test fallisce, non modificarlo per farlo passare**: il fallimento è la scoperta di un difetto di integrazione fra due task che singolarmente erano verdi. Riportalo con lo stato `DONE_WITH_CONCERNS` o `BLOCKED`, allegando l'output, e lascia decidere al controller.

Una nota su TC-02 e TC-03: dipendono dal modello spaCy, quindi le loro asserzioni sono deliberatamente lasche — TC-02 verifica l'assenza di una categoria, non un conteggio di entità.

- [ ] **Step 3: Eseguire l'intera suite, marker inclusi**

Run: `.venv\Scripts\python -m pytest`
Expected: tutto verde, output pulito.

- [ ] **Step 4: Commit**

```bash
git add tests/test_matrice_consegna.py
git commit -m "test: la matrice della consegna e il test anti-fuga generico"
```

---

## Fine del piano 2

Alla fine di questi nove task un fascicolo può essere caricato da TXT o PDF, analizzato dal motore del piano 1, approvato, esportato mascherato, salvato in un vault cifrato e riaperto, e una risposta dell'IA può essere ripristinata. Manca solo l'involucro: route HTTP, interfaccia di revisione e `tools/e2e_gemini.py`, che sono il piano 3.
