# Handoff — stato dell'esecuzione al 2026-09-10

Documento per riprendere il lavoro in una sessione nuova, eventualmente da un altro
account. Contiene lo stato esatto, il punto di ripresa, e le decisioni prese finora.

## Dove siamo

**Ramo di lavoro:** `feat/motore-riconoscimento` (partito da `master`)
**Piano in esecuzione:** `docs/superpowers/plans/2026-09-10-motore-riconoscimento.md` — piano **1 di 3**
**Spec di riferimento:** `docs/superpowers/specs/2026-09-10-cryptocustode-design.md` — autorità vincolante
**Suite:** 40 test, tutti verdi

| Commit | Contenuto |
|---|---|
| `53485d7` | configurazione agenti (`CLAUDE.md`, `docs/agents/`) e design | 
| `549b071` | piano 1 e correzione di un'incoerenza della spec |
| `4d48f18` | Task 1 — ambiente, scaffolding, test di architettura |
| `3dfd29e` | Task 1 fix round 1 — lacune di rilevamento import |
| `71d921d` | Task 2 — tipi di dominio |
| `cfc31ae` | Task 3 — validatori CF, P.IVA, IBAN |

### Stato dei task del piano 1

| Task | Stato |
|---|---|
| 1 — Ambiente, scaffolding, invariante di purezza | **completo**, revisione pulita dopo 1 round di correzione |
| 2 — Modello dati | **completo**, revisione approvata, 2 Minor differiti |
| 3 — Validatori deterministici | **implementato e revisionato, qualità approvata**, con **1 rilievo Important aperto**: vedi sotto |
| 4 — Pattern e motore a regole | da fare, brief già estratto |
| 5 — Risoluzione degli span | da fare |
| 6 — Riconoscimento statistico con spaCy | da fare |
| 7 — Entità, euristiche, coda ambiguità | da fare, **con il Ruling 2 da applicare** |
| 8 — Masking puro e hash canonico | da fare |

## Il punto di ripresa esatto

**Primo lavoro: irrobustire il test sull'omocodia del Task 3.** La revisione del Task 3 ha
approvato la qualità del task e confermato la correttezza dei validatori — il revisore ha
anche ricalcolato a mano un CIN su input sintetico per verificare le voci di `_DISPARI` mai
esercitate dai test, senza trovare discrepanze. Resta però **un rilievo Important aperto**,
che è un difetto del piano e non dell'implementatore:

`tests/test_validators.py`, `test_omocodia_non_fa_esplodere_il_calcolo` asserisce soltanto
`cin.isalpha() and len(cin) == 1`. Verifica quindi che il lookup nelle tabelle non sollevi
`KeyError`, non che il calcolo su un codice fiscale omocodico sia corretto. Poiché la
selezione della tabella dipende solo dalla parità della posizione, uno scambio fra
`_DISPARI` e `_PARI` in condizioni particolari passerebbe inosservato.

*Come chiuderlo:* sostituire l'asserzione debole con un valore atteso concreto, calcolato a
mano dalle tabelle ufficiali su un codice omocodico sintetico, e verificare che
`cf_valido` accetti quel codice completo del suo CIN corretto e lo rifiuti con un CIN
alterato. Il calcolo va fatto a mano e mostrato nel commento del test: **non** derivare il
valore atteso eseguendo la funzione che il test deve verificare, perché sarebbe circolare.

Non ho aperto un round di correzione per questo: vedi Ruling 6.

**Poi si procede col Task 4**, il cui brief è rigenerabile con
`scripts/task-brief <piano> 4` della skill `subagent-driven-development`. Il materiale dei
task già chiusi è in `docs/superpowers/esecuzione/report/`.

## Ricostruire l'ambiente

`.venv/` non è nel repo (giustamente: contiene 550 MB di modello linguistico). Su una
macchina nuova:

```
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m spacy download it_core_news_lg
```

Verifica che il modello carichi e riconosca:

```
.venv\Scripts\python -c "import spacy; nlp=spacy.load('it_core_news_lg'); print([(e.text,e.label_) for e in nlp('Il contratto e firmato da Mario Rossi a Torino.').ents])"
```

Atteso: `[('Mario Rossi', 'PER'), ('Torino', 'LOC')]`.

Poi la suite:

```
.venv\Scripts\python -m pytest -q
```

Atteso: 40 test verdi. I test marcati `lento` caricano il modello; per saltarli,
`-m "not lento"`.

**Versioni verificate** su Python 3.14.5: `spacy` 3.8.16, modello `it_core_news_lg` 3.8.0,
`pymupdf` 1.28.0, `cryptography` 48.0.0, `fastapi` 0.137.1, `uvicorn` 0.49.0,
`python-multipart` 0.0.20, `pytest` 9.1.1, `httpx` 0.28.1. Le wheel `cp314` esistono per
tutto lo stack nativo di spaCy, quindi non serve un compilatore.

## Decisioni prese senza conferma dell'utente

Sei, in ordine. Ognuna è revocabile; la colonna del costo dice cosa si rischia se la
decisione era sbagliata.

**Ruling 1 — Ramo in-place invece di worktree separato.** Il Task 1 scarica 550 MB di
modello dentro `.venv/`, che è gitignored e non sopravvivrebbe alla cancellazione di un
worktree, costringendo a riscaricarlo. *Costo se sbagliato:* `master` non è protetto da un
checkout accidentale; si rimedia con `git switch`.

**Ruling 2 — Il Task 7 deve aggiungere `suggerisci_fusioni`. DA APPLICARE.** Il piano
espone `chiavi_equivalenti` e la testa, ma non la chiama mai in produzione: nessun codice
genera le ambiguità `HEURISTIC_MERGE_SUGGESTION` che la spec §7 richiede. Quando arriverai
al Task 7, aggiungi `suggerisci_fusioni(fascicolo) -> None` che confronta a coppie le
entità di `_CATEGORIE_CON_VARIANTI` con `chiavi_equivalenti` e apre una ambiguità
`HEURISTIC_MERGE_SUGGESTION` **non bloccante** per ogni coppia equivalente non già
segnalata, più un test che verifica che "M. Rossi" e "Mario Rossi" in documenti diversi
producano un suggerimento non bloccante. *Costo se non applicato:* la spec §7 e il punto 4
della consegna restano parzialmente non implementati, e il piano 3 costruirebbe una UI di
disambiguazione senza nulla da mostrare.

**Ruling 3 — `-p no:cacheprovider` in `pyproject.toml`.** Il repo vive in una cartella
sincronizzata da OneDrive, che nega intermittentemente la scrittura su `.pytest_cache` e
produce un `PytestCacheWarning` a ogni esecuzione. "Output dei test pulito" è un criterio
di revisione, quindi il rumore sarebbe stato segnalato a ogni task. *Costo se sbagliato:*
si perdono `--lf` e `--ff`.

**Ruling 4 — Correzione del test di architettura del Task 1.** Il codice che avevo scritto
nel piano non rilevava `cryptocustode.state` importato come `from cryptocustode import
state`, `import cryptocustode.state.store`, `from ..state import State` o `from .. import
state`: quattro stili idiomatici, tutti verificati come non rilevati. La spec §4 invariante
1 esige una garanzia funzionante e la spec è l'autorità vincolante, quindi ho corretto il
piano invece di difenderlo. Ora la logica risolve gli import relativi in nomi assoluti,
considera `modulo.alias` per gli `ImportFrom`, e confronta per prefisso. *Costo se
sbagliato:* nessuno sul prodotto; senza la correzione l'invariante centrale del progetto
sarebbe aggirabile e i task successivi scriverebbero in `core/` senza rete.

**Ruling 5 — Messaggio di commit senza accento.** Il commit `71d921d` dice "priorita"
invece di "priorità". Non riscrivo la storia git per un diacritico. *Costo se sbagliato:*
nessuno.

**Ruling 6 — Fermato il ciclo sul rilievo aperto del Task 3 invece di correggerlo.** Il
rilievo sul test dell'omocodia è fondato, ma i crediti stavano finendo e la priorità era
consegnare uno stato ripartibile: un round di implementatore più re-review li avrebbe
consumati senza garanzia di arrivare in fondo. Il rilievo resta **aperto e documentato**,
non accettato in silenzio, ed è il primo lavoro della prossima sessione. *Costo se
sbagliato:* i validatori restano corretti — verificati due volte, dal report
dell'implementatore e dal controllo indipendente del revisore — ma finché il test non è
irrobustito un futuro scambio di tabelle su input omocodici non verrebbe intercettato.

## Rilievi differiti, da triagiare nella revisione finale

- **Task 2** — `test_fascicolo_accetta_al_massimo_dieci_documenti` verifica solo che la
  costante valga 10, non che il fascicolo rifiuti un undicesimo documento. Il nome promette
  più di quanto asserisca; l'enforcement vero vive nel piano 2.
- **Task 2** — il docstring di `models.py` dice "nessun comportamento" ma il modulo ha tre
  `@property` derivate. Tensione solo lessicale, imposta dal piano.
- **Task 4, da tenere d'occhio** — la regex IBAN `\b[A-Z]{2}\d{2}(?:\s?[0-9A-Z]){11,30}\b`
  è greedy: se un IBAN è seguito da testo in maiuscolo può inglobarlo, il match più lungo
  non supera MOD-97 e l'IBAN viene perso del tutto invece di essere riconosciuto. Non si
  manifesta sui test del piano. Se emerge, la correzione è rendere il quantificatore lazy.

## Cosa resta oltre il piano 1

- **Piano 2** — caricamento TXT e PDF, verdetto scansione, controllo dei segnaposto
  preesistenti, tetto di 10 documenti, macchina a stati, gate di esportazione, ripristino
  della risposta dell'IA, vault cifrato.
- **Piano 3** — route HTTP, interfaccia web di revisione, test anti-fuga end-to-end,
  documenti di verifica distinti da quelli di sviluppo, README con istruzioni di avvio e
  limiti noti, script `tools/e2e_gemini.py`.

Nessuno dei due è ancora scritto: vanno prodotti con la skill `writing-plans` a partire
dalla spec, come è stato fatto per il piano 1.

## Nota sulle issue GitLab

Il progetto è `emanuele.quagliotto/CryptoCustode` (id 105) su `gitlab.trecuori.org`:
namespace personale, **non** `welfare/ai_service/` come diceva la versione precedente di
questa nota. `glab` è autenticato e funzionante.

**Il blocco sui permessi è risolto** (verificato 2026-09-10, 11:10 locali). Il token in uso
è `Claude_Access` (id 69, `granular: false`, scope `api` e `write_repository`, scadenza
2027-09-10), creato alle 10:26 locali. `projects/105`, `projects/105/issues` e
`projects/105/labels` rispondono tutti 200.

La nota precedente riportava `403 insufficient_granular_scope`, con `Project: Read` ma
senza `Work Item` né `Label`. Era vera, ma descriveva un token fine-grained già sostituito
36 minuti prima che questa riga venisse committata: è stata riportata senza retest. Non
ripetere quella conclusione senza aver prima riprovato una chiamata.

Il tracker resta comunque **vuoto**: 0 issue e 0 label. Le cinque label canoniche di
`docs/agents/triage-labels.md` non sono mai state create e i task 4-8 non esistono come
issue. `/to-tickets` e `/triage` ora hanno i permessi per crearle.

Attenzione: sull'istanza restano attivi cinque token granulari (`test`, `test 2`, `test 3`,
`test 4`, `accessoClaude`), nessuno dei quali ha `Work Item` o `Label`. Un client ancora
puntato su uno di essi continuerà a vedere `403 insufficient_granular_scope` anche ora che
`glab` funziona, perché è una credenziale diversa. Vanno revocati o riconfigurati.

Il percorso del binario, che non sempre è sul PATH delle shell degli agenti, è
`C:\Users\<utente>\AppData\Local\Programs\glab\glab.exe`.
