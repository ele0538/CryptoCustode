# SDD ledger — plan: docs/superpowers/plans/2026-09-10-motore-riconoscimento.md

Spec: docs/superpowers/specs/2026-09-10-cryptocustode-design.md (leggibile, autorità vincolante)
Ramo: feat/motore-riconoscimento — BASE iniziale 549b071

Ruling: lavoro su ramo in-place invece che su worktree separato — il Task 1 scarica
`it_core_news_lg` (~550 MB) dentro `.venv/`, che è gitignored e non sopravvivrebbe alla
cancellazione del worktree, costringendo a riscaricarlo nella directory principale.
Costo se sbagliato: `master` non è isolato da un checkout accidentale; rimediabile con
`git switch`.

## Pre-flight scan

### Coppie di task che condividono file o interfacce

| Da | A | Prodotto contro consumato | Esito |
|---|---|---|---|
| T1 | tutti | struttura di package `cryptocustode/`, `cryptocustode/core/`, `core/detect/` | coerente: ogni task successivo crea file dentro quei package |
| T1 | T6 | marker `lento` dichiarato in `pyproject.toml` contro `pytestmark = pytest.mark.lento` | coerente; `--strict-markers` renderebbe l'errore visibile |
| T1 | T7, T8 | comando `-m "not lento"` contro il marker dichiarato | coerente |
| T2 | T4 | `Category`, `Source`, `Span` contro import in `rules.py` | coerente |
| T2 | T5 | `PRIORITA` esposta via `Span.priorita` contro `_forza()` | coerente |
| T2 | T6 | `Category`, `Source`, `Span` contro `ner.py` | coerente |
| T2 | T7 | `Ambiguity`, `AmbiguityKind`, `Entity`, `Fascicolo` contro `entities.py` | coerente |
| T2 | T8 | `Document`, `Entity`, `Fascicolo`, `Span` contro `mask.py` | coerente |
| T3 | T4 | `cf_valido`, `piva_valida`, `iban_valido` contro `_VALIDATORI` in `rules.py` | coerente, nomi identici |
| T4 | T7 | `trova_per_regole(testo, doc_id)` contro `analizza_documento` | coerente |
| T5 | T7 | `risolvi(spans)` contro `analizza_documento` | coerente |
| T6 | T7 | `trova_per_ner(testo, doc_id)` contro `analizza_documento(usa_ner=True)` | coerente |
| T7 | T8 | nessuna dipendenza diretta: i test di T8 costruiscono entità a mano | coerente, voluto |
| T4 | T4 | `MESI` esportata da `patterns.py` contro import in `rules.py` | coerente |

### Coerenza interna di ciascun task

| Task | Test specificati contro codice specificato | Esito |
|---|---|---|
| T1 | il test di architettura viene fatto fallire deliberatamente prima di essere accettato | coerente |
| T2 | `MAX_DOCUMENTI = 10` senza annotazione non diventa un campo della dataclass | corretto |
| T3 | dati di test calcolati a mano (CIN `Q`, P.IVA `...903`, IBAN MOD-97 = 1) | verificati a mano, non circolari |
| T4 | **incoerenza**: il docstring dice "span di priorità P1-P3", ma `PATTERN` contiene anche `AZIENDA` e `INDIRIZZO`, che sono P4 | vedi Ruling 1 |
| T5 | `si_sovrappongono` più `risolvi` contro l'invariante testata su 6 span | coerente |
| T6 | asserzioni volutamente lasche (nessun conteggio esatto di entità) | coerente con la fragilità del modello |
| T7 | **lacuna**: `chiavi_equivalenti` è testata ma nessun codice genera `HEURISTIC_MERGE_SUGGESTION`, che la spec §7 richiede | vedi Ruling 2 |
| T8 | `dataclasses.replace` su dataclass congelata; hash indipendente dall'ordine dei documenti | coerente |

### Rulings pre-esecuzione

**Ruling 1 (T4)** — Il docstring di `rules.py` che promette "P1-P3" è sbagliato, non il
codice: la spec §6 assegna ad `AZIENDA` e `INDIRIZZO` sia il NER sia i pattern, quindi il
motore a regole produce legittimamente anche span P4. Il docstring va scritto "span da
regole deterministiche, di qualunque priorità". Costo se sbagliato: solo una frase di
commento fuorviante.

**Ruling 2 (T7)** — Lacuna reale di copertura della spec: la §7 impone che una
corrispondenza per euristica apra una `HEURISTIC_MERGE_SUGGESTION`, ma il piano espone
`chiavi_equivalenti` senza mai chiamarla in produzione. Il Task 7 deve aggiungere
`suggerisci_fusioni(fascicolo) -> None`, che confronta a coppie le entità di
`_CATEGORIE_CON_VARIANTI` con `chiavi_equivalenti` e apre una ambiguità
`HEURISTIC_MERGE_SUGGESTION` non bloccante per ogni coppia equivalente non già
segnalata; più un test che verifica che "M. Rossi" e "Mario Rossi" in documenti diversi
producano un suggerimento non bloccante. Costo se sbagliato: senza questo, la spec §7 e
il punto 4 della consegna restano parzialmente non implementati, e il piano 3 costruirebbe
una UI di disambiguazione senza nulla da mostrare.

### Punto da tenere d'occhio (non un ruling)

La regex IBAN `\b[A-Z]{2}\d{2}(?:\s?[0-9A-Z]){11,30}\b` è greedy e, se un IBAN è seguito
da testo in maiuscolo, può inglobarlo: il match più lungo non supera MOD-97 e l'IBAN viene
perso del tutto invece di essere riconosciuto. Non si manifesta sui test del Task 4. Se
emergerà, la correzione è rendere il quantificatore lazy o ancorare la lunghezza.

## Avanzamento

Task 1: implementato (commit 4d48f18, "chore: ambiente, scaffolding e test di architettura su core/"),
  1/1 test passa, RED dimostrato allo step 10. Revisione dispacciata.
  Concern dell'implementatore: `PytestCacheWarning` (WinError 5) intermittente, causato dalla
  sincronizzazione OneDrive sulla cartella `.pytest_cache`.

Ruling 3 (ambiente) — Il repo vive in una cartella sincronizzata da OneDrive, che nega
  intermittentemente la scrittura su `.pytest_cache`. Il warning inquinerebbe l'output dei
  test di tutti gli 8 task, e "output pulito" è un criterio di revisione: ogni revisore lo
  segnalerebbe di nuovo. Decido di aggiungere `-p no:cacheprovider` ad `addopts` in
  `pyproject.toml`, disattivando la cache di pytest. Costo se sbagliato: si perdono `--lf` e
  `--ff`, che su una suite di questa dimensione non servono. La modifica viaggia nel dispatch
  del Task 2 come cambiamento autorizzato fuori brief, e va dichiarata al suo revisore.

Task 1: revisione — spec ✅ conforme (pin, struttura, commit singolo, evidenza TDD genuina),
  ma 1 Important `plan-mandated`: il test di architettura non rileva `cryptocustode.state`
  negli stili `from cryptocustode import state`, `from ..state import State`,
  `from .. import state`, `import cryptocustode.state.store`. Qualità: servono correzioni.
  ⚠️ risolto dal controller: `pip freeze` corrisponde a tutti i pin del brief; modello
  it_core_news_lg 3.8.0 carica e riconosce ("Mario Rossi" PER, "Torino" LOC).

Ruling 4 (T1) — Il rilievo è fondato e il difetto è del piano, non dell'implementatore:
  ho verificato i quattro stili di import e nessuno viene rilevato. La spec §4 invariante 1
  esige una garanzia funzionante, e la spec è l'autorità vincolante: il codice del piano va
  corretto, non difeso. Il test deve risolvere gli import relativi in nomi assoluti,
  considerare `modulo.alias` per gli `ImportFrom`, e confrontare per prefisso invece che per
  uguaglianza o primo segmento. Costo se sbagliato: nessuno sul comportamento del prodotto;
  senza la correzione l'invariante centrale del progetto sarebbe aggirabile con import
  idiomatici, e i sette task successivi scriverebbero codice in `core/` senza rete di
  protezione.

Ruling 3 rivisto — `-p no:cacheprovider` entra nel fix round del Task 1 invece che nel
  dispatch del Task 2: il revisore ha segnalato lo stesso rumore in autonomia (Minor 1), e
  farlo qui evita che nel Task 2 sembri una modifica fuori ambito.
Task 1: fix round 1/5 (2 addressed, 0 open — lacune di rilevamento import risolte con funzione
  pura `nomi_vietati_in` + risoluzione import relativi + confronto per prefisso; `-p no:cacheprovider`
  aggiunto; commits 4d48f18..3dfd29e), 10/10 test, output pulito.
Task 1: complete (commits 549b071..3dfd29e, review clean)
Task 2: implementato (commit 71d921d, "feat: tipi di dominio con priorita e fascicolo vuoto"),
  8/8 su test_models + 10/10 architettura. Revisione dispacciata. BASE task 2 = 3dfd29e.
Task 2: revisione — spec ✅ conforme (12 categorie, priorità P1-P4, stati senza DIRTY, frozen,
  MAX_DOCUMENTI senza annotazione, solo import stdlib), qualità Approvato, 0 Critical, 0 Important.
Task 2: minor (deferred): `test_fascicolo_accetta_al_massimo_dieci_documenti` verifica solo la
  costante, non il rifiuto dell'undicesimo documento — il nome promette più di quanto asserisca;
  l'enforcement vive nel piano 2.
Task 2: minor (deferred): il docstring di models.py dice "nessun comportamento" ma il modulo ha
  tre @property derivate (plan-mandated); tensione solo lessicale.
Task 2: ⚠️ risolti dal controller — formato segnaposto, logica AND dei due interruttori e reset a
  PENDING_REVIEW non appartengono a questo task: i primi due arrivano nei Task 7 e 8, il terzo nel
  piano 2. Non sono lacune.
Task 2: complete (commits 3dfd29e..71d921d, review clean)

Ruling 5 (T2) — Il messaggio del commit 71d921d dice "priorita" senza accento, mentre il brief
  scriveva "priorità". Verificato con `git log -1 --format=%B`. Accetto così com'è: riscrivere la
  storia git per un diacritico costa più di quanto valga. Costo se sbagliato: nessuno funzionale,
  solo una lettera senza accento nella storia.

Task 3: implementato (commit cfc31ae, "feat: validatori di codice fiscale, partita IVA e IBAN"),
  22/22 su test_validators, 40 totali, nessuna regressione. Revisione dispacciata. BASE = 71d921d.

Task 3: revisione — spec ✅ conforme (trascrizione fedele, nessun valore atteso alterato,
  regex CF con omocodia corretta, P.IVA e IBAN corretti, solo import stdlib). Qualità: Approvato.
  Il revisore ha eseguito il controllo mirato autorizzato sulle voci K,P,T,V,X,Z di _DISPARI
  calcolando a mano un CIN su input sintetico: nessuna discrepanza.
Task 3: 1 Important APERTO, `plan-mandated` — `test_omocodia_non_fa_esplodere_il_calcolo`
  asserisce solo `cin.isalpha() and len(cin)==1`, quindi verifica che il lookup non sollevi
  KeyError, non che il calcolo sull'omocodia sia corretto. Difetto del piano, non
  dell'implementatore.

Ruling 6 (T3) — Il rilievo è fondato, ma NON apro un fix round: l'utente ha comunicato che i
  crediti stanno finendo e ha chiesto di consegnare tutto su GitLab per riprendere da un altro
  account. Fermo il ciclo qui e lascio il rilievo APERTO e documentato nell'handoff, invece di
  spendere un round di implementatore piu re-review. Costo se sbagliato: il validatore resta
  corretto (verificato due volte, dal report e dal controllo mirato del revisore), ma un futuro
  scambio di tabelle su input omocodici passerebbe inosservato fino a quando il test non viene
  irrobustito. NON e un'accettazione silenziosa: e il primo lavoro della prossima sessione.

Esecuzione interrotta su richiesta dell'utente dopo il Task 3. Task 4-8 da fare.
