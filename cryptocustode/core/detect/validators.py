"""Checksum deterministici. Un valore che non supera il controllo non diventa
uno span della sua categoria: al più resta materiale per il NER (spec §6)."""

import re

# Tabelle ufficiali del CIN del codice fiscale.
# Posizioni dispari contando da 1 (1ª, 3ª, ... 15ª).
_DISPARI = {
    "0": 1, "1": 0, "2": 5, "3": 7, "4": 9, "5": 13, "6": 15, "7": 17, "8": 19, "9": 21,
    "A": 1, "B": 0, "C": 5, "D": 7, "E": 9, "F": 13, "G": 15, "H": 17, "I": 19, "J": 21,
    "K": 2, "L": 4, "M": 18, "N": 20, "O": 11, "P": 3, "Q": 6, "R": 8, "S": 12, "T": 14,
    "U": 16, "V": 10, "W": 22, "X": 25, "Y": 24, "Z": 23,
}

# Posizioni pari: le cifre valgono se stesse, le lettere la loro posizione (A=0).
_PARI = {str(n): n for n in range(10)} | {chr(65 + n): n for n in range(26)}

_FORMA_CF = re.compile(
    r"\A[A-Z]{6}[0-9LMNPQRSTUV]{2}[ABCDEHLMPRST][0-9LMNPQRSTUV]{2}"
    r"[A-Z][0-9LMNPQRSTUV]{3}[A-Z]\Z"
)

# I separatori che nei documenti veri stanno *fra i gruppi* di un codice con
# checksum: lo spazio di qualunque forma e il trattino (issue #37).
_SEPARATORE_DI_GRUPPO = re.compile(r"[\s\-]")


def _codice_normalizzato(valore: str) -> str | None:
    """Il codice senza i separatori fra i gruppi e in maiuscolo, oppure `None`
    se il valore comincia o finisce con un separatore.

    Qui sta l'invariante che regge tutta la issue #37: il checksum si calcola
    sul valore **normalizzato**, così le regex possono ammettere le forme
    spaziate dei documenti veri — "IT60-X054-...", "IT60  X054  ...",
    "RSSMRA 85M01 H501Q" — senza che la verifica si allenti di un bit.
    Allargare il riconoscimento perdendo il controllo sarebbe lo scambio
    peggiore possibile.

    Il rifiuto ai *bordi* è la seconda metà, e non è pignoleria: è ciò che
    tiene lo span esattamente sul codice. `rules.py` accorcia un candidato
    troppo lungo tagliandolo all'**ultimo** separatore, quindi davanti a una
    coppia di spazi ("... 456  PRESSO") il candidato intermedio è "... 456 ",
    con uno spazio rimasto in fondo — e la *lunghezza* del candidato accettato
    è ciò che fissa la fine dello span. Se il validatore accettasse quel
    candidato, lo span coprirebbe un carattere che nel codice non c'è e il
    segnaposto finirebbe attaccato alla parola dopo. Rifiutandolo, il ritaglio
    fa un passo in più e si ferma sul codice.
    """
    if not valore:
        return None
    if _SEPARATORE_DI_GRUPPO.search(valore[0] + valore[-1]):
        return None
    return _SEPARATORE_DI_GRUPPO.sub("", valore).upper()


def cin_atteso(primi_quindici: str) -> str:
    """Calcola il carattere di controllo dai primi 15 caratteri del codice fiscale.

    I caratteri sono usati così come compaiono: nell'omocodia alcune cifre sono
    sostituite da lettere, e le tabelle ufficiali le contemplano già.
    """
    corpo = primi_quindici.upper()
    if len(corpo) != 15:
        raise ValueError("il corpo del codice fiscale deve avere 15 caratteri")
    totale = 0
    for indice, carattere in enumerate(corpo, start=1):
        tabella = _DISPARI if indice % 2 == 1 else _PARI
        if carattere not in tabella:
            raise ValueError(f"carattere non ammesso nel codice fiscale: {carattere!r}")
        totale += tabella[carattere]
    return chr(65 + totale % 26)


def cf_valido(valore: str) -> bool:
    """Il CIN sul valore normalizzato: il codice fiscale dei moduli a caselle
    arriva a gruppi ("RSSMRA 85M01 H501Q") e deve superare lo stesso controllo
    della forma compatta, né più né meno (issue #37)."""
    codice = _codice_normalizzato(valore)
    if codice is None or not _FORMA_CF.match(codice):
        return False
    try:
        return cin_atteso(codice[:15]) == codice[15]
    except ValueError:
        return False


def piva_valida(valore: str) -> bool:
    """Cifra di controllo della partita IVA italiana: 11 cifre, l'ultima calcolata
    sulle prime 10 raddoppiando le posizioni pari."""
    cifre = valore.strip().upper().removeprefix("IT")
    if len(cifre) != 11 or not cifre.isdigit():
        return False
    totale = 0
    for indice, carattere in enumerate(cifre[:10]):
        n = int(carattere)
        if indice % 2 == 1:  # 2ª, 4ª, ... contando da 1
            n *= 2
            if n > 9:
                n -= 9
        totale += n
    return (10 - totale % 10) % 10 == int(cifre[10])


def iban_valido(valore: str) -> bool:
    """ISO 7064 MOD 97-10: sposta i primi 4 caratteri in coda, converte le lettere
    in numeri (A=10 ... Z=35) e verifica che il resto modulo 97 sia 1.

    La normalizzazione toglie anche i trattini, non solo gli spazi: è la forma
    in cui gestionali e home banking mostrano l'IBAN, e il checksum non deve
    accorgersene (issue #37).
    """
    codice = _codice_normalizzato(valore)
    if codice is None or not re.fullmatch(r"[A-Z]{2}\d{2}[0-9A-Z]{11,30}", codice):
        return False
    riordinato = codice[4:] + codice[:4]
    resto = 0
    for carattere in riordinato:
        if carattere.isdigit():
            pezzo = carattere
        else:
            pezzo = str(ord(carattere) - 55)  # 'A' -> '10'
        for cifra in pezzo:
            resto = (resto * 10 + int(cifra)) % 97
    return resto == 1
