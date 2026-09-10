"""Riconoscimento statistico delle entità con spaCy: priorità P4 (spec §6).

Il modello è generalista: non offre garanzie di completezza. Serve ad assistere
la revisione umana, non a sostituirla.
"""
from __future__ import annotations

from functools import lru_cache

import spacy
from spacy.language import Language

from cryptocustode.core.models import Category, Source, Span

MAPPA_LABEL: dict[str, Category] = {
    "PER": Category.PERSONA,
    "ORG": Category.AZIENDA,
    "LOC": Category.INDIRIZZO,
}


@lru_cache(maxsize=2)
def carica_modello(nome: str = "it_core_news_lg") -> Language:
    """Carica il modello una volta sola per processo: sono circa 550 MB."""
    try:
        return spacy.load(nome)
    except OSError as errore:
        raise RuntimeError(
            f"modello spaCy '{nome}' non installato. "
            f"Eseguire: python -m spacy download {nome}"
        ) from errore


def trova_per_ner(testo: str, doc_id: str) -> list[Span]:
    """Span ricavati dal NER, senza risoluzione delle sovrapposizioni."""
    documento = carica_modello()(testo)
    trovati: list[Span] = []
    for entita in documento.ents:
        categoria = MAPPA_LABEL.get(entita.label_)
        if categoria is None:
            continue
        # Gli offset di spaCy possono includere spazi ai bordi: li riduco, così
        # il testo mascherato non resta con spazi doppi.
        inizio = entita.start_char + (len(entita.text) - len(entita.text.lstrip()))
        fine = entita.end_char - (len(entita.text) - len(entita.text.rstrip()))
        if fine - inizio <= 1:
            continue
        trovati.append(
            Span(
                span_id=f"{doc_id}:{inizio}-{fine}:{categoria.value}",
                doc_id=doc_id,
                start=inizio,
                end=fine,
                category=categoria,
                source=Source.NER,
                entity_id="",
            )
        )
    trovati.sort(key=lambda s: (s.start, -s.lunghezza))
    return trovati
