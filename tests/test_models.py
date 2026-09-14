import dataclasses

import pytest

from cryptocustode.core.models import (
    PRIORITA,
    Category,
    Document,
    Entity,
    Fascicolo,
    Mascheratura,
    Regione,
    Rilevazione,
    Source,
    Span,
    State,
    StatoTag,
    Tag,
    fascicolo_vuoto,
)


def test_span_e_immutabile():
    span = Span(
        span_id="s1", doc_id="d1", start=0, end=4,
        category=Category.PERSONA, source=Source.RULE, entity_id="e1",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        span.start = 5


def test_span_nasce_abilitato():
    span = Span(
        span_id="s1", doc_id="d1", start=0, end=4,
        category=Category.PERSONA, source=Source.RULE, entity_id="e1",
    )
    assert span.enabled is True


def test_document_e_immutabile():
    doc = Document(doc_id="d1", filename="a.txt", text="ciao", page_offsets=[0], sha256="x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        doc.text = "altro"


def test_ogni_categoria_ha_una_priorita():
    assert set(PRIORITA) == set(Category)
    assert all(1 <= p <= 4 for p in PRIORITA.values())


def test_le_priorita_seguono_la_spec():
    assert PRIORITA[Category.CF] == 1
    assert PRIORITA[Category.IBAN] == 1
    assert PRIORITA[Category.PIVA] == 1
    assert PRIORITA[Category.EMAIL] == 2
    assert PRIORITA[Category.DATA] == 3
    assert PRIORITA[Category.PERSONA] == 4


def test_fascicolo_vuoto_parte_in_draft_con_tutte_le_categorie_attive():
    f = fascicolo_vuoto("f1")
    assert f.fascicolo_id == "f1"
    assert f.state is State.DRAFT
    assert f.approval_hash is None
    assert f.documents == []
    assert set(f.category_enabled) == set(Category)
    assert all(f.category_enabled.values()), "di default tutto è mascherato"
    assert all(v == 0 for v in f.counters.values())


def test_entity_tiene_traccia_delle_varianti():
    e = Entity(
        entity_id="e1", category=Category.PERSONA, placeholder="[PERSONA_1]",
        canonical_value="Mario Rossi", variants={"Mario Rossi", "M. Rossi"},
    )
    assert "M. Rossi" in e.variants
    assert e.canonical_value == "Mario Rossi"


def test_il_modello_dichiara_il_tetto_di_dieci_documenti():
    """Pianta la costante, non il comportamento: il 10 è un contratto verso
    l'utente (spec §1) e compare come letterale anche nel `match="10"` del
    loader. Il tetto lo *applica* `aggiungi_documento`, ed è
    `test_l_undicesimo_documento_viene_rifiutato` in `tests/test_loader.py` a
    provare il rifiuto."""
    assert Fascicolo.MAX_DOCUMENTI == 10


class TestITipiDelTagging:
    """I tipi della spec §5 del 2026-09-14. Solo dati: nessun comportamento."""

    def test_la_rilevazione_tiene_valore_e_categoria(self):
        r = Rilevazione(valore="Mario Rossi", categoria=Category.PERSONA)
        assert r.valore == "Mario Rossi"
        assert r.categoria is Category.PERSONA

    def test_il_tag_nasce_non_trovato_e_a_zero_occorrenze(self):
        """`assegna_tag` crea i tag prima di sapere se il testo li contiene:
        lo stato vero lo decide `conta_occorrenze` (task 5)."""
        t = Tag(
            tag="[PERSONA_1]",
            categoria=Category.PERSONA,
            valore="Mario Rossi",
            occorrenze=0,
            stato=StatoTag.NON_TROVATO,
        )
        assert t.tag == "[PERSONA_1]"
        assert t.occorrenze == 0
        assert t.stato is StatoTag.NON_TROVATO

    def test_la_regione_si_riferisce_al_testo_originale(self):
        regione = Regione(start=8, end=19, tag="[PERSONA_1]")
        assert "Il sig. Mario Rossi paga."[regione.start:regione.end] == "Mario Rossi"

    def test_la_mascheratura_tiene_testo_tag_e_regioni(self):
        m = Mascheratura(mascherato="ciao", tags=[], regioni=[])
        assert m.mascherato == "ciao"
        assert m.tags == []
        assert m.regioni == []

    def test_il_fascicolo_vuoto_ha_la_tabella_dei_tag_vuota(self):
        fascicolo = fascicolo_vuoto("f1")
        assert fascicolo.tags == {}

    def test_i_tipi_del_tagging_sono_congelati(self):
        """Congelati come `Span` lo era: la tabella dei tag attraversa
        `hash_approvazione`, e un tipo mutabile permetterebbe di cambiare un
        valore dopo l'approvazione senza passare da `registra_mutazione`."""
        t = Tag(
            tag="[CF_1]",
            categoria=Category.CF,
            valore="RSSMRA80A01H501U",
            occorrenze=1,
            stato=StatoTag.APPLICATO,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            t.valore = "altro"
