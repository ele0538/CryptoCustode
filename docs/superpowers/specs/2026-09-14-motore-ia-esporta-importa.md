# Motore IA, Esporta e Importa — Design

**Data:** 2026-09-14
**Stato:** approvato in brainstorming, da tradurre in piani di implementazione
**Sostituisce:** le §6 (pipeline di riconoscimento), §7 (entità e ambiguità) e §11
(ripristino) di `2026-09-10-cryptocustode-design.md`, ed emenda le decisioni 2 e 6
della sua §2. Tutto il resto di quella spec — caricamento, vault, contratto di
esportazione, gestione degli errori — resta in vigore e va letto insieme a questa.

## 1. Scopo e ambito

Sostituire il motore di riconoscimento scritto a mano (regex, validatori, NER
statistico) con un modello linguistico, e chiudere il giro d'uso che la spec
precedente lasciava a metà: un pulsante **Esporta** che scarica il documento
mascherato come file, e un pulsante **Importa** che riceve indietro lo stesso file
modificato dall'utente e ne ricostruisce la versione in chiaro.

Il caso d'uso completo, nell'ordine in cui l'utente lo vive:

1. carica i documenti;
2. preme Esporta: l'app fa riconoscere i dati personali a Gemini, li sostituisce con
   tag, mostra cosa ha trovato, e su approvazione scarica un `.txt` mascherato;
3. apre quel file con un editor qualunque, riscrive il testo attorno ai tag, li
   sposta, ne cancella qualcuno — e nel frattempo può darlo a una qualunque IA di
   terze parti senza esporre dati personali;
4. preme Importa e ricarica il file: l'app ritrova la mappa, rimette i dati veri al
   loro posto e restituisce il documento finale in chiaro.

**Fuori ambito di questo documento:** OCR, formati diversi da TXT e PDF in ingresso e
da TXT in uscita, multiutenza, fornitori diversi da Gemini.

## 2. Decisioni chiuse

| # | Decisione | Motivo |
|---|---|---|
| D1 | Il rilevamento dei dati personali passa a un modello linguistico; `core/detect/` e la dipendenza spaCy vengono cancellati | Le regex coprono solo ciò che qualcuno ha previsto, e ogni forma nuova è una issue (#33, #34, #35, #37, #47 in tre giorni). Un modello generalizza sulle forme che nessuno ha scritto |
| D2 | **Contratto B.** Gemini restituisce l'elenco dei dati sensibili (`valore`, `categoria`); il testo mascherato lo costruisce l'app | Il modello non produce testo, quindi non può riscrivere il documento mentre lo maschera. La risposta è corta: niente troncamento sui documenti lunghi, latenza e costo bassi |
| D3 | Il ripristino è una sostituzione letterale deterministica; Gemini interviene **solo** quando i tag sono storpiati o sconosciuti, e la sua proposta viene mostrata all'utente prima di essere applicata | Con i tag integri la sostituzione è esatta e gratuita: passare comunque da un modello introdurrebbe un rischio di errore dove non ce n'era nessuno |
| D4 | Un solo fornitore: Gemini, modello `gemini-3.8-flash`, con structured output vincolato da JSON Schema | Nessuna astrazione da mantenere per un secondo fornitore che oggi non esiste. Lo schema imposto rende la risposta verificabile invece che interpretabile |
| D5 | All'esportazione l'app salva da sé un `.vault` cifrato e lo registra in un indice locale; all'importazione lo ritrova dal nome del file | Esporta e Importa sono separati da ore o giorni: senza persistenza automatica il file esportato diventa irrecuperabile alla chiusura dell'app |
| D6 | Il formato di scambio è testo semplice, in entrambi i versi | I tag devono sopravvivere alla modifica dell'utente: è la condizione su cui regge tutto il giro. Il testo semplice non li spezza, non li formatta e non li nasconde |
| D7 | Il gate di approvazione sopravvive, ma si sposta dal testo evidenziato alla **tabella dei tag** | Nessun controllo automatico può accorgersi di un dato che il modello non ha nominato. L'unico rimedio è che una persona guardi l'elenco prima che il file esca |
| D8 | La chiave API deve appartenere a un progetto con **fatturazione attiva**; senza, l'applicazione rifiuta di avviarsi | Sul piano gratuito i termini dicono letteralmente «Do not submit sensitive, confidential, or personal information to the Unpaid Services», Google usa i contenuti per sviluppare i propri prodotti e revisori umani possono leggerli. L'eccezione UE/CH/UK estende le protezioni del piano a pagamento anche al gratuito, ma è una nota regionale nei termini: la riservatezza del prodotto non ci si appoggia |

### Emendamenti alla spec del 2026-09-10

**La decisione 6 («nessuna chiamata di rete nell'applicazione») è ritirata.** Era la
promessa più forte del prodotto e va detto per intero cosa si perde: il documento
**in chiaro** esce dalla macchina a ogni esportazione. Il mascheramento non protegge
più da ogni IA, protegge da **tutte le IA tranne Gemini**, che diventa un fornitore
fidato con accesso completo. Il compromesso è consapevole: si baratta la garanzia
assoluta contro una qualità di riconoscimento che le regex non raggiungono, e lo si
paga verso un fornitore i cui termini a pagamento vietano l'addestramento sui dati e
limitano la conservazione al rilevamento degli abusi. D8 è ciò che rende vera la
seconda metà di questa frase.

**La decisione 2 («il testo estratto è immutabile») è emendata, non ritirata.** Resta
immutabile *dentro* l'applicazione, che è ciò che serve all'hash di approvazione. Ma
il file esportato è ora esplicitamente fatto per essere riscritto dall'utente, e il
documento che rientra non è più il documento che è uscito. La §11 dice cosa succede
quando quella riscrittura tocca i tag.

**La decisione 4 («tutte le categorie mascherate di default, incluse date e importi»)
è ribaltata.** Un fascicolo nuovo **non maschera niente**: tutte e dodici le
categorie partono spente, e l'utente accende quelle che gli servono.

La ragione è emersa alla prima prova su un documento vero, il 2026-09-14, e la
decisione è del proprietario del prodotto dopo averla vista all'opera. Con tutto
mascherato, un contratto di locazione perde il canone, la decorrenza e la scadenza:
il testo che l'utente consegna all'IA non dice più quanto si paga né quando. La
prudenza integrale non proteggeva di più — produceva un documento svuotato da
riaprire pezzo per pezzo, e chi conosce il documento preferisce partire da zero e
scegliere.

**Il rischio va scritto qui per intero, perché è l'unico posto dove viene deciso.**
Chi carica un documento, non tocca nessun interruttore e preme Esporta, esporta il
documento **in chiaro**. Nessun controllo automatico lo ferma, ed è il contrario di
quello che la decisione 4 originale garantiva. Restano due mitigazioni, entrambe
deboli e dichiarate tali: l'analisi mostra comunque ogni dato che ha trovato,
evidenziato e col suo segnaposto accanto, quindi l'utente *vede* cosa sta per
lasciar passare; e il gate di approvazione lo obbliga a premere un secondo pulsante
prima che il testo esca. Nessuna delle due sostituisce un default sicuro: la
sicurezza, in questo disegno, è responsabilità di chi usa lo strumento.

**L'invariante 4 della §4 («il dizionario non appare in nessuna risposta HTTP») è
emendato.** La tabella di revisione di D7 mostra all'utente, per ogni tag, il valore
reale che sostituisce: senza quella colonna non c'è niente da rivedere. Il dizionario
esce quindi sulla risposta di **revisione**, su loopback, verso l'utente proprietario
di quei dati. Resta vietato nel payload di **esportazione**, che è l'invariante che
contava: la §8 della spec precedente è intatta.

## 3. Stack

| Componente | Scelta | Note |
|---|---|---|
| Modello | `gemini-3.8-flash` | Flash di punta, stabile, con structured output vincolato da JSON Schema |
| Client | `google-genai` (SDK Python ufficiale) | Unica dipendenza nuova |
| Chiave | variabile d'ambiente `CRYPTOCUSTODE_GEMINI_API_KEY` | Mai nel repo, mai nel vault, mai in una risposta HTTP |
| Rimosso | `spacy`, `it_core_news_lg` | ~550 MB di modello, e il marcatore `lento` con loro |

Tutto il resto dello stack della §3 precedente resta: Python 3.14, PyMuPDF, FastAPI,
`cryptography`, pytest.

## 4. Architettura

`core/` resta puro. Il client HTTP **non** ci entra: vive in un package fratello.

```
cryptocustode/
├── ai/                        ← NUOVO: l'unico posto che parla con la rete
│   ├── gemini.py              # implementa core.rilevatore.Rilevatore
│   ├── prompt.py              # istruzioni e JSON Schema della risposta
│   └── soccorso.py            # la chiamata di ricollocazione dell'import (§11)
├── core/
│   ├── rilevatore.py          # NUOVO: il Protocol `Rilevatore` e `Rilevazione`
│   ├── tagga.py               # NUOVO: (testo, rilevazioni) -> mascherato + tag  [PURA]
│   ├── placeholders.py        # invariato: possiede la forma `[TIPO_N]`
│   ├── unmask.py              # invariato
│   ├── vault.py               # invariato
│   ├── indice.py              # NUOVO: quale vault appartiene a quale file
│   ├── models.py              # semplificato (§5)
│   ├── errors.py              # quattro errori in più (§12)
│   └── ingest/                # invariato: TXT e PDF entrano ancora da qui
├── state/session.py           # transizioni semplificate
├── api/
│   ├── routes_fascicolo.py    # caricamento e analisi
│   ├── routes_esporta.py      # NUOVO: revisione, approvazione, download
│   └── routes_importa.py      # NUOVO: ritrovamento vault, ripristino, consegna
└── ui/
```

### Invarianti

1. **`core/` non conosce HTTP, né lo stato di sessione, né il fornitore IA.** Il test
   di architettura esistente si estende: sotto `core/` non devono comparire import di
   `fastapi`, `uvicorn`, `state`, `httpx`, `requests`, `google` o `google.genai`. Il
   confine con l'IA è un `Protocol` dichiarato in `core/rilevatore.py`, e `ai/gemini.py`
   è la sua unica implementazione di produzione.
2. **`tagga.py` è deterministica.** Nessun filesystem, nessun orologio, nessun random:
   gli stessi argomenti danno lo stesso risultato, altrimenti l'hash di approvazione
   fallirebbe a caso. Il non determinismo del *modello* sta a monte e non entra qui —
   `tagga()` riceve una lista di valori, non un documento da interpretare.
3. **Solo `routes_esporta.py` fa uscire il testo mascherato come file.**
4. **La mappa tag→valore esce dal processo solo dentro il vault cifrato**, e verso
   l'utente solo sulla risposta di revisione (§2, emendamento).
5. **Nessun test della suite predefinita tocca la rete.** Il `Rilevatore` è sostituito
   da un doppio in memoria; la chiamata vera vive dietro il marcatore `rete`, che già
   esiste in `pyproject.toml`.

## 5. Modello dati

Le dodici categorie restano identiche a quelle della spec precedente — `PERSONA`,
`AZIENDA`, `INDIRIZZO`, `EMAIL`, `TELEFONO`, `CF`, `PIVA`, `IBAN`, `DATA`, `IMPORTO`,
`PRATICA`, `CATASTO` — e sono i valori ammessi dell'enum nello schema JSON della
risposta.

```python
@dataclass(frozen=True)
class Rilevazione:          # ciò che il modello dice di aver trovato
    valore: str
    categoria: Category

class StatoTag(str, Enum):
    APPLICATO = "APPLICATO"        # sostituito nel testo
    NON_TROVATO = "NON_TROVATO"    # il modello l'ha nominato, il testo non lo contiene
    DISATTIVATO = "DISATTIVATO"    # l'utente l'ha rimesso in chiaro

@dataclass(frozen=True)
class Tag:
    tag: str                # "[PERSONA_1]", da core/placeholders.py
    categoria: Category
    valore: str
    occorrenze: int         # totali nel fascicolo, per la tabella di revisione
    stato: StatoTag

@dataclass(frozen=True)
class Regione:
    start: int              # offset nel testo ORIGINALE
    end: int
    tag: str

@dataclass(frozen=True)
class Mascheratura:
    mascherato: str
    tags: list[Tag]
    regioni: list[Regione]  # le occorrenze rivendicate, in ordine di start

@dataclass
class Fascicolo:
    fascicolo_id: str
    documents: list[Document]          # invariato, massimo 10
    tags: dict[str, Tag]               # chiave: il tag. Sostituisce spans + entities
    category_enabled: dict[Category, bool]
    state: State                       # DRAFT | PENDING_REVIEW | APPROVED
    approval_hash: str | None
    counters: dict[Category, int]
```

**`Regione` non è uno `Span` risorto.** Uno `Span` era un'entità di dominio con
identità, interruttore e sorgente, che l'utente manipolava una per una e che il
modello produceva. Una `Regione` è il verbale di ciò che `tagga()` ha appena fatto al
testo: nasce dentro la funzione, non ha identità, nessuno la modifica, e il modello
non la vede mai. Serve a due cose concrete — dipingere il testo evidenziato nella UI
di revisione, e contare le occorrenze — e senza di lei quei due compiti andrebbero
rifatti cercando di nuovo le stringhe, con il rischio di trovare posizioni diverse da
quelle davvero sostituite.

**Cosa sparisce dal modello.** `Span` (il modello restituisce valori, non posizioni,
e le posizioni che restano le calcola l'app), `Entity` (un tag *è* l'entità: valore canonico e segnaposto in
un oggetto solo), `Ambiguity` e `AmbiguityKind` con tutto il sottosistema delle
ambiguità, `Source` (la sorgente è sempre il modello o l'utente, e la distinzione non
governa più niente), la tabella `PRIORITA` (non ci sono più categorie che si contendono
lo stesso testo per priorità: la contesa si risolve per lunghezza, §7).

**Perché l'ambiguità muore.** La coda esisteva perché due occorrenze dello stesso nome
potevano essere due persone diverse, e la spec precedente chiedeva all'utente di
decidere. Con il contratto B due occorrenze della stessa stringa sono lo stesso tag
**per costruzione**: `tagga()` cerca una stringa e sostituisce tutte le sue occorrenze.
Non c'è più un momento in cui l'applicazione possa porre la domanda, perché non c'è più
un momento in cui due entità distinte esistano. Diventa il limite noto 2 della §16, ed
è un peggioramento reale rispetto a prima: fra documenti diversi, l'omonimia era
intercettata e bloccante, adesso è silenziosa.

**Indici mai riciclati.** `counters` cresce e non torna indietro, come nella spec
precedente e per lo stesso motivo: un testo esportato ieri non deve contenere un tag
che oggi significa un'altra persona.

**Un solo tavolo di tag per fascicolo.** Le rilevazioni di tutti i documenti
confluiscono in un'unica tabella: lo stesso valore in due file riceve lo stesso tag.
È ciò che permette all'utente di dare all'IA di terze parti più documenti coerenti fra
loro.

## 6. Il contratto con Gemini

**Una chiamata per documento**, con `temperature = 0` e il response schema imposto:

```json
{
  "type": "array",
  "items": {
    "type": "object",
    "properties": {
      "valore":    { "type": "string" },
      "categoria": { "type": "string", "enum": ["PERSONA", "AZIENDA", "INDIRIZZO",
                     "EMAIL", "TELEFONO", "CF", "PIVA", "IBAN", "DATA", "IMPORTO",
                     "PRATICA", "CATASTO"] }
    },
    "required": ["valore", "categoria"],
    "propertyOrdering": ["valore", "categoria"]
  }
}
```

**La richiesta centrale del prompt**, ed è quella da cui dipende tutto il resto: ogni
`valore` deve essere una **sottostringa letterale del documento**, copiata carattere
per carattere come vi compare — non normalizzata, non corretta, non riordinata, senza
titoli aggiunti o tolti. Il prompt lo dice e lo motiva al modello, e la §7 dice cosa
succede quando il modello lo fa lo stesso.

`temperature = 0` riduce la varianza fra due chiamate ma non la elimina: il modello
resta non deterministico e la §16 lo dichiara. È il motivo per cui `tagga()` deve
essere pura — il non determinismo va confinato a monte del calcolo dell'hash.

**Il fallimento è sempre pulito.** Se la chiamata non torna, va in timeout, o torna
qualcosa che lo schema non accetta, il fascicolo resta esattamente com'era: niente
analisi parziale, niente tag a metà. L'utente riceve l'errore della §12 e riprova.

## 7. Tagging: da valori a testo mascherato

Due funzioni pure, e la divisione non è cosmetica: i tag sono **di fascicolo**, il
testo mascherato è **di documento**. Se una funzione sola facesse entrambe le cose,
lo stesso valore riceverebbe tag diversi in file diversi e il §5 («un solo tavolo di
tag per fascicolo») sarebbe falso.

```python
assegna_tag(rilevazioni: list[Rilevazione],
            tabella: dict[str, Tag],
            contatori: dict[Category, int]) -> tuple[dict[str, Tag], dict[Category, int]]

tagga(testo: str, tabella: dict[str, Tag]) -> Mascheratura
```

`assegna_tag` gira **una volta per fascicolo**, sulle rilevazioni di tutti i documenti
messe insieme; `tagga` gira una volta per documento, sulla tabella che ne è uscita.
Nessuna delle due tocca filesystem, orologio o random.

**`assegna_tag`, nell'ordine:**

1. **Deduplica** le rilevazioni sul valore esatto, e scarta quelle il cui valore è già
   nella tabella. Lo stesso valore nominato due volte dal modello, o già visto in un
   altro documento, è un tag solo.
2. **Assegna il tag** dal contatore della categoria, tramite `costruisci_segnaposto()`
   di `core/placeholders.py` — che resta l'unica fonte della forma, così ciò che il
   tagging scrive è esattamente ciò che `unmask.py` sa leggere. I valori nuovi vengono
   presi in ordine di lunghezza decrescente e, a parità, alfabetico: serve a rendere
   l'ordine **totale**, quindi la numerazione riproducibile e indipendente dall'ordine
   in cui il modello li ha elencati.

**`tagga`, nell'ordine:**

1. **Ordina i valori della tabella per lunghezza decrescente**, a parità alfabetico.
   L'ordinamento non è estetico ed è il cuore della correttezza: senza, `Rossi`
   verrebbe taggato dentro `Mario Rossi` e produrrebbe `Mario [PERSONA_2]` invece di
   `[PERSONA_1]`.
2. **Rivendica le occorrenze.** Per ogni valore, cerca tutte le occorrenze letterali
   nelle regioni di testo **non ancora rivendicate**. Un valore più corto non può
   rivendicare dentro una regione già presa da uno più lungo. La ricerca è **esatta**:
   sensibile a maiuscole, accenti, punteggiatura e spaziatura, senza alcuna
   normalizzazione. È la controparte del vincolo di letteralità imposto al modello
   nella §6, e ciò che rende vera l'identità della §8.
3. **Valori a zero occorrenze in questo documento**: nessuna sostituzione. Se il valore
   non compare in **nessun** documento del fascicolo, il suo stato è `NON_TROVATO` e il
   tag compare comunque nella tabella di revisione.
4. **Costruisce il testo mascherato** sostituendo le regioni rivendicate da destra a
   sinistra, così ogni sostituzione lascia validi gli offset di quelle ancora da
   applicare — la stessa ragione della §9 precedente.
5. **Restituisce anche le regioni**, ordinate per `start` crescente e riferite al
   testo **originale**. Sono ciò che permette alla UI di revisione di continuare a
   dipingere il testo evidenziato senza ricercare le stringhe una seconda volta, e
   quindi senza poter evidenziare un punto diverso da quello davvero sostituito.

**`NON_TROVATO` non è un caso d'angolo, è il modo in cui il modello sbaglia più
spesso.** Un modello che restituisce `Mario Rossi` per un documento che scrive
`ROSSI Mario`, o `via Roma 12` per `Via Roma, 12`, sta facendo la cosa che gli viene
più naturale: normalizzare. Se l'applicazione ignorasse quei valori, il dato resterebbe
in chiaro nel file esportato **e nessuno lo saprebbe**. Perciò quei valori diventano
righe visibili della tabella, con il valore che il modello ha proposto, perché
all'utente serve per andarlo a cercare a mano nel documento.

**Rivendicazione manuale.** Dalla tabella l'utente può aggiungere un valore che il
modello non ha nominato: lo digita o lo incolla, sceglie la categoria, e passa per lo
stesso `tagga()`. Non esiste una seconda strada per scrivere nel testo mascherato.

## 8. Le due garanzie

**Garanzia strutturale: il testo mascherato lo scrive l'applicazione.** Discende da D2
e non richiede alcun controllo, perché non c'è niente da controllare: Gemini non
produce testo, quindi non può riscrivere una frase, saltare un paragrafo o allucinare
una clausola. Il file che l'utente scarica è il documento che ha caricato, con delle
sottostringhe sostituite.

**Garanzia verificata: l'identità del round-trip.**

```
unmask(tagga(testo, tabella).mascherato, mappa) == testo
```

Vale per costruzione quando tutti i tag sono `APPLICATO`, si verifica in memoria, non
costa una chiamata, e diventa il test centrale della suite al posto dell'attuale test
anti-fuga. Se un giorno `tagga()` corrompesse un offset o `unmask()` cambiasse la forma
del segnaposto, questo test cade prima di chiunque altro.

Accanto resta, invariato nello spirito, il test anti-fuga della §14 precedente: **per
ogni tag `APPLICATO`, il suo valore non compare nel testo esportato.**

**Cosa nessuna delle due copre.** Un dato personale che Gemini non ha nominato non è
un errore rilevabile: non compare nella mappa, quindi non compare nel round-trip e non
compare nel test anti-fuga. Resta in chiaro nel file, e l'unica difesa è una persona
che legge la tabella. È il motivo per cui D7 tiene in vita il gate, ed è il limite noto
1 della §16.

## 9. Stato ed esportazione

La macchina a stati resta quella della §8 precedente:

```
DRAFT --(analisi completata)--> PENDING_REVIEW --(approvazione)--> APPROVED
                                      ^                                |
                                      +------(qualsiasi mutazione)------+
```

Mutazione significa: nuova analisi, tag disattivato o riattivato, tag aggiunto a mano,
interruttore di categoria. Ognuna riporta a `PENDING_REVIEW` e azzera `approval_hash`.
Non esistono più ambiguità bloccanti: l'approvazione è rifiutata solo se il fascicolo
non è in `PENDING_REVIEW`.

L'hash canonico di approvazione non cambia: documenti ordinati per nome file, ciascuno
emette `filename\n<lunghezza>\n<testo mascherato>`, SHA-256 sulla concatenazione UTF-8.

**La revisione** (`GET /revisione`) restituisce, per ogni documento, il testo
mascherato, e per il fascicolo la tabella dei tag con `tag · categoria · valore ·
occorrenze · stato`. È qui, e solo qui, che la mappa attraversa HTTP (§2, emendamento
all'invariante 4).

**L'esportazione** (`POST /esporta`) esegue i controlli della §8 precedente nello
stesso ordine — fascicolo risolto, stato `APPROVED`, hash ricalcolato e confrontato —
e poi, in un solo passo:

1. produce un file per documento, chiamato `<nome originale completo>.mascherato.txt`,
   UTF-8: `contratto.pdf` esce come `contratto.pdf.mascherato.txt`. Il suffisso si
   aggiunge al nome **intero**, estensione compresa, e non la sostituisce: così
   `contratto.pdf` e `contratto.txt` non collassano nello stesso file esportato, e il
   nome originale resta ricostruibile per intero togliendo il suffisso — che è ciò su
   cui si regge il ritrovamento del vault alla §11;
2. cifra l'intero fascicolo in un `.vault` (§10) con la password che l'utente
   fornisce in questo momento;
3. registra il fascicolo nell'indice (§10);
4. consegna i file al browser.

Se la scrittura del vault fallisce, **l'esportazione fallisce**: un file mascherato
senza la sua mappa è irrecuperabile, e consegnarlo comunque significherebbe consegnare
un documento che nessuno potrà più ricostruire.

**Payload del download:** solo il testo mascherato. Nessun valore reale, nessun
metadato, nessuna traccia della mappa.

## 10. Vault automatico e indice

Il formato del `.vault` non cambia: magic `CCV1`, iterazioni KDF, salt, nonce,
AES-256-GCM con l'intestazione come associated data, PBKDF2-HMAC-SHA256 a 600.000
iterazioni. Cambia solo chi decide quando scriverlo: prima l'utente, ora
l'esportazione.

**Dove.** Una cartella di lavoro fuori dal repo e fuori dalle cartelle sincronizzate,
`%LOCALAPPDATA%\CryptoCustode\vaults` su Windows, `~/.local/share/cryptocustode/vaults`
altrove, configurabile. Un file per fascicolo, il cui nome è il `fascicolo_id`.

**L'indice** è un `indice.json` nella stessa cartella, e contiene una riga per
fascicolo:

```json
{ "fascicolo_id": "...", "creato_il": "2026-09-14T10:12:00Z",
  "documenti": 3, "nomi_hash": ["<sha256 del nome file>", "..."] }
```

**Perché il nome del file sta lì come hash e non in chiaro.** Un nome di file è spesso
esso stesso un dato personale — `contratto_rossi_mario.txt` dice tutto quello che il
documento avrebbe dovuto nascondere — e l'indice è l'unico pezzo di questo sistema che
vive su disco non cifrato. L'hash serve la funzione che deve servire: ritrovare il
vault di un file il cui nome è noto, perché l'utente lo sta ricaricando in quel momento.
Non serve a elencare nomi, e infatti non li elenca. I nomi leggibili vivono **dentro**
il payload cifrato, e riappaiono solo dopo la password.

Restano in chiaro nell'indice la data e il numero di documenti, ed è dichiarato al
limite noto 6: chi legge quella cartella sa quando hai lavorato e su quanti file, non
su cosa.

## 11. Importazione e ripristino

`POST /importa` riceve il `.txt` modificato.

**Si importa un file per volta**, e si ricostruisce quel documento. Un fascicolo di
dieci file esportati si reimporta con dieci importazioni, ciascuna delle quali ritrova
lo stesso vault: la mappa è di fascicolo, quindi i tag continuano a significare la
stessa cosa in tutti e dieci.

**Passo 1 — trovare il fascicolo.** L'app toglie dal nome del file caricato il suffisso
`.mascherato.txt`, ottenendo il nome originale per intero (§9, passo 1), ne calcola lo
SHA-256 e lo cerca fra i `nomi_hash` dell'indice. Corrispondenza unica: quello è il
fascicolo. Nessuna corrispondenza — perché l'utente ha rinominato il file — o più d'una:
l'app mostra i candidati con data e numero di documenti, tutto ciò che sa senza
password, e fa scegliere. Non indovina mai in silenzio. Indice vuoto o nessun candidato
scelto: `VaultNotFound`, 404.

**Passo 2 — aprire il vault.** Password dell'utente, decifratura, mappa in mano. Le
diagnosi restano indistinguibili fra password errata e file manomesso, per la ragione
già scritta nella §13 precedente.

**Passo 3 — classificare ciò che l'utente ha fatto al testo.** Quattro casi, e solo
due sono anomalie:

| Caso | Significato | Trattamento |
|---|---|---|
| Tag ben formato e presente nella mappa | l'utente l'ha lasciato intatto, ovunque l'abbia spostato | sostituzione letterale |
| Tag **storpiato** (`[PERSONA_1`, `[persona_1]`, `[PERSONA 1]`) | l'editor o l'utente l'hanno rotto | **anomalia** |
| Tag ben formato ma **sconosciuto** (`[PERSONA_99]`) | non appartiene a questo fascicolo, o è uno storpiato che resta ben formato | **anomalia** |
| Valore della mappa il cui tag **non compare più** nel testo | l'utente ha cancellato quella frase | **non è un errore** |

Il rilevamento delle prime due riusa le due regex che `core/unmask.py` già possiede,
severa e permissiva, senza duplicarle.

Il quarto caso merita di essere chiamato per nome, perché la spec precedente non lo
prevedeva: **cancellare una frase è un uso legittimo del file esportato**, non un
guasto. L'app riferisce quali dati non compaiono nel documento finale e va avanti.

**Passo 4a — nessuna anomalia.** Sostituzione letterale, chiavi ordinate per lunghezza
decrescente, documento consegnato. Nessuna chiamata a Gemini, nessun costo, nessuna
attesa. È il percorso normale.

**Passo 4b — ci sono anomalie: il soccorso.** Gemini riceve il testo modificato, i
frammenti anomali così come compaiono, e l'elenco dei valori orfani con la loro
categoria. Deve restituire, con lo stesso vincolo di letteralità della §6:

```json
{ "type": "array",
  "items": { "type": "object",
    "properties": { "frammento": {"type": "string"}, "tag": {"type": "string"} },
    "required": ["frammento", "tag"] } }
```

cioè **quale tag della mappa corrisponde a quale frammento rotto**. Anche qui il
modello non scrive testo: propone un accoppiamento, e la sostituzione la fa l'app. Un
frammento che il modello non sa accoppiare resta non accoppiato, e non viene inventato.

**Passo 5 — l'utente vede la proposta.** Tabella `frammento → valore proposto`, una
riga per accoppiamento, ciascuna accettabile o rifiutabile. Solo dopo la conferma
l'app sostituisce.

**Passo 6 — nessun ripristino parziale.** La regola della §11 precedente resta e si
estende: se dopo la conferma restano frammenti anomali non risolti, il ripristino si
interrompe e l'app elenca quali. Un documento in cui l'utente non sa cosa è stato
ricostruito e cosa no è peggio di un errore.

## 12. Errori

Dei tredici casi della §13 precedente ne restano validi dodici: `UnresolvedAmbiguities`
sparisce con il sottosistema che lo generava (§5). Se ne aggiungono quattro:

| Situazione | Errore | HTTP | Messaggio |
|---|---|---|---|
| `CRYPTOCUSTODE_GEMINI_API_KEY` assente, o progetto senza fatturazione attiva | `AIKeyMissing` | **503** | come configurare la chiave e perché deve essere a pagamento (D8) |
| Gemini irraggiungibile, in timeout, o in errore di trasporto | `AIUnavailable` | **503** | servizio non raggiungibile, il fascicolo è intatto, riprova |
| Risposta che lo schema non accetta, o valori fuori dall'enum delle categorie | `AIResponseInvalid` | **502** | il modello ha risposto in un formato non valido, il fascicolo è intatto |
| Nessun vault corrisponde al file importato | `VaultNotFound` | **404** | nessun fascicolo per questo file, con i candidati se ce ne sono |

**Perché 503 per la chiave mancante e non 500.** Non è un difetto del server: è una
dipendenza non configurata, cioè un servizio temporaneamente non disponibile per una
ragione che l'utente può rimuovere. Il messaggio deve dire come.

**Perché 502 per la risposta fuori schema.** Il gateway a monte ha risposto male. È
distinto dal 503 perché la reazione dell'utente è diversa: sul 503 riprova, sul 502
riprova *e* se si ripete c'è qualcosa da segnalare.

**La chiave non compare mai in un messaggio d'errore**, nemmeno troncata.

## 13. Test

**Il test centrale** è l'identità della §8: per ogni documento di prova,
`unmask(tagga(...))` restituisce l'originale carattere per carattere. Accanto, il test
anti-fuga: per ogni tag applicato, il valore non compare nell'esportato.

**`tagga()` sotto property test**, sui casi che fanno male:

- un valore sottostringa di un altro (`Rossi` dentro `Mario Rossi`, `Rossi` dentro
  `Rossini`) — verifica l'ordinamento per lunghezza del passo 2;
- due valori della stessa lunghezza in ordine scambiato — verifica che l'output non
  dipenda dall'ordine di arrivo;
- un valore con zero occorrenze — stato `NON_TROVATO`, testo invariato, riga presente
  in tabella;
- un valore che compare venti volte — venti sostituzioni, un tag solo;
- valori sovrapposti (`Via Roma` e `Roma`) — il più lungo rivendica, il più corto
  prende solo il resto;
- determinismo: due esecuzioni identiche, hash identico;
- **stabilità fra documenti**: lo stesso valore in due documenti riceve lo stesso tag,
  e un valore già in tabella non ne consuma uno nuovo — è il test che tiene onesta la
  divisione fra `assegna_tag` e `tagga` (§7).

**Il `Rilevatore` è sempre un doppio** nella suite predefinita: una classe che
restituisce una lista fissata dal test. Gli unici test che chiamano Gemini davvero
stanno dietro il marcatore `rete` ed escono dalla suite di default.

**I casi della matrice di consegna**, aggiornati:

- `TC-01` PDF con una pagina scansionata su cinque: rifiuto totale — **invariato**
- `TC-02` CF con CIN errato: **ritirato**, non esistono più validatori
- `TC-03` omonimia fra documenti: **ritirato**, non esiste più la coda delle ambiguità
- `TC-04` export in stato `DRAFT`: `ExportNotAllowed` — **invariato**
- `TC-05` testo importato con `[PERSONA_99]` sconosciuto: anomalia, soccorso, e se
  non si risolve il ripristino si interrompe — **adattato**
- `TC-06` mutazione dopo l'approvazione: stato di nuovo `PENDING_REVIEW`, export negato
  — **invariato**
- `TC-07` **nuovo**: il modello restituisce un valore che nel testo non c'è alla
  lettera → riga `NON_TROVATO`, testo invariato, nessun errore
- `TC-08` **nuovo**: il modello risponde fuori schema → `AIResponseInvalid`, fascicolo
  intatto
- `TC-09` **nuovo**: l'utente cancella una frase con dentro un tag → ripristino
  regolare, con l'avviso di quale dato non compare nel documento finale

**Round-trip completo di fase 3**: carica, esporta, modifica il testo fuori dai tag,
reimporta, ottieni l'originale. È il test che dimostra il prodotto.

**Test di architettura** esteso all'invariante 1 nella sua nuova forma.

Tutti i dati di test restano inventati.

## 14. Fasi

Il lavoro non entra in un piano solo. Tre fasi, ciascuna con un piano proprio e
ciascuna che consegna qualcosa di funzionante:

**Fase 1 — il motore.** `core/rilevatore.py`, `core/tagga.py`, `ai/gemini.py`,
`ai/prompt.py`; `models.py` semplificato; cancellazione di `core/detect/`,
`core/spans.py`, `core/entities.py`, di spaCy e dei sei file di test relativi; suite
riscritta; test di architettura esteso. A fine fase l'analisi fa ciò che faceva prima,
ma la fa Gemini, e la UI non è cambiata.

**Fase 2 — Esporta.** Tabella di revisione al posto dell'evidenziazione a span,
aggiunta e disattivazione manuale dei tag, approvazione, download dei `.txt`, vault
automatico, `core/indice.py`. A fine fase il giro di andata è completo.

**Fase 3 — Importa.** Ritrovamento del vault, classificazione delle anomalie,
ripristino deterministico, soccorso IA con conferma dell'utente, consegna del
documento finale. Chiude l'issue #8.

## 15. Cosa viene cancellato

| File | Righe |
|---|---|
| `core/detect/patterns.py` | 606 |
| `core/detect/rules.py` | 305 |
| `core/detect/ner.py` | 225 |
| `core/detect/validators.py` | 124 |
| `core/entities.py` | 296 |
| `core/spans.py` | 41 |

Più i test `test_patterns`, `test_rules`, `test_ner`, `test_validators`, `test_spans`,
`test_entities`, la dipendenza `spacy`, il modello `it_core_news_lg` da ~550 MB, il
marcatore `lento` in `pyproject.toml` e la nota sul parallelismo in `requirements.txt`.

Circa 1.600 righe di produzione, e con loro il debito che le issue #33, #34, #35, #37
e #47 stavano pagando a rate.

**L'issue #47** (CAP posposto dopo il comune) riguarda una regex di `patterns.py`: va
chiusa in fase 1 con il motivo, non corretta.

## 16. Limiti noti

1. **Un dato che il modello non nomina resta in chiaro**, e nessun controllo automatico
   può accorgersene. L'unica difesa è il gate di revisione (D7). È il limite più grave
   del disegno e non è eliminabile.
2. **Omonimi indistinguibili, anche fra documenti.** Lo stesso valore è lo stesso tag
   per costruzione. Peggioramento reale rispetto alla spec precedente, dove l'omonimia
   fra documenti apriva una coda bloccante.
3. **Il documento in chiaro esce dalla macchina** a ogni esportazione, verso Gemini
   (§2, emendamento alla decisione 6).
4. **Il rilevamento non è deterministico.** Due analisi dello stesso documento possono
   produrre tag diversi. L'hash di approvazione resta valido *dentro* una revisione —
   che è ciò che gli serve — ma non lega due analisi distinte.
5. **Costo e latenza per documento**, proporzionali alla lunghezza del testo, su un
   fascicolo fino a dieci file.
6. **L'indice espone data e numero di documenti** in chiaro su disco. I nomi dei file
   no, sono hash (§10).
7. **Impaginazione persa**: un PDF entra e ne esce testo semplice.
8. **Nessun OCR**: i PDF scansionati restano respinti.
9. **Tag preesistenti nel testo caricato**: l'avviso della §12 precedente resta
   necessario, e ora anche più importante, perché al ripristino quella stringa
   diventerebbe un dato vero.
10. **Il soccorso dell'import può proporre l'accoppiamento sbagliato.** L'utente lo
    vede e può rifiutarlo, ma su un documento lungo con molte anomalie la conferma
    rischia di diventare un riflesso.
11. **Il vault protegge i dati a riposo, non la memoria**: invariato dalla spec
    precedente.

## 17. Fuori ambito

OCR, DOCX e altri formati, fornitori diversi da Gemini, esecuzione locale del modello,
multiutente, autenticazione, packaging in eseguibile autonomo, interfaccia a riga di
comando, ricostruzione dell'impaginazione del PDF.
