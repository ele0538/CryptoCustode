# SDD ledger — plan: docs/superpowers/plans/2026-09-10-motore-riconoscimento.md

Controller secondario: esegue SOLO i Task 5, 6 e 8. Il Task 4 (e poi il 7) sono di un
altro controller vivo che possiede `progress.md` in questa stessa workspace.

BASE comune dei tre task: 6343d23 (Task 4 verde, 63 test passanti).

## Pre-flight

Il pre-flight scan completo di questo piano esiste gia' in
`docs/superpowers/esecuzione/ledger-piano-1.md`. Non lo rifaccio: ho ri-verificato solo le
righe dei miei tre task leggendo i blocchi Files/Interfaces dei brief.

| Task | File creati | Consuma | Esito |
|---|---|---|---|
| T5 | `core/spans.py`, `tests/test_spans.py` | solo i tipi del Task 2 (71d921d) | indipendente da T4, T6, T8 |
| T6 | `detect/ner.py`, `tests/test_ner.py` | solo i tipi del Task 2 | indipendente da T4, T5, T8 |
| T8 | `core/mask.py`, `tests/test_mask.py` | solo i tipi del Task 2 | indipendente; i test costruiscono le entita' a mano |

Nessuna coppia fra i tre condivide un file. T7 li consuma tutti e resta all'altro controller.

## Rulings

Ruling A — Tre implementatori in parallelo, contro "Never dispatch multiple
implementation subagents in parallel (conflicts)" della skill. Il partner umano l'ha
chiesto esplicitamente e le istruzioni dell'utente prevalgono sulle skill. Il rischio che
la regola presidia e' la collisione nell'albero di lavoro condiviso: lo elimino dando a
ogni agente il proprio worktree e il proprio ramo, con file dimostrabilmente disgiunti
(tabella sopra). Costo se sbagliato: tre cicli di revisione che arrivano insieme con me
come collo di bottiglia, e merge da fare a mano se due task toccassero lo stesso file —
cosa che i brief escludono.

Ruling B — Ledger separato `progress-t568.md`. Un altro controller vivo scrive su
`progress.md` di questa workspace: appendervi significherebbe sovrascrivere le sue voci.
Costo se sbagliato: due ledger da riconciliare alla chiusura del piano 1.

Ruling C — venv condiviso, niente venv nei worktree. Gli agenti usano l'interprete del
venv principale per percorso assoluto con cwd nel proprio worktree. Verificato prima di
dispacciare: da `cc-wt/t5`, `python -m pytest` da' 63 passed, `cryptocustode` si risolve
dal worktree e `spacy.util.get_installed_models()` vede gia' `it_core_news_lg`. Senza
questa regola il Task 6 ri-scaricherebbe 550 MB (Ruling 1 originale). Costo se sbagliato:
un worktree non puo' avere dipendenze diverse dal principale — impossibile per questi tre
task, che usano solo stdlib piu' lo spaCy gia' installato.

Ruling D — Rami separati `feat/t5-spans`, `feat/t6-ner`, `feat/t8-mask` da 6343d23. Git
rifiuta due worktree sullo stesso ramo, quindi non e' una scelta di stile. Il merge in
`feat/motore-riconoscimento` lo faccio io a task verde e revisionato. Costo se sbagliato:
nessuno, i file sono disgiunti.

## Avanzamento

Setup: worktree creati, brief estratti, label canoniche create su GitLab (5/5),
commit c14d939..6343d23 pushati su origin.

Task 5: implementatore dispacciato (haiku — il brief contiene il codice completo, quindi
  trascrizione piu' test). BASE 6343d23, ramo feat/t5-spans, worktree cc-wt/t5.
Task 6: implementatore dispacciato (sonnet — carica il modello, test fragili per natura,
  interazione con l'ambiente). BASE 6343d23, ramo feat/t6-ner, worktree cc-wt/t6.
Task 8: implementatore dispacciato (sonnet — 268 righe di brief, offset da destra a
  sinistra e hash canonico, vincolo di purezza da sorvegliare). BASE 6343d23, ramo
  feat/t8-mask, worktree cc-wt/t8.

Nota portata a tutti e tre nel dispatch: quattro task su quattro di questo piano hanno
avuto un difetto nel proprio brief, quindi ho chiesto trascrizione fedele e rosso onesto
invece di test piegati per farli passare.

Task 5: implementato (commit f86c08b, "feat: risoluzione degli span per priorita' con
  invariante di non sovrapposizione"), 9/9 nuovi test, 72/72 suite, nessuna preoccupazione
  dichiarata. Revisione dispacciata (sonnet: diff piccolo, 4276 byte, logica pura).
Task 6: implementato (commit 69001a0, "feat: riconoscimento statistico con spaCy per
  persone, aziende e luoghi"), 7/7 in test_ner.py piu' 63 passed / 7 deselected con
  -m "not lento". L'implementatore dichiara che il brief non conteneva contraddizioni,
  a differenza dei precedenti. Revisione dispacciata (sonnet).
Task 8: implementato (commit badbb82, "feat: mascheratura pura e hash canonico di
  approvazione"), 77 passed (63 di base piu' 14 nuovi in test_mask.py). Revisione
  dispacciata (sonnet: diff 8619 byte, il piu' grande dei tre).
Task 8: osservazione dell'implementatore risolta dal controller — lo step 5 del brief
  parla dei test `lento` del Task 6, che nel worktree t8 non esistono perche' il Task 6
  vive sul ramo feat/t6-ner. E' una conseguenza attesa del Ruling A (rami separati), non
  un difetto: i due si incontrano al merge. Il conteggio combinato atteso dopo il merge
  dei tre rami e' 63 + 9 (T5) + 14 (T8) = 86 non-lento, piu' 7 lento del T6.

Task 6: revisione — spec OK conforme (trascrizione verbatim verificata riga per riga,
  lru_cache genuina, marker `lento` registrato, nessun percorso di fallback), qualita'
  Approvato, 0 Critical, 0 Important.
Task 6: minor (deferred): `carica_modello` restituisce `spacy.language.Language` e
  quindi fa trapelare il tipo di spaCy nella superficie pubblica del modulo. Verbatim dal
  brief; il Task 7 consuma solo `trova_per_ner` e `MAPPA_LABEL`. Da triagiare nella
  revisione finale.
Task 6: warning del revisore risolto dal controller — non poteva eseguire i test che
  caricano il modello. Eseguiti io in cc-wt/t6: `pytest tests/test_ner.py -m lento` da'
  7 passed in 2.88s, zero warning nell'output.
Task 6: complete (commits 6343d23..69001a0, review clean)

Task 5: revisione — spec OK conforme (trascrizione verbatim, chiave di tie-break
  tracciata a mano contro PRIORITA, invariante di non sovrapposizione verificata su 6
  span multi-priorita'), qualita' Approvato, 0 Critical. 1 Important `plan-mandated`.
Task 5: 1 Important APERTO — la terza regola di tie-break della spec §6 ("a parita' di
  lunghezza vince quello che inizia prima") non e' verificata da nessun test. Ho
  controllato di persona invece di fidarmi del revisore: `_forza` restituisce
  `(priorita, -lunghezza, start, span_id)`, `test_a_parita_di_priorita_vince_il_piu_lungo`
  usa due span che iniziano entrambi a 0, e `test_risoluzione_deterministica` usa due span
  con stesso start E stessa lunghezza, quindi esercita solo il tiebreak finale su span_id.
  Il termine `span.start` non e' coperto: negarlo lascerebbe verdi tutti e nove i test.

Ruling E (T5) — Il rilievo e' fondato e il difetto e' del piano, non dell'implementatore:
  l'elenco dei test dello Step 1 del brief non contiene il caso. La spec §6 e' l'autorita'
  vincolante ed enumera tre regole ordinate; lasciarne una senza rete e' la stessa forma
  del rilievo sull'omocodia del Task 3, che questa sessione ha appena dovuto chiudere.
  Costa un test solo, quindi apro un fix round invece di parcheggiarlo. Costo se
  sbagliato: un test in piu' del minimo indispensabile.

Task 5: fix round 1/5 (1 addressed, 0 open — aggiunto
  `test_a_parita_di_priorita_e_lunghezza_vince_quello_che_inizia_prima` con due span P4
  sovrapposti, stessa lunghezza, start diversi e span_id scelti in modo che senza il
  termine `start` vincerebbe l'altro; commit f86c08b..753f52e), 73 test.
  Verificato dal controller prima della re-review: il commit tocca solo tests/test_spans.py,
  `git diff` su spans.py e' vuoto.

Task 8: revisione — spec OK conforme (trascrizione verbatim verificata con un diff
  meccanico contro i blocchi di codice del brief, zero delta), purezza confermata
  (solo hashlib e models), sostituzione da destra a sinistra verificata e coperta da un
  test discriminante. Qualita': Needs fixes. 0 Critical, 2 Important, entrambi
  `plan-mandated`, piu' 3 Minor.
Task 8: minor (deferred): (a) gli span sovrapposti non sono ne' difesi ne' testati in
  `maschera` — non possono far trapelare testo originale ma possono produrre un segnaposto
  malformato; (b) il docstring di `hash_approvazione` sovrastima l'inambiguita' perche'
  `filename` non e' length-prefixed; (c) mancano i casi limite di span adiacenti a gap zero
  e span che finisce a fine testo. Da triagiare nella revisione finale.

Ruling F (T8) — Il `continue` su entita' mancante (mask.py:29-31) va sostituito da un
  errore esplicito. Il rilievo e' fondato: uno `Span` il cui `entity_id` non risolve
  lascia il testo originale intatto nell'output, cioe' dato personale in chiaro, che e'
  esattamente il fallimento che questo modulo esiste per impedire — e nessun test lo
  intercetta. Ho controllato la spec prima di decidere: la §9 impone solo la purezza e
  l'ordine decrescente, e la tabella della §13 elenca situazioni dell'utente, non
  violazioni di invarianti interni, quindi non sto contraddicendo la spec ma riempiendo
  un silenzio. Per uno strumento di anonimizzazione l'errore giusto e' fallire chiuso, non
  aperto. Costo se sbagliato: se il piano 2 producesse legittimamente fascicoli con
  entity_id pendenti (per esempio durante una fusione di entita'), il masking solleverebbe
  invece di degradare in silenzio, e il piano 2 dovra' gestirlo deliberatamente. E' la
  direzione giusta in cui sbagliare.

Ruling G (T8) — La chiave di ordinamento dell'hash (mask.py:53) passa da `d.filename` a
  `(d.filename, d.doc_id)`. Con soli filename l'ordine non e' totale: due documenti
  omonimi (due upload chiamati "scan.pdf" sono realistici) rendono l'hash dipendente
  dall'ordine di inserimento, contraddicendo il docstring della funzione e il requisito di
  canonicita' su cui il piano 2 costruira' il gate di esportazione. Non mi appoggio a una
  garanzia di unicita' dei filename che vivrebbe in un piano non ancora scritto. Costo se
  sbagliato: nessuno — `doc_id` e' gia' la chiave unica del dominio, aggiungerlo puo' solo
  rendere l'ordine totale, e non esistono hash gia' salvati da invalidare.

Task 5: re-review round 1 — finding ADDRESSED, nessuna nuova rottura, `spans.py` intatto.
  MA il controller ha verificato la prova invece di accettarla: il re-revisore ha ripetuto
  il ragionamento dell'implementatore senza controllarlo. Il test e' load-bearing contro la
  NEGAZIONE del termine `start` (dimostrata), non contro la sua RIMOZIONE: con
  `span(0,10,"z")` e `span(5,15,"a")` gli span_id sono "s0-10z" e "s5-15a", e "s0-10z" e'
  gia' minore per via delle cifre dell'offset — il suffisso "z"/"a" non viene mai
  confrontato. Verificato con un confronto diretto delle chiavi. Il commento del test
  afferma esattamente il contrario ed e' falso.

Ruling H (T5) — Apro il round 2 invece di accettare l'ADDRESSED. Due ragioni: il commento
  del test dichiara una protezione che non esiste, e chi lo leggera' fra sei mesi si
  fidera'; e la lacuna comportamentale vera resta scoperta, cioe' il caso in cui l'ordine
  degli span_id contraddice l'ordine degli start. Basta cambiare le coordinate: con
  INDIRIZZO (9,19) e AZIENDA (10,20) — stessa priorita' P4, stessa lunghezza 10,
  sovrapposti — gli span_id diventano "s9-19" e "s10-20", e "s1" < "s9" fa vincere
  AZIENDA senza il termine start. Cosi' il test fallisce sia se il termine viene negato
  sia se viene rimosso, e il commento diventa vero. Costo se sbagliato: un round in piu'
  su un test da nove righe, speso per non lasciare in repo un commento che mente.

Task 8: fix round 1/5 (2 addressed secondo l'implementatore, re-review dispacciata —
  commit badbb82..5708860, "fix: solleva errore su entity_id assente e rende canonico
  l'hash con filename duplicati"), 79 test, 0 warning.
  Verificato dal controller prima della re-review: il diff tocca solo mask.py (8 righe) e
  test_mask.py (31 righe); le uniche modifiche di produzione sono il `raise ValueError`
  con messaggio italiano che nomina span_id ed entity_id, e la chiave di ordinamento che
  diventa `(d.filename, d.doc_id)`. Nessun Minor differito e' stato toccato.
  Al re-revisore ho chiesto esplicitamente di giudicare da se' il potere discriminante dei
  due nuovi test, citando l'errore del re-revisore del Task 5 come precedente da non
  ripetere.
Task 8: re-review round 1 — entrambi i finding ADDRESSED, nessuna nuova rottura
  Critical/Important. Il re-revisore ha verificato per conto proprio invece di ripetere
  l'implementatore: ha tracciato a mano che con la vecchia chiave singola il sort stabile
  faceva seguire l'ordine di input ai due documenti omonimi, quindi il test sarebbe
  fallito prima del fix, e ha controllato in models.py che lo span fantasma superi
  `span_attivo` e arrivi davvero al lookup.
Task 8: minor (deferred): il docstring di `maschera` non menziona il nuovo contratto di
  sollevamento su entity_id pendente — lacuna di documentazione introdotta insieme al
  cambio di comportamento. Da triagiare nella revisione finale.
Task 8: complete (commits 6343d23..5708860, review clean dopo 1 fix round)
Task 5: re-review round 2 — finding ADDRESSED. Il re-revisore ha derivato per conto
  proprio l'ordine lessicografico ("s10-20" < "s9-19" perche' '1' < '9') e ha verificato
  entrambe le mutazioni: negazione e rimozione fanno vincere AZIENDA e rompono
  l'asserzione. Il commento ora dice il vero. spans.py invariato.
Task 5: complete (commits 6343d23..e4e7b02, review clean dopo 2 fix round)

## Chiusura dei tre task

Merge dei tre rami in feat/motore-riconoscimento con --no-ff (62fc71f, fddf27b, 91a7063).
Il ramo condiviso era nel frattempo arrivato a 12c7518: l'altra sessione ha portato il
Task 4 da 63 a 84 test nei suoi giri di correzione. Working tree pulito al momento del
merge, verificato prima di toccarlo.

Verifica aritmetica: 84 (base) + 10 (T5) + 16 (T8) = 110 non-lento attesi, piu' i 7 lento
del T6. Misurato dopo il merge: 110 passed / 7 deselected, e 117 passed con i lento
inclusi. Zero warning. Nessun test perso nel merge.
Verificato che i fix siano davvero nell'albero unito: il `raise ValueError` e la chiave
`(d.filename, d.doc_id)` in mask.py, le coordinate (9,19) nel test del tiebreaker.

Pushato: 6343d23..91a7063 su origin.

Restano al piano 1: il Task 7 (giunzione di T4+T5+T6, con il Ruling 2 da applicare) e poi
la revisione finale dell'intero ramo, che deve triagiare i minor differiti qui sotto piu'
quelli nel ledger dell'altro controller.

Minor differiti da questo controller, per la revisione finale:
- T6: `carica_modello` restituisce `spacy.language.Language`, il tipo di spaCy trapela
  nella superficie pubblica del modulo.
- T8: gli span sovrapposti non sono ne' difesi ne' testati in `maschera` (non fanno
  trapelare testo originale, ma possono produrre un segnaposto malformato).
- T8: il docstring di `hash_approvazione` sovrastima l'inambiguita' (filename non
  length-prefixed).
- T8: il docstring di `maschera` non menziona il contratto di sollevamento su entity_id
  pendente, introdotto dal Ruling F.

## Task 7 (assegnato a questo controller dal partner umano)

Task 7: implementatore dispacciato (opus — e' la giunzione del piano, consuma T4+T5+T6,
  e il Ruling 2 aggiunge codice che il brief non contiene). BASE 91a7063, ramo
  feat/t7-entities, worktree cc-wt/t7. Il dispatch porta il Ruling 2 esplicito:
  `suggerisci_fusioni(fascicolo)` piu' il test "M. Rossi"/"Mario Rossi" non bloccante.
  Lasciato `CLAIM-task-7.md` nella workspace condivisa perche' l'altro controller aveva
  il Task 7 come prossimo lavoro e non ho modo di scrivergli.

Task 7: implementato (commit 42caa2f, "feat: aggregazione in entita', euristiche sui nomi
  e coda delle omonimie"), 138 test (117 di base + 21 nuovi), DONE_WITH_CONCERNS.
  Il Ruling 2 e' stato applicato: `suggerisci_fusioni` esiste e ha il suo test.
  L'implementatore dichiara sei mutazioni deliberate che hanno reso rossa la suite,
  quindi i nuovi test sarebbero load-bearing — da far verificare al revisore, non da
  accettare sulla parola.

Ruling I (T7) — La preoccupazione 1 dell'implementatore e' fondata e la parcheggio invece
  di correggerla. Verificato di persona: `Entity.cf` non viene assegnato in nessun punto
  del codice di produzione, e l'unica lettura, `entita.cf is not None` a entities.py:182,
  e' quindi un ramo morto. Ne segue che la meta' della regola della spec §7 — "CF identico
  fonde automaticamente; CF diversi separano automaticamente" — non e' implementata.
  Perche' parcheggio: la degradazione e' nella direzione sicura. Con `cf` sempre None la
  guardia non sopprime mai l'ambiguita', quindi ogni omonimia fra documenti apre una
  SAME_NAME_NO_CF bloccante e l'approvazione si ferma. Il sistema non decide al posto
  dell'umano: gli chiede sempre. Il costo e' lavoro manuale in piu', non una fuga di dati.
  Perche' non la correggo qui: legare un CF a una persona richiede una regola di
  prossimita' o di co-occorrenza che la spec non enuncia da nessuna parte. Inventarla ora,
  dentro un task gia' consegnato e non ancora revisionato, e' piu' rischioso che
  documentarla. Va decisa in un emendamento alla spec prima che il piano 3 costruisca la
  UI di disambiguazione. Costo se sbagliato: resta in `entities.py` un ramo che sembra
  funzionante e non lo e'; il revisore deve saperlo, e il piano 3 non deve presumere che
  la separazione automatica per CF esista.

Task 7: preoccupazione 2 risolta dal controller — `analizza_documento` non aggiunge il
  documento a `fascicolo.documents` ed e' corretto cosi': la registrazione e' compito di
  `aggiungi_documento`, che il piano 2 introduce nel suo Task 4 e chiama prima
  dell'analisi. Non e' una lacuna.
Task 7: preoccupazione 3 annotata — un MemoryError transitorio nel caricamento del modello
  spaCy alla prima esecuzione completa, non riprodotto nelle quattro successive.
  Ambientale, da tenere d'occhio su macchine con poca RAM.

Task 7: revisione — spec OK conforme su tutte e quattro le regole della §7 piu' l'aggiunta
  del Ruling 2. Il revisore ha rifatto per conto proprio il diff meccanico contro i blocchi
  del brief (la trascrizione regge, le uniche cancellazioni sono le due righe dichiarate) e
  ha ragionato su tutte e sei le mutazioni invece di ripetere l'implementatore: reggono.
  Qualita': Needs fixes. 0 Critical, 3 Important, 8 Minor.

Ruling J (T7) — CORREGGE IL RULING I. La mia premessa era sbagliata a meta' e il revisore
  l'ha smentita con un controesempio che ho riletto nel codice: `risolvi_ambiguita_omonimia`
  salta ogni entita' con `len(documenti) < 2` (entities.py:182) e `_assegna` fonde per
  valore normalizzato senza distinguere il documento (entities.py:116-124). Quindi due
  persone omonime **dentro lo stesso documento** — padre e figlio nello stesso rogito —
  diventano una sola entita', condividono `[PERSONA_1]`, e la coda delle ambiguita' resta
  vuota: l'approvazione non viene bloccata. La degradazione sicura che avevo dichiarato
  vale solo per il caso fra documenti, dove ho verificato che non esiste percorso che
  aggiri la SAME_NAME_NO_CF bloccante. Dentro un documento non esiste rete, e non puo'
  esistere finche' manca proprio la meta' non implementata della §7 ("CF diversi separano
  automaticamente"). Conseguenza da registrare: la proprieta' di sicurezza non vive nel
  motore ma nel gate di esportazione del piano 2, e il de-masking di un testo cosi'
  ripristinerebbe il nome sbagliato. L'emendamento alla spec sul legame CF-persona deve
  coprire esplicitamente anche il caso intra-documento. Non e' correggibile dentro il Task
  7. Costo di aver sbagliato la prima volta: se avessi chiuso il task sulla mia premessa
  originale, "degradazione sicura" sarebbe finito nel ledger senza qualificazioni e il
  piano 3 ci avrebbe costruito sopra.

Ruling K (T7) — Apro un fix round su Important 2 e 3, entrambi in `aggiungi_span_manuale`,
  entrambi chiudibili senza decisioni di spec. Il 2 e' netto: la funzione accetta offset
  grezzi e li passa a uno slice Python, che tronca in silenzio; un intervallo invertito o
  fuori dai limiti produce `canonical_value=""`, brucia per sempre un indice di segnaposto
  (che per progetto non si ricicla) e lascia in `fascicolo.spans` uno span di lunghezza
  negativa su cui il piano 2 mascherera'. E' il punto d'ingresso della UI di tagging del
  piano 2, cioe' l'unica funzione qui che ricevera' interi scelti da un umano.
  Sul 3 decido la forma della correzione, perche' il revisore ne offriva due e una
  inventa politica: NON far passare lo span manuale da `risolvi` — lo scarterebbe in
  silenzio quando perde la priorita', e perdere in silenzio il tag che l'utente ha appena
  messo a mano e' peggio del problema. La funzione deve invece **sollevare** se
  l'intervallo richiesto si sovrappone a uno span gia' presente sullo stesso documento,
  dicendo quale. Cosi' l'invariante di non sovrapposizione vale su entrambi i percorsi,
  niente sparisce senza dirlo, e la politica "il manuale vince" resta una decisione della
  spec invece di essere decisa di straforo qui. Costo se sbagliato: un utente che vuole
  ri-taggare una porzione gia' coperta deve prima disattivare lo span esistente; e' un
  passaggio in piu' nella UI del piano 3, reversibile cambiando la regola in una riga.

Ruling L (T7) — Faccio entrare nel fix round un Minor, in deroga alla regola che i Minor
  non entrano mai nel ciclo. `occurrence_span_ids` non e' asserito da nessun test:
  sostituirlo con `[]` in entrambi i punti lascerebbe verdi tutti e 21 i test. E' l'unico
  output della funzione estratta `_span_id_per_entita`, cioe' proprio la deviazione che ha
  toccato il codice del brief, ed e' il campo che serve alla UI per dire all'utente **dove**
  si trova l'ambiguita'. Sto gia' aprendo un giro su quella stessa area e l'aggiunta e'
  un'asserzione. Costo se sbagliato: un test in piu' in un round gia' aperto.

Task 7: minor (deferred) per la revisione finale: l'aritmetica dei test nel report
  dell'implementatore e' sbagliata (15+6, non 13+8; i totali tornano, l'attribuzione no);
  il pairing greedy di `chiavi_equivalenti` puo' dare falsi negativi, direzione sicura;
  il commento a entities.py:222-223 asserisce un invariante che la fusione del piano 2
  falsifichera'; `normalizza` puo' restituire "" e far collassare entita' diverse su
  chiave vuota; `gia_aperte` include le ambiguita' gia' risolte, quindi una terza
  occorrenza non riapre nulla; `analizza_documento` non e' idempotente; import `Span`
  inutilizzato nei test.

Task 7: fix round 1/5 (3 addressed secondo l'implementatore, re-review dispacciata —
  commit 42caa2f..a26a2f2, "fix: convalida aggiungi_span_manuale contro range invalidi e
  sovrapposizioni"), 140 non-lento.
Task 7: la dichiarazione dell'implementatore che i test `lento` fallissero per esaurimento
  della memoria e' stata smentita dal controller: rieseguiti in cc-wt/t7 danno 8 passed in
  2.77s, e la suite completa 148 passed con zero warning. Era la macchina sotto carico con
  quattro agenti attivi, non il codice. Nota di metodo: l'implementatore ha fatto bene a
  dichiararlo invece di nasconderlo, ma una diagnosi ambientale va sempre riprovata a
  freddo prima di finire nel ledger come fatto.
Task 7: re-review round 1 — tutti e tre i finding ADDRESSED, nessuna nuova rottura. Il
  re-revisore ha controllato la condizione booleana della guardia invece del docstring
  (`not (0 <= inizio < fine <= len(...))`, con il termine `inizio < fine` presente), ha
  verificato che il filtro per doc_id esista davvero e non sia solo implicito, e ha
  tracciato a mano gli offset dei test multi-documento per mostrare che quel filtro e'
  esercitato. Nota: entrambe le guardie sollevano prima di `prossimo_placeholder`, quindi
  un rifiuto non brucia un indice — che era il punto.
Task 7: minor (deferred): `aggiungi_span_manuale` costruisce due volte lo stesso
  intervallo, un `candidato` usa-e-getta per il controllo di sovrapposizione e poi il
  `grezzo` definitivo. Nessun impatto.
Task 7: nota per il piano 2 — il fix del Finding 1 rende vincolante la preoccupazione 2:
  ora un chiamante reale DEVE registrare il Document nel fascicolo prima di chiamare
  `aggiungi_span_manuale`, altrimenti la nuova guardia lo rifiuta. Il piano 2 gia' lo fa
  (`aggiungi_documento` nel suo Task 4, chiamato prima dell'analisi), ma era una
  convenzione e adesso e' un requisito.
Task 7: complete (commits 91a7063..a26a2f2, review clean dopo 1 fix round)

Merge di feat/t7-entities nel ramo condiviso. Base 136 test (l'altra sessione ne ha
aggiunti altri al Task 4 nel frattempo) + 31 di test_entities.py = 167 passed, zero
warning. Aritmetica verificata, niente perso nel merge. Pushato.

REVISIONE FINALE: NON ancora lanciata, e non per dimenticanza. Il ledger dell'altro
controller e' al fix round 3/5 del Task 4 con 1 Important ancora aperto, e continua a
committare sul ramo condiviso. Una revisione dell'intero ramo adesso leggerebbe un
bersaglio in movimento, proprio nell'area dove il churn e' maggiore. Va lanciata quando
il Task 4 e' chiuso. Chi la lancia deve puntarla su ENTRAMBI i ledger: i minor differiti
e i parcheggi stanno metà in progress.md e metà in progress-t568.md.
