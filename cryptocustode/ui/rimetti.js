// Rimettere i dati veri: l'altra metà del prodotto.
//
// Senza questo il mascheramento è a senso unico. Prima viveva in fondo a
// `index.html`, sotto il vault e le somiglianze, come una casella di testo in
// cui incollare — cioè nel posto in cui non la trovava chi non sapeva già che
// esistesse.
//
// Nessuna sostituzione avviene qui. Il testo va al server, che ha il
// dizionario, e torna ripristinato. Tenere la mappa `segnaposto -> valore` nel
// JavaScript significherebbe farla uscire dal processo, che è esattamente ciò
// che l'invariante 4 della spec §4 tiene dentro.
//
// **Quello che questa pagina deve dire prima di ogni altra cosa** è quale
// fascicolo sta usando. Il ripristino legge la tabella del fascicolo attivo: se
// in memoria c'è il fascicolo di ieri, i segnaposto di oggi diventano dati di
// ieri — o un errore, se va bene. Il riquadro in cima non è decorazione, è la
// risposta alla sola domanda che rende affidabile il risultato.

const ROTTA_STATO = "/api/fascicolo";
const ROTTA_RIPRISTINO = "/api/fascicolo/ripristino";
const ROTTA_VAULT_APRI = "/api/vault/apri";

const statoFascicolo = document.getElementById("stato-fascicolo");
const moduloVault = document.getElementById("modulo-vault-apri");
const fileVault = document.getElementById("vault-file");
const nomeVault = document.getElementById("vault-file-scelto");
const passwordVault = document.getElementById("vault-password-apri");
const campoAltra = document.getElementById("campo-altra-passphrase");
const usaAltra = document.getElementById("usa-altra-passphrase");
const statoVault = document.getElementById("stato-vault");

const card = document.getElementById("card-ripristino");
const moduloRipristino = document.getElementById("modulo-ripristino");
const sceltaRisposte = document.getElementById("scelta-risposte");
const risposteScelte = document.getElementById("risposte-scelte");
const moduloIncolla = document.getElementById("modulo-incolla");
const rispostaIA = document.getElementById("risposta-ia");
const statoRipristino = document.getElementById("stato-ripristino");

const esitoRipristino = document.getElementById("esito-ripristino");
const ripristinati = document.getElementById("ripristinati");
const scaricaTutti = document.getElementById("scarica-tutti");

// I testi ripristinati di questo giro, per il pulsante «Scarica tutti». Non è
// una copia dello stato del server: è ciò che l'utente ha appena ottenuto e non
// ha ancora salvato, e sparisce al ridisegno successivo.
let ottenuti = [];

// --- da dove vengono i segnaposto -------------------------------------------

function descriviFascicolo(stato) {
  if (!stato || stato.documenti.length === 0) {
    statoFascicolo.className = "origine-riga vuota";
    statoFascicolo.textContent =
      "Nessun fascicolo aperto. Carica il file fascicolo.vault che avevi " +
      "scaricato insieme ai documenti mascherati: è lì che vivono i dati veri.";
    moduloVault.hidden = false;
    usaAltra.hidden = false;
    return;
  }

  const quanti = stato.documenti.length;
  statoFascicolo.className = "origine-riga piena";
  statoFascicolo.textContent =
    `Fascicolo aperto adesso: ${quanti} ` +
    `${window.cc.plurale(quanti, "documento", "documenti")} — ` +
    stato.documenti.map((d) => d.filename).join(", ") +
    ". I segnaposto verranno risolti con la tabella di questo fascicolo.";
  // Il modulo del vault resta raggiungibile anche con un fascicolo aperto: chi
  // ha in memoria il fascicolo sbagliato deve poter caricare quello giusto, e
  // nasconderglielo lo costringerebbe a riavviare il programma.
  moduloVault.hidden = false;
  usaAltra.hidden = false;
}

async function leggiStato() {
  const esito = await window.cc.chiedi(ROTTA_STATO, undefined, "GET");
  if (!esito.ok) {
    statoFascicolo.className = "origine-riga vuota";
    statoFascicolo.textContent = esito.errore;
    return;
  }
  descriviFascicolo(esito.dati);
}

usaAltra.addEventListener("click", () => {
  campoAltra.hidden = false;
  usaAltra.hidden = true;
  passwordVault.focus();
});

fileVault.addEventListener("change", () => {
  const scelto = fileVault.files[0];
  nomeVault.textContent = scelto === undefined ? "Nessun vault scelto" : scelto.name;
});

moduloVault.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const scelto = fileVault.files[0];
  if (scelto === undefined) {
    statoVault.textContent = "Scegli il file .vault da riaprire.";
    return;
  }

  statoVault.textContent = "Apertura in corso…";
  const corpo = new FormData();
  corpo.append("file", scelto);
  // La password si manda solo se l'utente ne ha scritta una: il campo vuoto
  // significa «usa la passphrase della configurazione», che è il caso normale.
  // Mandare una stringa vuota la farebbe passare per una scelta esplicita, e il
  // vault non si aprirebbe mai.
  if (passwordVault.value !== "") {
    corpo.append("password", passwordVault.value);
  }

  const esito = await window.cc.manda(ROTTA_VAULT_APRI, corpo);
  if (!esito.ok) {
    statoVault.textContent = esito.errore;
    // Password sbagliata e file manomesso arrivano con lo stesso messaggio: qui
    // si offre l'unica cosa che l'utente può ancora provare, invece di lasciarlo
    // davanti a un errore senza seguito.
    if (campoAltra.hidden) {
      usaAltra.hidden = true;
      campoAltra.hidden = false;
    }
    return;
  }

  passwordVault.value = "";
  statoVault.textContent = `Fascicolo riaperto da ${scelto.name}.`;
  descriviFascicolo(esito.dati);
});

// --- il ripristino ----------------------------------------------------------

function descriviScelta(files) {
  const quanti = files.length;
  if (quanti === 0) {
    return "Nessun file scelto";
  }
  return quanti === 1 ? "1 file scelto" : `${quanti} file scelti`;
}

function mostraEsito(nome, testo) {
  ottenuti.push({ nome, testo });
  esitoRipristino.hidden = false;

  const riga = document.createElement("li");
  riga.className = "caricato ripristinato";

  const titolo = document.createElement("div");
  titolo.className = "documento-testa";
  const chi = document.createElement("strong");
  chi.textContent = nome;
  titolo.appendChild(chi);

  const bottone = document.createElement("button");
  bottone.type = "button";
  bottone.className = "pillola chiara";
  bottone.textContent = "Scarica";
  bottone.addEventListener("click", () => window.cc.scarica(testo, nome));
  titolo.appendChild(bottone);
  riga.appendChild(titolo);

  // L'anteprima e non il testo intero: questa roba contiene dati personali
  // veri, e riempirne lo schermo la mette davanti a chiunque passi dietro.
  const anteprima = document.createElement("pre");
  anteprima.className = "anteprima-export";
  anteprima.textContent = testo;
  riga.appendChild(anteprima);

  ripristinati.appendChild(riga);
}

function segnalaRifiuto(nome, motivo) {
  esitoRipristino.hidden = false;
  const riga = document.createElement("li");
  riga.className = "rifiutato";
  riga.textContent = `${nome} — ${motivo}`;
  ripristinati.appendChild(riga);
}

// Un file per richiesta, come il caricamento e per la stessa ragione: ogni
// rifiuto ha il suo messaggio, e un file che si ferma non deve fermare gli
// altri. Chi riceve nove testi buoni e un rifiuto sa esattamente quale
// rimandare all'IA; con una richiesta sola avrebbe un errore e nove testi mai
// calcolati.
async function ripristinaTesto(nome, testo) {
  if (testo.trim() === "") {
    segnalaRifiuto(nome, "il file è vuoto");
    return;
  }
  const esito = await window.cc.chiedi(ROTTA_RIPRISTINO, { risposta: testo });
  if (!esito.ok) {
    // Il messaggio del dominio dice **quali** segnaposto hanno fermato il
    // ripristino, ed è già in italiano: arriva all'utente com'è.
    segnalaRifiuto(nome, esito.errore);
    return;
  }
  mostraEsito(window.cc.nomeRipristinato(nome), esito.dati.ripristinato);
}

async function ripristinaTutti(files) {
  const scelti = Array.from(files);
  if (scelti.length === 0) {
    statoRipristino.textContent = "Scegli prima i file che ti ha restituito l'IA.";
    return;
  }
  ripristinati.replaceChildren();
  ottenuti = [];
  statoRipristino.textContent = "Ripristino in corso…";

  for (const file of scelti) {
    let testo;
    try {
      testo = await file.text();
    } catch (errore) {
      // Succede coi PDF e con qualunque cosa non sia testo: `text()` non
      // fallisce davvero, restituisce byte illeggibili — ma un file che non si
      // riesce a leggere va detto qui invece di finire al server come rumore.
      segnalaRifiuto(file.name, "non riesco a leggerlo come testo");
      continue;
    }
    await ripristinaTesto(file.name, testo);
  }

  const riusciti = ottenuti.length;
  statoRipristino.textContent =
    riusciti === scelti.length
      ? `Fatto: ${riusciti} ${window.cc.plurale(riusciti, "file ripristinato", "file ripristinati")}. ` +
        "Contengono dati personali veri."
      : `${riusciti} su ${scelti.length} ripristinati. Gli altri sono elencati qui sotto col motivo.`;
}

sceltaRisposte.addEventListener("change", () => {
  risposteScelte.textContent = descriviScelta(sceltaRisposte.files);
});

moduloRipristino.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  await ripristinaTutti(sceltaRisposte.files);
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
  await ripristinaTutti(evento.dataTransfer.files);
});

moduloIncolla.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const testo = rispostaIA.value;
  if (testo.trim() === "") {
    statoRipristino.textContent = "Incolla prima la risposta dell'IA.";
    return;
  }
  ripristinati.replaceChildren();
  ottenuti = [];
  statoRipristino.textContent = "Ripristino in corso…";
  await ripristinaTesto("testo-incollato.txt", testo);
  statoRipristino.textContent =
    ottenuti.length === 1
      ? "Ripristinato: sotto c'è il testo coi dati veri. Contiene dati personali."
      : "Il ripristino si è fermato: il motivo è qui sotto.";
});

scaricaTutti.addEventListener("click", () => {
  for (const { nome, testo } of ottenuti) {
    window.cc.scarica(testo, nome);
  }
});

leggiStato();
