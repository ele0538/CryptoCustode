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

  conteggio.textContent =
    `Documenti nel fascicolo: ${esito.documenti_nel_fascicolo} ` +
    `di ${esito.massimo_documenti}.`;
}

modulo.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const scelti = Array.from(scelta.files);
  if (scelti.length === 0) {
    aggiungi("avviso", "Nessun file scelto.");
    return;
  }
  for (const file of scelti) {
    await carica(file);
  }
  scelta.value = "";
});

// --- Revisione: testo evidenziato e interruttori (issue #4) -----------------
//
// Il testo arriva dal server **già spezzato in segmenti** sugli offset degli
// span, e qui non si fa aritmetica su nessun offset: tagliare da questa parte
// significherebbe tenere una seconda copia di quel calcolo, che diverge alla
// prima differenza fra il modo in cui Python e JavaScript contano i caratteri.
//
// Il testo non è modificabile in nessun punto, ed è la decisione 2 della spec
// §2: l'utente agisce solo sugli span. Ogni segmento è un nodo di solo testo,
// scritto con `textContent` e senza alcun attributo di modifica; gli unici
// campi della pagina sono la scelta dei file e le caselle di spunta degli
// interruttori.

const ROTTA_ANALISI = "/api/fascicolo/analisi";
const ROTTA_CATEGORIA = "/api/fascicolo/categoria";
const ROTTA_SPAN = "/api/fascicolo/span";

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

function disegnaInterruttori(elenco) {
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
      // Il tag è scelto fra due letterali e non costruito: `mark` porta
      // l'evidenziazione anche a chi non distingue i colori, e restare su due
      // nomi scritti per esteso è ciò che rende verificabile che questa pagina
      // non costruisca mai un elemento modificabile.
      if (segmento.span_id === null) {
        const pezzo = document.createElement("span");
        pezzo.textContent = segmento.testo;
        corpo.appendChild(pezzo);
        continue;
      }
      const pezzo = document.createElement("mark");
      pezzo.textContent = segmento.testo;
      pezzo.className =
        `evidenza cat-${segmento.categoria}` + (segmento.mascherato ? "" : " spenta");
      pezzo.dataset.spanId = segmento.span_id;
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
  const coda = revisione.ambiguita;
  statoAnalisi.textContent =
    `Stato del fascicolo: ${revisione.stato}. ` +
    `Ambiguità in coda: ${coda.totale}, di cui ${coda.bloccanti} ` +
    `${coda.bloccanti === 1 ? "blocca" : "bloccano"} l'approvazione.`;
  disegnaInterruttori(revisione.categorie);
  disegnaDocumenti(revisione.documenti);
}

avvio.addEventListener("click", async () => {
  statoAnalisi.textContent = "Analisi in corso…";
  disegna(await chiedi(ROTTA_ANALISI));
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
  const spanId = evento.target.dataset.spanId;
  if (spanId === undefined) {
    return;
  }
  // Il verso si legge da ciò che è disegnato: cliccare su un'occorrenza accesa
  // la spegne. Tenerlo in una variabile del JavaScript lo farebbe divergere
  // dal fascicolo appena due schede — o due ridisegni — non coincidessero.
  const attivo = evento.target.dataset.mascherato !== "1";
  disegna(await chiedi(ROTTA_SPAN, { span_id: spanId, attivo }));
});
