# CryptoCustode — Design

**Data:** 2026-09-10
**Stato:** approvato in brainstorming, da tradurre in piano di implementazione

## 1. Scopo e ambito

Applicazione locale mono-utente che sostituisce i dati personali di un gruppo di
documenti italiani con segnaposto, permette all'utente di verificare e approvare il
risultato, ne consente l'esportazione come solo testo mascherato, e ripristina i dati
originali dentro la risposta restituita da un'IA esterna.

L'applicazione non effettua alcuna chiamata di rete. Il trasferimento del testo verso
l'IA e il ritorno della risposta avvengono per copia-incolla, a cura dell'utente.

**Capacità:** massimo 10 documenti per fascicolo, un fascicolo attivo per volta.

**Formati accettati:** TXT con codifica UTF-8; PDF digitali con testo estraibile.
**Formati respinti:** PDF scansionati o a prevalenza raster (rifiuto dell'intero file).

## 2. Decisioni chiuse

| # | Decisione | Motivo |
|---|---|---|
| 1 | FastAPI + uvicorn su `127.0.0.1`, UI HTML/CSS/JS vanilla in una scheda del browser aperta all'avvio | L'API di esportazione richiesta dalla consegna esiste letteralmente ed è dimostrabile; la UI di revisione con testo evidenziato e selezione manuale è molto più semplice in HTML; il gate di approvazione è testabile con `TestClient` |
| 2 | Il testo estratto è immutabile; l'utente agisce solo sugli span | Elimina la contraddizione fra editing libero e masking basato su offset; rende il masking una funzione pura, quindi l'hash di approvazione riproducibile; impedisce all'utente di reintrodurre dati reali nel testo esportabile |
| 3 | Fusione automatica solo su codice fiscale identico; le euristiche sui nomi producono suggerimenti da confermare; separare è il default | Fondere per errore corrompe i dati e rivela il nome di una persona al posto di un'altra; separare per errore degrada solo la qualità della risposta dell'IA |
| 4 | Tutte le categorie mascherate di default, incluse date e importi; toggle per categoria più controllo sul singolo span | Prudente sulla privacy e aderente alla lettera della consegna, senza rinunciare al controllo dell'utente |
| 5 | Nessuna scrittura in chiaro su disco; il `.vault` cifrato contiene l'intero fascicolo | Consente di riprendere una revisione e di ripristinare una risposta in una sessione successiva, al costo di qualche campo in più nello stesso blob cifrato |
| 6 | Nessuna chiamata di rete nell'applicazione; la API key Gemini vive solo in `tools/e2e_gemini.py` | Storia della privacy verificabile: nessun dato esce dal processo. Lo script serve a provare il giro completo e il comportamento dell'IA che storpia i segnaposto |

## 3. Stack tecnologico

Verificato sulla macchina di sviluppo il 2026-09-10.

| Componente | Scelta | Note |
|---|---|---|
| Runtime | Python 3.14.5 | unico interprete installato; le wheel `cp314` esistono per tutto lo stack nativo di spaCy (`spacy` 3.8.16, `thinc`, `blis`, `murmurhash`, `preshed`, `srsly`, `cymem`), verificate con `pip download --only-binary=:all:` |
| Estrazione PDF | PyMuPDF 1.28 | già installato |
| NER | spaCy 3.8 + `it_core_news_lg` | da installare; il modello è una wheel `py3-none-any` vincolata alla serie 3.8, da verificare in fase di setup |
| Crittografia | `cryptography` 48 | già installato |
| HTTP | FastAPI 0.137 + uvicorn 0.49 | già installati |
| Test | pytest 9.1 | già installato |

L'ambiente va isolato in un virtualenv di progetto: oggi i pacchetti sono installati
globalmente e il repo non ne ha uno.

## 4. Architettura dei moduli

```
cryptocustode/
├── core/                     ← libreria pura: non importa fastapi, non importa state/
│   ├── ingest/
│   │   ├── txt_loader.py     # UTF-8 strict
│   │   └── pdf_loader.py     # PyMuPDF: estrazione + verdetto scansione
│   ├── detect/
│   │   ├── patterns.py       # le regex, una per categoria
│   │   ├── validators.py     # CIN codice fiscale, cifra di controllo P.IVA, IBAN MOD-97
│   │   ├── rules.py          # regex + validatori -> Span
│   │   └── ner.py            # spaCy -> Span
│   ├── spans.py              # risoluzione priorità e sovrapposizioni
│   ├── entities.py           # Span -> Entity, euristiche nomi, coda ambiguità
│   ├── mask.py               # (testo, span attivi) -> testo mascherato   [PURA]
│   ├── unmask.py             # (risposta IA, dizionario) -> testo ripristinato
│   └── vault.py              # AES-256-GCM + PBKDF2, header versionato
├── state/
│   ├── models.py             # dataclass del dominio
│   └── session.py            # macchina a stati, hash di approvazione, SessionStore
├── api/
│   ├── app.py                # crea l'app, bind loopback, apre il browser
│   ├── routes_fascicolo.py   # upload, analisi, revisione, approvazione
│   ├── routes_restore.py     # ripristino della risposta IA
│   └── export.py             # UNICO punto da cui esce il testo mascherato
├── ui/                       # index.html, app.js, style.css
├── tests/
└── tools/
    └── e2e_gemini.py         # script separato, fuori dall'applicazione
```

### Invarianti

1. **`core/` non conosce né HTTP né lo stato di sessione.** Garantita da un test di
   architettura che ispeziona gli import sotto `core/` e fallisce se trova `fastapi`,
   `uvicorn` o `state`.
2. **`mask.py` è deterministica.** Nessun filesystem, nessun orologio, nessun random.
   Necessario perché `approval_hash` deve essere riproducibile: un masking non
   deterministico farebbe fallire il confronto a caso.
3. **Solo `api/export.py` fa uscire il testo mascherato.** Nessun'altra route lo
   serializza.
4. **Il dizionario delle corrispondenze non appare in nessuna risposta HTTP.** Esce dal
   processo soltanto come blob cifrato dentro il `.vault`.

La route di revisione **restituisce** il testo originale in chiaro, perché il punto 5
della consegna richiede che l'utente legga tutte le pagine e corregga. Non contraddice
l'invariante 3: revisione ed esportazione sono due contratti distinti, e il vincolo del
punto 6 della consegna riguarda solo il secondo.

**Nessuna anteprima del testo mascherato prima dell'approvazione.** La UI di revisione
mostra il testo originale con gli span evidenziati e, accanto a ciascuno, il segnaposto
che lo sostituirà. Non materializza mai il documento mascherato completo. La ragione è
che un'anteprima integrale sarebbe copiabile, quindi esportabile di fatto, e renderebbe
il gate di approvazione una formalità aggirabile. Il testo mascherato completo esiste in
due soli momenti: nel calcolo dell'`approval_hash` e nel payload di `export.py`. Ne
segue anche un beneficio pratico: la logica di masking non va duplicata in JavaScript,
quindi non può divergere da quella su cui si calcola l'hash.

## 5. Modello dati

```python
Category = PERSONA | AZIENDA | INDIRIZZO | EMAIL | TELEFONO | CF | PIVA
         | IBAN | DATA | IMPORTO | PRATICA | CATASTO
Source   = RULE | NER | MANUAL
State    = DRAFT | PENDING_REVIEW | APPROVED
AmbiguityKind = SAME_NAME_NO_CF | HEURISTIC_MERGE_SUGGESTION

@dataclass(frozen=True)
class Document:
    doc_id: str
    filename: str
    text: str                  # testo estratto, mai modificato
    page_offsets: list[int]    # offset di inizio di ogni pagina
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

@dataclass
class Entity:
    entity_id: str
    category: Category
    placeholder: str           # "[PERSONA_1]"
    canonical_value: str       # valore usato nel ripristino
    variants: set[str]
    cf: str | None

@dataclass
class Ambiguity:
    ambiguity_id: str
    kind: AmbiguityKind
    category: Category
    candidate_entity_ids: list[str]
    occurrence_span_ids: list[str]   # per mostrare il contesto all'utente
    resolved: bool

@dataclass
class Fascicolo:
    fascicolo_id: str          # uuid4, usato per l'isolamento fra sessioni
    documents: list[Document]  # massimo 10
    spans: list[Span]
    entities: dict[str, Entity]
    category_enabled: dict[Category, bool]
    ambiguities: list[Ambiguity]
    state: State
    approval_hash: str | None
    counters: dict[Category, int]
```

### Regole del modello

**Due interruttori indipendenti.** Uno span viene mascherato se e solo se
`span.enabled AND category_enabled[span.category]`. Il primo è l'override sul singolo
caso, il secondo l'interruttore di massa. Tenerli distinti dà una risposta ovvia alla
domanda "disattivo la categoria e poi la riattivo: che fine fanno gli span che avevo
disattivato a mano?". Rimuovere uno span lo disattiva invece di cancellarlo: l'utente
torna indietro senza bisogno di uno stack di undo.

**Nessuno stato `DIRTY`.** Ogni mutazione — nuovo span, span disattivato, entità fusa o
separata, toggle di categoria, ambiguità risolta — riporta lo stato a `PENDING_REVIEW`
e azzera `approval_hash`. Il ricalcolo dell'hash in export resta come seconda linea di
difesa contro una futura mutazione che dimenticasse il reset.

**Indici mai riciclati.** `counters` cresce e non torna indietro: se `[PERSONA_3]` viene
fuso in `[PERSONA_1]`, l'indice 3 resta bruciato, così un testo esportato in precedenza
non può contenere un segnaposto che oggi significa un'altra persona.

## 6. Pipeline di riconoscimento

Approccio ibrido a priorità decrescente su span di caratteri. Uno span di priorità
superiore consuma il testo e lo sottrae ai livelli successivi. A parità di priorità
vince lo span più lungo; su sovrapposizione parziale vince la priorità più alta.

| Pri | Categoria | Estrazione | Validazione |
|---|---|---|---|
| P1 | CF | `[A-Z]{6}[0-9LMNPQRSTUV]{2}[ABCDEHLMPRST][0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{3}[A-Z]` | CIN sul 16° carattere con le tabelle ufficiali pari/dispari, applicate ai 15 caratteri così come compaiono, incluse le sostituzioni di omocodia |
| P1 | IBAN | `\b[A-Z]{2}\d{2}[0-9A-Z]{11,30}\b` | ISO 7064 MOD 97-10 |
| P1 | PIVA | `\b(?:IT)?\d{11}\b`, con requisito di contesto (vedi sotto) | cifra di controllo della partita IVA italiana, calcolata sulle prime 10 cifre |
| P2 | EMAIL | regex RFC 5322 semplificata | struttura e TLD plausibile |
| P2 | TELEFONO | prefisso `+39`/`0039`, oppure cellulare `3\d{2}` più 6-7 cifre, oppure fisso `0\d{1,3}` più 6-8 cifre; separatori spazio, punto, trattino, slash | lunghezza complessiva 9-11 cifre; requisito di contesto se manca il prefisso internazionale |
| P2 | CATASTO | regex contestuale su `foglio`/`fg` più numero, seguito entro 40 caratteri da `particella`/`mappale` più numero, con `sub` opzionale | numerici entro intervalli plausibili |
| P2 | PRATICA | regex contestuale su `pratica`/`fascicolo`/`protocollo`/`riferimento` seguito dall'identificativo | l'identificativo contiene almeno una cifra |
| P3 | DATA | `DD/MM/YYYY`, `DD-MM-YYYY`, `DD.MM.YYYY`, `YYYY-MM-DD`, `D <mese italiano> YYYY` | parsing con `datetime`: la data deve esistere |
| P3 | IMPORTO | cifre con separatori europei accompagnate da `€`, `EUR` o `euro`, prima o dopo | separatore migliaia `.` e decimale `,` coerenti |
| P4 | PERSONA | spaCy `it_core_news_lg`, label `PER` | scarto stopword e token di una sola lettera |
| P4 | AZIENDA | spaCy label `ORG` più suffissi societari (`s.r.l.`, `s.p.a.`, `s.n.c.`, `s.a.s.`, `s.c.a.r.l.`) | presenza del suffisso oppure etichetta NER |
| P4 | INDIRIZZO | spaCy label `LOC` più regex sui toponimi (`via`, `viale`, `piazza`, `corso`, `largo`, `vicolo`, `strada`, `contrada`, `località`, `borgo`, `salita`, `lungomare`) con civico e CAP opzionali | toponimo presente; il CAP da solo non genera mai uno span |

**Requisito di contesto per P.IVA e telefono.** Una sequenza di 11 cifre nuda, o un
numero senza prefisso internazionale, viene taggata solo se compare il prefisso `IT`
oppure una parola chiave di contesto entro i 30 caratteri precedenti (`p. iva`,
`partita iva`, `p.i.`, `vat` per la P.IVA; `tel`, `telefono`, `cell`, `cellulare`,
`fax`, `mobile` per il telefono). Senza questo vincolo qualunque numero lungo del
documento verrebbe mascherato. Il costo è dichiarato tra i limiti noti.

## 7. Segnaposto, entità e ambiguità

**Formato:** `[TIPO_INDICE]`, corrispondente a `\[[A-Z]+_\d+\]`. I tipi sono i nomi
delle categorie: `[PERSONA_1]`, `[AZIENDA_1]`, `[INDIRIZZO_1]`, `[EMAIL_1]`,
`[TELEFONO_1]`, `[CF_1]`, `[PIVA_1]`, `[IBAN_1]`, `[DATA_1]`, `[IMPORTO_1]`,
`[PRATICA_1]`, `[CATASTO_1]`.

L'indice è incrementale per tipo e **globale al fascicolo**: la stessa entità usa lo
stesso segnaposto in tutti i documenti.

### Normalizzazione per il confronto

NFKC, casefold, collasso degli spazi, rimozione dei titoli (`sig.`, `sig.ra`, `dott.`,
`dott.ssa`, `avv.`, `ing.`, `arch.`, `geom.`, `rag.`, `prof.`, `on.`, `spett.le`). Per
le aziende, i suffissi societari vengono normalizzati e ignorati nel confronto.

### Regole di aggregazione

| Situazione | Comportamento |
|---|---|
| CF identico | fusione automatica |
| CF diversi, stesso nome | entità distinte, automaticamente, nessuna domanda |
| Stringa normalizzata identica, stesso documento | stessa entità. Assunzione dichiarata: dentro un singolo documento lo stesso nome indica la stessa persona |
| Stringa normalizzata identica, documenti diversi, nessun CF che discrimini | **ambiguità `SAME_NAME_NO_CF`** in coda: l'utente decide se unire o separare (TC-03) |
| Corrispondenza per euristica: token invertiti (`Rossi Mario` come `Mario Rossi`), iniziale compatibile (`M. Rossi` candidato di `Mario Rossi`) | **ambiguità `HEURISTIC_MERGE_SUGGESTION`**: suggerimento, mai automatico |

### Blocco dell'approvazione

Le ambiguità `SAME_NAME_NO_CF` non risolte **bloccano** l'approvazione: sono ambiguità
reali e la consegna chiede che l'utente decida. Le `HEURISTIC_MERGE_SUGGESTION` non
bloccano: ignorare un suggerimento significa mantenere le entità separate, che è il
default sicuro.

## 8. Macchina a stati e contratto di esportazione

```
DRAFT --(analisi completata)--> PENDING_REVIEW --(approvazione)--> APPROVED
                                      ^                                |
                                      +------(qualsiasi mutazione)------+
```

**Approvazione.** Rifiutata se esistono ambiguità bloccanti non risolte. Genera il testo
mascherato di ogni documento, calcola l'hash e lo salva in `approval_hash`.

**Serializzazione canonica per l'hash.** I documenti vengono ordinati per nome file e
per ognuno si emette `filename\n<lunghezza del testo mascherato>\n<testo mascherato>`;
lo SHA-256 si calcola sulla concatenazione UTF-8 del risultato. La lunghezza esplicita
rende la concatenazione non ambigua, così due fascicoli diversi non possono produrre lo
stesso digest.

**Contratto:** `export_sanitized_text(fascicolo_id: str) -> dict[str, str]`

Controlli, in ordine:

1. `fascicolo.state == APPROVED`, altrimenti `ExportNotAllowed`.
2. Ricalcolo dell'hash sul testo mascherato corrente e confronto con `approval_hash`;
   se differisce, `IntegrityError`.

**Payload:** esclusivamente `{nome_file: testo_mascherato}`. Nessun testo originale,
nessun dizionario, nessun metadato sensibile, nessuno span.

## 9. Masking

Le sostituzioni vengono applicate in ordine di `start` **decrescente**, così ogni
sostituzione non invalida gli offset di quelle ancora da applicare. È il motivo per cui
il masking può restare una funzione pura di due argomenti, senza ricalcolo continuo
degli offset.

`mask(text: str, spans: list[Span], entities: dict) -> str` non tocca né filesystem né
orologio né random.

## 10. Vault cifrato

**Struttura del file `.vault`:**

```
[MAGIC "CCV1"        4 byte]
[ITERAZIONI KDF      4 byte, uint32 big-endian]
[SALT               16 byte, casuale]
[NONCE              12 byte, casuale]
[CIPHERTEXT || TAG   n byte]
```

**Derivazione della chiave:** PBKDF2-HMAC-SHA256, 600.000 iterazioni, salt casuale di
16 byte, chiave di 32 byte.

**Cifratura:** AES-256-GCM. I primi 24 byte (magic, iterazioni, salt) sono passati come
**associated data**, così l'intestazione è autenticata e nessuno può abbassare il numero
di iterazioni di un file esistente senza far fallire la verifica.

Il tag non è un campo separato: `AESGCM.encrypt()` restituisce già `ciphertext || tag` e
`decrypt()` si aspetta lo stesso formato. L'intestazione con magic e numero di iterazioni
permette di cambiare i parametri KDF in futuro senza rendere illeggibili i vault
esistenti.

**Contenuto cifrato** (JSON, UTF-8): `vault_version`, `fascicolo_id`, `created_at`,
`documents`, `spans`, `entities`, `category_enabled`, `ambiguities`, `state`,
`approval_hash`. Cioè l'intero fascicolo, così riaprirlo consente sia di riprendere la
revisione sia di ripristinare una risposta dell'IA.

Fuori dal vault, il fascicolo vive **solo** nella RAM del processo.

## 11. Ripristino

1. **Associazione.** La risposta va associata al `fascicolo_id` attivo, o a quello
   caricato da un vault.
2. **Estrazione.** Tutti i token che corrispondono a `\[[A-Z]+_\d+\]`.
3. **Rilevamento delle alterazioni.** Una seconda regex più permissiva,
   `\[[A-Za-z]+[_\-\s]?\d*\]?`, individua i quasi-segnaposto che non hanno superato la
   prima: `[PERSONA_1` senza chiusura, `[PERSON_1]` con un tipo inesistente,
   `[persona_1]` in minuscolo. Ognuno viene segnalato letteralmente all'utente.
4. **Validazione.** Un segnaposto ben formato ma assente dal dizionario del fascicolo
   attivo produce l'errore "segnaposto non riconosciuto o appartenente a un'altra
   sessione" (TC-05).
5. **Sostituzione.** Solo se i passi 3 e 4 non hanno prodotto errori. Chiavi ordinate
   per lunghezza decrescente, così `[PERSONA_10]` viene sostituito prima di
   `[PERSONA_1]` e non resta uno `0` orfano.

**Nessun ripristino parziale, in nessun caso.** Un testo in cui l'utente non sa quali
segnaposto siano stati risolti e quali no è peggio di un errore.

## 12. Validazione documentale

### TXT

Decodifica UTF-8 *strict*. In caso di fallimento, errore esplicito con l'offset del byte
incriminato. Nessun fallback ad altre codifiche: una decodifica errata altera i
caratteri, i checksum di CF e IBAN smettono di tornare e i dati sensibili passano
inosservati in silenzio.

### PDF — verdetto scansione

Per ogni pagina, con `chars = len(page.get_text("text").strip())` e `img_ratio` uguale
all'area coperta dalle immagini diviso l'area della pagina:

| Condizione | Verdetto |
|---|---|
| `chars == 0` e la pagina ha immagini | **respinto** — immagine senza testo: è una scansione |
| `chars == 0` e nessuna immagine | accettato — pagina bianca, non contiene nulla da proteggere |
| `chars < 40` e `img_ratio > 0.5` | **respinto** — pagina prevalentemente raster con testo residuo |
| altrimenti | accettato |

Il rifiuto riguarda **l'intero file**, che non entra nel fascicolo, con un messaggio che
indica il numero di pagina. Nessuna elaborazione parziale.

Le due soglie (40 caratteri e 0.5 di area) stanno in un modulo di configurazione, così
sono ritoccabili e testabili.

Rispetto all'euristica di partenza (`chars < 40 AND immagini > 0`) questa versione chiude
un falso negativo — una scansione le cui immagini PyMuPDF non riporta viene comunque
bloccata perché senza testo — ed elimina un falso positivo, la pagina di copertina o di
firme con poco testo e un logo.

### Segnaposto preesistenti

Se il testo estratto contiene già una stringa nella forma `\[[A-Z]+_\d+\]`, l'utente
viene avvisato con la posizione: al ripristino quella stringa verrebbe interpretata come
un segnaposto e sostituita con dati veri, corrompendo il testo.

## 13. Gestione degli errori

| Situazione | Errore nel core | HTTP | Messaggio |
|---|---|---|---|
| TXT non UTF-8 | `InvalidEncoding` | 422 | codifica non valida, con l'offset del byte |
| PDF scansionato | `ScannedDocumentRejected` | 422 | documento bloccato, con il numero di pagina |
| Undicesimo documento | `FascicoloFull` | 422 | massimo 10 documenti per fascicolo |
| Export con stato diverso da `APPROVED` | `ExportNotAllowed` | **409** | il fascicolo non è approvato |
| Hash di approvazione non corrispondente | `IntegrityError` | 409 | il testo è cambiato dopo l'approvazione |
| Approvazione con ambiguità aperte | `UnresolvedAmbiguities` | 409 | elenco delle ambiguità da risolvere |
| Segnaposto estraneo al fascicolo | `UnknownPlaceholder` | 422 | elenco dei segnaposto non riconosciuti |
| Segnaposto alterato | `MalformedPlaceholder` | 422 | i frammenti anomali, citati letteralmente |
| Password del vault errata o file corrotto | `VaultUnreadable` | 422 | "password errata o file danneggiato" |

**Perché 409 e non 403.** Le specifiche di partenza indicavano 403 per l'export negato,
ma 403 significa "non hai il permesso", mentre qui la risorsa è nello stato sbagliato,
che è precisamente il significato di 409 Conflict. È uno scostamento consapevole e
reversibile in una riga.

**Perché il vault non distingue i due casi di errore.** La verifica del tag GCM fallisce
identicamente per password errata e per file manomesso. Distinguerli comunicherebbe a chi
ci prova che la password è l'unico ostacolo rimasto.

## 14. Strategia di test

Il test più importante della suite è generico e anti-fuga: **per ogni valore del
dizionario, quel valore non compare nel testo esportato.** Non verifica che il masking
abbia fatto la cosa giusta in un caso particolare, verifica che non ne abbia dimenticato
nessuno, e continuerà a valere quando verranno aggiunte categorie.

Intorno a quello:

- **I sei casi della matrice della consegna**, come test che portano quei nomi:
  - `TC-01` PDF con una pagina scansionata su cinque: rifiuto totale al caricamento
  - `TC-02` CF con CIN errato: ignorato dalla regola, resta al più un'entità NER
  - `TC-03` due documenti con lo stesso nome e nessun CF: ambiguità in coda, approvazione
    bloccata
  - `TC-04` export in stato `DRAFT`: `ExportNotAllowed`
  - `TC-05` risposta con `[PERSONA_99]` inesistente: ripristino interrotto
  - `TC-06` mutazione dopo l'approvazione: stato di nuovo `PENDING_REVIEW`, export negato
- **PDF di test generati con PyMuPDF**, non committati come binari: uno script costruisce
  il PDF di 5 pagine con 4 di testo e 1 immagine. Riproducibile e ispezionabile.
- **Validatori** con casi veri e falsi noti: CF con CIN corretto e sbagliato, CF con
  omocodia, P.IVA valide e non, IBAN con MOD-97 corretto e alterato.
- **Determinismo del masking**: due esecuzioni sullo stesso fascicolo producono lo stesso
  hash.
- **Invariante sugli span**: dopo `resolve()` nessuna coppia di span si sovrappone.
- **Test di architettura** sugli import di `core/` (invariante 1).
- **Round-trip del vault**: salva, ricarica, confronta; e ricarica con password errata.
- **Documenti di verifica distinti da quelli di sviluppo**, come chiede la consegna: due
  set separati, il secondo scritto dopo il completamento del motore.
- `tools/e2e_gemini.py` **fuori dalla suite**: richiede rete e API key, quindi marcato ed
  escluso di default.

Tutti i dati di test sono inventati.

## 15. Scostamenti dalle specifiche di partenza

1. Stato `DIRTY` eliminato: tre stati e una regola sola (§5).
2. Euristica di rifiuto delle scansioni riscritta, per chiudere un falso negativo e un
   falso positivo (§12).
3. Validazione P.IVA corretta: la formula di controllo della partita IVA italiana. Le
   specifiche parlavano di "Luhn modificato per l'omocode", che confonde due cose diverse:
   l'omocodia riguarda il codice fiscale, non la partita IVA. La regex del CF è stata
   estesa per accettare gli omocodici (§6).
4. IBAN generico validato con MOD-97 invece del solo formato italiano: il validatore è
   abbastanza forte da scartare i falsi positivi, e così si coprono anche gli IBAN esteri
   (§6).
5. Export negato mappato su 409 invece di 403 (§13).
6. Vault con intestazione versionata e autenticata; tag non separato perché AES-GCM lo
   concatena già al ciphertext (§10).
7. Il vault contiene l'intero fascicolo, non solo il dizionario, così una sessione può
   essere ripresa (§10).
8. Controllo dei segnaposto già presenti nei documenti caricati (§12).
9. Nessuna chiamata di rete nell'applicazione; l'integrazione con Gemini vive solo nello
   script di test (§2).
10. Package `cryptocustode` invece di `secure_llm_proxy`, per allinearlo al nome del repo.
11. Toggle per categoria su date e importi, oltre al controllo sul singolo span (§5).
12. Euristiche sui nomi italiani come suggerimenti da confermare: le specifiche
    affrontavano solo gli omonimi, non le varianti dello stesso nome, che nei contratti
    italiani sono il caso più frequente (§7).

## 16. Limiti noti

1. **Omografi e nomi comuni.** Nomi propri che coincidono con parole comuni ("Rosa",
   "Patti", "Marche") a inizio frase possono generare falsi positivi.
2. **Formati destrutturati.** Numeri di pratica e dati catastali privi delle parole chiave
   ("foglio", "mappale", "pratica") non vengono rilevati: restano al tagging manuale.
3. **P.IVA e telefoni senza contesto.** Una P.IVA nuda o un numero senza prefisso né
   parola chiave vicina non vengono rilevati, per non mascherare ogni numero lungo del
   documento.
4. **L'IA può storpiare i segnaposto.** `[PERSONA_1]` può tornare come `[PERSON_1]`.
   L'app lo intercetta e blocca il ripristino, ma non lo corregge automaticamente.
5. **Il ripristino non è byte-identico all'originale.** Tutte le varianti di un'entità
   ripristinano `canonical_value`. Non è un problema per il caso d'uso, perché ciò che si
   ripristina è la risposta dell'IA, un testo nuovo.
6. **Nessun OCR.** I PDF scansionati sono respinti, non elaborati. L'aggiunta dell'OCR
   richiederà prove dedicate.
7. **Qualità del NER.** `it_core_news_lg` è un modello generalista: nessuna garanzia di
   completezza sul riconoscimento dei dati personali. Lo strumento assiste la revisione
   umana, non la sostituisce.
8. **Nessuna coreferenza pronominale.** "il Conduttore", "la predetta", "egli" non vengono
   collegati alla persona a cui si riferiscono.
9. **Il vault protegge i dati a riposo, non la memoria.** Nessuna difesa contro un dump
   della RAM o la scrittura su file di swap da parte del sistema operativo.
10. **PDF cifrati o protetti da password** vengono trattati come non leggibili e respinti.

## 17. Fuori ambito

OCR, DOCX e altri formati, multi-utente, autenticazione, chiamate a LLM dentro
l'applicazione, packaging in eseguibile autonomo, interfaccia a riga di comando.
