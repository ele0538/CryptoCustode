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
  return {
    nome,
    className: "",
    textContent: "",
    files: [],
    value: "",
    figli: [],
    gestori: {},
    appendChild(figlio) {
      this.figli.push(figlio);
    },
    addEventListener(evento, gestore) {
      this.gestori[evento] = gestore;
    },
  };
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

// `json` assente significa: la risposta non ha un corpo JSON, e `risposta.json()`
// rigetta. È il caso del 500 non gestito, servito come testo.
const SCENARI = {
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
};

const programmate = SCENARI[scenario];
if (programmate === undefined) {
  console.error(`scenario sconosciuto: ${scenario}`);
  process.exit(2);
}

const tentativi = [];
let indice = 0;
globalThis.fetch = async (url, opzioni) => {
  const parte = opzioni.body.parti.find(([nome]) => nome === "file");
  tentativi.push({ url, campo: parte === undefined ? null : parte[0], file: parte?.[1]?.name });
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

const modulo = document.getElementById("modulo-caricamento");
const scelta = document.getElementById("scelta-file");
scelta.files = ["uno.txt", "due.txt", "tre.txt"]
  .slice(0, Math.max(programmate.length, 1))
  .map((name) => ({ name }));

await modulo.gestori.submit({ preventDefault() {} });

const esiti = document.getElementById("esiti");
console.log(
  JSON.stringify({
    righe: esiti.figli.map((riga) => ({
      classe: riga.className,
      testo: riga.textContent,
      dettaglio: riga.figli.length > 0 ? riga.figli[0].textContent : null,
    })),
    conteggio: document.getElementById("conteggio").textContent,
    tentativi,
    scelta_svuotata: scelta.value === "",
  })
);
