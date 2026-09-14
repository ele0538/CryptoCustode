// Esercita cryptocustode/ui/app.js fuori dal browser (issue #3).
//
// Non c'è infrastruttura JavaScript in questo repo, e la conseguenza misurata è
// che tre rotture da un solo token nella UI lasciavano la suite verde: il campo
// multipart rinominato, un id che non esiste nella pagina, e una risposta senza
// corpo JSON che uccideva la fila dei file senza dire niente all'utente.
//
// Questo harness carica il vero `app.js` — non una copia, non una riscrittura —
// dentro un DOM finto e con una `fetch` programmata, esegue il gestore del
// submit e stampa su stdout quello che l'utente avrebbe visto. I test Python lo
// invocano con il nome di uno scenario e asseriscono su quel JSON.
//
// Quello che l'harness NON prova: il rendering, il CSS, e che il browser esegua
// la pagina. Quello resta un controllo umano.

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { runInThisContext } from "node:vm";

const scenario = process.argv[2];
const radice = join(dirname(fileURLToPath(import.meta.url)), "..");

function elementoFinto(nome) {
  const elemento = {
    nome,
    className: "",
    textContent: "",
    files: [],
    value: "",
    // `dataset`, `checked` e `replaceChildren` sono arrivati con la revisione
    // (issue #4): gli interruttori sono caselle di spunta, le evidenziazioni
    // portano il proprio tag in `data-tag`, e ogni toggle ridisegna da capo
    // la pagina invece di ritoccarla. Sono aggiunte: nessuno scenario del
    // caricamento le usa, e il loro comportamento non è cambiato.
    dataset: {},
    checked: false,
    figli: [],
    gestori: {},
    // `classList` come nel DOM: la card di caricamento la usa per lo stato
    // "trascinando" durante il drag-and-drop.
    classi: new Set(),
    classList: {
      add(nome) {
        this.classi.add(nome);
      },
      remove(nome) {
        this.classi.delete(nome);
      },
      classi: null,
    },
    appendChild(figlio) {
      this.figli.push(figlio);
    },
    replaceChildren(...figli) {
      this.figli = figli;
    },
    addEventListener(evento, gestore) {
      this.gestori[evento] = gestore;
    },
  };
  elemento.classList.classi = elemento.classi;
  return elemento;
}

const elementi = new Map();
globalThis.document = {
  getElementById(id) {
    if (!elementi.has(id)) {
      elementi.set(id, elementoFinto(id));
    }
    return elementi.get(id);
  },
  createElement(tag) {
    return elementoFinto(tag);
  },
};

globalThis.FormData = class {
  constructor() {
    this.parti = [];
  }
  append(nome, valore) {
    this.parti.push([nome, valore]);
  }
};

const CARICATO = {
  stato: 201,
  json: {
    doc_id: "d_1",
    filename: "uno.txt",
    testo: "Il sig. Rossi è a Torino, in via Roma 1, e paga 1.200,00 euro.",
    caratteri: 61,
    pagine: 1,
    documenti_nel_fascicolo: 1,
    massimo_documenti: 10,
    segnaposto_preesistenti: [],
  },
};

// --- Revisione (issue #4) ---------------------------------------------------
//
// Il testo e gli offset sono quelli che la route servirebbe davvero: i segmenti
// concatenati ricompongono `TESTO_REVISIONE` carattere per carattere, che è la
// proprietà su cui poggia tutta la revisione (spec §2 decisione 2).
const TESTO_REVISIONE = "Il sig. Mario Rossi paga 1.200,00 euro.";
const TAG_PERSONA = "[PERSONA_1]";
const TAG_IMPORTO = "[IMPORTO_1]";

function revisioneFinta({ persona = true, importo = true } = {}) {
  return {
    stato: "PENDING_REVIEW",
    categorie: [
      { categoria: "PERSONA", attiva: persona, quanti: 1 },
      { categoria: "IMPORTO", attiva: importo, quanti: 1 },
    ],
    documenti: [
      {
        doc_id: "d_uno",
        filename: "uno.txt",
        segmenti: [
          { testo: "Il sig. ", tag: null, categoria: null, mascherato: false, segnaposto: null },
          {
            testo: "Mario Rossi", tag: TAG_PERSONA, categoria: "PERSONA",
            mascherato: persona, segnaposto: TAG_PERSONA,
          },
          { testo: " paga ", tag: null, categoria: null, mascherato: false, segnaposto: null },
          {
            testo: "1.200,00 euro", tag: TAG_IMPORTO, categoria: "IMPORTO",
            mascherato: importo, segnaposto: TAG_IMPORTO,
          },
          { testo: ".", tag: null, categoria: null, mascherato: false, segnaposto: null },
        ],
      },
    ],
  };
}

// `json` assente significa: la risposta non ha un corpo JSON, e `risposta.json()`
// rigetta. È il caso del 500 non gestito, servito come testo.
//
// Gli scenari del caricamento (issue #3) sono **liste** di risposte e guidano
// l'invio del modulo. Quelli della revisione (issue #4) sono **oggetti** con un
// campo `eventi`, perché la revisione non ha un modulo da inviare ma bottoni e
// interruttori da premere in sequenza. I due tipi di valore sono il modo in cui
// il driver in fondo al file sa quale dei due giri eseguire, e nessuno dei due
// vede l'altro: aggiungere uno scenario di revisione non può cambiare quello
// che i sette test del caricamento osservano.
const SCENARI = {
  // Due caricamenti con numeri diversi: le metriche del fascicolo devono
  // sommare pagine, caratteri e avvisi, e prendere i documenti dal payload.
  metriche: [
    CARICATO,
    {
      stato: 201,
      json: {
        ...CARICATO.json,
        filename: "due.txt",
        caratteri: 40,
        pagine: 3,
        documenti_nel_fascicolo: 2,
        segnaposto_preesistenti: [
          { posizione: 4, segnaposto: "[PERSONA_1]" },
          { posizione: 20, segnaposto: "[LUOGO_2]" },
        ],
      },
    },
  ],
  // I file lasciati cadere sulla card seguono la stessa strada del modulo.
  trascinamento: [CARICATO],
  "corpo-non-json": [
    CARICATO,
    { stato: 500 },
    CARICATO,
  ],
  "dettaglio-di-validazione": [{ stato: 422, json: { detail: "campo mancante: file" } }],
  "tetto-dal-payload": [
    {
      stato: 201,
      json: { ...CARICATO.json, documenti_nel_fascicolo: 3, massimo_documenti: 7 },
    },
  ],
  "avvisi-molti": [
    {
      stato: 201,
      json: {
        ...CARICATO.json,
        segnaposto_preesistenti: Array.from({ length: 8 }, (_, indice) => ({
          posizione: indice * 10,
          segnaposto: `[PERSONA_${indice + 1}]`,
        })),
      },
    },
  ],
  "server-chiuso": [{ rete: false }],

  "revisione-analisi": {
    risposte: [{ stato: 200, json: revisioneFinta() }],
    eventi: [{ su: "avvia-analisi", tipo: "click" }],
  },
  "revisione-categoria-spenta": {
    risposte: [
      { stato: 200, json: revisioneFinta() },
      { stato: 200, json: revisioneFinta({ persona: false }) },
    ],
    eventi: [
      { su: "avvia-analisi", tipo: "click" },
      // Il bersaglio non è inventato: viene cercato fra gli elementi che la
      // pagina ha appena disegnato, quindi il test fallisce anche se
      // l'interruttore c'è ma non porta la categoria nel suo `dataset`.
      {
        su: "categorie", tipo: "change",
        cerca: { categoria: "PERSONA" }, imposta: { checked: false },
      },
    ],
  },
  "revisione-tag-spento": {
    risposte: [
      { stato: 200, json: revisioneFinta() },
      { stato: 200, json: revisioneFinta({ importo: false }) },
    ],
    eventi: [
      { su: "avvia-analisi", tipo: "click" },
      { su: "documenti", tipo: "click", cerca: { tag: TAG_IMPORTO } },
    ],
  },
  "revisione-analisi-rifiutata": {
    risposte: [{ stato: 422, json: { errore: "non c'è nessun documento da analizzare" } }],
    eventi: [{ su: "avvia-analisi", tipo: "click" }],
  },
};

const copione = SCENARI[scenario];
if (copione === undefined) {
  console.error(`scenario sconosciuto: ${scenario}`);
  process.exit(2);
}

// Gli scenari del caricamento sono liste di risposte; quelli della revisione
// portano le risposte in `risposte` e gli eventi da premere in `eventi`.
const programmate = Array.isArray(copione) ? copione : copione.risposte;

const tentativi = [];
let indice = 0;
globalThis.fetch = async (url, opzioni) => {
  // Il caricamento manda un `FormData`, la revisione una stringa JSON: la
  // ricerca della parte vale solo per il primo, e il ramo che segue lascia
  // intatto quello che i sette test del caricamento leggono.
  const corpo = opzioni.body;
  const parti = corpo === undefined || typeof corpo === "string" ? undefined : corpo.parti;
  const parte = parti === undefined ? undefined : parti.find(([nome]) => nome === "file");
  tentativi.push({
    url,
    metodo: opzioni.method,
    campo: parte === undefined ? null : parte[0],
    file: parte?.[1]?.name,
    corpo: typeof corpo === "string" ? corpo : null,
  });
  const risposta = programmate[Math.min(indice++, programmate.length - 1)];
  if (risposta.rete === false) {
    throw new TypeError("fetch failed");
  }
  return {
    ok: risposta.stato < 400,
    status: risposta.stato,
    json: async () => {
      if (risposta.json === undefined) {
        throw new SyntaxError("Unexpected token 'I', \"Internal S\"... is not valid JSON");
      }
      return risposta.json;
    },
  };
};

runInThisContext(readFileSync(join(radice, "cryptocustode", "ui", "app.js"), "utf8"));

async function eseguiCaricamento() {
  const modulo = document.getElementById("modulo-caricamento");
  const scelta = document.getElementById("scelta-file");
  scelta.files = ["uno.txt", "due.txt", "tre.txt"]
    .slice(0, Math.max(programmate.length, 1))
    .map((name) => ({ name }));

  // Il conteggio dei file scelti si aggiorna al `change` dell'input, prima del submit.
  if (scelta.gestori.change !== undefined) {
    scelta.gestori.change({ target: scelta });
  }
  const fileSceltiDopoLaScelta = document.getElementById("file-scelti").textContent;

  if (scenario === "trascinamento") {
    // Niente submit: i file arrivano lasciati cadere sulla card di caricamento.
    const card = document.getElementById("card-caricamento");
    await card.gestori.drop({
      preventDefault() {},
      dataTransfer: { files: scelta.files },
    });
  } else {
    await modulo.gestori.submit({ preventDefault() {} });
  }

  const esiti = document.getElementById("esiti");
  return {
    righe: esiti.figli.map((riga) => ({
      classe: riga.className,
      testo: riga.textContent,
      dettaglio: riga.figli.length > 0 ? riga.figli[0].textContent : null,
    })),
    conteggio: document.getElementById("conteggio").textContent,
    tentativi,
    scelta_svuotata: scelta.value === "",
    file_scelti: fileSceltiDopoLaScelta,
    metriche: {
      documenti: document.getElementById("metrica-documenti").textContent,
      pagine: document.getElementById("metrica-pagine").textContent,
      caratteri: document.getElementById("metrica-caratteri").textContent,
      avvisi: document.getElementById("metrica-avvisi").textContent,
    },
  };
}

// --- Revisione (issue #4) ---------------------------------------------------

function* discendenti(elemento) {
  for (const figlio of elemento.figli) {
    yield figlio;
    yield* discendenti(figlio);
  }
}

function cerca(radiceElemento, criteri) {
  for (const nodo of discendenti(radiceElemento)) {
    if (Object.entries(criteri).every(([chiave, valore]) => nodo.dataset[chiave] === valore)) {
      return nodo;
    }
  }
  return undefined;
}

async function eseguiRevisione() {
  for (const evento of copione.eventi) {
    const contenitore = document.getElementById(evento.su);
    const gestore = contenitore.gestori[evento.tipo];
    if (gestore === undefined) {
      console.error(`nessun gestore "${evento.tipo}" su "${evento.su}"`);
      process.exit(3);
    }
    // Senza `cerca` il bersaglio è il contenitore stesso (è il caso del
    // bottone). Con `cerca`, il bersaglio va **trovato fra i nodi che la
    // pagina ha disegnato**: un rendering che non porta l'identificativo
    // dello span o il nome della categoria nel `dataset` fa fallire qui,
    // invece di lasciar passare un evento sintetico che nessun utente
    // potrebbe produrre.
    let bersaglio = contenitore;
    if (evento.cerca !== undefined) {
      bersaglio = cerca(contenitore, evento.cerca);
      if (bersaglio === undefined) {
        console.error(
          `nessun elemento in "${evento.su}" con ${JSON.stringify(evento.cerca)}`
        );
        process.exit(3);
      }
    }
    Object.assign(bersaglio, evento.imposta ?? {});
    await gestore({ target: bersaglio, preventDefault() {} });
  }

  const documenti = document.getElementById("documenti");
  return {
    stato: document.getElementById("stato-analisi").textContent,
    testo_atteso: TESTO_REVISIONE,
    // L'ultimo payload servito dalla `fetch` programmata, riportato tale e
    // quale: è quello che un test Python confronta, per forma, con il payload
    // che la rotta vera manda. Senza quel confronto uno scenario invecchiato
    // eserciterebbe la UI contro una forma immaginaria restando verde.
    payload_servito: programmate.at(-1).json ?? null,
    interruttori: [...discendenti(document.getElementById("categorie"))]
      .filter((nodo) => nodo.dataset.categoria !== undefined)
      .map((nodo) => ({ categoria: nodo.dataset.categoria, acceso: nodo.checked })),
    documenti: documenti.figli.map((riquadro) => {
      const nodi = [...discendenti(riquadro)];
      const titolo = nodi.find((nodo) => nodo.dataset.filename !== undefined);
      const corpo = nodi.find((nodo) =>
        nodo.className.split(" ").includes("testo-originale")
      );
      return {
        filename: titolo === undefined ? null : titolo.textContent,
        // `elemento` è il nome del tag HTML disegnato (`mark` o `span`); `tag`
        // è il tag di dominio della revisione (`[PERSONA_1]`, ...). Sono due
        // cose diverse che condividevano il nome per un caso di vocabolario:
        // qui restano distinte, altrimenti la seconda sovrascriverebbe la
        // prima nell'oggetto letterale.
        segmenti: (corpo === undefined ? [] : corpo.figli).map((nodo) => ({
          elemento: nodo.nome,
          classe: nodo.className,
          testo: nodo.textContent,
          tag: nodo.dataset.tag ?? null,
          categoria: nodo.dataset.categoria ?? null,
          mascherato: nodo.dataset.mascherato ?? null,
        })),
      };
    }),
    tentativi,
  };
}

console.log(
  JSON.stringify(Array.isArray(copione) ? await eseguiCaricamento() : await eseguiRevisione())
);
