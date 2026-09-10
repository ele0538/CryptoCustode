"""Mascheratura e hash canonico di approvazione.

Modulo deliberatamente puro: nessuna I/O, nessun orologio, nessun random. Se
mascherare lo stesso fascicolo due volte producesse output diversi, il
confronto con `approval_hash` fallirebbe a caso e il controllo di integrità
diventerebbe rumore invece di una difesa (spec §4, invariante 2).
"""
from __future__ import annotations

import hashlib

from cryptocustode.core.models import Document, Entity, Fascicolo, Span


def span_attivo(span: Span, fascicolo: Fascicolo) -> bool:
    """Uno span viene mascherato solo se sono chiusi entrambi gli interruttori:
    quello sul singolo span e quello sulla categoria (spec §5)."""
    return span.enabled and fascicolo.category_enabled.get(span.category, True)


def maschera(testo: str, spans: list[Span], entities: dict[str, Entity]) -> str:
    """Sostituisce gli span con i segnaposto delle rispettive entità.

    Procede da destra a sinistra: così ogni sostituzione lascia validi gli
    offset di quelle ancora da applicare (spec §9).
    """
    risultato = testo
    for span in sorted(spans, key=lambda s: s.start, reverse=True):
        entita = entities.get(span.entity_id)
        if entita is None:
            raise ValueError(
                f"span {span.span_id!r} fa riferimento all'entità "
                f"{span.entity_id!r}, assente dal fascicolo: mascheratura "
                "impossibile, dati personali a rischio di fuga"
            )
        risultato = risultato[:span.start] + entita.placeholder + risultato[span.end:]
    return risultato


def maschera_documento(fascicolo: Fascicolo, documento: Document) -> str:
    attivi = [
        s for s in fascicolo.spans
        if s.doc_id == documento.doc_id and span_attivo(s, fascicolo)
    ]
    return maschera(documento.text, attivi, fascicolo.entities)


def hash_approvazione(fascicolo: Fascicolo) -> str:
    """SHA-256 su una serializzazione canonica dei testi mascherati.

    I documenti sono ordinati per nome file e ciascuno emette
    `filename\\n<lunghezza>\\n<testo>`. La lunghezza esplicita rende la
    concatenazione non ambigua, così due fascicoli diversi non possono
    produrre lo stesso digest (spec §8).
    """
    digest = hashlib.sha256()
    for documento in sorted(fascicolo.documents, key=lambda d: (d.filename, d.doc_id)):
        mascherato = maschera_documento(fascicolo, documento)
        blocco = f"{documento.filename}\n{len(mascherato)}\n{mascherato}"
        digest.update(blocco.encode("utf-8"))
    return digest.hexdigest()
