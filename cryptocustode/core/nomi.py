"""L'euristica sui nomi: quando due scritture possono indicare la stessa cosa.

Modulo puro — solo stringhe, nessun fascicolo e nessuna I/O — e questo è il
motivo per cui è sopravvissuto al passaggio a Gemini mentre il resto di
`core/entities.py` è stato cancellato: confronta due valori, e non ha mai avuto
bisogno degli offset nel testo che il modello non restituisce.

Principio guida (spec §7): fondere per errore corrompe i dati e rivela il nome
di una persona al posto di un'altra; separare per errore degrada soltanto la
qualità della risposta dell'IA. Quindi separare è il default, e **queste
funzioni non fondono niente**: producono un suggerimento che solo l'utente può
accettare.

La normalizzazione è una chiave di confronto e nient'altro. Il valore
originale non si perde mai: è quello che `tagga` cerca nel testo carattere per
carattere, e un valore normalizzato nel dizionario di ripristino restituirebbe
un nome in minuscolo e senza titolo al posto di quello vero.
"""

import re
import unicodedata

TITOLI = (
    "sig.ra", "sig.", "sig", "signora", "signor", "dott.ssa", "dott.", "dottore",
    "dottoressa", "avv.", "avvocato", "ing.", "ingegner", "arch.", "geom.",
    "rag.", "prof.ssa", "prof.", "on.", "spett.le", "spett.",
)
"""I titoli che non distinguono una persona da un'altra.

L'ordine conta: le forme lunghe stanno prima delle loro abbreviazioni, così
`sig.ra` viene tolto prima che `sig.` possa morderne il prefisso lasciando un
`ra` attaccato al nome.
"""


def normalizza(valore: str) -> str:
    """Chiave di confronto: NFKC, minuscolo, senza titoli, spazi collassati.

    Il ciclo toglie i titoli finché ne trova, perché si impilano: «Spett.le
    Sig. Rossi» ne ha due, e toglierne uno solo lascerebbe una chiave che non
    combacia con nessun'altra scrittura dello stesso nome.
    """
    testo = unicodedata.normalize("NFKC", valore).casefold().strip()
    testo = re.sub(r"\s+", " ", testo)
    cambiato = True
    while cambiato:
        cambiato = False
        for titolo in TITOLI:
            if testo.startswith(titolo + " ") or testo == titolo:
                testo = testo[len(titolo):].strip()
                cambiato = True
    return testo


def _token(valore: str) -> list[str]:
    return [t for t in re.split(r"[\s,]+", normalizza(valore)) if t]


def _iniziale_compatibile(a: str, b: str) -> bool:
    breve, lungo = sorted((a.rstrip("."), b.rstrip(".")), key=len)
    return len(breve) == 1 and len(lungo) > 1 and lungo.startswith(breve)


def chiavi_equivalenti(a: str, b: str) -> bool:
    """Vero se le due stringhe possono indicare la stessa entità, a meno
    dell'ordine dei token e delle iniziali abbreviate.

    È un suggerimento: non autorizza da sé alcuna fusione.

    Il numero di token deve coincidere. «Mario Rossi» e «Mario Rossi Bianchi»
    possono benissimo essere due persone, e suggerirne la fusione spingerebbe
    verso l'errore che la spec §7 dichiara il più caro.

    La lista vuota è esclusa in partenza: un valore che si riduce a niente —
    un titolo nudo, per esempio — diventerebbe altrimenti equivalente a ogni
    altro valore che si riduce a niente.
    """
    primi, secondi = _token(a), _token(b)
    if not primi or not secondi or len(primi) != len(secondi):
        return False
    if sorted(primi) == sorted(secondi):
        return True
    # Accoppiamento greedy: a ogni token del primo valore si cerca un token
    # ancora libero del secondo. Basta che uno resti spaiato perché le due
    # scritture non siano equivalenti.
    rimasti = list(secondi)
    for token in primi:
        accoppiato = None
        for candidato in rimasti:
            if token == candidato or _iniziale_compatibile(token, candidato):
                accoppiato = candidato
                break
        if accoppiato is None:
            return False
        rimasti.remove(accoppiato)
    return True
