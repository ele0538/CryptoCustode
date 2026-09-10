import pytest

from cryptocustode.core.detect.ner import MAPPA_LABEL, carica_modello, trova_per_ner
from cryptocustode.core.models import Category, Source

pytestmark = pytest.mark.lento


def valori(testo: str, categoria: Category) -> list[str]:
    return [testo[s.start:s.end] for s in trova_per_ner(testo, "d1") if s.category is categoria]


def test_il_modello_si_carica_una_volta_sola():
    assert carica_modello() is carica_modello()


def test_riconosce_una_persona():
    testo = "Il presente contratto è sottoscritto da Mario Rossi in data odierna."
    assert any("Rossi" in v for v in valori(testo, Category.PERSONA))


def test_riconosce_una_azienda():
    testo = "La società Alfa Costruzioni S.r.l. si impegna a consegnare l'opera."
    assert any("Alfa" in v for v in valori(testo, Category.AZIENDA))


def test_le_label_mappate_coprono_le_tre_categorie_previste():
    assert set(MAPPA_LABEL.values()) == {
        Category.PERSONA, Category.AZIENDA, Category.INDIRIZZO,
    }


def test_gli_span_sono_marcati_come_ner():
    testo = "Contratto firmato da Mario Rossi."
    for span in trova_per_ner(testo, "d1"):
        assert span.source is Source.NER
        assert span.entity_id == ""
        assert testo[span.start:span.end].strip() == testo[span.start:span.end]


def test_scarta_token_di_una_sola_lettera():
    for span in trova_per_ner("La lettera A firmata da B.", "d1"):
        assert span.lunghezza > 1


def test_offset_coerenti_con_il_testo():
    testo = "Il signor Mario Rossi abita a Torino."
    for span in trova_per_ner(testo, "d1"):
        assert 0 <= span.start < span.end <= len(testo)
