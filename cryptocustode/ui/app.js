// Caricamento dei documenti dalla UI (issue #3).
//
// Un file per richiesta, in sequenza. La ragione è che ogni rifiuto è uno stato
// HTTP con un messaggio (spec §13): con dieci file in una richiesta sola
// l'esito sarebbe misto e un solo stato non potrebbe dirlo. Così ogni file ha
// il suo verdetto, e l'utente vede quale è entrato e quale no.
//
// Qui non si maschera niente e non si mostra alcuna anteprima del mascherato:
// l'invariante 3 della spec §4 vuole che il testo mascherato esca solo dal gate
// di esportazione. L'estratto che si vede è il testo originale del documento,
// che la §4 autorizza esplicitamente a servire in revisione.

const ROTTA = "/api/fascicolo/documenti";
const AVVISI_MOSTRATI = 5;
const CARATTERI_DI_ESTRATTO = 140;

const modulo = document.getElementById("modulo-caricamento");
const scelta = document.getElementById("scelta-file");
const esiti = document.getElementById("esiti");
const conteggio = document.getElementById("conteggio");
const card = document.getElementById("card-caricamento");
const fileScelti = document.getElementById("file-scelti");
const svuota = document.getElementById("svuota-fascicolo");

// Le quattro cifre grandi della scheda del fascicolo. I documenti li dice il
// server a ogni risposta (è lui a sapere quanti sono); pagine, caratteri e
// avvisi si accumulano qui, perché il payload parla di un documento alla volta.
const metriche = {
  documenti: document.getElementById("metrica-documenti"),
  tetto: document.getElementById("metrica-tetto"),
  pagine: document.getElementById("metrica-pagine"),
  caratteri: document.getElementById("metrica-caratteri"),
  avvisi: document.getElementById("metrica-avvisi"),
};
// Niente accumulatore qui: i totali arrivano dal server a ogni risposta.
// Sommarli nella pagina era la metà della #50 che sopravviveva anche al
// ridisegno — un accumulatore non scende mai, quindi dopo lo svuotamento del
// fascicolo avrebbe continuato a dichiarare i caratteri di documenti che non
// ci sono più.

function aggiungi(classe, testo, dettaglio) {
  const riga = document.createElement("li");
  riga.className = classe;
  riga.textContent = testo;
  if (dettaglio) {
    const secondaRiga = document.createElement("p");
    secondaRiga.className = "estratto";
    secondaRiga.textContent = dettaglio;
    riga.appendChild(secondaRiga);
  }
  esiti.appendChild(riga);
}

// Tre forme possibili per un rifiuto, e la terza è quella che faceva danni:
// `errore` è la tabella della spec §13; `detail` è la validazione di FastAPI,
// che si incontra per esempio con una richiesta senza la parte `file`; e un 500
// non gestito arriva come testo, senza alcun corpo JSON.
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

function estrattoDi(testo) {
  const unaRiga = (testo || "").replace(/\s+/g, " ").trim();
  if (unaRiga === "") {
    return "nessun testo estratto: controlla il file";
  }
  if (unaRiga.length <= CARATTERI_DI_ESTRATTO) {
    return unaRiga;
  }
  return unaRiga.slice(0, CARATTERI_DI_ESTRATTO) + "…";
}

function mostraAvvisi(nome, segnaposto) {
  for (const avviso of segnaposto.slice(0, AVVISI_MOSTRATI)) {
    aggiungi(
      "avviso",
      `${nome} — attenzione: il testo contiene già ${avviso.segnaposto} alla ` +
        `posizione ${avviso.posizione}. Al ripristino verrebbe confuso con un ` +
        `segnaposto nostro e sostituito con dati veri: controllalo prima di approvare.`
    );
  }
  const restanti = segnaposto.length - AVVISI_MOSTRATI;
  if (restanti > 0) {
    aggiungi("avviso", `${nome} — e altri ${restanti} segnaposto già presenti nel testo.`);
  }
}

function aggiornaMetriche(totali) {
  metriche.documenti.textContent = String(totali.documenti);
  metriche.tetto.textContent = `/ ${totali.massimo_documenti}`;
  metriche.pagine.textContent = String(totali.pagine);
  metriche.caratteri.textContent = String(totali.caratteri);
  metriche.avvisi.textContent = String(totali.avvisi);
  conteggio.textContent =
    totali.documenti === 0
      ? "Nessun documento nel fascicolo."
      : `Documenti nel fascicolo: ${totali.documenti} di ${totali.massimo_documenti}.`;
  svuota.hidden = totali.documenti === 0;
}

function descriviScelta(files) {
  const quanti = files.length;
  if (quanti === 0) {
    return "Nessun file scelto";
  }
  return quanti === 1 ? "1 file scelto" : `${quanti} file scelti`;
}

async function carica(file) {
  const corpo = new FormData();
  corpo.append("file", file);

  let risposta;
  try {
    risposta = await fetch(ROTTA, { method: "POST", body: corpo });
  } catch (errore) {
    // L'app è locale: se la fetch non arriva, il server è stato chiuso.
    aggiungi("rifiutato", `${file.name} — l'applicazione non risponde: è ancora avviata?`);
    return;
  }

  // Fuori dal `try` questa riga uccideva il ciclo: su una risposta senza corpo
  // JSON la promessa veniva rigettata, i file successivi non venivano nemmeno
  // tentati, e l'unica traccia restava in una console che l'utente non guarda.
  let esito = null;
  try {
    esito = await risposta.json();
  } catch (errore) {
    esito = null;
  }

  if (!risposta.ok) {
    aggiungi("rifiutato", `${file.name} — ${messaggioDiErrore(esito, risposta.status)}`);
    return;
  }

  aggiungi(
    "caricato",
    `${file.name} — caricato: ${esito.caratteri} caratteri, ` +
      `${esito.pagine} ${esito.pagine === 1 ? "pagina" : "pagine"}`,
    estrattoDi(esito.testo)
  );
  mostraAvvisi(file.name, esito.segnaposto_preesistenti);
  aggiornaMetriche(esito.totali);
}

// La stessa strada per il modulo e per il trascinamento: un file per richiesta,
// in ordine, così ogni file ha il suo verdetto.
async function caricaTutti(files) {
  const scelti = Array.from(files);
  if (scelti.length === 0) {
    aggiungi("avviso", "Nessun file scelto.");
    return;
  }
  for (const file of scelti) {
    await carica(file);
  }
}

// L'input dei file è nascosto dietro un pulsante a pillola, quindi il browser
// non mostra più da sé i nomi scelti: lo dice questa riga.
scelta.addEventListener("change", () => {
  fileScelti.textContent = descriviScelta(scelta.files);
});

modulo.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  await caricaTutti(scelta.files);
  scelta.value = "";
  fileScelti.textContent = descriviScelta([]);
});

card.addEventListener("dragover", (evento) => {
  evento.preventDefault();
  card.classList.add("trascinando");
});

card.addEventListener("dragleave", () => {
  card.classList.remove("trascinando");
});

card.addEventListener("drop", async (evento) => {
  evento.preventDefault();
  card.classList.remove("trascinando");
  await caricaTutti(evento.dataTransfer.files);
});

// --- Revisione: testo evidenziato e interruttori (issue #4) -----------------
//
// Il testo arriva dal server **già spezzato in segmenti** sulle regioni che
// la mascheratura rivendica, e qui non si fa aritmetica su nessun offset:
// tagliare da questa parte significherebbe tenere una seconda copia di quel
// calcolo, che diverge alla prima differenza fra il modo in cui Python e
// JavaScript contano i caratteri.
//
// Il testo non è modificabile in nessun punto, ed è la decisione 2 della spec
// §2: l'utente agisce solo sui tag. Ogni segmento è un nodo di solo testo,
// scritto con `textContent` e senza alcun attributo di modifica; gli unici
// campi della pagina sono la scelta dei file e le caselle di spunta degli
// interruttori.

const ROTTA_ANALISI = "/api/fascicolo/analisi";
const ROTTA_CATEGORIA = "/api/fascicolo/categoria";
const ROTTA_TAG = "/api/fascicolo/tag";

const avvio = document.getElementById("avvia-analisi");
const statoAnalisi = document.getElementById("stato-analisi");
const categorie = document.getElementById("categorie");
const documenti = document.getElementById("documenti");

// Le tre richieste della revisione hanno lo stesso corpo di errore del
// caricamento — `errore` della tabella §13, `detail` di FastAPI, o niente —
// quindi riusano `messaggioDiErrore`. Restituisce `null` quando la richiesta
// non è andata: chi chiama non ridisegna, e il motivo resta scritto in pagina
// invece di sparire in una console che l'utente non guarda.
async function chiedi(rotta, corpo) {
  const opzioni = { method: "POST" };
  if (corpo !== undefined) {
    opzioni.headers = { "Content-Type": "application/json" };
    opzioni.body = JSON.stringify(corpo);
  }

  let risposta;
  try {
    risposta = await fetch(rotta, opzioni);
  } catch (errore) {
    statoAnalisi.textContent = "L'applicazione non risponde: è ancora avviata?";
    return null;
  }

  let esito = null;
  try {
    esito = await risposta.json();
  } catch (errore) {
    esito = null;
  }

  if (!risposta.ok) {
    statoAnalisi.textContent = messaggioDiErrore(esito, risposta.status);
    return null;
  }
  return esito;
}

// Quante categorie sono accese adesso. Serve all'avviso prima dell'export, e
// si legge dall'ultimo payload servito invece di contare le caselle disegnate:
// le caselle sono il riflesso dello stato, non lo stato.
let categorieAccese = 0;

function disegnaInterruttori(elenco) {
  categorieAccese = elenco.filter((voce) => voce.attiva).length;
  categorie.replaceChildren();
  for (const voce of elenco) {
    const etichetta = document.createElement("label");
    etichetta.className = "interruttore";

    const casella = document.createElement("input");
    casella.type = "checkbox";
    casella.checked = voce.attiva;
    casella.dataset.categoria = voce.categoria;
    etichetta.appendChild(casella);

    const nome = document.createElement("span");
    nome.className = `pastiglia cat-${voce.categoria}`;
    nome.textContent = `${voce.categoria} (${voce.quanti})`;
    etichetta.appendChild(nome);

    categorie.appendChild(etichetta);
  }
}

function disegnaDocumenti(elenco) {
  documenti.replaceChildren();
  for (const documento of elenco) {
    const riquadro = document.createElement("article");
    riquadro.className = "documento";

    const titolo = document.createElement("h3");
    titolo.textContent = documento.filename;
    titolo.dataset.filename = documento.filename;
    riquadro.appendChild(titolo);

    const corpo = document.createElement("p");
    corpo.className = "testo-originale";
    for (const segmento of documento.segmenti) {
      // Il tag HTML è scelto fra due letterali e non costruito: `mark` porta
      // l'evidenziazione anche a chi non distingue i colori, e restare su due
      // nomi scritti per esteso è ciò che rende verificabile che questa pagina
      // non costruisca mai un elemento modificabile.
      if (segmento.tag === null) {
        const pezzo = document.createElement("span");
        pezzo.textContent = segmento.testo;
        corpo.appendChild(pezzo);
        continue;
      }
      const pezzo = document.createElement("mark");
      pezzo.textContent = segmento.testo;
      pezzo.className =
        `evidenza cat-${segmento.categoria}` + (segmento.mascherato ? "" : " spenta");
      pezzo.dataset.tag = segmento.tag;
      pezzo.dataset.categoria = segmento.categoria;
      pezzo.dataset.mascherato = segmento.mascherato ? "1" : "0";
      pezzo.title = segmento.mascherato
        ? `${segmento.categoria}: diventerà ${segmento.segnaposto}. Clicca per lasciarlo in chiaro.`
        : `${segmento.categoria}: resterà in chiaro. Clicca per mascherarlo.`;
      corpo.appendChild(pezzo);
    }
    riquadro.appendChild(corpo);

    documenti.appendChild(riquadro);
  }
}

// Ogni toggle ridisegna la pagina dal payload che il server restituisce, invece
// di ritoccare il nodo che è stato cliccato. Ritoccarlo significherebbe tenere
// nella pagina una seconda copia dello stato del fascicolo, e quella che
// l'utente vede sarebbe la copia che non decide che cosa viene mascherato.
function disegna(revisione) {
  if (revisione === null) {
    return;
  }
  statoAnalisi.textContent = `Stato del fascicolo: ${revisione.stato}.`;
  disegnaInterruttori(revisione.categorie);
  disegnaDocumenti(revisione.documenti);
}

avvio.addEventListener("click", async () => {
  statoAnalisi.textContent = "Analisi in corso…";
  disegna(await chiedi(ROTTA_ANALISI));
  // L'analisi è l'unico momento in cui si spende: il riquadro della spesa si
  // aggiorna qui e non a intervalli, così il numero cambia quando l'utente sta
  // guardando il motivo per cui è cambiato. `config.js` espone l'aggancio sulla
  // finestra perché i due file sono due `<script>`, non due moduli.
  if (typeof window.aggiornaSpesa === "function") {
    await window.aggiornaSpesa();
  }
});

// Un gestore solo sul contenitore, e non uno per interruttore: gli
// interruttori vengono ricreati a ogni ridisegno, quindi agganciarli
// singolarmente lascerebbe i gestori attaccati a nodi che non sono più in
// pagina, e dal secondo toggle in poi non succederebbe più niente.
categorie.addEventListener("change", async (evento) => {
  const categoria = evento.target.dataset.categoria;
  if (categoria === undefined) {
    return;
  }
  disegna(await chiedi(ROTTA_CATEGORIA, { categoria, attiva: evento.target.checked }));
});

documenti.addEventListener("click", async (evento) => {
  const tag = evento.target.dataset.tag;
  if (tag === undefined) {
    return;
  }
  // Il verso si legge da ciò che è disegnato: cliccare su un'occorrenza accesa
  // la spegne. Tenerlo in una variabile del JavaScript lo farebbe divergere
  // dal fascicolo appena due schede — o due ridisegni — non coincidessero.
  const attivo = evento.target.dataset.mascherato !== "1";
  disegna(await chiedi(ROTTA_TAG, { tag, attivo }));
});


// --- Lo stato al primo disegno e dopo il refresh (issue #50) ----------------
//
// La pagina nasceva sempre vuota e non aveva modo di sapere che il server
// teneva ancora il fascicolo: da lì i tre sintomi della #50 — la scheda a zero
// dopo un F5, il file ricaricato rifiutato come duplicato «anche se non c'era
// più niente», e i documenti vecchi che riaffioravano in revisione al primo
// «Analizza». Non erano tre bug, era la pagina che non chiedeva mai.
//
// Si chiede una volta sola, all'avvio, e poi si riusa la stessa risposta che
// ogni rotta restituisce: la regola resta quella già scelta per i toggle — la
// pagina disegna ciò che il server dice di avere, e non tiene una seconda
// copia dello stato.

const ROTTA_STATO = "/api/fascicolo";

function ridisegnaTutto(stato) {
  if (stato === null) {
    return;
  }
  aggiornaMetriche(stato.totali);
  // Le sezioni della revisione si disegnano solo se c'è qualcosa: un
  // fascicolo appena svuotato deve lasciare la pagina pulita, non gli
  // interruttori dell'analisi precedente.
  if (stato.documenti.length === 0) {
    categorie.replaceChildren();
    documenti.replaceChildren();
    statoAnalisi.textContent = "";
    return;
  }
  disegnaInterruttori(stato.categorie);
  disegnaDocumenti(stato.documenti);
}

async function leggiStato() {
  let risposta;
  try {
    risposta = await fetch(ROTTA_STATO);
  } catch (errore) {
    // All'avvio questo non è allarmante quanto sembra: la pagina può essere
    // aperta da un segnalibro mentre il server non c'è. Si dice, e basta.
    statoAnalisi.textContent = "L'applicazione non risponde: è ancora avviata?";
    return null;
  }
  if (!risposta.ok) {
    return null;
  }
  try {
    return await risposta.json();
  } catch (errore) {
    return null;
  }
}

svuota.addEventListener("click", async () => {
  // Una conferma, perché il gesto non si disfa: il fascicolo vive solo nella
  // memoria del processo, quindi qui non c'è niente da recuperare dopo.
  const quanti = metriche.documenti.textContent;
  const messaggio =
    `Butto via il fascicolo con ${quanti} ` +
    `${quanti === "1" ? "documento" : "documenti"}? ` +
    "Il testo vive solo nella memoria di questo programma: non si torna indietro.";
  if (!window.confirm(messaggio)) {
    return;
  }
  let risposta;
  try {
    risposta = await fetch(ROTTA_STATO, { method: "DELETE" });
  } catch (errore) {
    statoAnalisi.textContent = "L'applicazione non risponde: è ancora avviata?";
    return;
  }
  if (!risposta.ok) {
    return;
  }
  esiti.replaceChildren();
  ridisegnaTutto(await risposta.json());
});

// `defer` non serve: lo script è in fondo al body, quindi il DOM c'è già.
leggiStato().then(ridisegnaTutto);


// --- Approvazione ed esportazione (issue #7, comandi in pagina) --------------
//
// Il testo mascherato esce da una sola porta, `GET /api/fascicolo/esportazione`,
// che a sua volta passa dal gate di `export_sanitized_text`. Qui non si
// costruisce niente e non si maschera niente: comporre il mascherato nella
// pagina significherebbe avere una seconda versione di quel calcolo, e sarebbe
// quella non sorvegliata a finire negli appunti dell'utente.

const ROTTA_APPROVAZIONE = "/api/fascicolo/approvazione";
const ROTTA_ESPORTAZIONE = "/api/fascicolo/esportazione";

const approvaBottone = document.getElementById("approva");
const copiaBottone = document.getElementById("copia");
const scaricaBottone = document.getElementById("scarica");
const statoEsportazione = document.getElementById("stato-esportazione");
const anteprimaExport = document.getElementById("anteprima-export");

function esportazionePermessa(permessa) {
  copiaBottone.disabled = !permessa;
  scaricaBottone.disabled = !permessa;
}

// Un documento solo esce nudo; piu' documenti vanno separati, altrimenti chi
// incolla non sa dove finisce l'uno e comincia l'altro.
function unisci(documenti) {
  const nomi = Object.keys(documenti);
  if (nomi.length === 1) {
    return documenti[nomi[0]];
  }
  return nomi
    .map((nome) => `===== ${nome} =====\n${documenti[nome]}`)
    .join("\n\n");
}

// Un fascicolo nuovo non maschera niente: si accende cio' che serve. E' una
// decisione di prodotto presa apposta — chi conosce il documento decide cosa
// nascondere — ma ha un bordo tagliente che adesso e' a un clic di distanza:
// caricare, approvare ed esportare senza toccare un interruttore consegna il
// documento **in chiaro**. Il gate non lo impedisce e non deve: l'utente ha il
// diritto di esportare un documento che non contiene niente da nascondere.
// Quello che si puo' fare e' non lasciarglielo fare per distrazione.
function confermaSeNienteMascherato() {
  if (categorieAccese > 0) {
    return true;
  }
  return window.confirm(
    "Nessuna categoria è accesa: il testo uscirà IN CHIARO, con i dati "
      + "personali come sono nel documento originale.\n\n"
      + "Se volevi mascherarli, annulla e accendi gli interruttori nella "
      + "sezione «Rivedi il testo».\n\n"
      + "Esportare lo stesso?"
  );
}

async function prendiEsportazione() {
  let risposta;
  try {
    risposta = await fetch(ROTTA_ESPORTAZIONE);
  } catch (errore) {
    statoEsportazione.textContent = "L'applicazione non risponde: è ancora avviata?";
    return null;
  }
  let esito = null;
  try {
    esito = await risposta.json();
  } catch (errore) {
    esito = null;
  }
  if (!risposta.ok) {
    // Il 409 qui e' quasi sempre uno dei due casi del gate: non approvato, o
    // testo cambiato dopo l'approvazione. Il messaggio del dominio lo dice, e
    // arriva all'utente cosi' com'e'.
    statoEsportazione.textContent = messaggioDiErrore(esito, risposta.status);
    return null;
  }
  return esito.documenti;
}

approvaBottone.addEventListener("click", async () => {
  statoEsportazione.textContent = "Approvazione in corso…";
  const esito = await chiedi(ROTTA_APPROVAZIONE);
  if (esito === null) {
    // `chiedi` ha gia' scritto il motivo in `stato-analisi`; qui si toglie il
    // "in corso" invece di lasciarlo acceso su un'operazione finita male.
    statoEsportazione.textContent = statoAnalisi.textContent;
    return;
  }
  disegna(esito);
  esportazionePermessa(true);
  statoEsportazione.textContent =
    "Fascicolo approvato: il testo mascherato è firmato e puoi esportarlo. " +
    "Se tocchi ancora gli interruttori, riapprova prima di esportare.";
});

copiaBottone.addEventListener("click", async () => {
  if (!confermaSeNienteMascherato()) {
    return;
  }
  const documenti = await prendiEsportazione();
  if (documenti === null) {
    return;
  }
  const testo = unisci(documenti);
  try {
    await navigator.clipboard.writeText(testo);
    statoEsportazione.textContent =
      "Copiato negli appunti: puoi incollarlo nell'IA esterna.";
  } catch (errore) {
    // Gli appunti possono essere negati dal browser. Mostrare il testo e' il
    // ripiego onesto: l'utente lo seleziona a mano invece di restare senza.
    anteprimaExport.textContent = testo;
    anteprimaExport.hidden = false;
    statoEsportazione.textContent =
      "Il browser non mi lascia usare gli appunti: eccolo qui sotto, selezionalo e copialo.";
  }
});

scaricaBottone.addEventListener("click", async () => {
  if (!confermaSeNienteMascherato()) {
    return;
  }
  const documenti = await prendiEsportazione();
  if (documenti === null) {
    return;
  }
  const blob = new Blob([unisci(documenti)], { type: "text/plain;charset=utf-8" });
  const indirizzo = URL.createObjectURL(blob);
  const collegamento = document.createElement("a");
  collegamento.href = indirizzo;
  collegamento.download = "mascherato.txt";
  collegamento.click();
  URL.revokeObjectURL(indirizzo);
  statoEsportazione.textContent = "Scaricato come mascherato.txt.";
});
