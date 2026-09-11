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
