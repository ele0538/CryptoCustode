// Caricamento dei documenti dalla UI (issue #3).
//
// Un file per richiesta, in sequenza. La ragione è che ogni rifiuto è uno stato
// HTTP con un messaggio (spec §13): con dieci file in una richiesta sola
// l'esito sarebbe misto e un solo stato non potrebbe dirlo. Così ogni file ha
// il suo verdetto, e l'utente vede quale è entrato e quale no.
//
// Qui non si maschera niente e non si mostra alcuna anteprima del mascherato:
// l'invariante 3 della spec §4 vuole che il testo mascherato esca solo dal gate
// di esportazione.

const ROTTA = "/api/fascicolo/documenti";

const modulo = document.getElementById("modulo-caricamento");
const scelta = document.getElementById("scelta-file");
const esiti = document.getElementById("esiti");
const conteggio = document.getElementById("conteggio");

function aggiungi(classe, testo) {
  const riga = document.createElement("li");
  riga.className = classe;
  riga.textContent = testo;
  esiti.appendChild(riga);
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

  const esito = await risposta.json();

  if (!risposta.ok) {
    aggiungi("rifiutato", `${file.name} — ${esito.errore}`);
    return;
  }

  aggiungi(
    "caricato",
    `${file.name} — caricato: ${esito.caratteri} caratteri, ${esito.pagine} pagine`
  );

  for (const avviso of esito.segnaposto_preesistenti) {
    aggiungi(
      "avviso",
      `${file.name} — attenzione: il testo contiene già ${avviso.segnaposto} ` +
        `alla posizione ${avviso.posizione}. Al ripristino verrebbe confuso con ` +
        `un segnaposto nostro e sostituito con dati veri: controllalo prima di approvare.`
    );
  }

  conteggio.textContent = `Documenti nel fascicolo: ${esito.documenti_nel_fascicolo} di 10.`;
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
