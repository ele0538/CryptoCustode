"""Il client Gemini, provato senza toccare la rete (spec §4, invariante 5)."""

import json

import pytest

from cryptocustode.ai.gemini import RilevatoreGemini
from cryptocustode.core.errors import AIKeyMissing, AIResponseInvalid, AIUnavailable
from cryptocustode.core.models import Category, Rilevazione
from cryptocustode.core.rilevatore import Rilevatore


def _chiamata(risposta: str):
    """Una `Chiamata` che restituisce sempre lo stesso JSON grezzo."""
    def chiama(modello, istruzioni, testo, schema, chiave):
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

    def chiama(modello, istruzioni, testo, schema, chiave):
        chiamate.append(testo)
        return "[]"

    with pytest.raises(AIKeyMissing):
        RilevatoreGemini(chiave=None, chiama=chiama).rileva("Mario Rossi")
    assert chiamate == []


def test_un_errore_di_trasporto_diventa_AIUnavailable():
    def chiama(modello, istruzioni, testo, schema, chiave):
        raise TimeoutError("connessione scaduta")

    with pytest.raises(AIUnavailable):
        RilevatoreGemini(chiave="finta", chiama=chiama).rileva("Mario Rossi")


def test_il_dettaglio_dell_errore_di_trasporto_non_espone_la_chiave():
    """Il testo di un'eccezione di trasporto può contenere l'URL della
    richiesta fallita, e l'API REST di Google accetta la chiave anche come
    parametro `?key=` nell'URL: se `AIUnavailable` interpolasse `str(errore)`,
    la chiave finirebbe nel corpo di una risposta 503, cioè sotto gli occhi
    dell'utente. Questo test blocca quella regressione anche se qualcuno
    rimettesse `str(errore)` per comodità di debug."""
    def chiama(modello, istruzioni, testo, schema, chiave):
        raise ConnectionError(
            "richiesta a https://generativelanguage.googleapis.com/v1?key=SEGRETISSIMO fallita"
        )

    with pytest.raises(AIUnavailable) as informazioni:
        RilevatoreGemini(chiave="finta", chiama=chiama).rileva("Mario Rossi")
    assert "SEGRETISSIMO" not in str(informazioni.value)


def test_json_malformato_diventa_AIResponseInvalid():
    with pytest.raises(AIResponseInvalid):
        _rilevatore("non sono json").rileva("Mario Rossi")


def test_una_risposta_scalare_diventa_AIResponseInvalid():
    """Uno scalare JSON — non una lista, non un oggetto — è il caso che
    esercita davvero la guardia `isinstance(dati, list)`: senza quella
    guardia, `enumerate` su un intero o su `None` non itera affatto, solleva
    `TypeError` e il test diventerebbe rosso per l'eccezione sbagliata invece
    che per l'assenza della guardia. Un dizionario non lo dimostrerebbe,
    perché `enumerate` su un dizionario itera le sue chiavi — stringhe — e la
    guardia successiva (`voce` non è un oggetto) solleverebbe comunque
    `AIResponseInvalid`, lasciando il test verde anche senza questa guardia."""
    with pytest.raises(AIResponseInvalid):
        _rilevatore("42").rileva("Mario Rossi")
    with pytest.raises(AIResponseInvalid):
        _rilevatore("null").rileva("Mario Rossi")


def test_una_risposta_a_oggetto_diventa_comunque_AIResponseInvalid():
    """Un oggetto JSON al posto della lista finisce comunque in
    `AIResponseInvalid`, ma non per la guardia sulla lista in modo esclusivo:
    `enumerate` su un dizionario ne itera le chiavi (stringhe), che la guardia
    successiva rifiuta perché non sono oggetti. Il nome dice questo, per non
    promettere una prova che il caso non dà — è `test_una_risposta_scalare_
    diventa_AIResponseInvalid` sopra a testare la guardia sulla lista."""
    with pytest.raises(AIResponseInvalid):
        _rilevatore('{"valore": "Mario Rossi"}').rileva("Mario Rossi")


def test_una_voce_non_oggetto_in_una_lista_valida_diventa_AIResponseInvalid():
    """Una lista ben formata con dentro un elemento che non è un oggetto: il
    caso che il task chiedeva di rifiutare e che, senza questo test, la
    guardia `isinstance(voce, dict)` esercitava solo per caso, tramite il
    test sulla risposta a oggetto qui sopra."""
    with pytest.raises(AIResponseInvalid):
        _rilevatore(json.dumps(["ciao"])).rileva("Mario Rossi")


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


def test_passa_al_fornitore_modello_istruzioni_schema_e_chiave():
    visti = {}

    def chiama(modello, istruzioni, testo, schema, chiave):
        visti.update(
            modello=modello, istruzioni=istruzioni, testo=testo, schema=schema, chiave=chiave
        )
        return "[]"

    RilevatoreGemini(chiave="finta", chiama=chiama).rileva("Mario Rossi paga.")
    assert visti["modello"] == "gemini-3.8-flash"
    assert visti["testo"] == "Mario Rossi paga."
    assert "letteral" in visti["istruzioni"].lower()
    assert visti["schema"]["type"] == "array"
    assert visti["chiave"] == "finta"
