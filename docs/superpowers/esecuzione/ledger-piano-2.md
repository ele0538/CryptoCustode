# SDD ledger — plan: docs/superpowers/plans/2026-09-10-stato-e-persistenza.md

Spec: docs/superpowers/specs/2026-09-10-cryptocustode-design.md (autorità vincolante)
Ramo di integrazione: `feat/stato-e-persistenza`, worktree `cc-wt/p2`, base 909a621
(il piano 1 completo, Task 1-8, con il Task 4 ancora in fix round presso l'altro
controller su `feat/motore-riconoscimento`).

Nota di contesto: questo piano l'ho scritto io stesso poche ore fa. Il pre-flight scan qui
sotto l'ho fatto trattandolo come se l'avesse scritto qualcun altro, perché l'autore è il
lettore peggiore del proprio piano.

## Pre-flight scan

### Coppie di task che condividono file o interfacce

| Da | A | Prodotto contro consumato | Esito |
|---|---|---|---|
| T1 | tutti | `errors.py` (9 classi + base), `ingest/config.py` (2 costanti) | coerente: T1 le crea, gli altri le importano |
| T1 | T3 | `CARATTERI_MINIMI_PAGINA`, `FRAZIONE_IMMAGINE_MASSIMA` | coerente, nomi identici nel codice del brief |
| T2 | T4 | `carica_txt(bytes) -> str` | coerente |
| T3 | T4 | `carica_pdf(bytes) -> tuple[str, list[int]]` | coerente, la tupla viene destrutturata correttamente |
| T3 | T9 | `tests/pdf_di_prova.py::pdf_di_prova`, `TESTO_DI_PAGINA` | coerente, T9 li importa |
| T4 | T9 | `costruisci_documento`, `aggiungi_documento` | coerente |
| T5 | nessuno | `salva`/`carica` non hanno consumatori dentro il piano 2 | voluto: il vault lo cabla il piano 3; i test di T5 costruiscono il fascicolo a mano |
| T6 | T9 | `ripristina(risposta, entities)` | coerente (TC-05) |
| T7 | T8 | **stesso file** `state/session.py`: T8 lo modifica, T7 lo crea | coerente col grafo, che mette 8 dopo 7 — ma i due NON possono correre in parallelo |
| T7 | T9 | `analisi_completata`, `approva`, `registra_mutazione` | coerente |
| T8 | T9 | `SessionStore`, `export_sanitized_text` | coerente |
| T7, T8 | piano 1 | `hash_approvazione`, `maschera_documento` da `core/mask.py` | verificato che esistano nell'albero: sì, dal Task 8 del piano 1 |

### Coerenza interna di ciascun task

| Task | Test specificati contro codice specificato | Esito |
|---|---|---|
| T1 | `inspect.getmembers` confrontato con l'insieme dei nomi della spec §13 | coerente; `errors.py` non importa nulla, quindi non entrano classi estranee |
| T2 | offset del byte invalido: `errore.start` su `b"abc\xe8def"` vale 3, e il test cerca "3" | coerente, verificato a mano |
| T3 | la tabella del verdetto contro le quattro pagine di prova | coerente per tutte e quattro le righe, tracciate a mano; vedi Ruling B per una fragilità |
| T4 | tetto dei 10, dispatch per estensione, sha256 dei byte originali | coerente |
| T5 | intestazione a 36 byte, salt e nonce a fette `[8:36]`, AD sui primi 24 | coerente: 4+4+16 = 24 di AD, +12 di nonce = 36 |
| T6 | i cinque passi contro le due regex | coerente, con il falso positivo `[Nota]` fissato deliberatamente da un test |
| T7 | **lacuna**: `analisi_completata` non popolava le code delle ambiguità | vedi Ruling A |
| T8 | i due controlli del gate e la forma del payload | coerente |
| T9 | **dipendeva dalla lacuna di T7**: TC-03 asseriva un'ambiguità che nessuno creava | risolto dal Ruling A |

### Verifiche fatte sull'ambiente invece che a memoria

- PyMuPDF 1.28.0 installato: `fitz.Rect.get_area()` restituisce 200.0 su un rettangolo
  10x20, `Page.insert_textbox` e `Pixmap.clear_with` esistono. Il codice del Task 3 usa
  solo questi tre, quindi non si romperà su un nome di API cambiato.
- `analizza_documento` del piano 1 non chiama né `risolvi_ambiguita_omonimia` né
  `suggerisci_fusioni`: verificato leggendo il corpo della funzione nel codice consegnato.

## Rulings pre-esecuzione

Ruling A (T7, T9) — **La coda delle ambiguità non veniva popolata da nessuno.** Il piano 1
costruisce `risolvi_ambiguita_omonimia` e `suggerisci_fusioni`, e il revisore del suo Task
7 aveva già osservato che nessuna delle due viene chiamata in produzione. Il mio piano 2
faceva di `analisi_completata` un semplice cambio di stato, quindi la lacuna sarebbe
sopravvissuta a entrambi i piani: coda sempre vuota, `approva` senza nulla da bloccare, e
il gate delle omonimie della spec §7 inesistente in produzione. Il TC-03 del Task 9, che
asserisce un'ambiguità bloccante, sarebbe fallito — e sarebbe stato l'implementatore del
Task 9 a scoprirlo, a otto task di distanza da dove sta il difetto. Decido: le due
chiamate entrano in `analisi_completata`, e non dentro `analizza_documento`, perché
un'omonimia è una proprietà del fascicolo intero e si può calcolare solo quando tutti i
documenti sono stati analizzati. Ho emendato il piano prima di dispacciare (commit
37ecb5f) aggiungendo le chiamate, due test che le coprono, e l'aggiornamento del conteggio
atteso del Task 7 da 13 a 15. Costo se sbagliato: se un giorno servisse la coda aggiornata
a metà caricamento, va spostata o duplicata; oggi nessun chiamante lo chiede.

Ruling B (T3) — **Un test del Task 3 è fragile e lo dichiaro adesso invece di scoprirlo
in revisione.** `test_l_offset_della_seconda_pagina_punta_al_suo_testo` asserisce che il
testo dalla seconda pagina cominci con i primi 20 caratteri di `TESTO_DI_PAGINA`. Ma
`insert_textbox` manda a capo il testo per farlo stare nel riquadro, e `get_text` restituisce
i capoversi con i newline inseriti: se l'andata a capo cadesse entro i primi 20 caratteri
l'asserzione fallirebbe per come PyMuPDF impagina, non per un difetto degli offset.
Con fontsize 11 in un riquadro di 495 punti la prima riga è ben più lunga di 20 caratteri,
quindi oggi passa. Se fallisse, la correzione autorizzata è asserire che la prima parola
sia contenuta nei primi 50 caratteri della pagina, non allargare la tolleranza a caso.
Costo se sbagliato: un test che va ritoccato una volta.

Ruling C (T5) — **Accetto che i test del vault siano lenti.** Quattordici test che
chiamano `salva` o `carica` pagano ognuno 600.000 iterazioni di PBKDF2, cioè qualche
secondo di file. È il costo voluto del KDF e non va ottimizzato abbassando le iterazioni
nei test: un test che gira su parametri diversi da quelli di produzione non prova la
produzione. Costo se sbagliato: la suite si allunga di qualche secondo.

## Avanzamento

Setup: ramo di integrazione `feat/stato-e-persistenza` creato a 909a621, worktree `cc-wt/p2`.

Task 1: implementato (commit 3543f04, "feat: tassonomia degli errori di dominio e soglie
  del verdetto di scansione"), 13/13 nuovi, 172 totali non-lento, nessuna regressione.
Task 1: revisione — spec OK conforme, qualita' Approvato, 0 Critical, 0 Important, 0 Minor.
  Il revisore ha verificato che `errors.py` non contenga nessun `import`, il che rende il
  test su `inspect.getmembers` anche una guardia implicita contro classi estranee.
Task 1: complete (commits 909a621..3543f04, review clean)

Ventaglio parallelo dispacciato da 3543f04: Task 2 (haiku, trascrizione), Task 3, 5, 6, 7
  (sonnet). Cinque implementatori in parallelo su rami e worktree separati, file
  disgiunti. Ruling A trasportato nel dispatch del Task 7, Ruling B in quello del Task 3
  come correzione pre-autorizzata da dichiarare se usata, Ruling C in quello del Task 5
  come divieto di abbassare le iterazioni del KDF nei test.

Task 2: implementato (commit 9011769, "feat: caricatore TXT con decodifica UTF-8 strict"),
  6/6 nuovi, 178 suite completa.
Task 2: revisione — spec OK conforme (trascrizione verbatim verificata contro il brief,
  `.decode("utf-8")` senza argomento `errors=` e senza ramo di fallback, `InvalidEncoding`
  importato e non ridefinito, `raise ... from`, messaggio italiano). Qualita': Approvato.
  1 Important `plan-mandated`.
Task 2: 1 Important — `pytest.raises(InvalidEncoding, match="3")` non fissa l'offset:
  `match` e' una ricerca regex sul messaggio, quindi qualunque "3" da qualunque parte la
  soddisfa. Regge solo per accidente su questo input, perche' il messaggio non contiene
  altre cifre. E' un difetto del mio piano, previsto nel dispatch al revisore e trovato.
Task 2: minor (deferred): `from __future__ import annotations` inutile in txt_loader.py,
  imposto dal brief.

Ruling D (T2) — Fix round su un'asserzione da una riga. La stessa famiglia di difetto —
  un test che sembra verificare un valore e verifica l'esistenza di un carattere — e'
  costata due giri sul tiebreaker degli span e uno sull'omocodia nel piano 1. Qui costa
  `match=r"offset 3\b"`. Ho corretto anche il documento del piano, non solo il codice:
  lasciarlo com'era significa che una riesecuzione del piano riprodurrebbe il difetto.
  Costo se sbagliato: nessuno; l'ancora e' piu' stretta e il messaggio la contiene.

Task 3: implementato (commit af90020, "feat: estrazione PDF con verdetto di scansione per
  pagina"), 9/9 nuovi, 189 suite completa. La correzione pre-autorizzata del Ruling B NON
  e' stata usata: il test fragile e' passato cosi' com'era, come previsto. Revisione
  dispacciata.
Task 5: implementato (commit 734ff06, "feat: vault cifrato AES-256-GCM con intestazione
  autenticata"), 14/14 nuovi, 194 suite completa. Nessuna contraddizione trovata nel brief.
  Revisione dispacciata; al revisore ho chiesto di ricontrollare a mano tutti i confini
  delle fette e, soprattutto, se `carica` passi come associated data i byte letti DAL FILE
  o li ricostruisca dalle costanti — ricostruirli vanificherebbe in silenzio la proprieta'
  "non si possono abbassare le iterazioni" lasciando verde il test di manomissione.
Task 7: implementato (commit 83f361a, "feat: macchina a stati con approvazione e
  invalidazione su mutazione"), 15/15 nuovi, 187 non-lento. Revisione dispacciata con la
  richiesta esplicita di derivare da se' se i due test sulle code fallirebbero davvero
  rimuovendo le chiamate: e' il punto del Ruling A e non va accettato sulla parola.
Task 2: fix round 1 dispacciato (Ruling D).

Task 6: implementato (commit 0f26279, "feat: ripristino della risposta dell'IA senza esiti
  parziali"), 14/14 nuovi, 194 suite completa. DONE_WITH_CONCERNS.

Ruling E (T6) — L'implementatore ha trovato un difetto nel mio piano che vale piu' del
  task, e l'ha trovato perche' gli avevo chiesto di verificare empiricamente se i test
  reggono invece di assumerlo. Il fatto: l'ordinamento per lunghezza decrescente in
  `ripristina` NON e' protetto dal test che dichiara di proteggerlo. Con segnaposto
  terminati da parentesi chiusa nessuno puo' essere sottostringa di un altro —
  "[PERSONA_1]" non compare in "[PERSONA_10]" perche' dopo l'1 viene uno 0 e non la
  chiusura — quindi `test_indice_a_due_cifre_non_lascia_uno_zero_orfano` passa anche
  invertendo l'ordinamento. Verificato da lui capovolgendo il sort, e il ragionamento
  regge alla lettura.
  Ne segue che la motivazione della spec §11 passo 5 ("altrimenti resta uno 0 orfano") e'
  vera solo per un formato senza terminatore, non per il nostro. Decido: l'ordinamento
  RESTA, come difesa in profondita' per il giorno in cui il formato cambiasse, ma il
  commento va riscritto perche' oggi afferma il falso, e il test va rinominato perche'
  promette una protezione che non da'. Aggiungo un test che fissa la proprieta' che ci
  protegge davvero — nessun segnaposto e' sottostringa di un altro — cosi' se il formato
  perdesse la parentesi chiusa qualcosa fallisce e indica dove l'ordinamento diventa
  indispensabile. Ho corretto anche il documento del piano.
  Costo se sbagliato: nessuno sul comportamento; si tiene un sort inutile oggi in cambio
  di una rete per un cambio di formato futuro, e un'assunzione invisibile diventa guardata.
Task 7: revisione — spec OK conforme, qualita' Approvato, 0 Critical, 0 Important, 0 Minor.
  Il revisore ha fatto la derivazione richiesta invece di ripetere l'implementatore: ha
  tracciato `core/entities.py` e verificato che `risolvi_ambiguita_omonimia` e
  `suggerisci_fusioni` sono le UNICHE funzioni del codice che scrivono su
  `fascicolo.ambiguities`, e che `analisi_completata` e' il loro unico chiamante in
  produzione — quindi senza le due chiamate la lista resta vuota e i due test nuovi
  fallirebbero su `any()` e `len()`. Ha anche tracciato normalizza/chiavi_equivalenti per
  confermare che le due fixture producano davvero una SAME_NAME_NO_CF e un
  HEURISTIC_MERGE_SUGGESTION, non solo test strutturalmente plausibili.
Task 7: complete (commits 3543f04..83f361a, review clean)
Task 2: re-review round 1 — finding ADDRESSED. Il re-revisore ha derivato da se' che
  `\b` dopo la cifra seguita da spazio e' un confine di parola valido, e ha confermato la
  prova di sabotaggio (messaggio cambiato in "byte value 0x03": contiene "3" ma non
  "offset 3", il nuovo matcher falla, il vecchio sarebbe passato).
Task 2: complete (commits 3543f04..c7b828e, review clean dopo 1 fix round)

Task 3: revisione — spec OK conforme. Il revisore ha tracciato tutte e quattro le righe
  della tabella del verdetto contro i quattro costruttori di pagina, ha verificato
  empiricamente la coerenza fra testo restituito e offset (offsets = [0, 123] e
  testo[123:153] e' l'inizio della seconda pagina), e ha confermato che il Ruling B non
  serviva perche' la prima riga impaginata e' piu' lunga di 20 caratteri. Qualita':
  Approvato. 1 Important `plan-mandated`, 2 Minor.

Ruling F (T3) — Fix round: il rifiuto dei PDF cifrati non e' verificato da nessun test.
  Il rilievo e' fondato e l'ho controllato di persona invece di fidarmi, scoprendo anche
  che il mio ragionamento iniziale era sbagliato. I fatti misurati: su byte cifrati
  `fitz.open()` NON solleva, quindi l'`except Exception` attorno all'apertura non scatta;
  `needs_pass` vale 1; e caricare una pagina solleva
  `ValueError("document closed or encrypted")`. Quindi senza il controllo `needs_pass`
  l'utente non riceverebbe un documento accettato per errore — riceverebbe un ValueError
  grezzo invece del messaggio italiano che la spec §13 pretende, e il limite 10 della §16
  resterebbe scoperto. Il test e' costruibile a runtime con
  `tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=...)`, verificato funzionante,
  quindi non serve committare un binario e la spec §14 e' rispettata. Ho aggiunto al piano
  il costruttore `pdf_cifrato()` e il test. Costo se sbagliato: un test in piu' che
  costruisce un PDF cifrato a ogni esecuzione, qualche millisecondo.
Task 5: revisione — spec OK conforme, qualita' Approvato, 0 Critical, 0 Important, 1 Minor.
  Il revisore ha ricontrollato a mano ogni confine di fetta, ha verificato che `carica`
  legga l'header dai byte DEL FILE e non lo ricostruisca dalle costanti (era la mia
  domanda: ricostruirlo vanificherebbe in silenzio l'autenticazione dell'intestazione), e
  ha provato a runtime un caso che i test non coprono — un blob con magic giusto ma
  ciphertext piu' corto del tag GCM — confermando che solleva VaultUnreadable e non
  un'eccezione non gestita.
Task 5: minor (deferred): `vault_version` viene scritto nel payload ma non confrontato con
  `VAULT_VERSION` in lettura, quindi un vault di formato futuro verrebbe interpretato male
  invece di essere respinto con un errore chiaro. Il brief assegna la gestione delle
  versioni al piano 3.
Task 5: complete (commits 3543f04..734ff06, review clean)
Task 6: fix round 1/5 (1 addressed — commit 0f26279..f92815b, "fix: chiarisce che
  l'ordinamento in ripristina e' difesa in profondita'"), 15/15, 195 suite completa.
  Re-review dispacciata.
Merge nel ramo di integrazione: task 2 e task 5.
Task 3: fix round 1/5 (1 addressed — commit af90020..e76ea44, "test: copre il rifiuto dei
  PDF cifrati"), 10/10, 182 non-lento. Il sabotaggio ha confermato la mia misurazione
  alla lettera: negando `needs_pass` esce un ValueError grezzo e non
  ScannedDocumentRejected. Re-review dispacciata.

Task 6: re-review round 1 — il finding originale ADDRESSED, ma il re-revisore ha aperto una
  nuova rottura Important **nel test che avevo prescritto io**, ed e' nel giusto.

Ruling G (T6) — Il test che avevo ordinato al round 1,
  `assert "[PERSONA_1]" not in "[PERSONA_10]"`, e' una tautologia su due stringhe scritte
  a mano: non deriva da `SEGNAPOSTO`, non da `prossimo_placeholder`, non da nessun
  `Entity`. Quindi il suo commento — "se un domani il formato perdesse il terminatore
  questo test fallisce" — e' falso: se il formato cambiasse, quelle due costanti
  resterebbero identiche e il test resterebbe verde. E' esattamente il difetto che il
  round 1 doveva chiudere, riproposto un livello sotto, e l'ho scritto io. Il re-revisore
  ha fatto il suo lavoro nel segnalarlo invece di approvare la mia prescrizione.
  Correzione, verificata prima di ordinarla: `prossimo_placeholder` incrementa il
  contatore e costruisce il segnaposto dal formato reale (provato: dodici chiamate danno
  da [PERSONA_1] a [PERSONA_12]). Il test genera i segnaposto con quella funzione e
  verifica a coppie che nessuno sia sottostringa di un altro. Senza la parentesi chiusa
  "PERSONA_1" tornerebbe contenuto in "PERSONA_10" e il test fallirebbe davvero.
  Costo se sbagliato: il test lega test_unmask.py a `entities.py`, un accoppiamento che
  prima non c'era; e' il prezzo per avere una guardia vera invece di una finta.
Task 8: implementato (commit 454e3fb, "feat: gate di esportazione con controllo di stato e
  integrita'"), 9/9 nuovi, 204 suite completa. BASE 10615ab (integrazione dopo il task 7).
  Revisione dispacciata.
Task 3: re-review round 1 — finding ADDRESSED. Il re-revisore ha costruito una prova
  inattaccabile che il ramo `needs_pass` e' l'unico cancello: il sabotaggio ha prodotto un
  ValueError NON gestito, cosa possibile solo se `fitz.open` era riuscito; se avesse
  sollevato, il primo `except` l'avrebbe convertito in ScannedDocumentRejected e il test
  sabotato sarebbe passato comunque.
Task 3: minor (deferred) — `match="password"` non discrimina fra i due rami: entrambi i
  messaggi di rifiuto contengono la parola. Oggi il ramo giusto e' provato empiricamente,
  ma il test non e' autocertificante: se una versione futura di PyMuPDF facesse sollevare
  `fitz.open` sui flussi cifrati, il test passerebbe esercitando l'altro ramo. Il
  re-revisore ha esplicitamente detto di non rimandarlo a un fix round, e sono d'accordo:
  il Minor non entra nel ciclo. Correzione pronta per l'ondata finale, una riga:
  ancorare a `match=r"il PDF è protetto da password"`, che il messaggio dell'altro ramo
  ("il PDF non è leggibile o è protetto da password") non contiene.
Task 3: complete (commits 3543f04..e76ea44, review clean dopo 1 fix round)
Merge nel ramo di integrazione: task 3.
Task 8: revisione — spec OK conforme, qualita' Approvato, 0 Critical, 0 Important, 1 Minor.
  Il revisore ha tracciato il test sulla mutazione attraverso `maschera()` per verificare
  che cambiare `entita.placeholder` alteri davvero il testo mascherato, e ha notato che
  l'implementatore ha scelto il campo giusto: mutare `canonical_value` o uno span
  disattivato avrebbe prodotto un test che passa per la ragione sbagliata.
Task 8: minor (deferred): `SessionStore.prendi` propaga un KeyError nudo invece di un
  errore di dominio. E' cio' che il test del brief asserisce, quindi plan-mandated; il
  piano 3 dovra' tradurlo in un errore HTTP.
Task 8: complete (commits 10615ab..454e3fb, review clean)
Merge nel ramo di integrazione: task 8.
Task 6: fix round 2/5 (1 addressed — commit f92815b..c3d4220, "fix: deriva il test
  anti-sottostringa dai segnaposto generati"), 15/15, 195 completa.
Task 6: re-review round 2 — ADDRESSED. Il re-revisore ha derivato la fallibilita' dal
  sorgente invece di accettare il log: dodici chiamate attraversano il confine fra una e
  due cifre (nove non l'avrebbero attraversato), `itertools.permutations` copre entrambe
  le direzioni quindi la coppia (PERSONA_1, PERSONA_10) e' controllata nel verso che
  conta, e senza la parentesi "PERSONA_1" e' letteralmente il prefisso di "PERSONA_10".
  Ha anche annotato che questo e' il primo dei tre tentativi il cui commento dice il vero.
Task 6: complete (commits 3543f04..c3d4220, review clean dopo 2 fix round)
Merge nel ramo di integrazione: task 6.
Task 4: implementato (commit 6a5a4a7, "feat: ingresso nel fascicolo con tetto di dieci
  documenti e avviso segnaposto"), 14/14 nuovi, 239 suite completa. Revisione dispacciata.
Task 4: l'implementatore ha segnalato un mio errore ed e' nel giusto. Gli avevo scritto
  "baseline 234 test" ma il suo worktree, creato da a036f4c, ne aveva 225: il 234 lo avevo
  misurato dopo aver unito i task 8 e 6, cioe' su un commit che il suo worktree non
  contiene. Ha verificato con `git stash` invece di fidarsi. Conseguenza pratica nulla —
  il numero era informativo — ma e' il terzo mio errore in questo piano dopo l'asserzione
  debole sull'offset e il test tautologico, e la forma e' sempre la stessa: ho riportato
  una misura senza controllare a quale commit appartenesse. 225 + 14 = 239 torna.

## Ripresa in sessione nuova

La sessione precedente si e' interrotta dopo aver dispacciato la revisione del Task 4:
il pacchetto `review-a036f4c..6a5a4a7.diff` esiste (14:50) ma nessun esito e' mai
arrivato al ledger. Stato accertato alla ripresa, verificato sull'albero e non sul
ledger: task 1, 2, 3, 5, 6, 7, 8 merged in `feat/stato-e-persistenza` (02a751d),
241 test non-lento verdi nel worktree di integrazione; task 4 implementato su
`feat/p2-t4-loader` (6a5a4a7) e non merged; task 9 mai iniziato.

Il partner umano ha scelto di chiudere il solo Task 4 e poi decidere, invece di
correre la revisione finale su 7 task di 9.

Task 4: revisione ri-dispacciata (sonnet) sullo stesso pacchetto diff, con in piu' una
  richiesta mirata: verificare che i test sul tetto dei dieci, sullo sha256 dei byte
  originali e sull'avviso dei segnaposto preesistenti fallirebbero davvero contro
  un'implementazione sbagliata. E' la famiglia di difetto che in questo piano si e' gia'
  presentata tre volte (Ruling D, E, G), sempre in test prescritti dal piano.
Task 4: revisione — spec OK conforme (tre funzioni, un file, un commit, nessun import
  vietato, regex del segnaposto conforme). Qualita': Needs fixes. 0 Critical,
  1 Important `plan-mandated`, 3 Minor. Il revisore ha confermato che i test sul tetto
  dei dieci reggono davvero: ha derivato che un no-cap, un off-by-one e un rollback
  mancato verrebbero tutti intercettati, perche' il test controlla insieme l'eccezione
  e la lunghezza del fascicolo esattamente al confine.

Ruling H (T4) — **Il test sullo sha256 non poteva distinguere le due implementazioni.**
  Il piano dice che `sha256` e' il digest dei byte originali "non del testo estratto",
  ma il test che dovrebbe fissarlo passa un `.txt`, e sul ramo TXT `carica_txt` e' un
  `decode("utf-8")` puro: ricodificare restituisce gli stessi byte. Un'implementazione
  che avesse hashato il testo estratto — l'errore esatto che il brief vieta — avrebbe
  prodotto lo stesso digest e il test sarebbe rimasto verde. Ho misurato prima di
  ordinare la correzione, invece di fidarmi del revisore: round-trip identico su ASCII,
  su un input con BOM e su testo accentato; e `pdf_di_prova(["testo"])` da' 948 byte
  contro 123 caratteri di testo estratto. Decido: l'asserzione sul TXT resta, perche' e'
  vera per quel ramo, e le si affianca un caso PDF, l'unico ingresso su cui le due
  implementazioni candidate danno risposte diverse. Fix round dispacciato con l'obbligo
  di provare per sabotaggio che il test nuovo fallisce davvero. E' la quarta volta in
  questo piano che un test prescritto dal piano promette una garanzia che non da'
  (dopo i Ruling D, E, G): la forma ricorrente e' sempre la stessa, un'asserzione che
  non puo' fallire contro l'implementazione sbagliata che nomina.
  Costo se sbagliato: un test in piu' che costruisce un PDF, qualche millisecondo.
Task 4: minor (deferred): il riempimento del fascicolo fino a MAX_DOCUMENTI e' ripetuto
  verbatim in tre test; una fixture `fascicolo_pieno` lo toglierebbe.
Task 4: minor (deferred): l'estensione `.PDF` maiuscola non ha un test esplicito, solo
  `.TXT`; il ramo e' simmetrico e il rischio e' basso.
Task 4: minor (chiuso, non differito): il revisore segnalava che il commento di
  `loader.py` rimanda a una regex gemella in `core/unmask.py`, modulo assente dal suo
  worktree. Verificato sul ramo di integrazione: `unmask.py` esiste dal Task 6 e
  contiene `SEGNAPOSTO = re.compile(r"\[[A-Z]+_\d+\]")`, identica. Il commento dice il
  vero dopo il merge; era un artefatto della base del worktree, non un rilievo.
Task 4: fix round 1/5 (1 addressed — commit 6a5a4a7..702e76f, "test: ancora lo sha256 al
  ramo PDF, dove i byte divergono dal testo"), 15/15 in test_loader.py, 232 non-lento nel
  worktree del task. Il sabotaggio ordinato ha dato 1 failed / 14 passed, e a fallire e'
  stato esattamente il test nuovo mentre quello sul TXT restava verde: la conferma
  sperimentale che il ramo TXT non discrimina.
Task 4: re-review round 1 — ADDRESSED, 0 rotture nuove. Il re-revisore ha fatto la
  derivazione richiesta invece di fidarsi del log: il test asserisce sia
  `doc.text.encode("utf-8") != contenuto` sia `doc.sha256 == sha256(contenuto)`, quindi
  un'implementazione che hashasse il testo estratto confronterebbe i digest di due
  preimmagini diverse e fallirebbe. Il test puo' fallire per costruzione, non per
  accidente: e' il primo di questa famiglia in cui la garanzia promessa dal nome esiste
  davvero senza che sia servito un secondo giro.
Task 4: complete (commits a036f4c..702e76f, review clean dopo 1 fix round)
Merge nel ramo di integrazione: task 4 (56e56e6). Suite sul ramo di integrazione:
  264 test verdi (256 non-lento + 8 lento), output pulito.
Piano emendato (522e93d su feat/motore-riconoscimento): il test sullo sha256 nel Task 4
  ora e' la coppia TXT+PDF atterrata davvero, e la prosa del task dice che la proprieta'
  e' verificabile solo sul ramo PDF. Senza questo, una riesecuzione del piano
  riprodurrebbe il difetto.

Stato: 8 task su 9 completi e merged. Resta il **Task 9** (matrice della consegna e test
anti-fuga, spec §14) e poi la revisione finale whole-branch, con il triage dei minor
differiti elencati sopra.

Nota sull'ambiente, rilevata durante il merge: nel worktree principale c'e' un'altra
sessione al lavoro (modifiche non committate a 13 file del piano 1 e un
`tests/test_documenti_di_verifica.py` non tracciato). Il commit del piano ha usato un
`git add` del solo file del piano, quindi non ha inglobato nulla di quel lavoro. Inoltre
git non riesce a potare `.git/worktrees/t5..t8`, residui dei worktree del piano 1 gia'
cancellati da disco: "Permission denied" di OneDrive a ogni comando che scrive. Rumore,
non un errore delle operazioni.

Task 9: dispacciato (sonnet) nel worktree `cc-wt/p2-t9`, ramo `feat/p2-t9-matrice`,
  base 56e56e6, baseline dichiarata 264 test (256 non-lento + 8 lento) misurata da me
  su quella stessa base — non su un altro commit, che e' l'errore fatto col Task 4.

Ruling I (T9) — **Dispaccio il Task 9 anche se la sessione vicina sta scrivendo un
  altro test sulla §14.** L'altra chat, che sta chiudendo il fix wave della revisione
  finale del piano 1, ha in lavorazione un `tests/test_documenti_di_verifica.py` non
  ancora committato che punta alla stessa sezione della spec del mio Task 9. Nomi di
  file diversi, quindi al merge non collidono; il rischio e' avere due suite anti-fuga
  che dicono la stessa cosa in due modi. Ho scritto alla sessione vicina chiedendo cosa
  copre la sua, ma non aspetto la risposta: il piano e' l'autorita' e i sei casi della
  matrice sono roba del piano 2, non della loro. Se la loro fixture risultasse la sede
  giusta per l'anti-fuga generico, la riconciliazione e' un dedup al merge, non un
  lavoro perso. Costo se sbagliato: un test duplicato da togliere.

Trasmesso all'implementatore del Task 9 un fatto che arriva dalla revisione finale del
  piano 1 e che il brief non contiene: il loro revisore ha visto un'asserzione anti-fuga
  PASSARE su un documento con quattro valori in chiaro. La ragione e' strutturale — il
  test quantifica sui valori del dizionario, e un valore che il motore non ha rilevato
  nel dizionario non c'e', quindi non puo' farlo fallire ed e' esattamente quello che
  fugge. Il test dimostra che il masking ha applicato gli span ricevuti, non l'assenza
  di fughe, e nome e commento devono dire solo quello.

Task 9: implementato (commit d33afde, "test: la matrice della consegna e il test anti-fuga
  generico"), 7 test nuovi (5 veloci + 2 lento), 271 suite completa. DONE_WITH_CONCERNS.
  Revisione dispacciata con il rilievo gia' nominato e verificato da me.

Ruling J (T9) — **Il fixture piu' ricco della matrice monta un codice fiscale che il
  motore e' progettato per scartare.** L'implementatore ha trovato che in `TESTO_RICCO`
  il CF `RSSMRA85M01H501Z` ha il CIN sbagliato. Verificato da me e non accettato sulla
  parola: `cf_valido("RSSMRA85M01H501Z")` e' False, `...Q` e' True; e quel valore e' il
  fixture NEGATIVO del progetto, usato in `tests/test_rules.py:19` e
  `tests/test_validators.py:21` proprio come CF da rifiutare, mentre ogni altro test usa
  la variante valida. Conseguenza: il CF non viene mai rilevato, non entra nel
  dizionario, e il test anti-fuga passa mentre quel codice fiscale esce in chiaro nel
  testo esportato. Stessa struttura per PERSONA, che solo il NER produce e che l'helper
  dei test tiene spento. Non ho ancora deciso la correzione: aspetto il revisore, perche'
  la domanda "quale implementazione sbagliata prenderebbe ciascuno dei sette test" e'
  esattamente quella che gli ho posto. E' il quinto difetto della stessa famiglia in
  questo piano, ma il primo in cui la garanzia mancante e' quella che da' il nome al
  prodotto.

Integrazione dei rami (referto dell'agente di analisi, letto e sintetizzato):
  - `git merge-tree --write-tree feat/stato-e-persistenza be67584` esce 0, un solo albero,
    nessun CONFLICT: i due rami toccano file di produzione disgiunti.
  - Ordine consigliato: prima il motore, poi lo stato.
  - Nessun dedup necessario sulla §14: `test_documenti_di_verifica.py` (motore) copre
    riconoscimento e mascheratura generici, `test_matrice_consegna.py` (stato) i sei
    scenari TC-01..TC-06 di ingresso, stato ed export. Due proprieta' distinte. Questo
    chiude la Domanda A che avevo mandato alla sessione vicina.
  - Da assorbire al merge: la versione del documento del piano 2 vive aggiornata solo sul
    ramo motore (2234 righe contro 2111), e `requirements.txt` documenta
    `it_core_news_lg` solo la'.
  - Avvertenza sul referto: dice che il Task 9 non e' committato su nessun ref. E' stale,
    l'agente ha guardato i due rami principali e non `feat/p2-t9-matrice`.

Ruling K — **Non sincronizzo i rami prima della revisione finale del piano 2.** Il
  referto consiglia di portare il motore dentro lo stato per primo, ed e' giusto come
  ordine di consegna, ma farlo adesso allargherebbe il diff della revisione finale del
  piano 2 (base 909a621) a tutto il lavoro del piano 1, che ha gia' avuto la sua
  revisione finale. Decido: prima chiudo il Task 9 e faccio la revisione finale del
  piano 2 sul suo ramo, poi si integra. Costo se sbagliato: il piano 2 viene revisionato
  senza le due correzioni di produzione arrivate dal motore dopo 909a621 — in particolare
  `2c61c8f`, che scarta gli span del NER fatti di sole parole di struttura; se
  interagissero con la matrice, emergerebbe all'integrazione invece che in revisione.
Task 9: revisione — spec conforme sulla struttura (trascrizione byte per byte del brief,
  nessun codice di produzione toccato), ma ❌ sul contenuto: qualita' Needs fixes,
  0 Critical, 1 Important `plan-mandated`, 1 Minor (il rumore del gc di git). Il revisore
  ha fatto il lavoro che gli avevo chiesto — per ciascuno dei sette test ha detto quale
  implementazione sbagliata prenderebbe, verificando ogni volta sul sorgente: TC-01
  contro il messaggio di pdf_loader.py:66, TC-03 contro il cablaggio in session.py:26 e
  il predicato in models.py:106, TC-04 e TC-06 contro il gate in session.py:87. Sei test
  su sette portano segnale vero.
  Aggiunge una sfumatura che il mio Ruling J non aveva: la vacuita' del settimo test e'
  PARZIALE. IBAN, P.IVA, telefono ed email del fixture sono validi e vengono rilevati
  davvero; il buco riguarda solo PERSONA e CF.

Ruling L (T9) — **Il fixture della matrice deve montare dati che il motore e' fatto per
  rilevare, e il test deve dire il vero su cosa prova.** Quattro correzioni, tutte
  obbligatorie: (1) `TESTO_RICCO` passa al CF valido `...Q`, perche' il `...Z` e' il
  fixture negativo del progetto e la sua sede sono i test che provano il rifiuto;
  (2) il test anti-fuga gira con `usa_ner=True` e marker `lento`, cosi' la gamba
  statistica viene esercitata invece di essere strutturalmente assente; (3) prima di
  quantificare sul dizionario, il test asserisce che le categorie che il fixture pianta
  di proposito sono state davvero rilevate — senza questa guardia il test torna a non
  provare nulla il giorno che il rilevamento regredisce, perche' il dizionario si
  restringe e il ciclo itera su meno roba restando verde; la guardia di non-vuoto che
  gia' c'era non e' bastata; (4) il docstring dice cosa il test prova e cosa non prova.
  All'implementatore ho ordinato due sabotaggi separati come prova di fallibilita' (CF
  rimesso a `...Z`; `usa_ner=False`) e gli ho vietato di indebolire l'asserzione se il
  NER non trovasse "Mario Rossi": in quel caso e' un rilievo sul prodotto, non un test
  da ammorbidire. Costo se sbagliato: un test `lento` in piu' e un accoppiamento della
  matrice al modello linguistico, che e' esattamente cio' che la spec §16.7 dichiara
  inaffidabile — ma tenerlo spento significava non provarlo mai.
Task 9: fix round 1 dispacciato (Ruling L).
Task 9: fix round 1/5 (1 addressed — commit d33afde..8ff54ec, "test: la matrice monta dati
  che il motore deve davvero rilevare"). Prove ordinate e prodotte: sabotaggio (a) CF
  rimesso a `...Z` -> fallisce su `mancanti = {Category.CF}`; sabotaggio (b)
  `usa_ner=False` -> fallisce su `mancanti = {Category.PERSONA}`; il NER trova davvero
  "Mario Rossi" (canonical_value esatto); e la fuga pre-fix e' stata esibita — con il
  vecchio fixture sia "Mario Rossi" sia il CF sopravvivevano verbatim nell'export mentre
  il test passava. 260 non-lento + 11 lento = 271, invariati: nessun test aggiunto, un
  marker spostato e le asserzioni irrobustite.
Task 9: re-review round 1 — ADDRESSED su tutti e quattro i punti del Ruling L, 0 rotture
  nuove. Il re-revisore ha ricalcolato il CIN a mano dalle tabelle di validators.py
  (somma 120, 120 % 26 = 16, chr(65+16) = 'Q') invece di accettare che il fixture fosse
  valido, e ha verificato che la guardia non e' tautologica: il lato sinistro
  (`categorie_rilevate`) e' derivato a runtime da `fascicolo.entities`, il destro e' un
  insieme fisso — quindi la guardia fallisce davvero se il motore regredisce.
Task 9: complete (commits 56e56e6..8ff54ec, review clean dopo 1 fix round)
Merge nel ramo di integrazione: task 9 (34cb02a). Suite completa: 271 verdi, output
  pulito. **Piano 2 completo: 9 task su 9.**
Piano emendato (2255f82): il fixture della matrice monta il CF valido, il test anti-fuga
  ha il marker lento, la guardia sulle categorie e il docstring onesto; e la prosa del
  Task 9 ora avverte di cosa quel test NON prova. Senza questo, una riesecuzione del
  piano ricostruirebbe la fuga.

Revisione finale whole-branch dispacciata (opus, come prescrive la Model Selection):
  pacchetto 909a621..34cb02a, 23 commit, 67 KB. Le e' stato dato: i tre scostamenti dalla
  spec che il piano dichiara, i sette rilievi differiti da triagiare uno per uno, le
  rulings A/C/E/G/F/H/J/L da contestare se sbagliate, e la lente — "quale implementazione
  sbagliata prenderebbe questo test" invece di "esiste un test" — con l'indicazione dei
  due punti dove vive la promessa del prodotto, il gate di esportazione e il vault.

Revisione finale: 0 Critical, 6 Important, molti Minor. Verdetto "Ready to merge: With
  fixes". Il rilievo che conta: `approva` non controllava lo stato, quindi su un fascicolo
  mai analizzato l'hash si calcolava sul testo NON mascherato, lo stato diventava APPROVED
  e il gate restituiva il documento originale in chiaro. TC-04 provava che l'export in
  DRAFT e' negato, non che in DRAFT non si possa approvare. La revisione ha anche
  giudicato giustificati tutti e tre gli scostamenti dichiarati dal piano, e ha stabilito
  che in due casi su tre **la spec e' sbagliata e il codice ha ragione**.
Ondata di fix finale (una sola, come prescrive la skill): commit e0cf5d6, F1-F8 tutti
  ADDRESSED, 277 verdi (266 non-lento + 11 lento), output pulito. Sei sabotaggi ordinati e
  tutti confermati: guardia rimossa -> DID NOT RAISE; formato del segnaposto da `_` a `-`
  -> falliscono entrambi i controlli nuovi; AAD tolto da encrypt/decrypt -> fallisce solo
  il test nuovo mentre gli altri 14 restano verdi; salt fisso a zero -> fallisce la
  scissione dell'asserzione; `_e_scansione` che ignora la frazione immagine -> fallisce
  solo il caso "logo"; `.lower()` rimosso -> fallisce con InvalidEncoding.
Re-review dell'ondata dispacciata: e' l'unica prevista, non c'e' una seconda ondata.

I ticket: 21 issue pubblicate sul progetto 105 (era vuoto). #1 integrazione dei rami come
  cancello, #2-#11 le slice verticali del piano 3, #12/#13/#19/#21 ready-for-human per le
  decisioni, #14-#18 e #20 i difetti noti e i residui. I riferimenti "Blocked by" usano
  gli iid, che coincidono con la numerazione perche' il progetto partiva vuoto.
