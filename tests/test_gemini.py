"""Il client Gemini, provato senza toccare la rete (spec §4, invariante 5)."""

import json

import pytest

from cryptocustode.ai.gemini import RilevatoreGemini
from cryptocustode.core.errors import AIKeyMissing, AIResponseInvalid, AIUnavailable
from cryptocustode.core.models import Category, Rilevazione
from cryptocustode.core.rilevatore import Rilevatore


def _chiamata(risposta: str):
    """Una `Chiamata` che restituisce sempre lo stesso JSON grezzo."""
    def chiama(modello, istruzioni, testo, schema):
        return risposta
    return chiama


def _rilevatore(risposta: str) -> RilevatoreGemini:
    return RilevatoreGemini(chiave="finta", chiama=_chiamata(risposta))


def test_soddisfa_il_protocollo():
    assert isinstance(_rilevatore("[]"), Rilevatore)


def test_traduce_la_risposta_in_rilevazioni():
    risposta = json.dumps(
        [{"valore": "Mario Rossi", "categoria": "PERSONA"},
         {"valore": "ACME s.r.l.", "categoria": "AZIENDA"}]
    )
    assert _rilevatore(risposta).rileva("qualunque") == [
        Rilevazione(valore="Mario Rossi", categoria=Category.PERSONA),
        Rilevazione(valore="ACME s.r.l.", categoria=Category.AZIENDA),
    ]


def test_una_lista_vuota_e_una_risposta_legittima():
    assert _rilevatore("[]").rileva("niente di personale") == []


def test_senza_chiave_solleva_prima_di_chiamare():
    """Il controllo precede la chiamata: chiedere a Gemini per poi scoprire che
    manca la chiave manderebbe il documento in rete per niente."""
    chiamate = []

    def chiama(modello, istruzioni, testo, schema):
        chiamate.append(testo)
        return "[]"

    with pytest.raises(AIKeyMissing):
        RilevatoreGemini(chiave=None, chiama=chiama).rileva("Mario Rossi")
    assert chiamate == []


def test_un_errore_di_trasporto_diventa_AIUnavailable():
    def chiama(modello, istruzioni, testo, schema):
        raise TimeoutError("connessione scaduta")

    with pytest.raises(AIUnavailable):
        RilevatoreGemini(chiave="finta", chiama=chiama).rileva("Mario Rossi")


def test_json_malformato_diventa_AIResponseInvalid():
    with pytest.raises(AIResponseInvalid):
        _rilevatore("non sono json").rileva("Mario Rossi")


def test_una_risposta_che_non_e_una_lista_diventa_AIResponseInvalid():
    with pytest.raises(AIResponseInvalid):
        _rilevatore('{"valore": "Mario Rossi"}').rileva("Mario Rossi")


def test_una_categoria_inventata_diventa_AIResponseInvalid():
    """`PERSONE` non è un valore di `Category`: lo schema dovrebbe averlo
    impedito, ma lo schema è una richiesta al fornitore, non una garanzia."""
    risposta = json.dumps([{"valore": "Mario Rossi", "categoria": "PERSONE"}])
    with pytest.raises(AIResponseInvalid):
        _rilevatore(risposta).rileva("Mario Rossi")


def test_una_voce_senza_valore_diventa_AIResponseInvalid():
    with pytest.raises(AIResponseInvalid):
        _rilevatore(json.dumps([{"categoria": "PERSONA"}])).rileva("Mario Rossi")


def test_un_valore_non_stringa_diventa_AIResponseInvalid():
    risposta = json.dumps([{"valore": 42, "categoria": "PERSONA"}])
    with pytest.raises(AIResponseInvalid):
        _rilevatore(risposta).rileva("Mario Rossi")


def test_passa_al_fornitore_modello_istruzioni_e_schema():
    visti = {}

    def chiama(modello, istruzioni, testo, schema):
        visti.update(modello=modello, istruzioni=istruzioni, testo=testo, schema=schema)
        return "[]"

    RilevatoreGemini(chiave="finta", chiama=chiama).rileva("Mario Rossi paga.")
    assert visti["modello"] == "gemini-3.8-flash"
    assert visti["testo"] == "Mario Rossi paga."
    assert "letteral" in visti["istruzioni"].lower()
    assert visti["schema"]["type"] == "array"
