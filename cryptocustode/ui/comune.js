// Quello che tutte e tre le pagine fanno allo stesso modo.
//
// Dal 2026-09-14 la UI non è più una pagina sola: l'ingresso (`home.html`)
// sceglie fra i due mestieri, `nascondi.html` maschera e `rimetti.html`
// ripristina. Sono tre documenti separati perché sono tre programmi separati —
// non condividono stato, e un guasto nell'uno non deve poter spegnere l'altro.
//
// Quello che invece condividono è il modo di parlare col server e il modo di
// dire all'utente che qualcosa non ha funzionato. Tenerlo in un file solo non
// è economia di righe: è che tre copie di `messaggioDiErrore` divergono, e la
// copia che diverge è quella che un giorno mostrerà «errore 422» al posto del
// messaggio del dominio.
//
// Niente moduli ES: i file si caricano come `<script>` e si parlano attraverso
// `window.cc`. È la stessa scelta che `app.js` e `config.js` avevano già fatto,
// e cambiarla adesso vorrebbe dire riscrivere anche l'harness dei test.

window.cc = (() => {
  // Tre forme possibili per un rifiuto, e la terza è quella che faceva danni:
  // `errore` è la tabella della spec §13; `detail` è la validazione di FastAPI,
  // che si incontra per esempio con una richiesta senza la parte `file`; e un
  // 500 non gestito arriva come testo, senza alcun corpo JSON.
  function messaggioDiErrore(esito, stato) {
    if (esito && typeof esito.errore === "string") {
      return esito.errore;
    }
    if (esito && typeof esito.detail === "string") {
      return esito.detail;
    }
    if (esito && esito.detail) {
      return "richiesta non valida";
    }
    return `errore ${stato}: l'applicazione non ha spiegato perché`;
  }

  const NON_RISPONDE = "L'applicazione non risponde: è ancora avviata?";

  async function corpoJson(risposta) {
    // Fuori da un `try` questa riga uccideva il ciclo dei caricamenti: su una
    // risposta senza corpo JSON la promessa veniva rigettata, i file successivi
    // non venivano nemmeno tentati, e l'unica traccia restava in una console
    // che l'utente non guarda.
    try {
      return await risposta.json();
    } catch (errore) {
      return null;
    }
  }

  // Restituisce sempre la stessa forma — `{ok, dati, errore}` — invece di
  // `null` in caso di guasto. `null` costringeva ogni chiamante a sapere *dove*
  // scrivere il motivo, e il motivo finiva scritto nel riquadro sbagliato: un
  // errore del vault che compariva sotto l'analisi manda l'utente a cercare il
  // guasto nel posto in cui non è successo niente.
  async function chiedi(rotta, corpo, metodo = "POST") {
    const opzioni = { method: metodo };
    if (corpo !== undefined) {
      opzioni.headers = { "Content-Type": "application/json" };
      opzioni.body = JSON.stringify(corpo);
    }

    let risposta;
    try {
      risposta = await fetch(rotta, opzioni);
    } catch (errore) {
      // L'app è locale: se la fetch non arriva, il server è stato chiuso.
      return { ok: false, dati: null, errore: NON_RISPONDE };
    }

    const esito = await corpoJson(risposta);
    if (!risposta.ok) {
      return { ok: false, dati: esito, errore: messaggioDiErrore(esito, risposta.status) };
    }
    return { ok: true, dati: esito, errore: null };
  }

  // La stessa cosa per le richieste che mandano un file: `FormData` non vuole
  // l'intestazione JSON, e metterla fa fallire il parsing multipart.
  async function manda(rotta, corpo) {
    let risposta;
    try {
      risposta = await fetch(rotta, { method: "POST", body: corpo });
    } catch (errore) {
      return { ok: false, dati: null, errore: NON_RISPONDE };
    }
    const esito = await corpoJson(risposta);
    if (!risposta.ok) {
      return { ok: false, dati: esito, errore: messaggioDiErrore(esito, risposta.status) };
    }
    return { ok: true, dati: esito, errore: null };
  }

  // Il blob non passa mai da un file scritto dal server: arriva nella risposta
  // e il browser lo salva. È la spec §10 — fuori dal vault il fascicolo vive
  // solo nella RAM del processo — e vale anche per il momento in cui esce.
  function scarica(contenuto, nome, tipo = "text/plain;charset=utf-8") {
    const blob = contenuto instanceof Blob ? contenuto : new Blob([contenuto], { type: tipo });
    const indirizzo = URL.createObjectURL(blob);
    const collegamento = document.createElement("a");
    collegamento.href = indirizzo;
    collegamento.download = nome;
    document.body.appendChild(collegamento);
    collegamento.click();
    collegamento.remove();
    // Senza `revokeObjectURL` il contenuto resta nella memoria della scheda
    // finché non la si chiude: memoria trattenuta per niente a ogni download.
    URL.revokeObjectURL(indirizzo);
  }

  // Il nome del file mascherato si costruisce qui e non in tre posti: deve
  // essere riconoscibile accanto all'originale nella cartella Download, e deve
  // restare `.txt` anche quando l'originale era un PDF — quello che esce è
  // testo, e dargli l'estensione di prima farebbe aprire un lettore di PDF su
  // un file che PDF non è.
  function nomeMascherato(originale) {
    const senzaEstensione = originale.replace(/\.[^.]+$/, "");
    return `${senzaEstensione}-mascherato.txt`;
  }

  function nomeRipristinato(originale) {
    const senzaEstensione = originale.replace(/\.[^.]+$/, "").replace(/-mascherato$/, "");
    return `${senzaEstensione}-ripristinato.txt`;
  }

  function plurale(quanti, singolare, plurale) {
    return quanti === 1 ? singolare : plurale;
  }

  return {
    messaggioDiErrore,
    chiedi,
    manda,
    scarica,
    nomeMascherato,
    nomeRipristinato,
    plurale,
    NON_RISPONDE,
  };
})();
