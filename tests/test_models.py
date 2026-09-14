import dataclasses

import pytest

from cryptocustode.core.models import (
    Category,
    Document,
    Fascicolo,
    Mascheratura,
    Regione,
    Rilevazione,
    State,
    StatoTag,
    Tag,
    fascicolo_vuoto,
)


def test_document_e_immutabile():
    doc = Document(doc_id="d1", filename="a.txt", text="ciao", page_offsets=[0], sha256="x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        doc.text = "altro"


def test_fascicolo_vuoto_parte_in_draft_mascherando_chi_identifica():
    f = fascicolo_vuoto("f1")
    assert f.fascicolo_id == "f1"
    assert f.state is State.DRAFT
    assert f.approval_hash is None
    assert f.documents == []
    assert set(f.category_enabled) == set(Category), "ogni categoria ha il suo interruttore"
    assert all(v == 0 for v in f.counters.values())


def test_di_default_non_si_maschera_niente():
    """Si parte da zero e si accende ciò che serve (spec §2, emendamento alla
    decisione 4).

    Asserito su ogni categoria e non con un `any()`, perché il giorno in cui
    qualcuno riaccendesse una singola categoria "per sicurezza" questo test
    deve dire **quale**, non limitarsi a diventare rosso.
    """
    attive = fascicolo_vuoto("f1").category_enabled
    for categoria in Category:
        assert attive[categoria] is False, categoria


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
