"""Aggregazione degli span in entità con segnaposto stabili sul fascicolo.

Principio guida (spec §7): fondere per errore corrompe i dati e rivela il nome
di una persona al posto di un'altra; separare per errore degrada soltanto la
qualità della risposta dell'IA. Quindi separare è il default, e solo il codice
fiscale identico autorizza una fusione automatica.
"""
from __future__ import annotations

import itertools
import re
import unicodedata
import uuid

from cryptocustode.core.detect.ner import trova_per_ner
from cryptocustode.core.detect.rules import trova_per_regole
from cryptocustode.core.models import (
    Ambiguity,
    AmbiguityKind,
    Category,
    Document,
    Entity,
    Fascicolo,
    Source,
    Span,
)
from cryptocustode.core.spans import risolvi

_TITOLI = (
    "sig.ra", "sig.", "sig", "signora", "signor", "dott.ssa", "dott.", "dottore",
    "dottoressa", "avv.", "avvocato", "ing.", "ingegner", "arch.", "geom.",
    "rag.", "prof.ssa", "prof.", "on.", "spett.le", "spett.",
)

# Categorie per cui ha senso confrontare varianti di nome. Su un IBAN o un CF
# l'uguaglianza è esatta o non è.
_CATEGORIE_CON_VARIANTI = {Category.PERSONA, Category.AZIENDA}


def normalizza(valore: str) -> str:
    """Chiave di confronto: NFKC, minuscolo, senza titoli, spazi collassati."""
    testo = unicodedata.normalize("NFKC", valore).casefold().strip()
    testo = re.sub(r"\s+", " ", testo)
    cambiato = True
    while cambiato:
        cambiato = False
        for titolo in _TITOLI:
            if testo.startswith(titolo + " ") or testo == titolo:
                testo = testo[len(titolo):].strip()
                cambiato = True
    return testo


def _token(valore: str) -> list[str]:
    return [t for t in re.split(r"[\s,]+", normalizza(valore)) if t]


def chiavi_equivalenti(a: str, b: str) -> bool:
    """Vero se le due stringhe possono indicare la stessa entità, a meno
    dell'ordine dei token e delle iniziali abbreviate. È un suggerimento:
    non autorizza da sé alcuna fusione."""
    primi, secondi = _token(a), _token(b)
    if not primi or not secondi or len(primi) != len(secondi):
        return False
    if sorted(primi) == sorted(secondi):
        return True
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


def _iniziale_compatibile(a: str, b: str) -> bool:
    breve, lungo = sorted((a.rstrip("."), b.rstrip(".")), key=len)
    return len(breve) == 1 and len(lungo) > 1 and lungo.startswith(breve)


def prossimo_placeholder(fascicolo: Fascicolo, categoria: Category) -> str:
    """Assegna il prossimo indice della categoria. I contatori non tornano mai
    indietro: un indice bruciato resta bruciato (spec §5)."""
    fascicolo.counters[categoria] = fascicolo.counters.get(categoria, 0) + 1
    return f"[{categoria.value}_{fascicolo.counters[categoria]}]"


def _entita_per_valore(
    fascicolo: Fascicolo, categoria: Category, valore: str
) -> Entity | None:
    chiave = normalizza(valore)
    for entita in fascicolo.entities.values():
        if entita.category is not categoria:
            continue
        if any(normalizza(v) == chiave for v in entita.variants):
            return entita
    return None


def _crea_entita(fascicolo: Fascicolo, categoria: Category, valore: str) -> Entity:
    entita = Entity(
        entity_id=str(uuid.uuid4()),
        category=categoria,
        placeholder=prossimo_placeholder(fascicolo, categoria),
        canonical_value=valore,
        variants={valore},
    )
    fascicolo.entities[entita.entity_id] = entita
    return entita


def _assegna(fascicolo: Fascicolo, documento: Document, span: Span) -> Span:
    valore = documento.text[span.start:span.end]
    entita = _entita_per_valore(fascicolo, span.category, valore)
    if entita is None:
        entita = _crea_entita(fascicolo, span.category, valore)
    else:
        entita.variants.add(valore)
    return Span(
        span_id=span.span_id, doc_id=span.doc_id, start=span.start, end=span.end,
        category=span.category, source=span.source, entity_id=entita.entity_id,
        enabled=span.enabled,
    )


def analizza_documento(
    fascicolo: Fascicolo, documento: Document, usa_ner: bool = True
) -> None:
    """Analizza un documento e aggiunge al fascicolo span ed entità.

    `usa_ner=False` esiste per i test che non devono caricare 550 MB di modello.
    """
    trovati = trova_per_regole(documento.text, documento.doc_id)
    if usa_ner:
        trovati += trova_per_ner(documento.text, documento.doc_id)
    for span in risolvi(trovati):
        fascicolo.spans.append(_assegna(fascicolo, documento, span))


def aggiungi_span_manuale(
    fascicolo: Fascicolo, documento: Document, inizio: int, fine: int,
    categoria: Category,
) -> Span:
    """Tagging manuale dell'utente sul testo selezionato (punto 5 della consegna)."""
    grezzo = Span(
        span_id=f"{documento.doc_id}:{inizio}-{fine}:{categoria.value}:manuale",
        doc_id=documento.doc_id, start=inizio, end=fine, category=categoria,
        source=Source.MANUAL, entity_id="",
    )
    span = _assegna(fascicolo, documento, grezzo)
    fascicolo.spans.append(span)
    return span


def _span_id_per_entita(fascicolo: Fascicolo) -> dict[str, list[str]]:
    """Gli span_id di ogni entità, nell'ordine in cui compaiono nel fascicolo."""
    per_entita: dict[str, list[str]] = {}
    for span in fascicolo.spans:
        per_entita.setdefault(span.entity_id, []).append(span.span_id)
    return per_entita


def risolvi_ambiguita_omonimia(fascicolo: Fascicolo) -> None:
    """Apre una ambiguità per ogni entità che compare in più documenti con lo
    stesso nome e senza codice fiscale che la discrimini (spec §7, TC-03)."""
    documenti_per_entita: dict[str, set[str]] = {}
    for span in fascicolo.spans:
        documenti_per_entita.setdefault(span.entity_id, set()).add(span.doc_id)
    span_per_entita = _span_id_per_entita(fascicolo)

    gia_aperte = {
        tuple(sorted(a.candidate_entity_ids)) for a in fascicolo.ambiguities
    }
    for entity_id, documenti in documenti_per_entita.items():
        entita = fascicolo.entities.get(entity_id)
        if entita is None or entita.category not in _CATEGORIE_CON_VARIANTI:
            continue
        if len(documenti) < 2 or entita.cf is not None:
            continue
        if (entity_id,) in gia_aperte:
            continue
        fascicolo.ambiguities.append(
            Ambiguity(
                ambiguity_id=str(uuid.uuid4()),
                kind=AmbiguityKind.SAME_NAME_NO_CF,
                category=entita.category,
                candidate_entity_ids=[entity_id],
                occurrence_span_ids=span_per_entita[entity_id],
            )
        )


def suggerisci_fusioni(fascicolo: Fascicolo) -> None:
    """Apre un suggerimento di fusione per ogni coppia di entità che l'euristica
    sui nomi giudica equivalenti (spec §7).

    È il solo consumatore in produzione di `chiavi_equivalenti`, e non fonde
    nulla: `HEURISTIC_MERGE_SUGGESTION` è non bloccante per costruzione, così
    ignorare il suggerimento lascia le entità separate — il default sicuro.
    Solo una decisione dell'utente può trasformarlo in una fusione.
    """
    span_per_entita = _span_id_per_entita(fascicolo)
    gia_suggerite = {
        tuple(sorted(a.candidate_entity_ids))
        for a in fascicolo.ambiguities
        if a.kind is AmbiguityKind.HEURISTIC_MERGE_SUGGESTION
    }
    confrontabili = [
        entita for entita in fascicolo.entities.values()
        if entita.category in _CATEGORIE_CON_VARIANTI
    ]
    for prima, seconda in itertools.combinations(confrontabili, 2):
        # Una persona e un'azienda con lo stesso nome restano due cose diverse.
        if prima.category is not seconda.category:
            continue
        if tuple(sorted((prima.entity_id, seconda.entity_id))) in gia_suggerite:
            continue
        # Tutte le varianti di un'entità condividono la stessa forma
        # normalizzata, quindi confrontare i valori canonici basta.
        if not chiavi_equivalenti(prima.canonical_value, seconda.canonical_value):
            continue
        fascicolo.ambiguities.append(
            Ambiguity(
                ambiguity_id=str(uuid.uuid4()),
                kind=AmbiguityKind.HEURISTIC_MERGE_SUGGESTION,
                category=prima.category,
                candidate_entity_ids=[prima.entity_id, seconda.entity_id],
                occurrence_span_ids=(
                    span_per_entita.get(prima.entity_id, [])
                    + span_per_entita.get(seconda.entity_id, [])
                ),
            )
        )
