"""Le regex per categoria e le parole chiave che fanno da contesto obbligatorio."""
from __future__ import annotations

import re
from re import Pattern

from cryptocustode.core.models import Category

MESI = (
    "gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|"
    "settembre|ottobre|novembre|dicembre"
)

TOPONIMI = (
    r"via|viale|v\.le|piazza|p\.zza|piazzale|corso|c\.so|largo|vicolo|"
    r"strada|contrada|localit[àa]|borgo|salita|lungomare"
)

SUFFISSI_SOCIETARI = (
    r"s\.?r\.?l\.?|s\.?p\.?a\.?|s\.?n\.?c\.?|s\.?a\.?s\.?|s\.?c\.?a\.?r\.?l\.?"
)

# Articoli e preposizioni che stanno *dentro* un odonimo o una ragione sociale
# ("Via dei Mille", "Banca di Roma S.p.A."): sono minuscoli, quindi la guardia
# sulle maiuscole li scarterebbe troncando il nome. Sono ammessi solo insieme
# ad almeno una parola con l'iniziale maiuscola, che resta obbligatoria.
# Ogni forma precede i propri prefissi (`dello` prima di `del`, `allo` prima di
# `al`, `de` per ultimo della sua famiglia): l'alternanza di `re` è ordinata e
# una forma corta messa davanti a una lunga la nasconderebbe. Le famiglie
# `dello`/`de'`/`de` e `al`/`ai`/`agli`/`alla`/`allo` sono indispensabili: senza
# di loro odonimi comunissimi ("Via dello Sport", "Via de' Tornabuoni",
# "Via ai Prati") non producevano alcuno span e finivano in chiaro. `del` non
# può coprire `dello`, perché al connettivo deve seguire `\s+` e dopo `del`
# viene una `l`; `dei` e `d'` non coprono `de'`.
# Le famiglie `all'`/`alle` e `sul`/`sulla` (ruling C1) chiudono una fuga
# totale: "Via alle Fonti 7" non produceva alcuno span e "Via all'Aeroporto 3,
# 10121 Torino" lasciava in chiaro toponimo e CAP. `allo`/`alla`/`agli`/`ai`/`al`
# c'erano già, ma `alle` e `all'` no, e nessuna forma della famiglia `sul`.
CONNETTIVI = (
    r"dell'|della|delle|dello|degli|dei|del|de'|de|"
    r"dall'|dalla|dalle|dagli|dal|"
    r"all'|alle|allo|alla|agli|ai|al|"
    r"sull'|sulla|sulle|sugli|sui|sul|"
    r"di|da|d'|gli|il|lo|la|le|l'"
)

# Un connettivo è seguito da spazio, tranne quando finisce per apostrofo
# ("Via Massimo d'Azeglio"), dove lo spazio non c'è.
_CONNETTIVO = rf"(?:{CONNETTIVI})(?:\s+|(?<=')\s*)"

# L'iniziale deve essere davvero maiuscola: il gruppo a flag locale
# `(?-i:...)` disattiva `re.IGNORECASE` solo su quel carattere.
# L'intervallo comprende anche le maiuscole accentate, perché il corpo della
# parola le ammetteva già e un'iniziale sola ASCII lasciava senza span odonimi
# come "Via Élia" o "Località Èboli". `Ø-Þ` è staccato da `À-Ö` di proposito:
# U+00D7 è il segno di moltiplicazione, non una lettera, e `À-Þ` lo includerebbe.
_INIZIALE_MAIUSCOLA = r"(?-i:[A-ZÀ-ÖØ-Þ])"
_PAROLA_INDIRIZZO = rf"{_INIZIALE_MAIUSCOLA}[\w'À-ÿ]*"
_PAROLA_AZIENDA = rf"{_INIZIALE_MAIUSCOLA}[\w'À-ÿ&.]*"

PATTERN: dict[Category, Pattern[str]] = {
    Category.CF: re.compile(
        r"\b[A-Z]{6}[0-9LMNPQRSTUV]{2}[ABCDEHLMPRST][0-9LMNPQRSTUV]{2}"
        r"[A-Z][0-9LMNPQRSTUV]{3}[A-Z]\b"
    ),
    # Lo `\s?` è voluto: i documenti reali raggruppano i caratteri dell'IBAN
    # ("IT60 X054 2811 ...") e `iban_valido` normalizza gli spazi. La coda vorace
    # può inglobare la parola successiva se è in maiuscolo: a disambiguare è il
    # checksum, con il ritaglio progressivo in `rules.py`.
    Category.IBAN: re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[0-9A-Z]){11,30}\b"),
    Category.PIVA: re.compile(r"\b(?:IT)?\d{11}\b"),
    Category.EMAIL: re.compile(
        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
    ),
    # I separatori (spazio, punto, trattino, slash) possono ripetersi fra le
    # cifre: la spec §6 li elenca senza limitarne il numero, mentre le due
    # forme nazionali ne ammettevano rispettivamente due e uno, e numeri
    # scritti a gruppi ("011 123 45 67", "02 1234 5678", "340 123 45 67") non
    # producevano alcuno span nemmeno *con* la parola chiave di contesto
    # accanto (ruling I2). Il conteggio complessivo resta a
    # `_telefono_plausibile` (9-11 cifre) e il requisito di contesto resta il
    # cancello: non si apre alcuna valanga.
    # Ogni ramo è chiuso da `\b`, così la corsa di cifre non si ferma in mezzo
    # a un numero più lungo né scavalca uno spazio (o un a capo
    # dell'estrazione PDF) finendo *dentro* la parola che segue.
    #
    # Il ramo dei fissi era anche pigro, e questo era un difetto: il suo
    # prefisso è lungo 2-4 cifre ma il minimo della ripetizione è fisso a 6,
    # quindi con un prefisso a due cifre la corsa pigra si fermava al primo
    # `\b` utile — 8 cifre in tutto, sotto il pavimento di 9 di
    # `_telefono_plausibile` — e i fissi di Milano e Roma scritti a gruppi
    # corti ("02 12 34 56 78") non producevano alcuno span pur avendo la
    # parola chiave accanto (issue #14). Ora è vorace, come quella dell'IBAN e
    # per la stessa ragione: la regex prende il più possibile e la lunghezza
    # esatta del valore la decide il validatore, con il ritaglio progressivo
    # di `rules.py` che riporta indietro la coda di troppo. Il pavimento del
    # ritaglio è per categoria proprio perché questo percorso funzioni anche
    # per il telefono.
    #
    # Il ramo dei cellulari resta pigro e va bene così: il suo prefisso è di
    # lunghezza fissa (`3\d{2}`), quindi il minimo della ripetizione fa 9
    # cifre esatte e non può scendere sotto la soglia del validatore.
    Category.TELEFONO: re.compile(
        # Il `\b` in coda vale per il prefisso internazionale quanto per gli
        # altri due rami, e qui mancava (issue #14): la corsa vorace arrivava a
        # dieci cifre nazionali mangiandosi la prima cifra di ciò che seguiva
        # ("+39 340 123456 1" davanti a "14/03/2024"). Il conteggio restava nei
        # 9-11 della spec §6, quindi il validatore accettava lo span sbagliato,
        # e la priorità P2 del telefono faceva scartare a `risolvi` l'intero
        # span DATA: la data restava in chiaro accanto a un numero storpiato.
        # Con il confine la corsa torna indietro di una cifra e i due valori
        # diventano due span distinti.
        r"(?:\+39|0039)[\s.\-/]?\d(?:[\s.\-/]?\d){8,9}\b"
        r"|\b3\d{2}(?:[\s.\-/]?\d){6,8}?\b"
        # Il prefisso interurbano può stare fra parentesi ("(011) 1234567"):
        # `\b` non serve nella variante con la parentesi aperta, perché fra uno
        # spazio e `(` non c'è alcun confine di parola.
        r"|(?:\(0\d{1,3}\)|\b0\d{1,3})(?:[\s.\-/]?\d){6,9}\b"
    ),
    Category.CATASTO: re.compile(
        # Alternanza esplicita: la spec §6 nomina sia `foglio` sia l'abbreviazione
        # `fg`, che una forma con la `l` obbligatoria non potrebbe mai matchare.
        r"(?:foglio|fogli|fog|fg)[\s.:n°]*\d{1,4}.{0,40}?"
        r"(?:part(?:icella)?|mapp(?:ale)?)[\s.:n°]*\d{1,5}"
        r"(?:[\s,]*sub\.?[\s.:n°]*\d{1,4})?",
        re.IGNORECASE | re.DOTALL,
    ),
    Category.PRATICA: re.compile(
        r"(?:pratica|fascicolo|prot(?:ocollo)?|rif(?:erimento)?)"
        # L'identificativo non può chiudersi con punteggiatura: altrimenti il
        # punto che termina la frase entra nello span e il masking se lo mangia.
        r"[\s.:n°/\-]{0,6}([A-Za-z0-9][A-Za-z0-9/._\-]{1,19}[A-Za-z0-9])",
        re.IGNORECASE,
    ),
    Category.DATA: re.compile(
        r"\b\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4}\b"
        r"|\b\d{4}-\d{2}-\d{2}\b"
        rf"|\b\d{{1,2}}\s+(?:{MESI})\s+\d{{4}}\b",
        re.IGNORECASE,
    ),
    Category.IMPORTO: re.compile(
        # La parte numerica alterna due forme: raggruppamento a migliaia
        # (`\d{1,3}(?:\.\d{3})+`) oppure cifre libere (`\d+`), in
        # quest'ordine — l'alternanza è ordinata e "12.345,67" deve restare
        # intero invece di degradare al ramo `\d+` fermandosi a "12". Senza
        # il ramo `\d+`, una sequenza di 4+ cifre senza punti di separazione
        # ("12345 EUR") non era rappresentabile affatto: sul primo ramo
        # mancava lo span, sul secondo (prima del lookbehind sotto) veniva
        # storpiato in "€123".
        # Il confine sta *dentro* l'alternanza, sulle sole forme alfabetiche.
        # Con `\b` dopo tutta l'alternanza il ramo del simbolo era
        # inservibile, perché `€` non è un carattere di parola e `\b`
        # pretendeva quindi una lettera o una cifra subito dopo: "1.250,00 €" e
        # "800€" non producevano alcuno span, mentre l'assurdo "1.250,00€netti"
        # sì (ruling C2). Sulle forme alfabetiche il confine serve e resta, ma
        # come "nessuna lettera dopo" invece di `\b`: quel che va tenuto fuori
        # è "eurodollaro", mentre "EUR100" — cifre attaccate alla sigla — è un
        # importo e con `\b` avrebbe smesso di essere riconosciuto.
        r"(?:€|(?:EUR|euro)(?![A-Za-zÀ-ÿ]))"
        r"\s?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?"
        # `(?![\d.,]*\d)` chiude a destra i decimali: senza confine
        # "€ 12.345,678" veniva troncato in "€ 12.345,67" e la terza cifra
        # restava in chiaro accanto a un importo storpiato (ruling I3). Con il
        # lookahead il match fallisce del tutto: un importo o è preso intero o
        # non è preso, mai a metà.
        r"(?![\d.,]*\d)"
        # `(?<![\d.,])` impedisce di agganciare la coda di un numero più lungo:
        # senza confine a sinistra "12345 EUR" produceva lo span "345 EUR",
        # cioè un importo storpiato e le due cifre iniziali in chiaro.
        r"|(?<![\d.,])(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?(?![\d.,]*\d)"
        r"\s?(?:€|(?:EUR|euro)(?![A-Za-zÀ-ÿ]))",
        re.IGNORECASE,
    ),
    # `re.IGNORECASE` resta perché gli indirizzi e le ragioni sociali tutti in
    # maiuscolo sono reali ("VIA GARIBALDI 42"), ma la sequenza di nomi deve
    # contenere almeno una parola con l'iniziale davvero maiuscola: senza quel
    # vincolo "via email dal cliente" diventava un indirizzo e "centro
    # benessere spa" un'azienda. Pretenderla su *ogni* parola era però troppo,
    # perché troncava "Via dei Mille": i connettivi minuscoli sono ammessi.
    Category.INDIRIZZO: re.compile(
        rf"\b(?:{TOPONIMI})\s+"
        # connettivi iniziali ("Via dei Mille"), poi la parola maiuscola
        # obbligatoria, poi altre parole con connettivi facoltativi in mezzo.
        # Ogni ripetizione è limitata: nessuna sequenza illimitata.
        rf"(?:{_CONNETTIVO}){{0,2}}{_PAROLA_INDIRIZZO}"
        rf"(?:\s+(?:{_CONNETTIVO}){{0,2}}{_PAROLA_INDIRIZZO}){{0,3}}"
        # Civico facoltativo. `(?!\d)` è indispensabile: su "Via Roma 10121
        # Torino" senza civico il gruppo si mangiava quattro delle cinque cifre
        # del CAP ("Via Roma 1012"), storpiando l'indirizzo e lasciando in
        # chiaro l'ultima cifra. Con il lookahead il gruppo, che è opzionale,
        # fallisce del tutto e lascia il CAP intero al gruppo successivo.
        # Il suffisso del civico ("12/A", "12 bis", "12-14") è un gruppo a sé:
        # `[a-zA-Z]?` attaccato alle cifre non poteva attraversare un
        # separatore, quindi su "Via Roma 12/A, 10121 Torino" lo span si
        # fermava a "Via Roma 12" e il gruppo del CAP non riusciva più ad
        # agganciarsi: restavano in chiaro il suffisso, il CAP *e* il comune
        # (ruling I1). Ogni alternativa ha il proprio confine a destra, così il
        # suffisso non si mangia l'inizio della parola successiva.
        r"(?:,?\s*n?\.?\s*\d{1,4}(?!\d)"
        r"(?:\s*[/\-]\s*\d{1,3}(?!\d)|\s*[/\-]?\s*[a-zA-Z](?!\w)"
        r"|\s+(?:bis|ter|quater)(?!\w))?)?"
        # Interno, scala e piano, facoltativi e fra il civico e il CAP ("Via
        # Roma 12 int. 3, 10121 Torino"): il gruppo del CAP pretende le cinque
        # cifre subito dopo il civico, quindi con l'interno in mezzo non si
        # agganciava e — essendo facoltativo — si arrendeva senza consumare
        # nulla. Lo span si fermava a "Via Roma 12" e CAP e comune restavano in
        # chiaro (issue #15). `int.` è comunissimo negli indirizzi italiani.
        # `piano` è la stessa fuga con un'altra parola, ed è stato aggiunto qui
        # (issue #22): la #15 si era fermata a interno e scala, e "Via Roma 12
        # int. 3 piano 2, 10121 Torino" si troncava a "Via Roma 12 int. 3"
        # mentre "Via Roma 12 piano 2, 10121 Torino", senza interno, si
        # troncava a "Via Roma 12". La correzione è una voce in più in questa
        # alternativa, non un allentamento dell'adiacenza: il gruppo del CAP
        # continua a pretendere le cinque cifre subito dopo, e ciò che sta in
        # mezzo deve essere una di queste forme chiuse. Ammettere invece "testo
        # breve qualunque" fra civico e CAP era la strada già esplorata e
        # scartata dalla #15, perché rende l'indirizzo vorace su testo che non
        # gli appartiene — difetto peggiore di quello chiuso.
        # Il gruppo non può allargare l'indirizzo a testo qualunque: la parola
        # chiave è obbligatoria e chiusa da `(?!\w)` (così "sca" non passa per
        # `sc` e "pianoforte" non passa per `piano`), e le è obbligatorio un
        # identificativo breve — poche cifre oppure una lettera sola con il
        # proprio confine a destra. È l'identificativo obbligatorio che tiene
        # fuori la prosa dove `piano` è una parola comune nel senso di progetto
        # ("piano di ristrutturazione", "piano regolatore") o regge un aggettivo
        # ("piano nobile"): lì il gruppo fallisce del tutto e l'indirizzo
        # preferisce troncarsi invece di inghiottire testo che non è un dato
        # personale. Le due ripetizioni ammesse coprono la forma composta
        # ("sc. B int. 3", "int. 3 piano 2"); nessuna sequenza illimitata.
        # `\d{1,4}(?!\d)` è lo stesso confine del civico e serve alla stessa
        # cosa: su "Via Roma int. 10121 Torino" impedisce all'identificativo di
        # mangiare quattro delle cinque cifre del CAP. Il gruppo, facoltativo,
        # fallisce del tutto e lascia il CAP intero a chi viene dopo.
        r"(?:,?\s*(?:int(?:erno)?|sc(?:ala)?|piano)(?!\w)\.?\s*"
        r"(?:\d{1,4}(?!\d)|[a-zA-Z](?!\w))){0,2}"
        # CAP e comune facoltativi (spec §6): il toponimo resta obbligatorio,
        # quindi un CAP da solo non genera mai uno span.
        rf"(?:,?\s*\d{{5}}\b(?:\s+{_PAROLA_INDIRIZZO})?)?",
        re.IGNORECASE,
    ),
    # La ragione sociale parte da una parola maiuscola e i connettivi stanno
    # solo tra due parole maiuscole: così "Banca di Roma S.p.A." resta intera
    # invece di ridursi a "Roma S.p.A".
    Category.AZIENDA: re.compile(
        rf"\b{_PAROLA_AZIENDA}"
        rf"(?:\s+(?:{_CONNETTIVO}){{0,2}}{_PAROLA_AZIENDA}){{0,3}}"
        rf"\s+(?:{SUFFISSI_SOCIETARI})\b",
        re.IGNORECASE,
    ),
}

# Categorie che richiedono una parola chiave vicina per non generare falsi positivi
# a valanga su qualunque numero lungo del documento (spec §6).
PAROLE_CONTESTO: dict[Category, tuple[str, ...]] = {
    Category.PIVA: (
        "p. iva",
        "p.iva",
        "partita iva",
        "p.i.",
        "vat",
        # Il codice fiscale di una società è un numero di undici cifre identico
        # per forma alla P.IVA, e nei documenti italiani è quasi sempre
        # introdotto da queste diciture invece che da "P. IVA" (issue #32).
        # Il checksum resta il cancello: queste aprono la porta, non decidono
        # chi entra.
        "codice fiscale",
        "cod. fisc.",
        "cod.fisc.",
        "c.f.",
        "cf",
        "partita i.v.a.",
        "p. i.v.a.",
        "piva",
    ),
    # `telefono` e `cellulare` non sono più qui: li copre `PREFISSI_CONTESTO`,
    # che ne prende anche le forme flesse. Restano qui le sigle che devono
    # essere parole intere, perché come prefisso diventerebbero voraci: `tel`
    # dentro `telaio`, `cell` dentro `particella`.
    Category.TELEFONO: ("tel", "telef.", "cell", "fax", "mobile"),
}

PREFISSI_CONTESTO: dict[Category, tuple[str, ...]] = {
    # Parole di contesto che ammettono un suffisso, perché la morfologia
    # italiana è aperta e un elenco di forme flesse è sempre incompleto:
    # `telefonico`, `telefonica`, `telefoniche`, `telefoni`, `telefonia`
    # (issue #32). La radice `telefon` è sicura perché ogni parola italiana
    # che comincia così parla di telefoni. `tel` **non** lo è, ed è per questo
    # che sta fra le parole intere: "numero di telaio" è una dicitura reale
    # dei documenti dei veicoli e non deve fare da contesto a un numero.
    Category.TELEFONO: ("telefon", "cellular", "telefax"),
}

FINESTRA_CONTESTO = 30
