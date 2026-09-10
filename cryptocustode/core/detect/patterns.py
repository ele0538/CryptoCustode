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
CONNETTIVI = (
    r"dell'|della|delle|dello|degli|dei|del|de'|de|"
    r"dall'|dalla|dalle|dagli|dal|"
    r"allo|alla|agli|ai|al|"
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
    Category.TELEFONO: re.compile(
        r"(?:\+39|0039)[\s.\-/]?\d(?:[\s.\-/]?\d){8,9}"
        r"|\b3\d{2}[\s.\-/]?\d{3}[\s.\-/]?\d{3,4}\b"
        r"|\b0\d{1,3}[\s.\-/]?\d{6,8}\b"
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
        r"(?:€|EUR|euro)\s?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2})?"
        # `(?<![\d.,])` impedisce di agganciare la coda di un numero più lungo:
        # senza confine a sinistra "12345 EUR" produceva lo span "345 EUR",
        # cioè un importo storpiato e le due cifre iniziali in chiaro.
        r"|(?<![\d.,])(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2})?\s?(?:€|EUR|euro)\b",
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
        r"(?:,?\s*n?\.?\s*\d{1,4}(?!\d)[a-zA-Z]?)?"
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
    Category.PIVA: ("p. iva", "p.iva", "partita iva", "p.i.", "vat"),
    Category.TELEFONO: ("tel", "telefono", "cell", "cellulare", "fax", "mobile"),
}

FINESTRA_CONTESTO = 30
