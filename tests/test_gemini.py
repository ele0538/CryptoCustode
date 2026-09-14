"""Il client Gemini, provato senza toccare la rete (spec §4, invariante 5)."""

import json

import pytest

from cryptocustode.ai.gemini import RilevatoreGemini, Risposta
from cryptocustode.core.errors import AIKeyMissing, AIResponseInvalid, AIUnavailable
from cryptocustode.core.models import Category, Rilevazione
from cryptocustode.core.rilevatore import Rilevatore


def _chiamata(risposta: str, token_input: int = 0, token_output: int = 0):
    """Una `Chiamata` che restituisce sempre lo stesso JSON grezzo.

    Da quando il conteggio dei token esiste, il confine non restituisce più una
    stringa ma una `Risposta`: il JSON e quanto è costato ottenerlo. I token
    stanno lì e non in un attributo del rilevatore perché sono una proprietà
    della singola chiamata, ed è ciò che permette di provare il conteggio senza
    toccare la rete — come tutto il resto di questo file.
    """
    def chiama(modello, istruzioni, testo, schema, chiave):
        return Risposta(
            testo=risposta, token_input=token_input, token_output=token_output
        )
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
        return Risposta(testo="[]")

    RilevatoreGemini(chiave="finta", chiama=chiama).rileva("Mario Rossi paga.")
    assert visti["modello"] == "gemini-3.8-flash"
    assert visti["testo"] == "Mario Rossi paga."
    assert "letteral" in visti["istruzioni"].lower()
    assert visti["schema"]["type"] == "array"
    assert visti["chiave"] == "finta"


class TestIlConteggioDeiToken:
    """I token che Gemini dichiara arrivano fino alla configurazione (#50 bis).

    Prima venivano buttati via insieme all'oggetto risposta: `chiamata_reale`
    restituiva `risposta.text` e basta, quindi `usage_metadata` — l'unico posto
    in cui il fornitore dice quanto ha consumato — non usciva dal modulo.
    """

    def _configurazione(self, tmp_path):
        from cryptocustode.config.impostazioni import Impostazioni
        from cryptocustode.config.stato import Configurazione

        return Configurazione(
            impostazioni=Impostazioni(prezzo_input=1.0, prezzo_output=2.0),
            percorso_file=tmp_path / "config.json",
        )

    def test_registra_i_token_della_chiamata(self, tmp_path):
        configurazione = self._configurazione(tmp_path)
        RilevatoreGemini(
            chiave="finta",
            chiama=_chiamata("[]", token_input=1000, token_output=200),
            configurazione=configurazione,
        ).rileva("qualunque")

        assert configurazione.sessione.token_input == 1000
        assert configurazione.sessione.token_output == 200
        assert configurazione.sessione.chiamate == 1

    def test_due_chiamate_si_sommano(self, tmp_path):
        configurazione = self._configurazione(tmp_path)
        rilevatore = RilevatoreGemini(
            chiave="finta",
            chiama=_chiamata("[]", token_input=10, token_output=5),
            configurazione=configurazione,
        )
        rilevatore.rileva("uno")
        rilevatore.rileva("due")

        assert configurazione.sessione.chiamate == 2
        assert configurazione.sessione.token_input == 20
        assert configurazione.consumo()["sessione"]["costo"] == pytest.approx(
            (20 * 1.0 + 10 * 2.0) / 1_000_000
        )

    def test_conta_anche_la_chiamata_con_risposta_malformata(self, tmp_path):
        """I token si pagano comunque. Non contarli farebbe sparire dal totale
        proprio le chiamate andate storte, cioè quelle su cui uno vorrebbe
        sapere quanto ha buttato."""
        configurazione = self._configurazione(tmp_path)
        with pytest.raises(AIResponseInvalid):
            RilevatoreGemini(
                chiave="finta",
                chiama=_chiamata("non json", token_input=700, token_output=3),
                configurazione=configurazione,
            ).rileva("qualunque")

        assert configurazione.sessione.token_input == 700
        assert configurazione.sessione.chiamate == 1

    def test_la_configurazione_decide_modello_e_chiave(self, tmp_path):
        """La precedenza è della configurazione: è ciò che l'utente ha appena
        scritto nella pagina, mentre gli argomenti di costruzione sono default.
        Al contrario la pagina mostrerebbe un modello diverso da quello vero."""
        from cryptocustode.config.impostazioni import Impostazioni, con_chiave_nuova
        from cryptocustode.config.stato import Configurazione

        impostazioni = con_chiave_nuova(
            Impostazioni(modello="gemini-3.8-pro"), "CHIAVE-DA-CONFIG", "frase"
        )
        configurazione = Configurazione(
            impostazioni=impostazioni, percorso_file=tmp_path / "config.json"
        )
        visti = {}

        def chiama(modello, istruzioni, testo, schema, chiave):
            visti.update(modello=modello, chiave=chiave)
            return Risposta(testo="[]")

        RilevatoreGemini(
            chiave="quella-di-costruzione",
            modello="gemini-3.8-flash",
            chiama=chiama,
            configurazione=configurazione,
        ).rileva("qualunque")

        assert visti["modello"] == "gemini-3.8-pro"
        assert visti["chiave"] == "CHIAVE-DA-CONFIG"
