"""Applica pattern e validatori al testo e produce span da regole deterministiche,
di qualunque priorità.

Gli span nascono con `entity_id` vuoto: l'assegnazione delle entità è compito
di `core/entities.py`.
"""
from __future__ import annotations

import re
from datetime import date

from cryptocustode.core.detect import validators
from cryptocustode.core.detect.patterns import (
    FINESTRA_CONTESTO,
    MESI,
    PAROLE_CONTESTO,
    PATTERN,
)
from cryptocustode.core.models import Category, Source, Span

_NOMI_MESI = {nome: numero for numero, nome in enumerate(MESI.split("|"), start=1)}


def _ha_contesto(testo: str, inizio: int, categoria: Category) -> bool:
    parole = PAROLE_CONTESTO.get(categoria)
    if parole is None:
        return True
    finestra = testo[max(0, inizio - FINESTRA_CONTESTO):inizio].lower()
    return any(parola in finestra for parola in parole)


def _data_esiste(valore: str) -> bool:
    ripulito = valore.strip().lower()
    numerica = re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", ripulito)
    if numerica:
        giorno, mese, anno = (int(g) for g in numerica.groups())
    else:
        iso = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", ripulito)
        if iso:
            anno, mese, giorno = (int(g) for g in iso.groups())
        else:
            testuale = re.fullmatch(r"(\d{1,2})\s+([a-zà-ÿ]+)\s+(\d{4})", ripulito)
            if not testuale:
                return False
            giorno = int(testuale.group(1))
            mese = _NOMI_MESI.get(testuale.group(2), 0)
            anno = int(testuale.group(3))
    try:
        date(anno, mese, giorno)
    except ValueError:
        return False
    return True


_VALIDATORI = {
    Category.CF: validators.cf_valido,
    Category.PIVA: validators.piva_valida,
    Category.IBAN: validators.iban_valido,
    Category.DATA: _data_esiste,
}


def _accettato(categoria: Category, valore: str) -> bool:
    validatore = _VALIDATORI.get(categoria)
    return True if validatore is None else validatore(valore)


def trova_per_regole(testo: str, doc_id: str) -> list[Span]:
    """Tutti gli span ricavabili da regex e checksum, senza risoluzione delle
    sovrapposizioni: quella è responsabilità di `core/spans.py`."""
    trovati: list[Span] = []
    for categoria, pattern in PATTERN.items():
        for corrispondenza in pattern.finditer(testo):
            # PRATICA cattura l'identificativo nel gruppo 1: lo span copre
            # l'intera espressione, parola chiave inclusa, così l'utente vede
            # il contesto che ha giustificato il riconoscimento.
            valore = corrispondenza.group(0)
            if categoria is Category.PRATICA and not any(
                c.isdigit() for c in corrispondenza.group(1)
            ):
                continue
            if not _accettato(categoria, valore):
                continue
            if not _ha_contesto(testo, corrispondenza.start(), categoria):
                continue
            inizio, fine = corrispondenza.start(), corrispondenza.end()
            trovati.append(
                Span(
                    span_id=f"{doc_id}:{inizio}-{fine}:{categoria.value}",
                    doc_id=doc_id,
                    start=inizio,
                    end=fine,
                    category=categoria,
                    source=Source.RULE,
                    entity_id="",
                )
            )
    trovati.sort(key=lambda s: (s.start, -s.lunghezza))
    return trovati
