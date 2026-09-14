// Suggerimenti di fusione (spec §7, issue #51).
//
// Chiede all'utente se due scritture sono la stessa cosa, e non lo decide mai
// da sé: fondere per errore rivela il nome di una persona al posto di
// un'altra, mentre lasciare separato degrada soltanto la qualità della
// risposta dell'IA. Per questo la card non ha un «fondi tutto», i due bottoni
// hanno lo stesso peso visivo, e la coda si può ignorare per sempre senza che
// niente si blocchi.
//
// File a parte da `app.js`, come `vault.js`. Dipende da `app.js` per la sola
// `disegna`: la decisione restituisce il payload della revisione, quindi la
// pagina si ridisegna col codice che ha già.
//
// Il ricalcolo ha un bottone suo e non si aggancia a «Analizza». Agganciarlo
// sembrava gratis — gli ascoltatori si sommano, quindi non serviva toccare
// `app.js` — ma il gestore dell'analisi è asincrono: un secondo ascoltatore
// partirebbe subito e leggerebbe la tabella dei tag *prima* che la risposta
// dell'analisi l'abbia scritta, non trovando mai niente. Un bottone esplicito
// evita di indovinare quando l'altra corsia ha finito, e dice anche la verità
// sul prodotto: cercare somiglianze è un passo che si può non fare.

const ROTTA_FUSIONI = "/api/fusioni";
const ROTTA_RICALCOLO = "/api/fusioni/ricalcolo";
const ROTTA_DECISIONE = "/api/fusioni/decisione";

const elencoFusioni = document.getElementById("fusioni");
const statoFusioni = document.getElementById("stato-fusioni");
const cercaSomiglianze = document.getElementById("cerca-somiglianze");

function messaggioFusioni(esito, stato) {
  if (esito !== null && typeof esito.errore === "string") {
    return esito.errore;
  }
  if (esito !== null && typeof esito.detail === "string") {
    return esito.detail;
  }
  return `L'applicazione ha risposto ${stato} senza spiegare perché.`;
}

async function chiediFusioni(rotta, metodo, corpo) {
  const opzioni = { method: metodo };
  if (corpo !== undefined) {
    opzioni.headers = { "Content-Type": "application/json" };
    opzioni.body = JSON.stringify(corpo);
  }

  let risposta;
  try {
    risposta = await fetch(rotta, opzioni);
  } catch (errore) {
    statoFusioni.textContent = "L'applicazione non risponde: è ancora avviata?";
    return null;
  }

  let esito = null;
  try {
    esito = await risposta.json();
  } catch (errore) {
    esito = null;
  }

  if (!risposta.ok) {
    statoFusioni.textContent = messaggioFusioni(esito, risposta.status);
    return null;
  }
  return esito;
}

// Il testo dei bottoni nomina i valori e non i segnaposto: chiedere se
// `[PERSONA_1]` e `[PERSONA_2]` sono la stessa persona è una domanda a cui
// nessuno può rispondere.
function disegnaProposta(proposta) {
  const riga = document.createElement("li");
  riga.className = proposta.risolta ? "fusione decisa" : "fusione";

  const domanda = document.createElement("p");
  domanda.className = "fusione-domanda";
  domanda.textContent = proposta.risolta
    ? `Deciso: ${proposta.valore_a ?? proposta.tag_a} e ${proposta.valore_b ?? proposta.tag_b}.`
    : `«${proposta.valore_a}» e «${proposta.valore_b}» sono la stessa cosa?`;
  riga.appendChild(domanda);

  const segnaposti = document.createElement("p");
  segnaposti.className = "tenue fusione-segnaposti";
  segnaposti.textContent = `${proposta.tag_a} · ${proposta.tag_b}`;
  riga.appendChild(segnaposti);

  if (proposta.risolta) {
    return riga;
  }

  const scelte = document.createElement("div");
  scelte.className = "fusione-scelte";

  // «Separa» per primo, e con lo stesso peso di «Fondi»: è il default sicuro
  // della spec §7, e una card che mettesse la fusione in evidenza spingerebbe
  // verso l'errore che costa di più.
  for (const [decisione, etichetta] of [
    ["separa", "No, sono diverse"],
    ["fondi", `Sì, usa ${proposta.tag_a}`],
  ]) {
    const bottone = document.createElement("button");
    bottone.type = "button";
    bottone.className = "pillola chiara";
    bottone.textContent = etichetta;
    bottone.dataset.fusione = proposta.fusione_id;
    bottone.dataset.decisione = decisione;
    scelte.appendChild(bottone);
  }

  riga.appendChild(scelte);
  return riga;
}

function disegnaFusioni(proposte) {
  elencoFusioni.replaceChildren();
  for (const proposta of proposte) {
    elencoFusioni.appendChild(disegnaProposta(proposta));
  }

  const aperte = proposte.filter((proposta) => !proposta.risolta).length;
  if (proposte.length === 0) {
    statoFusioni.textContent =
      "Nessuna somiglianza trovata fra i nomi del fascicolo.";
  } else if (aperte === 0) {
    statoFusioni.textContent = "Hai deciso su tutte le somiglianze trovate.";
  } else {
    statoFusioni.textContent =
      `${aperte} da decidere. Finché non decidi restano separate, ` +
      "che è il comportamento prudente: separare per errore peggiora solo la " +
      "risposta dell'IA, fondere per errore rivela un nome al posto di un altro.";
  }
}

async function ricalcola() {
  const esito = await chiediFusioni(ROTTA_RICALCOLO, "POST");
  if (esito !== null) {
    disegnaFusioni(esito.fusioni);
  }
}

// Un gestore solo sul contenitore: le proposte vengono ricreate a ogni
// ridisegno, e agganciare i bottoni uno per uno lascerebbe i gestori attaccati
// a nodi che non sono più in pagina.
elencoFusioni.addEventListener("click", async (evento) => {
  const fusioneId = evento.target.dataset.fusione;
  if (fusioneId === undefined) {
    return;
  }

  const revisione = await chiediFusioni(ROTTA_DECISIONE, "POST", {
    fusione_id: fusioneId,
    decisione: evento.target.dataset.decisione,
  });
  if (revisione === null) {
    // L'errore è già scritto in pagina. La coda va comunque riletta: un 409
    // dice che questa proposta è stata decisa altrove, e lasciarla disegnata
    // aperta inviterebbe a ripremere un bottone che risponderà 409 di nuovo.
    disegnaFusioni((await chiediFusioni(ROTTA_FUSIONI, "GET"))?.fusioni ?? []);
    return;
  }

  disegna(revisione);
  disegnaFusioni((await chiediFusioni(ROTTA_FUSIONI, "GET"))?.fusioni ?? []);
});

cercaSomiglianze.addEventListener("click", ricalcola);
