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
        r"(?:€|EUR|euro)\s?\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?"
        # `(?<![\d.,])` impedisce di agganciare la coda di un numero più lungo:
        # senza confine a sinistra "12345 EUR" produceva lo span "345 EUR",
        # cioè un importo storpiato e le due cifre iniziali in chiaro.
        r"|(?<![\d.,])\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?\s?(?:€|EUR|euro)\b",
        re.IGNORECASE,
    ),
    # `re.IGNORECASE` resta perché gli indirizzi e le ragioni sociali tutti in
    # maiuscolo sono reali ("VIA GARIBALDI 42"), ma le iniziali della sequenza
    # di nomi devono essere davvero maiuscole: il gruppo `(?-i:[A-Z])` disattiva
    # localmente il flag. Senza di esso "via email dal cliente" diventava un
    # indirizzo e "centro benessere spa" un'azienda.
    Category.INDIRIZZO: re.compile(
        rf"\b(?:{TOPONIMI})\s+(?:(?-i:[A-Z])[\w'À-ÿ]*\s?){{1,4}}"
        r"(?:,?\s*n?\.?\s*\d{1,4}[a-zA-Z]?)?"
        # CAP e comune facoltativi (spec §6): il toponimo resta obbligatorio,
        # quindi un CAP da solo non genera mai uno span.
        r"(?:,?\s*\d{5}\b(?:\s+(?-i:[A-Z])[\w'À-ÿ]*)?)?",
        re.IGNORECASE,
    ),
    Category.AZIENDA: re.compile(
        rf"\b(?:(?-i:[A-Z])[\w'À-ÿ&.]*\s+){{1,4}}(?:{SUFFISSI_SOCIETARI})\b",
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
