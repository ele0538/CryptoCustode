// Configurazione e conto della spesa.
//
// Sta in un file a parte da `app.js` perché è l'unica parte della pagina che
// deve funzionare **prima** che esista una chiave: se vivesse insieme al
// caricamento, un errore nel caricamento porterebbe giù anche la sola schermata
// da cui la chiave si può inserire.
//
// La chiave API entra e non esce più: il server non la restituisce mai, quindi
// il campo resta vuoto anche quando una chiave è salvata. È voluto — rimandarla
// indietro «per comodità» la metterebbe nella cronologia del browser e negli
// strumenti di sviluppo, che è ciò che cifrarla sul disco serve a evitare.

const ROTTA_CONFIG = "/api/config";
const ROTTA_SBLOCCA = "/api/config/sblocca";
const ROTTA_CONSUMO = "/api/consumo";

const pannello = document.getElementById("pannello-config");
const apriConfig = document.getElementById("apri-config");
const chiudiConfig = document.getElementById("chiudi-config");
const moduloConfig = document.getElementById("modulo-config");
const moduloSblocco = document.getElementById("modulo-sblocco");
const messaggioConfig = document.getElementById("messaggio-config");
const spiegaConfig = document.getElementById("spiega-config");
const spesa = document.getElementById("spesa");

const campo = {
  modello: document.getElementById("config-modello"),
  prezzoInput: document.getElementById("config-prezzo-input"),
  prezzoOutput: document.getElementById("config-prezzo-output"),
  valuta: document.getElementById("config-valuta"),
  chiave: document.getElementById("config-chiave"),
  passphrase: document.getElementById("config-passphrase"),
  sblocco: document.getElementById("config-sblocco"),
};

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
  if (consumo === null) {
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
      `${riga.chiamate} ${riga.chiamate === 1 ? "chiamata" : "chiamate"}`;
    voce.appendChild(dettaglio);

    spesa.appendChild(voce);
  }
}

// Tre schermi possibili, e il server dice quale: nessuna chiave salvata →
// si chiede tutto; chiave salvata ma chiusa → si chiede solo la passphrase;
// chiave aperta → il pannello serve solo se lo si apre apposta.
function disegnaConfig(stato) {
  if (stato === null) {
    return;
  }
  campo.modello.value = stato.modello;
  campo.prezzoInput.value = stato.prezzo_input;
  campo.prezzoOutput.value = stato.prezzo_output;
  campo.valuta.value = stato.valuta;
  campo.chiave.value = "";
  campo.passphrase.value = "";

  const daSbloccare = stato.chiave_salvata && !stato.pronta;
  moduloSblocco.hidden = !daSbloccare;
  moduloConfig.hidden = daSbloccare;

  if (daSbloccare) {
    spiegaConfig.textContent =
      "La tua chiave è salvata cifrata su questo computer. " +
      "Scrivi la passphrase per aprirla: serve a ogni avvio, ed è il prezzo " +
      "di non tenerla in chiaro sul disco.";
  } else if (stato.pronta) {
    spiegaConfig.textContent =
      "Chiave attiva. Puoi cambiare modello e prezzi senza riscriverla: " +
      "lascia vuoto il campo della chiave e verrà mantenuta quella che c'è.";
  } else {
    spiegaConfig.textContent =
      "Prima di analizzare serve una chiave di Gemini, da un progetto con " +
      "fatturazione attiva. I prezzi copiali dal listino del modello che " +
      "scegli: servono solo a calcolare quanto spendi, e puoi correggerli dopo.";
  }

  disegnaSpesa(stato.consumo);
  // Il pannello si apre da sé finché non c'è una chiave utilizzabile: senza,
  // il resto della pagina non può fare niente, e lasciarlo esplorare
  // significherebbe farlo arrivare a un errore che si poteva prevenire.
  pannello.hidden = stato.pronta;
  apriConfig.hidden = false;
}

async function chiediConfig(rotta, corpo, metodo = "POST") {
  const opzioni = { method: metodo };
  if (corpo !== undefined) {
    opzioni.headers = { "Content-Type": "application/json" };
    opzioni.body = JSON.stringify(corpo);
  }
  let risposta;
  try {
    risposta = await fetch(rotta, opzioni);
  } catch (errore) {
    messaggioConfig.textContent = "L'applicazione non risponde: è ancora avviata?";
    return null;
  }
  let esito = null;
  try {
    esito = await risposta.json();
  } catch (errore) {
    esito = null;
  }
  if (!risposta.ok) {
    messaggioConfig.textContent =
      esito && esito.errore
        ? esito.errore
        : esito && esito.detail
          ? "controlla i valori inseriti: qualcosa non è un numero valido"
          : `errore ${risposta.status}`;
    return null;
  }
  messaggioConfig.textContent = "";
  return esito;
}

moduloConfig.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const chiave = campo.chiave.value.trim();
  const passphrase = campo.passphrase.value;
  if (chiave && !passphrase) {
    messaggioConfig.textContent =
      "Per salvare la chiave serve anche una passphrase: è quella che la " +
      "protegge sul disco. Scegline una e non perderla — senza, la chiave " +
      "salvata non si riapre.";
    return;
  }
  const esito = await chiediConfig(ROTTA_CONFIG, {
    modello: campo.modello.value.trim(),
    prezzo_input: Number(campo.prezzoInput.value) || 0,
    prezzo_output: Number(campo.prezzoOutput.value) || 0,
    valuta: campo.valuta.value.trim() || "USD",
    chiave: chiave || null,
    passphrase: passphrase || null,
  });
  disegnaConfig(esito);
});

moduloSblocco.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  disegnaConfig(await chiediConfig(ROTTA_SBLOCCA, { passphrase: campo.sblocco.value }));
  campo.sblocco.value = "";
});

apriConfig.addEventListener("click", async () => {
  const stato = await chiediConfig(ROTTA_CONFIG, undefined, "GET");
  if (stato !== null) {
    disegnaConfig(stato);
    pannello.hidden = false;
  }
});

chiudiConfig.addEventListener("click", () => {
  pannello.hidden = true;
});

// Il conto si aggiorna dopo ogni analisi, che è l'unico momento in cui cambia.
// `app.js` non lo sa: espone questo aggancio sulla finestra invece di un
// import, perché i due file sono due `<script>` e non due moduli.
window.aggiornaSpesa = async () => {
  disegnaSpesa(await chiediConfig(ROTTA_CONSUMO, undefined, "GET"));
};

chiediConfig(ROTTA_CONFIG, undefined, "GET").then(disegnaConfig);
