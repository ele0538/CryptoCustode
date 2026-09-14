# CryptoCustode

Ti serve l'aiuto di un'IA su un documento che contiene dati personali, e quel
documento non puoi mandarlo com'è. CryptoCustode lo prepara: riconosce nomi,
indirizzi, codici fiscali, IBAN, importi e le altre categorie, li sostituisce con
segnaposto come `[PERSONA_1]`, e ti restituisce un testo che puoi incollare
dove vuoi. Quando la risposta torna indietro, rimette i dati veri al posto dei
segnaposto.

Gira sul tuo computer. L'unico momento in cui qualcosa esce è l'analisi, che
manda il testo a Gemini per farsi dire dove sono i dati personali.

## Come si usa

Due mestieri, due schermate.

**Nascondi i dati.** Carichi i documenti, l'analisi riconosce i dati personali,
tu decidi categoria per categoria — o singola occorrenza per singola occorrenza —
che cosa mascherare e che cosa lasciare in chiaro. Scarichi un file mascherato per
ogni documento, più il fascicolo cifrato `fascicolo.vault`.

**Rimetti i dati.** Carichi quello che l'IA ti ha restituito e i segnaposto
tornano a essere i dati veri. Se un segnaposto non è del tuo fascicolo o l'IA l'ha
storpiato, quel file si ferma e non restituisce niente: un testo ripristinato a
metà, in cui non sai quali dati siano veri e quali no, è peggio di un errore.

Si accettano TXT in UTF-8 e PDF con testo estraibile, dieci documenti per
fascicolo. I PDF scansionati vengono rifiutati per intero — senza testo non c'è
niente da mascherare.

## Requisiti

- Python 3.14 o successivo
- Una chiave API di Gemini, su un progetto **con fatturazione attiva** (vedi sotto)

## Installazione

```bash
git clone https://gitlab.trecuori.org/welfare/ai_service/CryptoCustode.git
cd CryptoCustode
python -m venv .venv
```

Attiva l'ambiente — `.venv\Scripts\activate` su Windows, `source .venv/bin/activate`
altrove — e installa le dipendenze:

```bash
pip install -r requirements.txt
```

## Avvio

```bash
python -m cryptocustode
```

È l'unico comando. Apre da solo una scheda del browser su
`http://127.0.0.1:8765/`. L'ascolto è sul solo loopback e non è configurabile:
un fascicolo contiene dati personali di terzi e l'applicazione non ha
autenticazione, quindi esporla in rete li offrirebbe a chiunque sia sulla stessa
rete.

Alla prima apertura la pagina ti chiede la chiave. Da lì in avanti basta la
passphrase con cui l'hai chiusa.

## La chiave di Gemini

La chiave si incolla nella pagina, che la salva **cifrata** in
`%APPDATA%\CryptoCustode\config.json` (su Windows) o
`~/.config/cryptocustode/config.json` altrove — mai nel repo, così chi clona il
progetto non eredita la chiave di nessuno. In chiaro vive solo in memoria,
finché il programma resta aperto.

In alternativa puoi passarla dall'ambiente, con `CRYPTOCUSTODE_GEMINI_API_KEY`.

**Il piano deve essere a pagamento.** Sul piano gratuito i termini di Gemini
dicono di non inviare dati personali, e Google usa i contenuti per sviluppare i
propri prodotti: CryptoCustode non manda altro che documenti con dati personali
dentro. L'applicazione ti chiede di dichiararlo prima di far partire la prima
analisi. Resta una dichiarazione e non una verifica — l'API non espone il piano
di fatturazione, quindi non c'è modo di controllarlo dal programma.

L'analisi è l'unica cosa che costa. La pagina ti mostra quanto, in base ai
prezzi che imposti tu.

## Il vault

**Senza `fascicolo.vault` non si ripristina più niente.**

Il fascicolo — i documenti, e soprattutto la tabella che dice che `[PERSONA_1]`
era Mario Rossi — vive nella memoria del programma finché resta aperto. Chiuso
il programma, quella tabella non esiste più da nessuna parte. Il vault è l'unico
modo di ritrovarla: è il fascicolo intero cifrato con AES-256-GCM, con la chiave
derivata dalla tua passphrase.

I file mascherati da soli non bastano a tornare indietro: sono testo con dentro
`[PERSONA_1]`, e senza la tabella quel segnaposto non è più nessuno.

Il vault si cifra con la stessa passphrase della chiave API. Il costo è reale:
chi cambia passphrase non riapre i vault vecchi. La pagina «Rimetti» accetta
anche una passphrase diversa da quella corrente, che è la via d'uscita.

## I test

```bash
pip install -r requirements-dev.txt
python -m pytest
```

## Com'è fatto

UI in HTML, CSS e JavaScript senza framework e senza web font: ogni host in più
è superficie in più di cui fidarsi senza motivo. Il server è FastAPI su uvicorn,
i PDF passano da PyMuPDF, la cifratura da `cryptography`.

Il codice è in italiano — nomi, commenti, messaggi d'errore. Le decisioni di
progetto e il perché stanno in `docs/`.
