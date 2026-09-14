// Nascondere i dati: carica, analizza, salva. Due schermate, un documento.
//
// Erede di `app.js`, che faceva questo più il ripristino più il vault più la
// configurazione, tutto impilato in una pagina sola. Il ripristino è andato in
// `rimetti.js` perché è l'altro mestiere; la configurazione in `home.js` perché
// viene prima di tutto. Qui resta una cosa sola, e si svolge in due passi.
//
// I due passi stanno nello stesso documento e non in due URL: condividono il
// fascicolo appena analizzato, e un giro dal server fra l'uno e l'altro
// rischierebbe di ridisegnare la revisione da uno stato che nel frattempo è
// cambiato. Cripta e rimetti invece sono due documenti, perché non condividono
// niente.
//
// Qui non si maschera niente e non si compone niente: il testo mascherato esce
// da una sola porta, `GET /api/fascicolo/esportazione`, che passa dal gate di
// `export_sanitized_text`. Comporlo nella pagina significherebbe avere una
// seconda versione di quel calcolo, e sarebbe quella non sorvegliata a finire
// nelle mani dell'utente.

const ROTTA_DOCUMENTI = "/api/fascicolo/documenti";
const ROTTA_STATO = "/api/fascicolo";
const ROTTA_ANALISI = "/api/fascicolo/analisi";
const ROTTA_CATEGORIA = "/api/fascicolo/categoria";
const ROTTA_TAG = "/api/fascicolo/tag";
const ROTTA_APPROVAZIONE = "/api/fascicolo/approvazione";
const ROTTA_ESPORTAZIONE = "/api/fascicolo/esportazione";
const ROTTA_VAULT_SALVA = "/api/vault/salva";

const NOME_FILE_VAULT = "fascicolo.vault";
const AVVISI_MOSTRATI = 5;
const CARATTERI_DI_ESTRATTO = 140;

const passi = {
  carica: document.getElementById("passo-carica"),
  salva: document.getElementById("passo-salva"),
};
const chip = {
  carica: document.getElementById("chip-carica"),
  salva: document.getElementById("chip-salva"),
};

const modulo = document.getElementById("modulo-caricamento");
const scelta = document.getElementById("scelta-file");
const esiti = document.getElementById("esiti");
const conteggio = document.getElementById("conteggio");
const card = document.getElementById("card-caricamento");
const cardFascicolo = document.getElementById("card-fascicolo");
const fileScelti = document.getElementById("file-scelti");
const svuota = document.getElementById("svuota-fascicolo");
const avvio = document.getElementById("avvia-analisi");
const statoAnalisi = document.getElementById("stato-analisi");

const categorie = document.getElementById("categorie");
const documenti = document.getElementById("documenti");
const riquadroEsposizione = document.getElementById("esposizione");
const tornaCarica = document.getElementById("torna-carica");

const salvaTutto = document.getElementById("salva-tutto");
const statoEsportazione = document.getElementById("stato-esportazione");
const scaricati = document.getElementById("scaricati");
const anteprimaExport = document.getElementById("anteprima-export");

// Le quattro cifre grandi. I documenti li dice il server a ogni risposta (è lui
// a sapere quanti sono); niente accumulatore qui: un accumulatore non scende
// mai, quindi dopo lo svuotamento continuerebbe a dichiarare i caratteri di
// documenti che non ci sono più.
const metriche = {
  documenti: document.getElementById("metrica-documenti"),
  tetto: document.getElementById("metrica-tetto"),
  pagine: document.getElementById("metrica-pagine"),
  caratteri: document.getElementById("metrica-caratteri"),
  avvisi: document.getElementById("metrica-avvisi"),
};

// Quante categorie sono accese adesso. Si legge dall'ultimo payload servito
// invece di contare le caselle disegnate: le caselle sono il riflesso dello
// stato, non lo stato.
let categorieAccese = 0;

// --- i due passi ------------------------------------------------------------

function vaiA(passo) {
  passi.carica.hidden = passo !== "carica";
  passi.salva.hidden = passo !== "salva";
  chip.carica.className = passo === "carica" ? "passo attivo" : "passo fatto";
  chip.salva.className = passo === "salva" ? "passo attivo" : "passo";
  if (passo === "carica") {
    chip.carica.setAttribute("aria-current", "step");
    chip.salva.removeAttribute("aria-current");
  } else {
    chip.salva.setAttribute("aria-current", "step");
    chip.carica.removeAttribute("aria-current");
  }
  // In cima, sempre: passare a una schermata nuova restando a metà pagina è
  // il modo più semplice di non accorgersi che è cambiata.
  window.scrollTo(0, 0);
}

// --- passo 1: caricamento ---------------------------------------------------

function aggiungi(classe, testo, dettaglioTesto) {
  const riga = document.createElement("li");
  riga.className = classe;
  riga.textContent = testo;
  if (dettaglioTesto) {
    const secondaRiga = document.createElement("p");
    secondaRiga.className = "estratto";
    secondaRiga.textContent = dettaglioTesto;
    riga.appendChild(secondaRiga);
  }
  esiti.appendChild(riga);
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
        `segnaposto nostro e sostituito con dati veri: controllalo prima di salvare.`
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
      ? "Nessun documento."
      : `${totali.documenti} di ${totali.massimo_documenti} documenti.`;
  svuota.hidden = totali.documenti === 0;
  // Quattro cifre grandi che dicono zero sono il peso visivo piu' grosso
  // della schermata a riposo, e non dicono niente. Restano dove sono — la
  // struttura non deve saltare al primo caricamento — ma in grigio finche'
  // non c'e' qualcosa da contare.
  cardFascicolo.classList.toggle("vuoto", totali.documenti === 0);
  // Analizzare un fascicolo vuoto costerebbe una chiamata a Gemini per
  // ottenere niente: il pulsante resta spento finché non c'è cosa analizzare.
  avvio.disabled = totali.documenti === 0;
}

function descriviScelta(files) {
  const quanti = files.length;
  if (quanti === 0) {
    return "Nessun file scelto";
  }
  return quanti === 1 ? "1 file scelto" : `${quanti} file scelti`;
}

// Un file per richiesta, in sequenza. Ogni rifiuto è uno stato HTTP con un
// messaggio (spec §13): con dieci file in una richiesta sola l'esito sarebbe
// misto e un solo stato non potrebbe dirlo.
async function carica(file) {
  const corpo = new FormData();
  corpo.append("file", file);

  const esito = await window.cc.manda(ROTTA_DOCUMENTI, corpo);
  if (!esito.ok) {
    aggiungi("rifiutato", `${file.name} — ${esito.errore}`);
    return;
  }

  const dati = esito.dati;
  aggiungi(
    "caricato",
    `${file.name} — caricato: ${dati.caratteri} caratteri, ` +
      `${dati.pagine} ${window.cc.plurale(dati.pagine, "pagina", "pagine")}`,
    estrattoDi(dati.testo)
  );
  mostraAvvisi(file.name, dati.segnaposto_preesistenti);
  aggiornaMetriche(dati.totali);
}

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

svuota.addEventListener("click", async () => {
  // Una conferma, perché il gesto non si disfa: il fascicolo vive solo nella
  // memoria del processo, quindi qui non c'è niente da recuperare dopo.
  const quanti = metriche.documenti.textContent;
  const messaggio =
    `Butto via il fascicolo con ${quanti} ` +
    `${window.cc.plurale(Number(quanti), "documento", "documenti")}? ` +
    "Il testo vive solo nella memoria di questo programma: non si torna indietro.";
  if (!window.confirm(messaggio)) {
    return;
  }
  const esito = await window.cc.chiedi(ROTTA_STATO, undefined, "DELETE");
  if (!esito.ok) {
    statoAnalisi.textContent = esito.errore;
    return;
  }
  esiti.replaceChildren();
  ridisegnaTutto(esito.dati);
});

// --- passo 2: revisione e salvataggio ---------------------------------------
//
// Il testo arriva dal server **già spezzato in segmenti** sulle regioni che la
// mascheratura rivendica, e qui non si fa aritmetica su nessun offset: tagliare
// da questa parte significherebbe tenere una seconda copia di quel calcolo, che
// diverge alla prima differenza fra il modo in cui Python e JavaScript contano
// i caratteri.

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

    const testa = document.createElement("div");
    testa.className = "documento-testa";

    const titolo = document.createElement("h3");
    titolo.textContent = documento.filename;
    titolo.dataset.filename = documento.filename;
    testa.appendChild(titolo);

    // Il bottone porta il `doc_id`, non il nome del file: è il nome a essere
    // scelto dall'utente, e legare la cancellazione a un identificativo
    // stabile costa una riga.
    const togli = document.createElement("button");
    togli.type = "button";
    togli.className = "pillola chiara pericolo togli-documento";
    togli.textContent = "Togli";
    togli.dataset.docId = documento.doc_id;
    togli.dataset.filename = documento.filename;
    testa.appendChild(togli);

    riquadro.appendChild(testa);

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

// Quanti dati usciranno in chiaro. Il numero arriva dal server dentro il
// payload della revisione, non contato qui: contarlo nel JavaScript
// significherebbe tenere una seconda definizione di «esce in chiaro» accanto a
// `tabella_attiva`, e sarebbe quella sbagliata a essere mostrata il giorno in
// cui le due divergono.
function disegnaEsposizione(esposizione) {
  if (esposizione === undefined) {
    return;
  }
  const { in_chiaro: inChiaro, mascherati, categorie: elenco } = esposizione;

  if (inChiaro === 0 && mascherati === 0) {
    riquadroEsposizione.className = "esposizione pulita";
    riquadroEsposizione.textContent =
      "L'analisi non ha trovato dati personali in questi documenti.";
    return;
  }
  if (inChiaro === 0) {
    riquadroEsposizione.className = "esposizione pulita";
    // La frase «in chiaro» non compare qui, e non è una svista: è la frase con
    // cui la pagina allarma, e un riquadro che la usa anche quando va tutto
    // bene insegna a leggerla come rumore. Il giorno che allarma per davvero
    // non la guarda più nessuno.
    riquadroEsposizione.textContent =
      `Tutti i ${mascherati} dati personali trovati diventeranno un segnaposto: ` +
      "nei file che scarichi non ne resta nessuno.";
    return;
  }

  riquadroEsposizione.className = "esposizione espone";
  riquadroEsposizione.replaceChildren();

  // La frase dice **tutte e due** le metà: «di 14 trovati, 3 mascherati e 11 in
  // chiaro» si legge come un bilancio, mentre il solo numero degli esposti si
  // legge come un dettaglio. Chi ha spento quattro interruttori su sei ha
  // bisogno di vedere la proporzione, non il resto.
  const titolo = document.createElement("span");
  titolo.textContent =
    `Di ${mascherati + inChiaro} dati personali trovati, ${mascherati} ` +
    `usciranno mascherati e ${inChiaro} ` +
    (inChiaro === 1 ? "uscirà in chiaro." : "usciranno in chiaro.");
  riquadroEsposizione.appendChild(titolo);

  const spiega = document.createElement("span");
  spiega.className = "dettaglio";
  const nomi = elenco.map((voce) => `${voce.categoria} (${voce.quanti})`).join(", ");
  spiega.textContent =
    `In chiaro: ${nomi}. Riaccendi i loro interruttori per mascherarli, ` +
    "oppure salva così se è quello che vuoi.";
  riquadroEsposizione.appendChild(spiega);
}

// Il nome che `fusioni.js` si aspetta di trovare sulla finestra: la decisione
// su una fusione restituisce il payload della revisione, e ridisegnare con
// questa funzione invece che con una sua copia è ciò che tiene una sola
// definizione di «come si disegna la revisione».
function disegna(revisione) {
  if (!revisione) {
    return;
  }
  disegnaInterruttori(revisione.categorie);
  disegnaDocumenti(revisione.documenti);
  disegnaEsposizione(revisione.esposizione);
  // Ogni tocco agli interruttori annulla l'approvazione lato server: la riga
  // di esito qui va spenta, o continuerebbe a dichiarare salvato un fascicolo
  // che nel frattempo è cambiato.
  statoEsportazione.textContent = "";
  scaricati.replaceChildren();
}

function ridisegnaTutto(stato) {
  if (!stato) {
    return;
  }
  aggiornaMetriche(stato.totali);
  if (stato.documenti.length === 0) {
    categorie.replaceChildren();
    documenti.replaceChildren();
    statoAnalisi.textContent = "";
    disegnaEsposizione({ in_chiaro: 0, mascherati: 0, categorie: [] });
    return;
  }
  disegnaInterruttori(stato.categorie);
  disegnaDocumenti(stato.documenti);
  disegnaEsposizione(stato.esposizione);
}

avvio.addEventListener("click", async () => {
  avvio.disabled = true;
  statoAnalisi.textContent = "Analisi in corso… il testo è in viaggio verso Gemini.";
  const esito = await window.cc.chiedi(ROTTA_ANALISI);
  avvio.disabled = false;
  if (!esito.ok) {
    statoAnalisi.textContent = esito.errore;
    return;
  }
  statoAnalisi.textContent = "";
  disegna(esito.dati);
  vaiA("salva");
});

tornaCarica.addEventListener("click", () => {
  vaiA("carica");
});

// Un gestore solo sul contenitore, e non uno per interruttore: gli interruttori
// vengono ricreati a ogni ridisegno, quindi agganciarli singolarmente
// lascerebbe i gestori attaccati a nodi che non sono più in pagina, e dal
// secondo toggle in poi non succederebbe più niente.
categorie.addEventListener("change", async (evento) => {
  const categoria = evento.target.dataset.categoria;
  if (categoria === undefined) {
    return;
  }
  const esito = await window.cc.chiedi(ROTTA_CATEGORIA, {
    categoria,
    attiva: evento.target.checked,
  });
  if (!esito.ok) {
    statoEsportazione.textContent = esito.errore;
    return;
  }
  disegna(esito.dati);
});

documenti.addEventListener("click", async (evento) => {
  const docId = evento.target.dataset.docId;
  if (docId !== undefined) {
    const nome = evento.target.dataset.filename;
    if (
      !window.confirm(
        `Tolgo ${nome} dal fascicolo? Il testo vive solo nella memoria di ` +
          "questo programma: per riaverlo dovrai ricaricarlo e rianalizzarlo, " +
          "cioè ripagare una chiamata a Gemini."
      )
    ) {
      return;
    }
    const esito = await window.cc.chiedi(
      `${ROTTA_STATO}/documenti/${encodeURIComponent(docId)}`,
      undefined,
      "DELETE"
    );
    if (!esito.ok) {
      statoEsportazione.textContent = esito.errore;
      return;
    }
    ridisegnaTutto(esito.dati);
    statoEsportazione.textContent = "";
    if (esito.dati.documenti.length === 0) {
      vaiA("carica");
    }
    return;
  }

  const tag = evento.target.dataset.tag;
  if (tag === undefined) {
    return;
  }
  // Il verso si legge da ciò che è disegnato: cliccare su un'occorrenza accesa
  // la spegne. Tenerlo in una variabile del JavaScript lo farebbe divergere dal
  // fascicolo appena due ridisegni non coincidessero.
  const attivo = evento.target.dataset.mascherato !== "1";
  const esito = await window.cc.chiedi(ROTTA_TAG, { tag, attivo });
  if (!esito.ok) {
    statoEsportazione.textContent = esito.errore;
    return;
  }
  disegna(esito.dati);
});

// --- il salvataggio ---------------------------------------------------------
//
// Un gesto solo, quattro passaggi: approva, esporta, cifra il vault, scarica.
// L'approvazione era un pulsante a parte ed è diventata parte di questo: è la
// firma che garantisce che il testo esportato sia quello che l'utente ha
// guardato, e nessuno l'ha mai voluta *per sé* — la si premeva perché senza non
// si poteva esportare. L'invariante resta (il testo esce solo firmato); il
// passo che non decideva niente, no.

function confermaSeNienteMascherato() {
  if (categorieAccese > 0) {
    return true;
  }
  return window.confirm(
    "Nessuna categoria è accesa: i file usciranno IN CHIARO, con i dati "
      + "personali come sono nei documenti originali.\n\n"
      + "Se volevi nasconderli, annulla e riaccendi gli interruttori.\n\n"
      + "Salvare lo stesso?"
  );
}

function segnalaScaricato(nome, nota) {
  const riga = document.createElement("li");
  riga.className = "caricato";
  riga.textContent = nome;
  if (nota) {
    const seconda = document.createElement("p");
    seconda.className = "estratto";
    seconda.textContent = nota;
    riga.appendChild(seconda);
  }
  scaricati.appendChild(riga);
}

// Il vault **prima** dei file mascherati, e non è un dettaglio d'ordine. Un
// file mascherato senza il vault che lo accompagna è un viaggio di sola andata:
// i segnaposto non tornano più dati veri una volta chiuso il programma. Se la
// cifratura non si può fare, è meglio non scaricare niente che consegnare
// all'utente dei file che scoprirà irreversibili fra tre giorni.
async function salvaIlVault() {
  let risposta;
  try {
    risposta = await fetch(ROTTA_VAULT_SALVA, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
  } catch (errore) {
    return { ok: false, errore: window.cc.NON_RISPONDE };
  }
  if (!risposta.ok) {
    let corpo = null;
    try {
      corpo = await risposta.json();
    } catch (errore) {
      corpo = null;
    }
    return { ok: false, errore: window.cc.messaggioDiErrore(corpo, risposta.status) };
  }
  return { ok: true, blob: await risposta.blob() };
}

salvaTutto.addEventListener("click", async () => {
  if (!confermaSeNienteMascherato()) {
    return;
  }
  salvaTutto.disabled = true;
  scaricati.replaceChildren();
  anteprimaExport.hidden = true;
  statoEsportazione.textContent = "Preparo i file…";

  try {
    const approvazione = await window.cc.chiedi(ROTTA_APPROVAZIONE);
    if (!approvazione.ok) {
      statoEsportazione.textContent = approvazione.errore;
      return;
    }

    const esportazione = await window.cc.chiedi(ROTTA_ESPORTAZIONE, undefined, "GET");
    if (!esportazione.ok) {
      // Il 409 qui è quasi sempre uno dei due casi del gate: non approvato, o
      // testo cambiato dopo l'approvazione. Il messaggio del dominio lo dice.
      statoEsportazione.textContent = esportazione.errore;
      return;
    }

    const vault = await salvaIlVault();
    if (!vault.ok) {
      statoEsportazione.textContent =
        `Non ho salvato niente: ${vault.errore} — senza il fascicolo cifrato i ` +
        "file mascherati non si potrebbero più ripristinare, quindi non te li do a metà.";
      return;
    }

    const documenti = esportazione.dati.documenti;
    for (const [nome, testo] of Object.entries(documenti)) {
      window.cc.scarica(testo, window.cc.nomeMascherato(nome));
      segnalaScaricato(window.cc.nomeMascherato(nome), "da dare all'IA esterna");
    }
    window.cc.scarica(vault.blob, NOME_FILE_VAULT);
    segnalaScaricato(
      NOME_FILE_VAULT,
      "tienilo: serve per rimettere i dati veri nella risposta dell'IA"
    );

    const quanti = Object.keys(documenti).length;
    statoEsportazione.textContent =
      `Scaricati ${quanti} ${window.cc.plurale(quanti, "file mascherato", "file mascherati")} ` +
      `e il fascicolo cifrato. Il browser potrebbe averti chiesto il permesso per ` +
      `più scaricamenti di fila: se ne manca qualcuno, premi di nuovo.`;
  } finally {
    // Nel `finally` perché ogni uscita di qui deve riaccendere il pulsante: un
    // pulsante rimasto spento dopo un errore lascia l'utente senza alcun modo
    // di riprovare, e la sola strada sarebbe ricaricare la pagina.
    salvaTutto.disabled = false;
  }
});

// --- lo stato al primo disegno ----------------------------------------------
//
// La pagina nasceva sempre vuota e non aveva modo di sapere che il server
// teneva ancora il fascicolo: da lì i sintomi della #50 — la scheda a zero dopo
// un F5, il file ricaricato rifiutato come duplicato, i documenti vecchi che
// riaffioravano al primo «Analizza». Non erano tre bug: era la pagina che non
// chiedeva mai.

async function leggiStato() {
  const esito = await window.cc.chiedi(ROTTA_STATO, undefined, "GET");
  if (!esito.ok) {
    // All'avvio questo non è allarmante quanto sembra: la pagina può essere
    // aperta da un segnalibro mentre il server non c'è. Si dice, e basta.
    statoAnalisi.textContent = esito.errore;
    return null;
  }
  return esito.dati;
}

leggiStato().then((stato) => {
  if (!stato) {
    return;
  }
  ridisegnaTutto(stato);
  // Chi ricarica la pagina a revisione già fatta torna dove stava: rimandarlo
  // al caricamento gli farebbe credere di aver perso il lavoro, e il gesto
  // istintivo — ricaricare i file — costerebbe una seconda analisi.
  const analizzato =
    stato.documenti.length > 0 && stato.categorie && stato.categorie.length > 0;
  vaiA(analizzato ? "salva" : "carica");
});
