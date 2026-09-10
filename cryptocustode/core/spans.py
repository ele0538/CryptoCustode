"""Risoluzione delle sovrapposizioni fra span, per priorità decrescente (spec §6)."""
from __future__ import annotations

from cryptocustode.core.models import Span


def si_sovrappongono(a: Span, b: Span) -> bool:
    """Due span si sovrappongono se condividono almeno un carattere.
    Gli span adiacenti (fine dell'uno uguale all'inizio dell'altro) non si
    sovrappongono."""
    return a.start < b.end and b.start < a.end


def _forza(span: Span) -> tuple[int, int, int, str]:
    """Chiave di ordinamento: priorità più alta prima, poi lo span più lungo,
    poi quello che inizia prima, infine lo span_id per rendere l'esito
    indipendente dall'ordine di ingresso."""
    return (span.priorita, -span.lunghezza, span.start, span.span_id)


def risolvi(spans: list[Span]) -> list[Span]:
    """Sceglie gli span vincenti e restituisce una lista senza sovrapposizioni,
    ordinata per offset crescente."""
    vincitori: list[Span] = []
    for candidato in sorted(spans, key=_forza):
        if any(si_sovrappongono(candidato, scelto) for scelto in vincitori):
            continue
        vincitori.append(candidato)
    vincitori.sort(key=lambda s: s.start)
    return vincitori
