"""Checksum deterministici. Un valore che non supera il controllo non diventa
uno span della sua categoria: al più resta materiale per il NER (spec §6)."""
from __future__ import annotations

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
    codice = valore.strip().upper()
    if not _FORMA_CF.match(codice):
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
    in numeri (A=10 ... Z=35) e verifica che il resto modulo 97 sia 1."""
    codice = re.sub(r"\s+", "", valore).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[0-9A-Z]{11,30}", codice):
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
