import pytest

from cryptocustode.core.detect.ner import (
    MAPPA_LABEL,
    carica_modello,
    solo_parole_di_struttura,
    trova_per_ner,
)
from cryptocustode.core.models import Category, Source

# Il marcatore vale per tutto il file: anche i test che non chiamano il modello
# pagano l'import di spaCy, che questo modulo fa all'import.
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


class TestScartoDelleStopword:
    """Validazione P4 della spec §6 ("scarto stopword e token di una sola
    lettera"), nella forma conservativa: si scarta solo se *ogni* token è una
    stopword, un titolo o un carattere singolo."""

    @pytest.mark.parametrize(
        "valore",
        ["CONTRATTO", "Locatore", "Conduttore", "Tel", "Sig", "Sig.", "Dott.ssa",
         "di seguito", "A B"],
    )
    def test_scarta_gli_span_di_sole_parole_di_struttura(self, valore):
        assert solo_parole_di_struttura(valore) is True

    @pytest.mark.parametrize(
        "valore",
        ["Alberto Ferrante", "Ferrante", "Sig. Rossi", "Mario Rossi",
         "Alfa Costruzioni S.r.l.", "Via Roma"],
    )
    def test_non_scarta_gli_span_con_almeno_un_token_pieno(self, valore):
        assert solo_parole_di_struttura(valore) is False

    @pytest.mark.parametrize("valore", ["Rosa", "Patti", "Costa", "Piazza"])
    def test_i_nomi_che_sono_anche_parole_comuni_non_vengono_scartati(self, valore):
        """Il vocabolario non contiene nessuna parola che possa essere un nome
        o un cognome italiano: quei falsi positivi restano coperti dal limite
        noto §16.1, perché scartarli è la direzione che fa fuggire i dati."""
        assert solo_parole_di_struttura(valore) is False

    def test_le_parole_di_struttura_non_diventano_span(self):
        testo = (
            "CONTRATTO DI LOCAZIONE\n\n"
            "Tra il Sig. Alberto Ferrante, di seguito il Locatore, e la "
            "Sig.ra Marta Lorusso,\ndi seguito il Conduttore.\n"
            "Tel. 011 1234567\n"
        )
        trovati = [testo[s.start:s.end] for s in trova_per_ner(testo, "d1")]
        assert "CONTRATTO" not in trovati
        assert "Locatore" not in trovati
        assert "Conduttore" not in trovati
        assert "Tel" not in trovati
        assert "Sig" not in trovati
        assert any("Ferrante" in v for v in trovati), (
            "il filtro non deve far cadere il nome vero"
        )
