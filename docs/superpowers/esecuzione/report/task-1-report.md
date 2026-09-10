# Task 1: Ambiente, scaffolding e invariante di purezza — Report

## Stato: DONE

## Cosa è stato implementato

Seguiti tutti i 12 step del brief, in ordine, senza deviazioni dai valori verbatim richiesti.

1. **Virtualenv** creato in `.venv/` con `python -m venv .venv` (Python 3.14.5).
2. **`requirements.txt`** scritto verbatim:
   ```
   fastapi==0.137.1
   uvicorn[standard]==0.49.0
   pymupdf==1.28.0
   cryptography==48.0.0
   spacy==3.8.16
   python-multipart==0.0.20
   ```
3. **`requirements-dev.txt`** scritto verbatim:
   ```
   -r requirements.txt
   pytest==9.1.1
   httpx==0.28.1
   ```
4. **Dipendenze installate** in `.venv` con `pip install --upgrade pip` seguito da `pip install -r requirements-dev.txt`. Tutte le wheel risolte come precompilate `cp314` per Windows (nessuna build da sorgenti, nessun compilatore richiesto), incluso l'intero stack nativo di spaCy (thinc, blis, murmurhash, preshed, srsly, cymem).
5. **Modello linguistico `it_core_news_lg`** scaricato con `python -m spacy download it_core_news_lg`. Non è stato necessario l'URL pinnato alternativo: il download standard ha funzionato al primo tentativo, risolvendo la versione `it_core_news_lg==3.8.0` (compatibile con spacy 3.8.16 dichiarato nel brief).
6. **Verifica di caricamento del modello**: eseguito il comando di verifica, vedi evidenza sotto.
7. **`pyproject.toml`** scritto verbatim con build-system, project, tool.setuptools.packages.find, tool.pytest.ini_options (inclusi i marker `lento` e `rete`).
8. **Struttura di package** creata: `cryptocustode/__init__.py`, `cryptocustode/core/__init__.py`, `cryptocustode/core/detect/__init__.py`, `cryptocustode/state/__init__.py` — tutti file vuoti (0 byte), più la directory `tests/`.
9. **Test di architettura** `tests/test_architettura.py` scritto verbatim, come da brief.
10. **Verifica RED**: creato `cryptocustode/core/_prova.py` con `import fastapi`, eseguito il test, confermato il fallimento atteso (evidenza sotto), poi rimosso il file.
11. **Verifica GREEN**: dopo la rimozione del file di prova, il test passa.
12. **Commit** creato con il messaggio esatto richiesto dal brief.

## Versione esatta del modello spaCy installato

`it-core-news-lg==3.8.0` (installato via `spacy download`, che ha risolto e scaricato `it_core_news_lg-3.8.0-py3-none-any.whl`, 567.9 MB).

## Step 6 — output della verifica di caricamento del modello

Comando eseguito:
```
.venv\Scripts\python -c "import spacy; nlp = spacy.load('it_core_news_lg'); print([(e.text, e.label_) for e in nlp('Il contratto è firmato da Mario Rossi a Torino.').ents])"
```

Output:
```
[('Mario Rossi', 'PER'), ('Torino', 'LOC')]
```

Atteso rispettato: entità `PER` per "Mario Rossi" presente nella lista.

## Evidenza TDD

### RED — Step 10

File temporaneo creato: `cryptocustode/core/_prova.py`
```python
import fastapi
```

Comando eseguito:
```
.venv\Scripts\python -m pytest tests/test_architettura.py -v
```

Output (estratto rilevante):
```
tests\test_architettura.py F                                             [100%]

================================== FAILURES ===================================
_____________________ test_core_non_importa_http_ne_stato _____________________

    def test_core_non_importa_http_ne_stato():
        violazioni = []
        for percorso in sorted(CORE.rglob("*.py")):
            for modulo in sorted(moduli_importati(percorso) & VIETATI):
                violazioni.append(f"{percorso.relative_to(RADICE)} importa {modulo}")
>       assert violazioni == [], "core/ deve restare puro:\n" + "\n".join(violazioni)
E       AssertionError: core/ deve restare puro:
E         cryptocustode\core\_prova.py importa fastapi
E       assert ['cryptocusto...orta fastapi'] == []

======================== 1 failed, 1 warning in 0.14s =========================
```

Il fallimento riporta esattamente il messaggio atteso dal brief: `cryptocustode\core\_prova.py importa fastapi`. Questo dimostra che il test individua correttamente una violazione reale dell'invariante (un modulo in `core/` che importa `fastapi`), e non è un test che passerebbe comunque per costruzione difettosa.

Nota: al primo run è comparso anche un `PytestCacheWarning: could not create cache path ... WinError 5: Accesso negato` nella creazione di `.pytest_cache`. Non è legato al test: è una race condition transitoria dovuta alla sincronizzazione OneDrive sulla cartella di progetto (la cartella `.pytest_cache` risultava comunque creata correttamente subito dopo). Riprodotto e verificato come intermittente: in altri run (incluso quello GREEN riportato sotto) non compare, e in un run successivo del comando finale di verifica è ricomparso una volta. Non influisce sul risultato del test (`assert`/`FAILED`/`PASSED` sono corretti in ogni caso) — è rumore ambientale, non applicativo. Non è stato apportato alcun rimedio applicativo perché fuori scope del task e non riproducibile in modo deterministico.

File di prova rimosso subito dopo la verifica (Step 11), non presente nel commit.

### GREEN — Step 11

Comando eseguito:
```
.venv\Scripts\python -m pytest tests/test_architettura.py -v
```

Output:
```
tests\test_architettura.py .                                             [100%]

============================== 1 passed in 0.03s ==============================
```

Nessun warning, output pulito.

## File creati/modificati

- `requirements.txt` (nuovo)
- `requirements-dev.txt` (nuovo)
- `pyproject.toml` (nuovo)
- `cryptocustode/__init__.py` (nuovo, vuoto)
- `cryptocustode/core/__init__.py` (nuovo, vuoto)
- `cryptocustode/core/detect/__init__.py` (nuovo, vuoto)
- `cryptocustode/state/__init__.py` (nuovo, vuoto)
- `tests/test_architettura.py` (nuovo)
- `.venv/` creato ma non tracciato (correttamente escluso da `.gitignore`)

## Commit

```
4d48f18 chore: ambiente, scaffolding e test di architettura su core/
 8 files changed, 64 insertions(+)
```

Nessun cambio di branch, nessun merge, nessun push. Branch rimasto `feat/motore-riconoscimento` per tutta la durata del task.

## Auto-revisione

- **Completezza**: tutti i 12 step del brief eseguiti nell'ordine dato, nessuno saltato. Nessun caso limite applicabile: il task è puro scaffolding.
- **Qualità**: i contenuti di `requirements.txt`, `requirements-dev.txt`, `pyproject.toml` e `tests/test_architettura.py` sono stati verificati byte-per-byte contro il testo del brief (confronto diretto via `cat`), risultano identici. I quattro `__init__.py` sono vuoti (0 byte) come richiesto.
- **Disciplina**: nessuna aggiunta oltre a quanto richiesto. Non ho creato file `README.md` o altra documentazione non richiesta. Non ho toccato `.gitignore` (già corretto per questo task). Non ho modificato lo stato preesistente di `.superpowers/` (che risulta ignorato da git per motivi indipendenti da questo task, non investigato oltre perché fuori scope).
- **Test**: il test verifica comportamento reale — è stato dimostrato che sa fallire (RED, con messaggio esatto atteso) e che passa quando l'invariante è rispettata (GREEN). Output finale pulito, un solo test, nessun warning nell'ultimo run pulito. Il warning intermittente di `PytestCacheWarning` legato a OneDrive è stato osservato, diagnosticato come rumore ambientale non deterministico, e documentato sopra.

## Problemi o preoccupazioni

- **Warning intermittente `PytestCacheWarning` (OneDrive)**: in alcuni run pytest non riesce a scrivere `.pytest_cache/v/cache/nodeids` per un `WinError 5: Accesso negato`, quasi certamente causato dalla sincronizzazione di OneDrive sulla cartella di progetto (che vive sotto `OneDrive - TRECUORI\Desktop\...`). Non influisce sull'esito dei test (pass/fail restano corretti) ed è già escluso da `.gitignore`. Segnalo perché potrebbe ripresentarsi nei task successivi durante l'esecuzione della suite; non richiede azione per questo task.
- Nessun altro problema riscontrato. Step 5 (download modello) e step 4 (installazione dipendenze) sono andati a buon fine al primo tentativo, senza necessità di fallback.

---

## Capitolo di fix: correzione rilievo `plan-mandated` su `test_architettura.py`

### Stato: DONE

### Contesto

La revisione ha giudicato conformi i requisiti e genuina l'evidenza TDD del Task 1, ma ha rilevato (Important, `plan-mandated`) che `moduli_importati()` in `tests/test_architettura.py` non rileva `cryptocustode.state` importato con quattro stili:

1. `from cryptocustode import state`
2. `import cryptocustode.state.store`
3. `from ..state import State`
4. `from .. import state`

Il difetto era nel codice fornito verbatim dal brief (Step 9), non nell'implementazione del task precedente. Il revisore ha autorizzato e richiesto la correzione, con una struttura specifica (funzione pura `nomi_vietati_in(sorgente, pacchetto) -> set[str]`) e un ciclo TDD esplicito.

### Cosa è stato cambiato

Modificato solo `tests/test_architettura.py` (logica) e `pyproject.toml` (una riga, deviazione minore autorizzata, vedi sotto). Nessun altro file toccato.

**In `tests/test_architettura.py`:**

- Rimossa la funzione `moduli_importati(percorso)` che operava per uguaglianza esatta su nomi raccolti con `ast.walk` + `split(".")[0]`.
- Aggiunta `_e_vietato(nome)`: un nome è vietato se `nome == vietato` oppure `nome.startswith(vietato + ".")`, per ciascun `vietato` in `VIETATI`. Sostituisce il confronto per uguaglianza/primo-segmento con un confronto per prefisso.
- Aggiunta `_base_import_relativo(livello, pacchetto)`: risolve la base assoluta di un `ImportFrom` relativo. Per `livello == 0` (import assoluto) restituisce `""`. Per `livello > 0`, tronca `pacchetto` di `livello - 1` segmenti e ne fa una stringa puntata.
- Aggiunta `nomi_vietati_in(sorgente: str, pacchetto: list[str]) -> set[str]`: funzione pura che analizza il sorgente con `ast.parse`, e per ogni nodo:
  - `ast.Import`: aggiunge `alias.name` per esteso (non più anche il primo segmento: il confronto per prefisso lo rende superfluo, come indicato dal revisore).
  - `ast.ImportFrom`: calcola `base` con `_base_import_relativo`, poi `modulo = f"{base}.{nodo.module}"` se `base` e `nodo.module` esistono entrambi, altrimenti `nodo.module` (se `base` è vuota, cioè import assoluto) o `base` (se `nodo.module` è `None`, cioè `from .. import x`). Aggiunge `modulo` e, per ciascun alias importato, `f"{modulo}.{alias.name}"` — è quest'ultimo a rendere rilevabili i casi 1 e 4, dove il nome vietato è il sibling importato e non il modulo di partenza.
  - Filtra l'insieme risultante con `_e_vietato`.
- Aggiunta `pacchetto_del_file(percorso: Path) -> list[str]`: il pacchetto di un file è `percorso.relative_to(RADICE).parts[:-1]` — vale uniformemente sia per un modulo (`core/rilevamento.py` → pacchetto `["cryptocustode", "core"]`) sia per un `__init__.py` (`core/detect/__init__.py` → pacchetto `["cryptocustode", "core", "detect"]`, cioè il pacchetto che l'`__init__.py` stesso rappresenta).
- `test_core_non_importa_http_ne_stato` ora costruisce `pacchetto` per ogni file con `pacchetto_del_file` e chiama `nomi_vietati_in(sorgente, pacchetto)` invece di intersecare `moduli_importati(percorso)` con `VIETATI`. Stesso messaggio di violazione (`"{percorso} importa {nome}"`), stessa asserzione (`violazioni == []`).

Verifica manuale della risoluzione dei quattro stili con `pacchetto = ["cryptocustode", "core"]` (il pacchetto usato in tutti i nuovi test unitari, rappresentativo di un modulo o `__init__.py` posto direttamente dentro `core/`):

| Stile | `nomi_vietati_in(...)` restituisce |
|---|---|
| `from cryptocustode import state` | `{"cryptocustode.state"}` |
| `import cryptocustode.state.store` | `{"cryptocustode.state.store"}` |
| `from ..state import State` | `{"cryptocustode.state", "cryptocustode.state.State"}` |
| `from .. import state` | `{"cryptocustode.state"}` |

### Test aggiunti

Nove test totali oltre a `test_core_non_importa_http_ne_stato` (che resta invariato nella firma, aggiornato solo nell'implementazione interna):

- `test_rileva_import_assoluto_fastapi` — `import fastapi` → `{"fastapi"}` (caso che già funzionava).
- `test_rileva_import_assoluto_uvicorn` — `import uvicorn` → `{"uvicorn"}` (caso che già funzionava).
- `test_rileva_from_import_assoluto_su_sottomodulo` — `from starlette.responses import JSONResponse` → non vuoto (caso che già funzionava; assert di non-vuotezza anziché di uguaglianza esatta, perché il contenuto esatto del set cambia con la correzione pur restando una rilevazione corretta in entrambe le versioni).
- `test_rileva_from_import_di_sibling_assoluto` — stile 1: `from cryptocustode import state` → `{"cryptocustode.state"}`.
- `test_rileva_import_assoluto_con_sottomoduli_multipli` — stile 2: `import cryptocustode.state.store` → `{"cryptocustode.state.store"}`.
- `test_rileva_from_import_relativo_a_due_punti` — stile 3: `from ..state import State` → `{"cryptocustode.state", "cryptocustode.state.State"}`.
- `test_rileva_import_relativo_del_pacchetto_sibling` — stile 4: `from .. import state` → `{"cryptocustode.state"}`.
- `test_non_vieta_import_di_moduli_interni_a_core` (negativo) — `from cryptocustode.core.models import Span` → `set()`.
- `test_non_vieta_import_del_pacchetto_radice` (negativo) — `import cryptocustode` → `set()`.

I due casi negativi verificano che il confronto per prefisso non sia sovra-aggressivo: `cryptocustode.core.models` non deve mai risultare vietato (è interno a `core/`), e importare il pacchetto radice `cryptocustode` da solo non deve bastare a far scattare il divieto su `cryptocustode.state`.

### Ciclo TDD seguito

**RED.** Prima di correggere, ho scritto `nomi_vietati_in` portando fedelmente la logica *buggata* precedente (uguaglianza esatta, nessuna risoluzione di import relativi, nessun alias per `ImportFrom`) nella nuova firma `nomi_vietati_in(sorgente, pacchetto)`, e ho aggiunto tutti e nove i test sopra. Comando eseguito:

```
.venv\Scripts\python -m pytest tests/test_architettura.py -v
```

Output (completo):

```
============================= test session starts =============================
platform win32 -- Python 3.14.5, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\emanuele.quagliotto\OneDrive - TRECUORI\Desktop\Progetti Claude\CryptoCustode
configfile: pyproject.toml
plugins: anyio-4.15.1
collected 10 items

tests\test_architettura.py ....FFFF..                                    [100%]

================================== FAILURES ===================================
_________________ test_rileva_from_import_di_sibling_assoluto _________________

    def test_rileva_from_import_di_sibling_assoluto():
        """`from cryptocustode import state`: il nome vietato è l'alias importato,
        non il modulo di partenza (che è solo `cryptocustode`)."""
        trovati = nomi_vietati_in("from cryptocustode import state\n", PACCHETTO_DI_PROVA)
>       assert trovati == {"cryptocustode.state"}
E       AssertionError: assert set() == {'cryptocustode.state'}
E         
E         Extra items in the right set:
E         'cryptocustode.state'
E         Use -v to get more diff

tests\test_architettura.py:76: AssertionError
____________ test_rileva_import_assoluto_con_sottomoduli_multipli _____________

    def test_rileva_import_assoluto_con_sottomoduli_multipli():
        """`import cryptocustode.state.store`: nessuna uguaglianza esatta con
        "cryptocustode.state" è possibile, serve il confronto per prefisso."""
        trovati = nomi_vietati_in("import cryptocustode.state.store\n", PACCHETTO_DI_PROVA)
>       assert trovati == {"cryptocustode.state.store"}
E       AssertionError: assert set() == {'cryptocustode.state.store'}
E         
E         Extra items in the right set:
E         'cryptocustode.state.store'
E         Use -v to get more diff

tests\test_architettura.py:83: AssertionError
________________ test_rileva_from_import_relativo_a_due_punti _________________

    def test_rileva_from_import_relativo_a_due_punti():
        """`from ..state import State`: l'import relativo va risolto con il
        prefisso del pacchetto assoluto prima del confronto."""
        trovati = nomi_vietati_in("from ..state import State\n", PACCHETTO_DI_PROVA)
>       assert trovati == {"cryptocustode.state", "cryptocustode.state.State"}
E       AssertionError: assert set() == {'cryptocusto....state.State'}
E         
E         Extra items in the right set:
E         'cryptocustode.state'
E         'cryptocustode.state.State'
E         Use -v to get more diff

tests\test_architettura.py:90: AssertionError
______________ test_rileva_import_relativo_del_pacchetto_sibling ______________

    def test_rileva_import_relativo_del_pacchetto_sibling():
        """`from .. import state`: nodo.module è None, il nome vietato è l'alias
        importato, non il modulo di partenza (che qui non esiste nemmeno)."""
        trovati = nomi_vietati_in("from .. import state\n", PACCHETTO_DI_PROVA)
>       assert trovati == {"cryptocustode.state"}
E       AssertionError: assert set() == {'cryptocustode.state'}
E         
E         Extra items in the right set:
E         'cryptocustode.state'
E         Use -v to get more diff

tests\test_architettura.py:97: AssertionError
============================== warnings summary ===============================
.venv\Lib\site-packages\_pytest\cacheprovider.py:469
  C:\Users\emanuele.quagliotto\OneDrive - TRECUORI\Desktop\Progetti Claude\CryptoCustode\.venv\Lib\site-packages\_pytest\cacheprovider.py:469: PytestCacheWarning: could not create cache path C:\Users\emanuele.quagliotto\OneDrive - TRECUORI\Desktop\Progetti Claude\CryptoCustode\.pytest_cache\v\cache\nodeids: [WinError 5] Accesso negato: 'C:\\Users\\emanuele.quagliotto\\OneDrive - TRECUORI\\Desktop\\Progetti Claude\\CryptoCustode\\pytest-cache-files-cghfnh2t' -> 'C:\\Users\\emanuele.quagliotto\\OneDrive - TRECUORI\\Desktop\\Progetti Claude\\CryptoCustode\\.pytest_cache'
    config.cache.set("cache/nodeids", sorted(self.cached_nodeids))

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ===========================
FAILED tests/test_architettura.py::test_rileva_from_import_di_sibling_assoluto
FAILED tests/test_architettura.py::test_rileva_import_assoluto_con_sottomoduli_multipli
FAILED tests/test_architettura.py::test_rileva_from_import_relativo_a_due_punti
FAILED tests/test_architettura.py::test_rileva_import_relativo_del_pacchetto_sibling
=================== 4 failed, 6 passed, 1 warning in 0.13s ====================
```

Le quattro rotture corrispondono esattamente ai quattro stili segnalati dal revisore, ognuna con `set()` restituito invece del set atteso — nessun errore di sintassi o di importazione, solo mancata rilevazione, esattamente come diagnosticato. Nota anche il `PytestCacheWarning` da OneDrive, riprodotto qui indipendentemente da quanto già osservato dall'implementatore precedente: risolto dalla modifica a `pyproject.toml` (vedi sotto).

**GREEN.** Sostituita l'implementazione buggata con `_e_vietato`, `_base_import_relativo` e `nomi_vietati_in` come descritti sopra. Comando eseguito:

```
.venv\Scripts\python -m pytest tests/test_architettura.py -v
```

Output (completo):

```
============================= test session starts =============================
platform win32 -- Python 3.14.5, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\emanuele.quagliotto\OneDrive - TRECUORI\Desktop\Progetti Claude\CryptoCustode
configfile: pyproject.toml
plugins: anyio-4.15.1
collected 10 items

tests\test_architettura.py ..........                                    [100%]

============================= 10 passed in 0.04s ==============================
```

Tutti e dieci i test passano.

### Deviazione minore autorizzata: `-p no:cacheprovider`

Autorizzata dal revisore in chat (non nel brief originale). Modificato `pyproject.toml`:

```diff
-addopts = "-q --strict-markers"
+addopts = "-q --strict-markers -p no:cacheprovider"
```

Motivo: il `PytestCacheWarning` (visto sia dall'implementatore precedente sia riprodotto sopra nella fase RED) è causato dalla sincronizzazione OneDrive sulla cartella di progetto e inquinerebbe l'output di tutti gli otto task. Disattivare il plugin di cache costa solo `--lf`/`--ff`, non necessari su questa suite. Verificato che dopo la modifica l'output torna pulito, senza warning:

```
.venv\Scripts\python -m pytest tests/test_architettura.py -v
```

```
============================= test session starts =============================
platform win32 -- Python 3.14.5, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\emanuele.quagliotto\OneDrive - TRECUORI\Desktop\Progetti Claude\CryptoCustode
configfile: pyproject.toml
plugins: anyio-4.15.1
collected 10 items

tests\test_architettura.py ..........                                    [100%]

============================= 10 passed in 0.03s ==============================
```

Il rilievo Minor sulla dimostrazione RED limitata a `import fastapi` è risolto di conseguenza dai nove test aggiunti sopra: non è stata apportata alcuna azione ulteriore.

### Suite completa

Comando eseguito (nessun altro file di test presente nel repo oltre a `tests/test_architettura.py`, quindi la suite completa coincide con l'esecuzione sopra):

```
.venv\Scripts\python -m pytest -v
```

Output (completo):

```
============================= test session starts =============================
platform win32 -- Python 3.14.5, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\emanuele.quagliotto\OneDrive - TRECUORI\Desktop\Progetti Claude\CryptoCustode
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.15.1
collected 10 items

tests\test_architettura.py ..........                                    [100%]

============================= 10 passed in 0.03s ==============================
```

### File modificati in questo capitolo di fix

- `tests/test_architettura.py` (logica di rilevamento riscritta, nove test aggiunti)
- `pyproject.toml` (una riga, deviazione autorizzata dal revisore)

Nessun altro file toccato. Nessun cambio di branch, nessun merge, nessun push. Branch rimasto `feat/motore-riconoscimento`.

### Auto-revisione del fix

- I quattro stili segnalati dal revisore sono ora tutti coperti da un test dedicato, con RED dimostrato sull'implementazione precedente (portata alla nuova firma) e GREEN dimostrato dopo la correzione.
- I casi che già funzionavano restano verificati (nessuna regressione).
- Due casi negativi verificano che il confronto per prefisso non sia sovra-aggressivo.
- `test_core_non_importa_http_ne_stato` continua a passare sul repo reale (nessuna violazione presente).
- Nessuna dipendenza aggiunta. Nessun file toccato oltre ai due autorizzati. Naming in italiano rispettato (`_e_vietato`, `_base_import_relativo`, `nomi_vietati_in`, `pacchetto_del_file`, `PACCHETTO_DI_PROVA`).
