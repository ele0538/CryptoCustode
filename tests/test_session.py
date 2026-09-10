import pytest

from cryptocustode.core.entities import aggiungi_span_manuale
from cryptocustode.core.errors import UnresolvedAmbiguities
from cryptocustode.core.models import (
    Ambiguity,
    AmbiguityKind,
    Category,
    Document,
    Entity,
    Source,
    Span,
    State,
    fascicolo_vuoto,
)
from cryptocustode.state.session import (
    analisi_completata,
    approva,
    registra_mutazione,
)


def fascicolo_analizzato():
    """Un fascicolo con un documento, uno span e la sua entità, pronto da approvare."""
    fascicolo = fascicolo_vuoto("f1")
    fascicolo.documents.append(
        Document(
            doc_id="d1",
            filename="contratto.txt",
            text="Mario Rossi abita a Torino.",
            page_offsets=[0],
            sha256="a" * 64,
        )
    )
    fascicolo.spans.append(
        Span(
            span_id="s1",
            doc_id="d1",
            start=0,
            end=11,
            category=Category.PERSONA,
            source=Source.NER,
            entity_id="e1",
        )
    )
    fascicolo.entities["e1"] = Entity(
        entity_id="e1",
        category=Category.PERSONA,
        placeholder="[PERSONA_1]",
        canonical_value="Mario Rossi",
    )
    analisi_completata(fascicolo)
    return fascicolo


def ambiguita_bloccante():
    return Ambiguity(
        ambiguity_id="a1",
        kind=AmbiguityKind.SAME_NAME_NO_CF,
        category=Category.PERSONA,
        candidate_entity_ids=["e1", "e2"],
        occurrence_span_ids=["s1"],
    )


def ambiguita_non_bloccante():
    return Ambiguity(
        ambiguity_id="a2",
        kind=AmbiguityKind.HEURISTIC_MERGE_SUGGESTION,
        category=Category.PERSONA,
        candidate_entity_ids=["e1", "e2"],
        occurrence_span_ids=["s1"],
    )


def test_un_fascicolo_nuovo_e_in_draft():
    assert fascicolo_vuoto("f1").state is State.DRAFT


def test_approvare_un_fascicolo_in_draft_e_rifiutato():
    # Senza questo controllo un DRAFT mai analizzato firmerebbe l'hash del
    # testo non ancora mascherato, e l'export lo restituirebbe verbatim.
    fascicolo = fascicolo_vuoto("f1")
    with pytest.raises(ValueError):
        approva(fascicolo)
    assert fascicolo.state is State.DRAFT
    assert fascicolo.approval_hash is None


def test_l_analisi_porta_in_pending_review():
    fascicolo = fascicolo_vuoto("f1")
    analisi_completata(fascicolo)
    assert fascicolo.state is State.PENDING_REVIEW


def test_l_approvazione_porta_in_approved():
    fascicolo = fascicolo_analizzato()
    approva(fascicolo)
    assert fascicolo.state is State.APPROVED


def test_l_approvazione_salva_l_hash():
    fascicolo = fascicolo_analizzato()
    approva(fascicolo)
    assert fascicolo.approval_hash is not None
    assert len(fascicolo.approval_hash) == 64


def test_l_approvazione_e_deterministica():
    primo, secondo = fascicolo_analizzato(), fascicolo_analizzato()
    approva(primo)
    approva(secondo)
    assert primo.approval_hash == secondo.approval_hash


def test_un_ambiguita_bloccante_impedisce_l_approvazione():
    fascicolo = fascicolo_analizzato()
    fascicolo.ambiguities.append(ambiguita_bloccante())
    with pytest.raises(UnresolvedAmbiguities, match="a1"):
        approva(fascicolo)


def test_il_rifiuto_lascia_lo_stato_invariato():
    fascicolo = fascicolo_analizzato()
    fascicolo.ambiguities.append(ambiguita_bloccante())
    with pytest.raises(UnresolvedAmbiguities):
        approva(fascicolo)
    assert fascicolo.state is State.PENDING_REVIEW
    assert fascicolo.approval_hash is None


def test_un_ambiguita_bloccante_risolta_non_impedisce_l_approvazione():
    fascicolo = fascicolo_analizzato()
    ambiguita = ambiguita_bloccante()
    ambiguita.resolved = True
    fascicolo.ambiguities.append(ambiguita)
    approva(fascicolo)
    assert fascicolo.state is State.APPROVED


def test_un_suggerimento_euristico_non_impedisce_l_approvazione():
    fascicolo = fascicolo_analizzato()
    fascicolo.ambiguities.append(ambiguita_non_bloccante())
    approva(fascicolo)
    assert fascicolo.state is State.APPROVED


def test_una_mutazione_dopo_l_approvazione_riporta_in_pending_review():
    # TC-06.
    fascicolo = fascicolo_analizzato()
    approva(fascicolo)
    registra_mutazione(fascicolo)
    assert fascicolo.state is State.PENDING_REVIEW


def test_una_mutazione_dopo_l_approvazione_cancella_l_hash():
    fascicolo = fascicolo_analizzato()
    approva(fascicolo)
    registra_mutazione(fascicolo)
    assert fascicolo.approval_hash is None


def test_una_mutazione_in_pending_review_non_cambia_nulla():
    fascicolo = fascicolo_analizzato()
    registra_mutazione(fascicolo)
    assert fascicolo.state is State.PENDING_REVIEW


def test_una_mutazione_in_draft_non_cambia_nulla():
    fascicolo = fascicolo_vuoto("f1")
    registra_mutazione(fascicolo)
    assert fascicolo.state is State.DRAFT


def test_l_analisi_popola_la_coda_delle_omonimie():
    # Senza le due chiamate dentro analisi_completata questa coda resterebbe
    # vuota per sempre e `approva` non avrebbe mai nulla da bloccare.
    fascicolo = fascicolo_vuoto("f1")
    for indice, testo in enumerate(["Il conduttore Mario Rossi.", "Il garante Mario Rossi."]):
        documento = Document(
            doc_id=f"d{indice}",
            filename=f"doc{indice}.txt",
            text=testo,
            page_offsets=[0],
            sha256=f"{indice}" * 64,
        )
        fascicolo.documents.append(documento)
        aggiungi_span_manuale(
            fascicolo, documento, testo.index("Mario Rossi"),
            testo.index("Mario Rossi") + 11, Category.PERSONA,
        )
    analisi_completata(fascicolo)
    assert any(a.blocca_approvazione for a in fascicolo.ambiguities)


def test_l_analisi_popola_anche_i_suggerimenti_euristici():
    fascicolo = fascicolo_vuoto("f1")
    for indice, (testo, nome) in enumerate(
        [("Il conduttore M. Rossi.", "M. Rossi"), ("Il garante Mario Rossi.", "Mario Rossi")]
    ):
        documento = Document(
            doc_id=f"d{indice}",
            filename=f"doc{indice}.txt",
            text=testo,
            page_offsets=[0],
            sha256=f"{indice}" * 64,
        )
        fascicolo.documents.append(documento)
        aggiungi_span_manuale(
            fascicolo, documento, testo.index(nome),
            testo.index(nome) + len(nome), Category.PERSONA,
        )
    analisi_completata(fascicolo)
    suggerimenti = [
        a
        for a in fascicolo.ambiguities
        if a.kind is AmbiguityKind.HEURISTIC_MERGE_SUGGESTION
    ]
    assert len(suggerimenti) == 1
    assert suggerimenti[0].blocca_approvazione is False
