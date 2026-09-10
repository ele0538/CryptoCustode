# Integrazione dei piani 1 e 2 (issue #1)

Ramo risultante: **`feat/integrazione-piani-1-2`**, creato da
`feat/motore-riconoscimento` e con `feat/stato-e-persistenza` unito dentro con
`--no-ff`. I due rami di partenza non sono stati toccati: se questa
integrazione va rifatta, si butta il ramo e si ricomincia.

## Il merge

`git merge-tree` era pulito e lo è rimasto: **zero conflitti**. I file di
produzione dei due rami sono disgiunti.

| Piano | File di produzione |
| --- | --- |
| 1 — motore | `core/detect/`, `core/entities`, `core/mask`, `core/spans`, `core/models` |
| 2 — ingresso, stato, persistenza | `core/errors`, `core/ingest/`, `core/unmask`, `core/vault`, `state/session` |

Il lavoro vero non era il merge testuale ma la **convivenza semantica**: il
piano 2 è stato scritto contro l'`entities.py` della base di merge, e nel
frattempo il piano 1 gli ha aggiunto due comportamenti che potevano rompere le
sue chiamate — la guardia di non-idempotenza in `analizza_documento`, che ora
solleva `ValueError` se il documento ha già span nel fascicolo, e il rifiuto
delle chiavi vuote in `_entita_per_valore`. Nessuno dei due ha rotto niente:
verificato eseguendo la suite, non leggendo il diff.

## Conteggio dei test

Contati eseguendo la suite su ciascun ramo, non stimati:

| Ramo | Test | Aggiunti sopra la base |
| --- | --- | --- |
| base di merge (`909a621`) | 167 | — |
| `feat/motore-riconoscimento` | 280 | +113 |
| `feat/stato-e-persistenza` | 277 | +110 |
| **integrazione** | **390** | **+223** |

`167 + 113 + 110 = 390`, che è esattamente il totale osservato dopo il merge:
nessun test è andato perso nel merge e nessuno è stato contato due volte. La
somma grezza `280 + 277 = 557` è priva di senso perché conterebbe due volte i
167 test della base, presenti su entrambi i rami.

Controprova contro l'accoppiamento fra file: ogni file di test eseguito da
solo passa, e la somma dei diciotto file isolati fa 390, lo stesso totale
della suite intera. Suite verde, output pulito, zero warning, zero skip.

## Le due asserzioni generiche della §14

La spec §14 chiede **due cose distinte**, e i due rami ne hanno implementata
una ciascuna. Non sono un duplicato, e infatti convivono:

- `test_matrice_consegna.py::test_anti_fuga_...` (piano 2) copre l'asserzione
  alla lettera — «non compare nel testo *esportato*» — sul percorso
  `approva` -> `export_sanitized_text`, quindi attraverso il gate di stato e
  il controllo di integrità.
- `test_documenti_di_verifica.py` (piano 1) copre l'altro punto della §14, i
  «documenti di verifica distinti da quelli di sviluppo», sul percorso
  `analizza_documento` -> `maschera_documento`, e in più misura il *richiamo*
  su tutte e dodici le categorie in prosa realistica.

La distinzione è stata **falsificata, non affermata**, con due mutazioni:

| Mutazione | `test_matrice_consegna` | `test_documenti_di_verifica` |
| --- | --- | --- |
| `export_sanitized_text` restituisce `documento.text` invece del mascherato | **fallisce** | passa per intero |
| il motore perde una categoria che la matrice non pianta (regex CATASTO spenta) | passa per intero | **fallisce** (3 test) |

Ognuna vede una fuga che l'altra non vede: togliere una delle due lascerebbe
scoperto un percorso intero. Il confronto è scritto nei docstring di entrambe,
così chi passerà da qui non le prenderà per una ripetizione da potare.

## Cose che il merge non ha cambiato, verificate

- Il documento del piano 2 (`docs/superpowers/plans/2026-09-10-stato-e-persistenza.md`)
  è la versione del ramo del motore, la più recente. Il ramo del piano 2 non
  l'ha mai toccato, quindi non c'era nulla da scegliere a mano: la versione
  vecchia differisce da quella sopravvissuta per 169 righe aggiunte e 17 tolte.
- `requirements.txt` è intatto, con l'istruzione di installare
  `it_core_news_lg` a parte e la nota sui 550 MB per processo.

## Lasciato aperto

`docs/superpowers/esecuzione/HANDOFF.md` è stale. Non toccato in questa
integrazione, su indicazione esplicita.
