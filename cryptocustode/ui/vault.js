// Vault dalla UI: salva il fascicolo cifrato, riaprilo, riprendi la revisione
// (issue #9, cablata dalla issue #51).
//
// File a parte da `app.js` di proposito: il vault non è un passo del flusso di
// revisione, è il modo in cui il fascicolo sopravvive alla chiusura del
// programma. Tenerlo separato significa anche che due sessioni possono
// lavorare sulla pagina senza sovrascriversi.
//
// Dipende da `app.js` per una cosa sola: `disegna`, che ridisegna la revisione
// dal payload del server. `/api/vault/apri` restituisce esattamente quel
// payload, quindi riaprire un vault e premere un interruttore ridisegnano la
// pagina con lo stesso codice. Scriverne un secondo qui significherebbe avere
// due percorsi di disegno che divergono al primo campo aggiunto.

const ROTTA_VAULT_SALVA = "/api/vault/salva";
const ROTTA_VAULT_APRI = "/api/vault/apri";
const NOME_FILE_VAULT = "fascicolo.vault";

const moduloSalva = document.getElementById("modulo-vault-salva");
const passwordSalva = document.getElementById("vault-password-salva");
const moduloApri = document.getElementById("modulo-vault-apri");
const passwordApri = document.getElementById("vault-password-apri");
const fileVault = document.getElementById("vault-file");
const nomeVault = document.getElementById("vault-file-scelto");
const statoVault = document.getElementById("stato-vault");

// La stessa lettura del corpo d'errore che fa `app.js`: `errore` della tabella
// della spec §13, `detail` di FastAPI quando la validazione rifiuta prima, o
// niente. Qui non si riusa `messaggioDiErrore` perché quella scrive il proprio
// esito nello stato dell'analisi, e un errore del vault che comparisse lì
// manderebbe l'utente a guardare il riquadro sbagliato.
function messaggioVault(esito, stato) {
  if (esito !== null && typeof esito.errore === "string") {
    return esito.errore;
  }
  if (esito !== null && typeof esito.detail === "string") {
    return esito.detail;
  }
  return `L'applicazione ha risposto ${stato} senza spiegare perché.`;
}

async function corpoDiErrore(risposta) {
  try {
    return await risposta.json();
  } catch (errore) {
    return null;
  }
}

// Il blob non passa mai da un file su disco scritto dal server: arriva nella
// risposta e il browser lo salva. È la spec §10 — fuori dal vault il fascicolo
// vive solo nella RAM del processo — e vale anche per il momento in cui esce.
function scarica(blob, nome) {
  const indirizzo = URL.createObjectURL(blob);
  const collegamento = document.createElement("a");
  collegamento.href = indirizzo;
  collegamento.download = nome;
  document.body.appendChild(collegamento);
  collegamento.click();
  collegamento.remove();
  // Senza `revokeObjectURL` il fascicolo cifrato resta nella memoria della
  // scheda finché non la si chiude. È cifrato, quindi non è una fuga di dati,
  // ma è memoria trattenuta per niente a ogni salvataggio.
  URL.revokeObjectURL(indirizzo);
}

moduloSalva.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  if (passwordSalva.value === "") {
    statoVault.textContent = "Scegli una password: senza, il vault non protegge niente.";
    return;
  }

  statoVault.textContent = "Salvataggio in corso…";
  let risposta;
  try {
    risposta = await fetch(ROTTA_VAULT_SALVA, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: passwordSalva.value }),
    });
  } catch (errore) {
    statoVault.textContent = "L'applicazione non risponde: è ancora avviata?";
    return;
  }

  if (!risposta.ok) {
    statoVault.textContent = messaggioVault(await corpoDiErrore(risposta), risposta.status);
    return;
  }

  scarica(await risposta.blob(), NOME_FILE_VAULT);
  // La password si cancella dopo l'uso: la pagina resta aperta per tutta la
  // sessione di lavoro, e lasciarla scritta in un campo la mostrerebbe a
  // chiunque passi davanti allo schermo.
  passwordSalva.value = "";
  statoVault.textContent =
    `Fascicolo salvato in ${NOME_FILE_VAULT}. Senza la password non è recuperabile: ` +
    "non esiste un modo per riaprirlo se la dimentichi.";
});

fileVault.addEventListener("change", () => {
  const scelto = fileVault.files[0];
  nomeVault.textContent = scelto === undefined ? "Nessun vault scelto" : scelto.name;
});

moduloApri.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const scelto = fileVault.files[0];
  if (scelto === undefined) {
    statoVault.textContent = "Scegli il file .vault da riaprire.";
    return;
  }

  statoVault.textContent = "Riapertura in corso…";
  const corpo = new FormData();
  corpo.append("file", scelto);
  corpo.append("password", passwordApri.value);

  let risposta;
  try {
    risposta = await fetch(ROTTA_VAULT_APRI, { method: "POST", body: corpo });
  } catch (errore) {
    statoVault.textContent = "L'applicazione non risponde: è ancora avviata?";
    return;
  }

  const esito = await corpoDiErrore(risposta);
  if (!risposta.ok) {
    statoVault.textContent = messaggioVault(esito, risposta.status);
    return;
  }

  passwordApri.value = "";
  // La riapertura sostituisce il fascicolo attivo, quindi la pagina va
  // ridisegnata per intero: `disegna` è la stessa funzione che usano i toggle,
  // e riceve lo stesso payload.
  disegna(esito);
  statoVault.textContent =
    `Fascicolo riaperto da ${scelto.name}: ${esito.documenti.length} documenti, ` +
    `stato ${esito.stato}.`;
});
