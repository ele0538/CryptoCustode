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

## Ripresa in sessione nuova — 2026-09-10

Ambiente verificato prima di toccare qualsiasi cosa: `.venv/` era sopravvissuto (non era
da ricreare), `it_core_news_lg` carica e riconosce ("Mario Rossi" PER, "Torino" LOC),
`40 passed in 0.07s`. Il workspace SDD non era stato ripulito: ledger, brief, report e
diff dei task 1-3 erano tutti al loro posto, e il ledger vivo e' risultato IDENTICO alla
copia consegnata in docs/superpowers/esecuzione/ledger-piano-1.md (diff vuoto), quindi non
e' servito nessun ripristino. HEAD = 0953ec0 (due commit di documentazione dopo cfc31ae).

Nota di processo: questa sessione non ha lo strumento TodoWrite, quindi il ledger e'
l'unico tracker. Ragione in piu' per tenerlo aggiornato a ogni passo.

Task 3: fix round 1/5 dispacciato (implementer fresco su sonnet: l'agente originale non
  sopravvive al cambio di sessione, quindi porta brief + report file + rilievo verbatim,
  come prevede la skill). FIX_BASE = 0953ec0.
  Controllo incrociato del controller: ho calcolato a mano il CIN di RSSMRAURMLNH5L1 per
  conto mio (somma 171, 171 mod 26 = 15) e verificato che con le tabelle _DISPARI/_PARI
  scambiate il risultato cambia (somma 167 -> 11), cioe' che quel codice discrimina
  davvero lo scambio che il rilievo teme. Il valore atteso NON e' stato passato
  all'implementatore, cosi' il suo calcolo a mano e' indipendente dal mio e i due si
  verificano a vicenda.
Task 3: fix round 1/5 (1 addressed, 0 open — asserzione debole sull'omocodia sostituita da
  `test_cin_omocodico_calcolato_a_mano` con CIN letterale "P" calcolato a mano, piu'
  cf_valido accettato con CIN corretto e rifiutato con CIN alterato; commits 0953ec0..c14d939),
  22/22 su test_validators, 40/40 totali, output pulito. validators.py non toccato.
  Verifica tripla indipendente: il CIN atteso e' stato calcolato a mano tre volte senza
  eseguire il codice sotto test — dal controller (171 -> 15 -> P), dall'implementatore
  (95+76=171 -> P) e dal re-revisore (95+76=171 -> P) — e tutte e tre concordano. Anche il
  controllo di discriminazione concorda: con le tabelle scambiate il risultato sarebbe 'L'
  (167 -> 11), diverso da 'P', quindi il test intercetta davvero uno scambio _DISPARI/_PARI.
  Il valore atteso e' un letterale nel test, non derivato da cin_atteso: non circolare.
Task 3: complete (commits 71d921d..c14d939, review clean — il rilievo Important lasciato
  aperto dal Ruling 6 della sessione precedente e' CHIUSO, non parcheggiato)

Task 4: implementato (commit 558eec2, "feat: pattern per categoria e motore a regole con
  requisito di contesto"), ma DONE_WITH_CONCERNS con 3 test FALLITI su 23. BASE task 4 = c14d939.
  L'implementatore ha trascritto il codice del brief verbatim, come gli era stato chiesto, e il
  codice del brief non passa i test del brief. Ho riprodotto i 3 fallimenti da solo e letto
  patterns.py e rules.py: le due cause sono difetti reali del piano, non dell'implementatore,
  e in entrambi i casi la spec sta con i test. Nessuna revisione dispacciata: i concern sono di
  correttezza, quindi si chiudono PRIMA della revisione (non consumano un fix round del ciclo).
  Nota di processo: l'implementatore ha committato con la suite rossa invece di fermarsi allo
  step 5. Non riscrivo la storia; il commit di correzione riporta la suite verde.

Ruling 7 (T4) — Il prefisso che si autocertifica. `_ha_contesto` guarda solo i 30 caratteri
  PRECEDENTI il match, quindi non puo' mai vedere un prefisso che fa parte del match stesso:
  `IT12345678903` e `+39 340 1234567` vengono scartati. Ma la spec §6 dice, alla lettera, che
  una sequenza nuda "viene taggata solo se compare il prefisso `IT` oppure una parola chiave di
  contesto entro i 30 caratteri precedenti", e che il requisito riguarda "una sequenza di 11
  cifre nuda, o un numero senza prefisso internazionale". Cioe': il prefisso IT soddisfa il
  requisito da solo, e un numero CON prefisso internazionale non e' soggetto al requisito.
  I due test del brief codificano la spec correttamente; il codice del brief no. La spec e'
  l'autorita' vincolante, quindi correggo il codice e NON i test. Decido: il contesto e'
  soddisfatto anche quando il match stesso inizia per `IT` (PIVA) o per `+39`/`0039` (TELEFONO)
  — la spec §6 nomina entrambi i prefissi internazionali, anche se il brief testa solo `+39`.
  Costo se sbagliato: se avessi letto male la spec, P.IVA con prefisso e numeri internazionali
  verrebbero mascherati senza parola chiave vicina — cioe' piu' mascheratura, non meno, quindi
  l'errore e' nella direzione prudente per la privacy; si revoca togliendo il controllo sul
  prefisso.

Ruling 8 (T4) — Parole di contesto con confine di parola, non sottostringa. `_ha_contesto` usa
  `parola in finestra`, matching per sottostringa: "particella" contiene "cell", quindi una
  particella catastale fabbrica contesto telefonico e un numero nudo viene taggato. Il difetto
  e' piu' ampio del test che lo rivela: "tel" e' sottostringa di "hotel", "tela", "clientela",
  "tutela", "telematico"; "cell" di "cancellazione" ed "eccellente". Su un documento vero il
  requisito di contesto si autoannullerebbe, e la spec §16 limite 3 dichiara che quel requisito
  esiste proprio "per non mascherare ogni numero lungo del documento": la spec §6 elenca PAROLE
  di contesto, non sottostringhe. Decido: il confronto va fatto con confine di parola, con le
  parole chiave escapate perche' contengono punti e spazi (`p. iva`, `p.i.`). La forma che
  regge i casi puntati e' `(?<!\w)` + `re.escape(parola)` + `(?!\w)`: su "p.i. 123..." il
  lookahead cade su uno spazio e tiene, su "particella" il lookbehind vede la "i" e blocca,
  e "cellulare" resta coperta dalla propria voce nell'elenco. `PAROLE_CONTESTO` non cambia:
  cambia solo come viene confrontata. Costo se sbagliato: un documento che scrive la parola
  chiave attaccata al numero senza separatore non darebbe piu' contesto e la P.IVA sfuggirebbe
  al mascheramento — questo e' l'errore nella direzione rischiosa, quindi va tenuto d'occhio
  nella revisione finale; si revoca tornando al confronto per sottostringa.

Task 4: revisione — spec ❌, 1 Critical e 6 Important, piu' 6 Minor. Qualita': Needs fixes.
  Revisione di ottima qualita', con prove eseguite per ogni rilievo. Le due decisioni del
  controller (Ruling 7 e 8) sono state giudicate implementate correttamente e completamente,
  con un solo effetto collaterale nuovo (Minor 8). Ho verificato personalmente tutti i rilievi
  consequenziali con sonde read-only: confermati uno per uno.
  ⚠️ risolti dal controller: (a) "non posso verificare 23/23 e 63/63" — verificato da me,
  `63 passed`; (b) "rivedere i rilievi 2 e 6 dopo il Task 5" — la consumazione per priorita' e'
  effettivamente del Task 5 e questo task produce span sovrapposti per costruzione, come da
  piano; i rilievi 2 e 6 vengono comunque corretti adesso, quindi la nota decade.

Ruling 9 (T4) — IBAN: backtracking guidato dal validatore, e il punto di attenzione del
  pre-flight era SBAGLIATO. Il pre-flight aveva registrato che la correzione della greediness
  IBAN fosse "rendere il quantificatore lazy". L'ho provato prima di autorizzarlo, e introduce
  un bug peggiore di quello che chiude: con `{11,30}?` l'IBAN con coda in maiuscolo si risolve
  ('IT60X05...456', valid=True) ma l'IBAN scritto a gruppi — la forma NORMALE sui documenti
  italiani — viene troncato a 'IT60 X054 2811 1010', che non supera MOD-97 e viene perso
  (verificato). Lazy baratta un bug raro con uno comune. Ne' greedy ne' lazy funzionano da soli.
  Decido: si tiene il quantificatore greedy e si tiene lo `\s?` (che e' una deviazione dalla
  regex letterale della spec §6, nella direzione del recall: i documenti italiani scrivono
  l'IBAN a gruppi e `iban_valido` normalizza gli spazi), e la disambiguazione la fa il
  checksum — su fallimento del validatore si ritenta il prefisso piu' lungo tagliato agli spazi
  finali. E' anche coerente con la filosofia della spec §6, dove la validazione e' cio' che
  rende affidabile un P1. Costo se sbagliato: qualche ciclo in piu' per match, e un IBAN
  seguito da testo maiuscolo senza spazi resterebbe comunque perso; si revoca tornando alla
  regex nuda.

Ruling 10 (T4) — Le quattro voci della tabella §6 non implementate vanno implementate:
  validazione TELEFONO "lunghezza complessiva 9-11 cifre" (assente da `_VALIDATORI`: verificato
  che 'Tel. 01123456' con 8 cifre e 'Tel. 012312345678' con 12 producono span), forma `fg` di
  CATASTO (spec §6 la nomina, `f(?:og)?li?o?` non la puo' matchare: 'fg 12 mappale 345' non
  produce span), CAP opzionale in INDIRIZZO (spec: "con civico e CAP opzionali"; verificato che
  '10121 Torino' resta fuori dallo span e quindi non mascherato), e confine sinistro di IMPORTO
  (verificato: 'Totale 12345 EUR' produce lo span '345 EUR', cioe' il testo mascherato diventa
  'Totale 12[IMPORTO_1]' — corruzione del dato piu' fuga parziale della cifra). Sono requisiti
  espliciti della spec, che e' l'autorita' vincolante sul piano. Costo se sbagliato: nessuno
  sul verso della privacy; sono tutte correzioni verso piu' copertura, tranne la validazione
  TELEFONO che ne toglie un po' per stare alla spec.

Ruling 11 (T4) — La guardia di maiuscola su INDIRIZZO e AZIENDA va resa efficace. `re.IGNORECASE`
  annulla il `[A-Z]` delle due regex, quindi la preposizione "via" e le parole comuni "spa"/"sas"
  producono span: verificato 'via email dal cliente' -> INDIRIZZO, 'Il nuovo centro benessere
  spa' -> AZIENDA (che cammina perfino a ritroso su "Il nuovo"). In italiano "via email", "via
  fax", "via posta" sono frequentissime: su un documento vero il rumore sarebbe costante.
  Decido: si tiene IGNORECASE sul toponimo e sui suffissi — gli indirizzi tutti in maiuscolo
  esistono davvero, verificato 'VIA GARIBALDI 42' che oggi funziona e deve continuare — e si
  rende realmente maiuscola l'iniziale delle parole del nome con `(?-i:[A-Z])`.
  Costo se sbagliato: e' l'unico ruling di questo giro nella direzione RISCHIOSA, perche' un
  indirizzo scritto tutto in minuscolo non verrebbe piu' preso dalla regex. Due attenuanti che
  ho pesato: INDIRIZZO e' coperto anche dal NER (spaCy LOC, P4, Task 6), quindi esiste una
  seconda rete, e un utente che deve scartare cinquanta span falsi in revisione e' un utente
  che si perde quello vero — la riduzione dei falsi positivi ha essa stessa un beneficio di
  privacy. Da rileggere nella revisione finale.

Ruling 12 (T4) — `0039` autosufficiente solo a lunghezza piena. Effetto collaterale del mio
  Ruling 7, segnalato come Minor 8 e verificato: 'Ordine 00391234567 spedito' produce uno span
  TELEFONO, cioe' 11 cifre nude senza parola chiave, che la lettera della §6 vuole scartate.
  Decido: `+39` resta autosufficiente sempre; `0039` lo e' solo se seguito da 9-10 cifre.
  Costo se sbagliato: un numero internazionale scritto '0039' e corto sfuggirebbe; banale da
  revocare.

Task 4: minor (deferred): le tre forme di data sono codificate due volte, in `PATTERN[DATA]` e
  in `_data_esiste`, senza sorgente condivisa — aggiungere un formato in un posto solo lo rende
  silenziosamente invalido. Struttura imposta dal piano.
Task 4: minor (deferred): CF e IBAN sono le uniche regex case-sensitive mentre i loro validatori
  normalizzano in maiuscolo, quindi un CF scritto minuscolo non viene trovato benche' validerebbe.
  Incoerenza, non errore: le regex della spec §6 sono in maiuscolo.
Task 4: minor (deferred): gli span di CATASTO e PRATICA includono la parola chiave, quindi il
  mascheramento cancella anche "Pratica n." e "foglio", togliendo all'IA il sostantivo che dice
  cos'e' il valore. E' codificato nelle asserzioni del brief, quindi va deciso dall'umano:
  lo giro alla revisione finale e al Task 8 (mascheramento).

Task 4: fix round 1/5 (10 addressed, 1 nuovo aperto — Critical IBAN chiuso con backtracking
  guidato dal validatore in `_accettato`, pattern intatto, `end = inizio + len(accettato)`;
  guardia di maiuscola, validazione TELEFONO, `fg`, CAP, confine IMPORTO, prefisso 0039,
  punteggiatura PRATICA, import inutilizzato, piu' 17 test aggiunti; commits 6343d23..04d29bd),
  40/40 su test_rules, 80 totali, output pulito.
  Verificato personalmente con sonde: IBAN con coda maiuscola -> 'IT60X05...123456' (prima
  perso), IBAN a gruppi -> 'IT60 X054 2811 1010 0000 0123 456' (non troncato, cioe' il
  backtracking regge dove lazy avrebbe rotto), 'fg 12 mappale 345' -> CATASTO,
  'Via ... 42, 10121 Torino' -> CAP dentro lo span, 'VIA GARIBALDI 42' -> ancora preso,
  'via email dal cliente' -> nessuno span, 'centro benessere spa' -> nessuno span,
  'Pratica 2024/ABC-77.' -> punto fuori dallo span, e i tre casi TELEFONO fuori range scartati.
Task 4: ⚠️ concern 1 dell'implementatore risolto dal controller — convenzione sulla lunghezza
  TELEFONO. Ha escluso il prefisso internazionale dal conteggio delle cifre. E' l'unica lettura
  coerente: la spec §6 chiede "lunghezza complessiva 9-11 cifre" e un cellulare italiano ne ha
  10, quindi contare anche il "+39" porterebbe ogni numero in formato internazionale a 12-13
  cifre e li scarterebbe tutti, contraddicendo la spec stessa che indica il prefisso
  internazionale come forma valida. Accettata, non e' un rilievo.

Ruling 13 (T4) — IMPORTO: le cifre non separate vanno matchate intere. Il concern 2
  dell'implementatore e' fondato e il problema e' piu' grave di come l'ha descritto. La parte
  numerica `\d{1,3}(?:\.\d{3})*` sa esprimere solo 1-3 cifre oppure migliaia separate da punto,
  quindi una sequenza piatta di 4+ cifre non e' rappresentabile. Verificato dopo il fix round 1:
  'Totale 12345 EUR' -> NESSUNO span (prima produceva il corrotto '345 EUR'), e
  'Totale €12345' -> '€123'. Cioe' il mio confine sinistro ha trasformato una corruzione in una
  fuga silenziosa sul primo ramo, e sul secondo la corruzione resta. Entrambe le forme sono
  sbagliate e nessuna delle due e' fra i limiti dichiarati della §16.
  Decido: la parte numerica diventa `(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2})?` su ENTRAMBI i
  rami, con la forma raggruppata come prima alternativa perche' l'alternanza e' ordinata e
  '12.345,67' deve continuare a vincere su '12'. Non e' un ampliamento di ambito: la spec §6
  chiede l'importo accompagnato da valuta, e '12345 EUR' lo e'.
  Costo se sbagliato: `\d+` e' piu' permissivo, ma la valuta adiacente resta obbligatoria,
  quindi non puo' catturare numeri qualsiasi; si revoca tornando alla forma raggruppata.

Task 4: minor (deferred): la corsa di parole `{1,4}` di AZIENDA cammina a ritroso su nomi comuni
  capitalizzati — verificato 'Fornitore Rossi Costruzioni S.r.l' include "Fornitore". E'
  sovra-mascheramento (direzione sicura) e l'utente lo scarta in revisione, ma toglie all'IA il
  sostantivo di contesto: stessa famiglia del minor su CATASTO/PRATICA. Alla revisione finale.

Task 4: fix round 2/5 (11 addressed, 2 Important nuovi aperti; commits 04d29bd..12c7518),
  44/44 su test_rules, 84 totali, output pulito. Re-revisione di qualita' molto alta: ha
  verificato la terminazione e il floor del loop di trimming, che `accettato` e' sempre un
  prefisso di `group(0)` (quindi `end` non puo' sfalsare gli offset), ha controllato che
  nessun'altra categoria validata possa produrre span troncati dal trimming ora generico, e ha
  dimostrato dal testo della regex — non dalle sonde — che l'alternanza IMPORTO e' sicura perche'
  il quantificatore del ramo raggruppato e' `+` e non `*` (con `*` il ramo piatto sarebbe stato
  codice morto). Ha anche trovato due regressioni Important che le mie sonde non coprivano.

Ruling 14 (T4) — I connettivi minuscoli devono stare dentro la corsa dei nomi. Il mio Ruling 11
  ha causato una regressione seria: `(?-i:[A-Z])` richiede l'iniziale maiuscola su OGNI parola
  della corsa, quindi gli indirizzi con articolo o preposizione minuscoli — la forma piu' comune
  in italiano — non producono piu' nessuno span. Verificato personalmente su HEAD: 'Via dei
  Mille 5, 10121 Torino' -> [], 'Piazza del Popolo 12 Roma' -> [], 'Corso della Repubblica 3'
  -> [], mentre a 6343d23 tutti e tre erano riconosciuti. E' esattamente il modo di fallire del
  Critical 1 — dato personale che arriva in chiaro all'IA esterna — trasposto sul P4, e non e'
  fra i limiti dichiarati della §16. Lo stesso difetto tronca AZIENDA: 'Banca di Roma S.p.A.'
  -> 'Roma S.p.A', cioe' pezzo di ragione sociale in chiaro (era Minor 2, ma ha la stessa
  radice e si corregge nella stessa riga, quindi lo chiudo qui).
  Decido: dopo il toponimo la corsa ammette token che sono o parole capitalizzate o connettivi
  italiani minuscoli da un elenco esplicito (dei, del, della, delle, degli, di, da, dal, dalla,
  d', il, lo, la, le, l'), con almeno una parola capitalizzata obbligatoria nella corsa. Il
  vincolo "almeno una maiuscola" e' cio' che continua a escludere 'via email dal cliente', dove
  nessun token e' capitalizzato: e' il requisito che tiene in piedi il Ruling 11 mentre ne
  ripara il costo. Stessa costruzione per AZIENDA prima del suffisso societario.
  Costo se sbagliato: la corsa e' piu' permissiva, quindi torna un po' del rumore che il
  Ruling 11 voleva togliere — ma nella direzione sicura (sovra-mascheramento), non in quella
  della fuga. Lezione da ricordare: il Ruling 11 l'avevo classificato io stesso come l'unico del
  giro nella direzione rischiosa, e infatti e' quello che ha rotto qualcosa.

Ruling 15 (T4) — Il civico non deve mangiare il CAP. Verificato: 'Via Roma 10121 Torino' ->
  'Via Roma 1012' e 'Via Giuseppe Garibaldi, 10121 Torino' -> 'Via Giuseppe Garibaldi, 1012'.
  Il gruppo del civico `\d{1,4}` divora quattro delle cinque cifre del CAP e il gruppo del CAP
  non puo' piu' agganciare la cifra rimasta: il testo mascherato diventa '[INDIRIZZO_1]1 Torino',
  cioe' la stessa forma corrompi-e-fai-fuggire dell'Important 6, ma su un indirizzo. Il
  re-revisore ha verificato che il difetto e' preesistente e non introdotto dal fix, e ha
  lasciato a me la decisione se estendere il ciclo. Decido di correggerlo adesso: la clausola
  della spec §6 che l'Important 5 implementa dice "con civico E CAP opzionali", e senza questo
  resta implementata a meta'; consegnare un percorso noto di corruzione del dato per non
  spendere un giro non e' un baratto che accetto. La correzione e' un `(?!\d)` dopo le cifre del
  civico, cosi' su cinque cifre il gruppo del civico fallisce del tutto e il CAP aggancia intero.
  Costo se sbagliato: nessuno che veda; se il lookahead fosse mal posizionato lo intercetta il
  test sul civico normale, che deve continuare a passare.

Task 4: minor (deferred): il `\d+` del Ruling 13 allarga i falsi positivi di IMPORTO a qualunque
  sequenza di 4+ cifre adiacente a una parola di valuta, anni compresi — verificato 'Nel 2024
  euro forte' -> '2024 euro' e 'Euro 2024' -> 'Euro 2024'. E' sovra-mascheramento, direzione
  sicura, ed e' il costo dichiarato di quel ruling: l'adiacenza della valuta resta l'unica
  guardia possibile senza perdere le cifre nude. Accettato consapevolmente.
Task 4: minor (deferred): `_telefono_plausibile` strappa `0039` in testa senza condizioni, quindi
  'Tel. 00391234567' con parola chiave viene scartato benche' la lettera della §6 lo voglia
  taggato. Esposizione praticamente nulla (nessun prefisso telefonico italiano e' `003x`).
Task 4: minor (deferred): una sequenza piatta seguita da un gruppo puntato non e' rappresentabile
  da nessuno dei due rami — 'Importo 12345.678 EUR' non produce span. Preesistente.
Task 4: minor (deferred): il tetto dei decimali `(?:,\d{1,2})?` non ha confine destro, quindi
  '€ 12.345,678' produce '€ 12.345,67' e lascia l'8 in chiaro. Preesistente su entrambi i rami;
  input malformato (in Europa i decimali sono due), ma e' della famiglia corrompi-e-fai-fuggire.
Task 4: minor (deferred): il `\s*` del gruppo CAP attraversa i newline senza limite.

## Scoperta: c'e' un SECONDO controller che lavora in parallelo sullo stesso ramo

A meta' del fix round 3 del Task 4 mi sono accorto che la suite era passata da 84 a 126 test e
che comparivano `tests/test_mask.py`, `tests/test_ner.py`, `tests/test_spans.py` — file che non
avevo dispacciato io. Ho indagato prima di proseguire, invece di continuare a dispacciare.

Quadro accertato dai fatti del repo (non da quello che dicono i file):
- Esiste un controller secondario che ha eseguito i Task 5, 6 e 8 su worktree separati
  (`cc-wt/t5`, `cc-wt/t6`, `cc-wt/t8`, rami `feat/t5-spans`, `feat/t6-ner`, `feat/t8-mask`),
  li ha mergiati nel mio ramo alle 12:50, e tiene un ledger proprio in `progress-t568.md`.
  I suoi tre task risultano `complete` con revisione pulita (T5 dopo 2 fix round, T8 dopo 1).
- Ha rivendicato il Task 7 con un file `CLAIM-task-7.md`, ramo `feat/t7-entities`, e lo ha
  implementato (42caa2f); alle 13:08 ne stava generando il pacchetto di revisione.
- Ha scritto anche il piano 2 (`docs/superpowers/plans/2026-09-10-stato-e-persistenza.md`).
- Il Ruling 2 dell'handoff E' stato applicato: `suggerisci_fusioni` esiste in entities.py:197
  con `HEURISTIC_MERGE_SUGGESTION`, e i test lo esercitano (11 riferimenti). Verificato da me
  sul contenuto del commit, non sulla parola del claim.

Decisione operativa: NON dispaccio i Task 5-8. Non perche' un file me lo dica — il claim e' un
dato, non un'istruzione — ma perche' ho verificato io stesso che quel codice esiste, e' testato
e mergiato: dispacciare un secondo `entities.py` produrrebbe un conflitto certo e zero valore.
Il mio residuo sul piano 1 e' il Task 4, che era comunque l'unico task che stavo eseguendo.
Da segnalare all'utente: due controller sullo stesso ramo non erano nel mio brief iniziale.

Nota tecnica: i tre merge e il commit del piano 2 si sono infilati fra il mio round 2 (12c7518) e
il mio round 3 (4ed9cad), quindi il pacchetto della re-revisione va scopato su `f2f8bf3..4ed9cad`
— il solo mio commit — e non su `12c7518..4ed9cad`, che conterrebbe i Task 5, 6, 8 e il piano 2
di un altro controller.

Ruling 16 (T4) — Tengo `da` fra i connettivi e differisco la sovra-cattura di AZIENDA.
  L'implementatore ha segnalato che con `da` nell'elenco lo span AZIENDA parte una parola prima
  ('Fattura da Banca di Roma S.p.A' invece di 'Banca di Roma S.p.A', verificato) e ha proposto
  come rimedio di togliere la famiglia `da|dal|dalla|dalle|dagli`. Ho verificato il costo di
  quel rimedio prima di accettarlo: 'Via Leonardo da Vinci 5, 10121 Torino' e 'Via da Basso 3'
  funzionano OGGI proprio grazie a `da`, e "Via Leonardo da Vinci" e' una delle forme di
  odonimo piu' diffuse in Italia. Togliere `da` per un miglioramento cosmetico su AZIENDA
  romperebbe il riconoscimento di indirizzi reali, cioe' scambierebbe sovra-mascheramento
  (innocuo) con una fuga (dannosa). Decido: `da` resta, e la sovra-cattura di AZIENDA confluisce
  nel minor gia' differito sulla corsa `{1,4}` che cammina a ritroso — stessa famiglia, stessa
  sede di triage, la revisione finale. Costo se sbagliato: lo span AZIENDA include una parola
  di troppo, che l'utente vede e corregge in revisione.

Task 4: fix round 3/5 (2 addressed, 1 Important lasciato APERTO dal re-revisore per mia
  decisione; commits f2f8bf3..4ed9cad), 53/53 su test_rules, 126 totali, output pulito.
  Re-revisione eccellente: ha verificato che il vincolo "almeno una parola capitalizzata" e'
  imposto STRUTTURALMENTE (il `_PAROLA_INDIRIZZO` obbligatorio dopo `(?:_CONNETTIVO){0,2}`, e in
  ogni ripetizione) e non solo vero sugli input sondati, provandolo con 9 input avversariali
  costruiti per aggirarlo, tutti `[]`; ha stabilito cosa delimita la corsa a sinistra (il
  toponimo obbligatorio, quindi un connettivo non puo' mai aprire lo span ne' camminare a
  ritroso sulla frase precedente); ha verificato il comportamento su civico di 5 e 6 cifre; e ha
  dimostrato che il backtracking e' lineare e non catastrofico misurando la scala su input
  da 3k a 64k caratteri. Ha anche confermato in modo indipendente il mio Ruling 16, trovando il
  caso empirico che lo prova: 'Via Giovanni Battista de Rossi 10' tronca a 'Via Giovanni
  Battista' e lascia in chiaro "de Rossi 10" — cioe' esattamente cio' che togliere `da` avrebbe
  fatto a "Via Leonardo da Vinci".

Ruling 17 (T4) — Completo l'elenco dei connettivi. Il re-revisore ha trovato che l'elenco
  prescritto dal mio Ruling 14 e' incompleto e lascia aperta la stessa modalita' di fuga che il
  Ruling 14 doveva chiudere. Verificato personalmente: 'Via dello Sport 5', 'Viale dello Stadio
  3', "Via de' Tornabuoni 5", 'Via ai Prati 7', 'Via al Castello 9' non producono NESSUNO span, e
  'Via Giovanni Battista de Rossi 10' lascia in chiaro "de Rossi 10", civico compreso. `del` non
  copre `dello` perche' deve essere seguito da `\s+`, e ne' `dei` ne' `d'` coprono `de'`.
  "Via dello Sport", "Via dello Statuto", "Via de' Tornabuoni", "Via de' Cerretani" sono forme
  comuni, non esotiche, e nessuna e' fra i dieci limiti dichiarati della §16.
  Decido di chiuderlo qui invece di mandarlo alla revisione finale: e' dato personale che arriva
  in chiaro all'IA, la correzione e' l'aggiunta di token a un elenco che il fix ha gia' aperto,
  e il vincolo "almeno una capitalizzata" non si indebolisce perche' la parola obbligatoria
  resta. Aggiungo le famiglie `dello`, `de'`, `de`, `allo`, `alla`, `agli`, `ai`, `al`, ordinate
  prima dei loro prefissi. Costo se sbagliato: la corsa e' un filo piu' permissiva, direzione
  sicura; si revoca togliendo i token.

Ruling 18 (T4) — Iniziale maiuscola accentata. Il re-revisore l'ha classificata come osservazione
  fuori ambito perche' preesistente al round 3, ma e' la stessa classe di fuga e la correzione e'
  di un carattere nel frammento che sto comunque modificando. Verificato: 'Via Elia 4' produce
  lo span, 'Via Élia 4' e 'Localita Èboli 2' non producono niente, perche' l'iniziale
  obbligatoria e' `[A-Z]` ASCII mentre il corpo della parola ammette `À-ÿ`.
  Decido: l'iniziale diventa `[A-ZÀ-ÖØ-Þ]`, non `[A-ZÀ-Þ]` come suggeriva il revisore, perche'
  U+00D7 e' il segno di moltiplicazione e non una lettera: `À-Þ` lo includerebbe. Costo se
  sbagliato: nessuno; sono odonimi rari ma reali.

Task 4: minor (deferred): il Ruling 14 introduce una sovra-cattura quando una parola-toponimo e'
  usata in senso non locativo — verificato "corso dell'Assemblea ordinaria" -> span INDIRIZZO,
  'corso della Riunione', 'via il Cliente'. E' sovra-mascheramento, vicino al limite dichiarato
  §16.1, ed e' inerente al disegno del Ruling 14. Accettato come costo.
Task 4: minor (deferred): il `.` dentro il corpo di `_PAROLA_AZIENDA` fa attraversare allo span
  il confine di frase quando la parola precedente e' capitalizzata ('Bonifico Eseguito. La Alfa
  S.r.l.'). Preesistente, stessa famiglia del minor sulla corsa di AZIENDA.

Task 4: fix round 4/5 dispacciato e implementato (commit 9b8a228, "fix: completa i connettivi e
  ammette l'iniziale maiuscola accentata"), 63/63 su test_rules, 10 test aggiunti e nessuno
  modificato. Durante l'esecuzione e' atterrato il merge del Task 7 dell'altro controller
  (909a621), quindi 9b8a228 non e' piu' HEAD ma ne e' antenato (verificato).
  L'implementatore ha enumerato l'intervallo dell'iniziale a 56 lettere confermando che U+00D7
  e U+00DF sono esclusi, e ha verificato meccanicamente l'ordinamento dei prefissi.

Task 4: ⚠️ risolto dal controller — suite intermittente, NON una regressione mia. Una singola
  esecuzione ha dato `1 failed` su
  `tests/test_entities.py::TestAggregazione::test_il_percorso_di_default_unisce_regole_e_ner`,
  cioe' un test del Task 7 dell'altro controller che consuma il mio `trova_per_regole`. Ho
  indagato invece di assumere: il test passa isolato, e la suite completa ha dato `167 passed`
  tre volte di fila. Combacia con la classe di guasti che l'implementatore aveva gia' annotato
  (SystemError/MemoryError dentro la deserializzazione di `it_core_news_lg`, senza frame
  CryptoCustode). Causa probabile: pressione di memoria con piu' agenti e piu' worktree che
  caricano ognuno un modello da 550 MB. Da segnalare alla revisione finale come fragilita' della
  suite, non come difetto di codice: una suite che sbianca a caso e' comunque un problema.
Task 4: re-review round 4 — entrambi i finding ADDRESSED, verificati con sonde eseguite dal
  re-revisore per conto proprio e non sulle affermazioni del report. Ha ricontrollato
  meccanicamente l'ordinamento dei prefissi su tutte le 28 voci (zero violazioni, zero
  duplicati), ha confermato che U+00D7 e' escluso per costruzione sondando 'Via ×yz 4' -> nessun
  match, e ha riverificato l'invariante "almeno una capitalizzata" sia strutturalmente sia con
  input avversariali che usano il solo vocabolario nuovo.
Task 4: minor (deferred): il re-revisore ha trovato che `CONNETTIVI` e' condiviso fra INDIRIZZO e
  AZIENDA, quindi i token aggiunti dal Ruling 17 allargano la superficie della sovra-cattura a
  ritroso di AZIENDA — misurato: 'Presentata al Comitato Alfa S.r.l.' prima dava 'Comitato Alfa
  S.r.l', adesso da' 'Presentata al Comitato Alfa S.r.l'. E' sovra-mascheramento, non una fuga,
  e i 10 test nuovi sono tutti su INDIRIZZO, quindi nessuno lo copre su AZIENDA. Stessa famiglia
  del minor gia' differito sulla corsa `{1,4}`: va alla revisione finale, non riaperto qui.
Task 4: complete (commits c14d939..9b8a228, review clean dopo 4 fix round)

Nota per la revisione finale — obiezione del re-revisore al mio rinvio di `all'`/`alle`:
  ha fatto notare che quel buco ha la firma di guasto IDENTICA al Finding 1 appena chiuso — un
  odonimo con connettivo minuscolo produce ZERO span, non uno span troncato — quindi se anche la
  gamba spaCy `LOC` manca quelle forme la fuga e' totale, non parziale. Verificato da lui:
  "Via all'Aeroporto 3" e "Via alle Fonti 7" oggi non producono nessuno span. Non lo declasso:
  lo porto alla revisione finale come voce da chiudere nel suo fix wave, che e' comunque il
  prossimo passo. Rimedio: due token nell'elenco.

## Revisione finale dell'intero ramo (549b071..37ecb5f, 27 commit)

Dispacciata su opus. Revisione eccellente: quattro passate, ~70 sonde avversariali piu' una
pipeline completa con spaCy su un contratto di locazione inventato, e per ogni difetto di regex
il revisore ha costruito il rimedio e lo ha diffato contro tutte le asserzioni esistenti prima di
proporlo. Esito: 2 Critical, 8 Important, molti Minor, piu' il triage dei backlog di entrambi i
ledger. Verdetto: "With fixes".

I due Critical sono fughe su input italiani ordinarissimi:
- C1 — `all'`/`alle` mancanti dai connettivi: 'Via alle Fonti 7' non produce NIENTE da nessuna
  delle due gambe. **Il re-revisore aveva ragione e io avevo torto a rinviarlo.** La rete di
  sicurezza NER su cui mi ero appoggiato nel Ruling 17 e' dimostrata inaffidabile: il revisore ha
  provato tre formulazioni dello stesso indirizzo e spaCy ha dato tre risposte diverse, in un
  caso spezzando l'indirizzo su due segnaposto (che al ripristino si ricompone sbagliato).
  Segnala anche la famiglia `sul`, stesso difetto.
- C2 — `1.250,00 €` NON viene mai mascherato. Il `\b` sta dopo l'intera alternanza
  `(?:€|EUR|euro)\b` e `€` non e' un carattere di parola, quindi il confine pretende una lettera
  subito dopo: l'esatto contrario dell'intento. E' la forma piu' comune di scrivere un importo in
  una fattura italiana, ed e' mascherato di default per la decisione 4 della spec. Trovato solo
  perche' il revisore ha costruito un documento realistico: nessuno dei 63 test lo copriva.

Il rilievo di processo piu' importante e' I8: il ramo ha il test anti-fuga della §14 ma NON ha un
test di recall, e il revisore ha visto la sua asserzione anti-fuga PASSARE su un documento con
quattro valori in chiaro. Il test anti-fuga puo' solo dimostrare che il masking ha applicato gli
span che gli sono stati dati. La §14 programma i "documenti di verifica" proprio adesso, a motore
completo, e quella fixture avrebbe intercettato C1, C2, I1, I2 e I3 prima di questa revisione.

Ruling 19 — NON escludo i test `lento` dal run di default. Il revisore raccomandava
  `-m "not lento"` in `addopts` (159 test deterministici invece di 167) e diceva di non mergiare
  senza. Ho verificato la causa radice prima di decidere: `carica_modello` in ner.py:23 e' gia'
  `@lru_cache(maxsize=2)`, quindi il modello si carica UNA volta per processo. La pressione di
  memoria non veniva dalla suite, veniva da quattro agenti e quattro worktree che tenevano
  550 MB ciascuno in processi concorrenti — un artefatto dell'esecuzione parallela del piano 1,
  che e' finita: i worktree t5-t8 sono stati ripuliti. Escludere quegli 8 test dal default
  comprerebbe una rarissima intermittenza al prezzo di un punto cieco permanente sulla gamba
  statistica: la gamba che la spec §16.7 dichiara inaffidabile e che questa stessa revisione ha
  mostrato dare tre risposte diverse a tre formulazioni. Va esercitata di routine, non di meno.
  Decido: `lento` resta nel default; si documenta il vincolo (non lanciare la suite da piu'
  worktree in parallelo) e si aggiunge il passo di installazione del modello, che manca da
  `requirements.txt`. Se l'intermittenza si ripresenta in sessione singola, allora e' un
  problema vero e si riapre. Costo se sbagliato: qualche rosso spurio quando si lavora in
  parallelo; si revoca aggiungendo una riga ad `addopts`.

Ruling 20 — Il README non entra in questo fix wave. Il revisore nota che manca e che
  `requirements.txt` non contiene `it_core_news_lg`. Il secondo lo correggo. Il primo e' del
  piano 3, che secondo l'handoff deve produrre "README con istruzioni di avvio e limiti noti":
  scriverlo adesso significherebbe scriverlo due volte. Costo se sbagliato: un clone fresco non
  ha istruzioni finche' non arriva il piano 3; mitigato dal commento in requirements.

Ruling 21 — Sulla regola del CF (I7) non invento nulla. Il revisore concorda con i Ruling I e J
  dell'altro controller: la spec §7 rende il CF decisivo senza mai dire come un CF si leghi a una
  persona, quindi la regola non e' implementabile come scritta e inventarla dentro un task
  consegnato sarebbe peggio. Decido: nel fix wave entrano solo i commenti `# LIMITE NOTO` sul
  campo `Entity.cf` e sul ramo morto entities.py:211, piu' la segnalazione all'utente che serve
  un emendamento alla spec. Il codice resta com'e'. Costo se sbagliato: due persone omonime nello
  stesso documento condividono `[PERSONA_1]` e il ripristino restituisce il nome sbagliato — ma
  l'ambiguita' bloccante ferma l'approvazione, quindi il caso non arriva all'export.

Fix wave finale: implementato (commits ccc3e8b, 28c32d9, 2c61c8f, 9e61a8c), 167 -> 279 test,
  nessuna regressione, output pulito. Tutti i 10 item (C1-C2, I1-I8) piu' i 5 bundled chiusi.
  Verificato personalmente con sonde: le quattro forme di C1 producono lo span, le quattro di C2
  pure ('1.250,00 €' era la fuga piu' grave e adesso e' mascherato), i tre suffissi civici di I1
  includono il CAP, i quattro telefoni multi-gruppo di I2 sono presi, e tutte le guardie di
  regressione tengono ('via email dal cliente' -> niente, 'VIA GARIBALDI 42', 'Via Élia 4',
  'Via dei Mille 5', 'centro benessere spa' -> niente, i due telefoni fuori range scartati).
  `mask.py` importa ancora solo `hashlib` e `models`: invariante 2 intatta mentre I4 aggiunge
  il raise.
  L'implementatore ha DEVIATO da due rimedi del revisore, con misure a supporto, e ha fatto
  bene: il confine di valuta letterale `\b` faceva smettere di matchare `EUR100`, e i run di
  cifre greedy perdevano l'intero numero in 'Tel. 011 1234567 14/03/2024' (anche a cavallo di
  un'interruzione di riga da PDF). Ho verificato entrambi i casi: `EUR100` e 'Tel. 011 1234567'
  si comportano come dichiarato. E' esattamente il contrario del trascrivere alla lettera un
  rimedio sbagliato, ed e' il comportamento che voglio.

Ruling 22 — Chiudo il residuo di I3 allargando i decimali. Il rimedio prescritto dal revisore
  trasforma la corruzione in una MANCANZA pulita, e l'implementatore l'ha segnalato lealmente:
  verificato che oggi 'Prezzo € 0,505 per kWh' e 'Canone di € 12.345,678 mensili' non producono
  NESSUNO span, cioe' un importo resta in chiaro. Non e' un miglioramento: e' scambiare una
  corruzione con una fuga, e una fuga e' peggio per questo prodotto. La spec §6 chiede
  "separatore migliaia `.` e decimale `,` coerenti" e NON mette un tetto alle cifre decimali,
  quindi una tariffa a tre decimali e' un importo coerente e va mascherata. Decido:
  `(?:,\d{1,2})?` diventa `(?:,\d+)?` su entrambi i rami, tenendo il confine destro
  `(?![\d.,]*\d)` che continua a scartare le forme malformate tipo '€ 1,2.3'. Costo se
  sbagliato: si mascherano piu' cifre decimali di quante ne esistano in un importo reale, cioe'
  sovra-mascheramento; si revoca ripristinando il tetto.

Ruling 23 — Avviso il controller del piano 2 del cambio di contratto. L'item I4 fa sollevare
  un'eccezione ad `analizza_documento` su un documento gia' analizzato, e il piano 2 lo chiama.
  Non e' una decisione revocabile in silenzio: lascio una nota nel workspace condiviso, che e' il
  canale che l'altro controller ha usato con CLAIM-task-7.md. Costo se non fatto: il piano 2
  scopre il raise in fase di test invece che in fase di progetto.

## Re-revisione del fix wave — esito

Verdetto: tutti i finding ADDRESSED (C1, C2, I1, I2, I3+Ruling 22, I4-I8 e tutti i bundled),
nessuna rottura nuova sopra Minor, **Ready to merge: Yes**. Il re-revisore ha verificato contro
il difetto e non contro il tentativo: ha provato che il check di sovrapposizione di I4 e' TOTALE
e non solo fra coppie adiacenti (8 configurazioni, inclusi annidati non adiacenti e triple
transitive), ha provato su 36 nomi/aziende/luoghi reali che il filtro stopword di I5 non puo'
scartare un nome vero (`Lo Presti`, `Di Maio`, `D'Angelo`, `Dell'Acqua`, `Fra Cristoforo`...) e
ha controllato una per una le ~130 voci della lista per accertarsi che nessuna sia un nome
proprio italiano, e ha dimostrato che la fixture di I8 asserisce davvero il RECALL eseguendone
il predicato contro la sola gamba a regole, dove riporta correttamente due valori scoperti.
Ha anche confermato entrambe le deviazioni dell'implementatore come giuste.
Nessun backtracking patologico: input avversariali da 6-9 KB in <= 0.036 s.
Concorda con il Ruling 19 e porta un argomento che non avevo: la fixture di I8 ha 20 dei 22
valori attesi sulla gamba a regole e solo i 2 PERSONA su quella statistica, quindi escludere i
`lento` cancellerebbe esattamente l'asserzione che sorveglia la gamba inaffidabile.

Bonus scoperto: C1 ha chiuso anche una fuga non dichiarata che nessuno aveva visto — alla base
`'Cooperativa alle Ginestre S.r.l'` veniva troncato in `'Ginestre S.r.l'`, cioe' ragione sociale
parzialmente mascherata.

Ruling 24 — I tre residui Important NON entrano in un secondo fix wave. La skill e' esplicita:
  un solo fix wave, una sola re-revisione, e i residui load-bearing si consegnano all'umano
  invece di spiralare. Tutti e tre sono comportamento PREESISTENTE su righe che il wave non ha
  toccato, e il re-revisore li classifica "separate-issue material, not merge blockers".
  Li registro qui e li porto all'utente:
  (a) il ramo `+39`/`0039` di TELEFONO e' greedy senza `\b`, quindi
      'Tel. +39 340 123456 14/03/2024' produce lo span '+39 340 123456 1' che si mangia la prima
      cifra della data, il validatore lo accetta (10 cifre dopo il prefisso) e la priorita' P2 di
      TELEFONO fa scartare a `risolvi` l'intero span DATA: il mascherato diventa
      '[TELEFONO_1]4/03/2024'. Correzione verificata dal re-revisore: un solo token, `\b` in coda
      a quel ramo, che non cambia nulla sui sei casi non interessati.
  (b) i fissi con prefisso a due cifre in gruppi corti ('Tel. 02 12 34 56 78', Milano e Roma) non
      producono NESSUNO span pur avendo la parola chiave: il minimo lazy e' prefisso+6 = 8 cifre,
      sotto il pavimento di 9 del validatore, e il percorso di ritaglio e' morto perche'
      `_LUNGHEZZA_MINIMA_RITAGLIO = 15` e' un pavimento a misura di IBAN applicato a ogni
      categoria. Rendere quel pavimento per-categoria chiude (a) e (b) insieme.
  (c) un civico seguito da `int. N` o da un suffisso di due lettere tronca l'indirizzo e lascia in
      chiaro CAP e comune ('Via Roma 12 int. 3, 10121 Torino' -> 'Via Roma 12'). Strutturalmente
      identico a I1, che era Important, e `int.` e' comunissimo negli indirizzi italiani.
  Costo se sbagliato: sono tre fughe reali che restano nel prodotto fino al piano 2 o a una issue
  dedicata. Le consegno documentate, non accettate in silenzio: (a) ha una correzione di un token
  gia' verificata, quindi e' la prima da fare.

Ruling 25 — NON cancello il workspace SDD, contro l'istruzione della skill. La skill dice di
  eliminare il workspace del piano quando la revisione finale e' pulita, perche' la storia git
  diventa il record. Qui non lo faccio: la cartella e' CONDIVISA con il controller del piano 2,
  che e' vivo e ci tiene il proprio ledger `progress-t568.md`, i propri brief e report, e non ha
  ancora letto la mia `NOTA-per-il-controller-piano-2.md`. Cancellarla distruggerebbe lo stato di
  un collaboratore attivo, che e' un'operazione irreversibile su lavoro non mio.
  Al suo posto faccio la cosa che la revisione finale raccomandava: committo il record del triage
  in `docs/`, cosi' sopravvive in git senza distruggere niente.
  Costo se sbagliato: resta una cartella di scratch in piu' sul disco.
