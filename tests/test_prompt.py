"""Lo schema imposto a Gemini (spec §6)."""

from cryptocustode.ai.prompt import MODELLO, SCHEMA_RILEVAZIONI, istruzioni
from cryptocustode.core.models import Category


def test_il_modello_e_quello_della_spec():
    assert MODELLO == "gemini-3.8-flash"


def test_l_enum_dello_schema_copre_esattamente_le_categorie():
    """Se una categoria venisse aggiunta a `Category` senza entrare qui, il
    modello non potrebbe mai nominarla e nessuno se ne accorgerebbe."""
    ammesse = SCHEMA_RILEVAZIONI["items"]["properties"]["categoria"]["enum"]
    assert sorted(ammesse) == sorted(c.value for c in Category)


def test_lo_schema_pretende_entrambi_i_campi():
    assert sorted(SCHEMA_RILEVAZIONI["items"]["required"]) == ["categoria", "valore"]


def test_lo_schema_e_una_lista_di_oggetti():
    assert SCHEMA_RILEVAZIONI["type"] == "array"
    assert SCHEMA_RILEVAZIONI["items"]["type"] == "object"


def test_le_istruzioni_pretendono_la_sottostringa_letterale():
    """È il vincolo da cui dipende tutto il resto: senza, i valori tornano
    normalizzati, `tagga` non li trova e i dati restano in chiaro."""
    testo = istruzioni().lower()
    assert "letteral" in testo
    assert "non normalizzare" in testo


def test_le_istruzioni_elencano_le_categorie():
    testo = istruzioni()
    for categoria in Category:
        assert categoria.value in testo
