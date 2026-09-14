// L'ingresso: una chiave, poi due strade.
//
// Erede di `config.js`, che faceva la stessa cosa dentro un pannello
// sovrapposto alla pagina di lavoro. Il pannello è la ragione per cui questo
// file esiste da solo: un pannello si chiude, e chiuso lasciava credere che
// l'applicazione fosse pronta quando non lo era — il flusso sotto era visibile,
// cliccabile, e rispondeva 409 a ogni gesto.
//
// Qui non c'è niente da chiudere. Il server dice in che stato è la chiave e si
// disegna **uno** schermo: o la si inserisce, o la si apre, o si sceglie cosa
// fare. Gli altri due non sono nascosti dietro un bottone: non sono in pagina.
//
// La chiave API entra e non esce più: il server non la restituisce mai, quindi
// il campo resta vuoto anche quando una chiave è salvata.

const ROTTA_CONFIG = "/api/config";
const ROTTA_SBLOCCA = "/api/config/sblocca";

const schermi = {
  chiave: document.getElementById("schermo-chiave"),
  sblocco: document.getElementById("schermo-sblocco"),
  scelta: document.getElementById("schermo-scelta"),
};

const apriConfig = document.getElementById("apri-config");
const chiudiConfig = document.getElementById("chiudi-config");
const rifaiChiave = document.getElementById("rifai-chiave");
const moduloConfig = document.getElementById("modulo-config");
const moduloSblocco = document.getElementById("modulo-sblocco");
const messaggioConfig = document.getElementById("messaggio-config");
const spiegaConfig = document.getElementById("spiega-config");
const cardSpesa = document.getElementById("card-spesa");
const spesa = document.getElementById("spesa");

const campo = {
  modello: document.getElementById("config-modello"),
  prezzoInput: document.getElementById("config-prezzo-input"),
  prezzoOutput: document.getElementById("config-prezzo-output"),
  valuta: document.getElementById("config-valuta"),
  chiave: document.getElementById("config-chiave"),
  passphrase: document.getElementById("config-passphrase"),
  sblocco: document.getElementById("config-sblocco"),
  piano: document.getElementById("config-piano"),
};

// Quando l'utente chiede la configurazione avendo già una chiave pronta, lo
// schermo della chiave va mostrato anche se il server dice che è tutto a posto.
// Senza questa variabile il primo ridisegno lo rispedirebbe alla scelta, e il
// pulsante «Configurazione» non farebbe niente di visibile.
let configurazioneChiesta = false;

// Quattro cifre decimali: una chiamata singola su un documento breve costa
// frazioni di centesimo, e arrotondare a due mostrerebbe «0,00» proprio nel
// momento in cui l'utente sta verificando che il conteggio funzioni.
function soldi(quanti, valuta) {
  return `${quanti.toFixed(4)} ${valuta}`;
}

function numero(quanti) {
  return quanti.toLocaleString("it-IT");
}

function disegnaSpesa(consumo) {
  if (!consumo) {
    return;
  }
  // Un conto a zero non si mostra: chi non ha mai analizzato niente non ha
  // bisogno di un riquadro che glielo confermi, e all'ingresso ogni riquadro
  // in più è una cosa in più da capire prima di poter premere un pulsante.
  const mai = consumo.totale.chiamate === 0;
  cardSpesa.hidden = mai;
  if (mai) {
    return;
  }

  const righe = [
    ["Questa sessione", consumo.sessione],
    ["Da sempre", consumo.totale],
  ];
  spesa.replaceChildren();
  for (const [titolo, riga] of righe) {
    const voce = document.createElement("div");
    voce.className = "voce-spesa";

    const nome = document.createElement("dt");
    nome.textContent = titolo;
    voce.appendChild(nome);

    const valore = document.createElement("dd");
    // Senza prezzi il costo sarebbe uno zero indistinguibile da «non ho speso
    // niente». Dirlo è l'unica risposta onesta: i prezzi non li sa nessuno
    // tranne chi legge il listino del fornitore.
    valore.textContent = consumo.prezzi_impostati
      ? soldi(riga.costo, consumo.valuta)
      : "prezzi non impostati";
    voce.appendChild(valore);

    const dettaglio = document.createElement("dd");
    dettaglio.className = "tenue";
    dettaglio.textContent =
      `${numero(riga.token_input)} token in entrata, ` +
      `${numero(riga.token_output)} in uscita, ` +
      `${riga.chiamate} ${window.cc.plurale(riga.chiamate, "chiamata", "chiamate")}`;
    voce.appendChild(dettaglio);

    spesa.appendChild(voce);
  }
}

// Quale dei tre schermi, e uno solo. La decisione sta in una funzione sola e
// non sparsa fra i gestori: tre `hidden` cambiati in tre punti diversi sono
// tre modi di finire con due schermi accesi insieme, o con nessuno.
function quale(stato) {
  if (stato.chiave_salvata && !stato.pronta) {
    return "sblocco";
  }
  // La dichiarazione sul piano è parte dell'essere pronti: senza, il rilevatore
  // rifiuta di partire, e mandare l'utente al caricamento per fermarlo dopo
  // dieci file sarebbe farglielo scoprire nel punto più caro.
  if (!stato.pronta || !stato.piano_attestato || configurazioneChiesta) {
    return "chiave";
  }
  return "scelta";
}

function disegna(stato) {
  if (!stato) {
    return;
  }
  campo.modello.value = stato.modello;
  campo.prezzoInput.value = stato.prezzo_input;
  campo.prezzoOutput.value = stato.prezzo_output;
  campo.valuta.value = stato.valuta;
  campo.piano.checked = stato.piano_attestato;
  campo.chiave.value = "";
  campo.passphrase.value = "";

  const acceso = quale(stato);
  for (const [nome, sezione] of Object.entries(schermi)) {
    sezione.hidden = nome !== acceso;
  }

  // Il pulsante in barra serve solo a chi *può* tornare indietro: se la chiave
  // non è pronta, lo schermo della configurazione è già quello in pagina e un
  // pulsante che lo riapre non porta da nessuna parte.
  const pronta = stato.pronta && stato.piano_attestato;
  apriConfig.hidden = !pronta;
  chiudiConfig.hidden = !pronta;

  if (stato.chiave_salvata && !stato.pronta) {
    spiegaConfig.textContent = "";
  } else if (pronta) {
    spiegaConfig.textContent =
      "Chiave attiva. Puoi cambiare modello e prezzi senza riscriverla: " +
      "lascia vuoto il campo della chiave e verrà mantenuta quella che c'è.";
  } else if (stato.pronta && !stato.piano_attestato) {
    spiegaConfig.textContent =
      "Chiave attiva, ma manca la dichiarazione sul piano: senza, l'analisi " +
      "si rifiuta di partire. È l'ultima casella qui sotto.";
  } else {
    spiegaConfig.textContent =
      "Serve una chiave di Gemini, da un progetto con fatturazione attiva. " +
      "I prezzi copiali dal listino del modello che scegli: servono solo a " +
      "calcolare quanto spendi, e puoi correggerli dopo.";
  }

  disegnaSpesa(stato.consumo);
}

async function chiediConfig(rotta, corpo, metodo = "POST") {
  const esito = await window.cc.chiedi(rotta, corpo, metodo);
  if (!esito.ok) {
    // La validazione di FastAPI qui è quasi sempre un prezzo scritto male, e
    // «richiesta non valida» non direbbe dove guardare.
    messaggioConfig.textContent =
      esito.dati && esito.dati.detail && !esito.dati.errore
        ? "controlla i valori inseriti: qualcosa non è un numero valido"
        : esito.errore;
    return null;
  }
  messaggioConfig.textContent = "";
  return esito.dati;
}

moduloConfig.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const chiave = campo.chiave.value.trim();
  const passphrase = campo.passphrase.value;
  if (chiave && !passphrase) {
    messaggioConfig.textContent =
      "Per salvare la chiave serve anche una passphrase: è quella che la " +
      "protegge sul disco, e che cifrerà i fascicoli. Scegline una e non " +
      "perderla — senza, né la chiave né i fascicoli salvati si riaprono.";
    return;
  }
  const esito = await chiediConfig(ROTTA_CONFIG, {
    modello: campo.modello.value.trim(),
    prezzo_input: Number(campo.prezzoInput.value) || 0,
    prezzo_output: Number(campo.prezzoOutput.value) || 0,
    valuta: campo.valuta.value.trim() || "USD",
    piano_attestato: campo.piano.checked,
    chiave: chiave || null,
    passphrase: passphrase || null,
  });
  // Salvare è il gesto con cui si esce dalla configurazione: se ha funzionato,
  // la richiesta esplicita è servita e non deve tenere l'utente fermo lì.
  if (esito !== null) {
    configurazioneChiesta = false;
  }
  disegna(esito);
});

moduloSblocco.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  disegna(await chiediConfig(ROTTA_SBLOCCA, { passphrase: campo.sblocco.value }));
  campo.sblocco.value = "";
});

apriConfig.addEventListener("click", async () => {
  configurazioneChiesta = true;
  disegna(await chiediConfig(ROTTA_CONFIG, undefined, "GET"));
});

chiudiConfig.addEventListener("click", async () => {
  configurazioneChiesta = false;
  disegna(await chiediConfig(ROTTA_CONFIG, undefined, "GET"));
});

// Chi ha perso la passphrase non ha modo di recuperare la chiave: quella è
// cifrata con essa e non esiste una porta di servizio. Quello che può fare è
// scriverne una nuova, ed è meglio dirglielo che lasciarlo davanti a un campo
// che non accetterà mai niente.
rifaiChiave.addEventListener("click", () => {
  configurazioneChiesta = true;
  schermi.sblocco.hidden = true;
  schermi.chiave.hidden = false;
  messaggioConfig.textContent =
    "Scrivi la chiave e una passphrase nuova. Attenzione: i fascicoli salvati " +
    "con la passphrase vecchia resteranno chiusi, perché è quella a cifrarli.";
});

chiediConfig(ROTTA_CONFIG, undefined, "GET").then(disegna);
