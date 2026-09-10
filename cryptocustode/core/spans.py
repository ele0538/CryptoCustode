"""Risoluzione delle sovrapposizioni fra span, per priorità decrescente (spec §6)."""
from __future__ import annotations

from cryptocustode.core.models import Span


def si_sovrappongono(a: Span, b: Span) -> bool:
    """Due span si sovrappongono se stanno nello stesso documento e
    condividono almeno un carattere.

    Gli span adiacenti (fine dell'uno uguale all'inizio dell'altro) non si
    sovrappongono, e nemmeno due span di documenti diversi: gli offset sono
    relativi al testo del proprio documento, quindi confrontarli fra documenti
    non significa niente. Senza il termine sul `doc_id`, `risolvi` su tutti gli
    span di un fascicolo scarterebbe in silenzio gli span di un documento
    perché "sovrapposti" a quelli di un altro, e quel testo resterebbe in
    chiaro."""
    return a.doc_id == b.doc_id and a.start < b.end and b.start < a.end


def _forza(span: Span) -> tuple[int, int, int, str]:
    """Chiave di ordinamento: priorità più alta prima, poi lo span più lungo,
    poi quello che inizia prima, infine lo span_id per rendere l'esito
    indipendente dall'ordine di ingresso."""
    return (span.priorita, -span.lunghezza, span.start, span.span_id)


def risolvi(spans: list[Span]) -> list[Span]:
    """Sceglie gli span vincenti e restituisce una lista senza sovrapposizioni,
    ordinata per offset crescente.

    Accetta span di più documenti: il confronto di sovrapposizione tiene conto
    del `doc_id`, quindi `risolvi(fascicolo.spans)` non perde nulla. L'ordine
    del risultato è per offset crescente e *non* raggruppa per documento: chi
    ha bisogno di un solo documento filtra per `doc_id`, come fa
    `maschera_documento`."""
    vincitori: list[Span] = []
    for candidato in sorted(spans, key=_forza):
        if any(si_sovrappongono(candidato, scelto) for scelto in vincitori):
            continue
        vincitori.append(candidato)
    vincitori.sort(key=lambda s: s.start)
    return vincitori
