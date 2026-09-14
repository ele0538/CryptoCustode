"""La coda dei suggerimenti di fusione vista dall'applicazione (issue #51).

Le rotte vivono in `api/routes_fusioni.py` e non dentro quelle del fascicolo:
il suggerimento non è un passo della revisione — non blocca niente e si può
ignorare per sempre — e tenerlo in un file suo lascia `routes_fascicolo.py` a
chi ci sta lavorando sopra.

Il ricalcolo è una rotta a sé e non un effetto dell'analisi per la stessa
ragione. La pagina lo chiama dopo aver analizzato; chi non lo chiama non vede
suggerimenti e non perde nulla di ciò che c'era prima.
"""

import pytest
from fastapi.testclient import TestClient

from cryptocustode.api.app import crea_app
from cryptocustode.api.routes_fascicolo import ID_FASCICOLO_ATTIVO
from cryptocustode.core.models import Category, Rilevazione, State
from cryptocustode.state.session import SessionStore, approva

from tests.doppi import RilevatoreFinto, accendi

INDIRIZZO_DI_PROVA = "http://127.0.0.1:8765"
ROTTA_DOCUMENTI = "/api/fascicolo/documenti"
ROTTA_ANALISI = "/api/fascicolo/analisi"
ROTTA_FUSIONI = "/api/fusioni"
ROTTA_RICALCOLO = "/api/fusioni/ricalcolo"
ROTTA_DECISIONE = "/api/fusioni/decisione"

TESTO = "Mario Rossi firma. Anche M. Rossi firma. Anna Bianchi no."
MARIO = Rilevazione(valore="Mario Rossi", categoria=Category.PERSONA)
M_ROSSI = Rilevazione(valore="M. Rossi", categoria=Category.PERSONA)
ANNA = Rilevazione(valore="Anna Bianchi", categoria=Category.PERSONA)


@pytest.fixture
def store() -> SessionStore:
    return SessionStore()


@pytest.fixture
def client(store):
    rilevatore = RilevatoreFinto(sempre=[MARIO, M_ROSSI, ANNA])
    with TestClient(
        crea_app(store=store, rilevatore=rilevatore), base_url=INDIRIZZO_DI_PROVA
    ) as client:
        yield client


@pytest.fixture
def analizzato(client, store):
    client.post(
        ROTTA_DOCUMENTI, files={"file": ("doc.txt", TESTO.encode("utf-8"), "text/plain")}
    )
    client.post(ROTTA_ANALISI)
    accendi(store.prendi(ID_FASCICOLO_ATTIVO), Category.PERSONA)
    return client


def fascicolo_di(store):
    return store.prendi(ID_FASCICOLO_ATTIVO)


def segnaposto_di(store, valore: str) -> str:
    """Il segnaposto assegnato a un valore.

    Chiesto alla tabella e non scritto a mano: gli indici li decide
    `assegna_tag` in ordine di lunghezza decrescente, non nell'ordine in cui il
    modello elenca i valori, e `Anna Bianchi` si prende infatti `[PERSONA_1]`
    pur non entrando in nessuna fusione. Un test che li fissasse a mano
    rifarebbe quel calcolo a occhio, e andrebbe riscritto a ogni ritocco del
    testo di prova.
    """
    return next(t.tag for t in fascicolo_di(store).tags.values() if t.valore == valore)


class TestRicalcolo:
    def test_la_coda_nasce_vuota(self, analizzato):
        """L'analisi da sola non apre suggerimenti: chi non chiede il ricalcolo
        vede il fascicolo esattamente com'era prima della issue #51."""
        assert analizzato.get(ROTTA_FUSIONI).json()["fusioni"] == []

    def test_il_ricalcolo_apre_la_coppia_equivalente(self, analizzato, store):
        esito = analizzato.post(ROTTA_RICALCOLO).json()

        assert len(esito["fusioni"]) == 1
        proposta = esito["fusioni"][0]
        assert proposta["tag_a"] == segnaposto_di(store, "Mario Rossi")
        assert proposta["tag_b"] == segnaposto_di(store, "M. Rossi")
        assert proposta["risolta"] is False

    def test_anna_bianchi_non_entra_in_nessuna_coppia(self, analizzato, store):
        """Il terzo tag del fascicolo non somiglia a nessuno, e deve restare
        fuori dalla coda: un suggerimento di troppo e' un invito a fondere due
        persone diverse."""
        esito = analizzato.post(ROTTA_RICALCOLO).json()

        anna = segnaposto_di(store, "Anna Bianchi")
        coinvolti = {t for f in esito["fusioni"] for t in (f["tag_a"], f["tag_b"])}
        assert anna not in coinvolti

    def test_la_proposta_porta_i_valori_e_non_solo_i_segnaposto(self, analizzato):
        """Senza i valori la pagina chiederebbe all'utente se `[PERSONA_1]` e
        `[PERSONA_2]` sono la stessa persona, che è una domanda a cui nessuno
        può rispondere."""
        proposta = analizzato.post(ROTTA_RICALCOLO).json()["fusioni"][0]

        assert {proposta["valore_a"], proposta["valore_b"]} == {"Mario Rossi", "M. Rossi"}

    def test_ricalcolare_due_volte_non_duplica(self, analizzato):
        analizzato.post(ROTTA_RICALCOLO)

        esito = analizzato.post(ROTTA_RICALCOLO).json()

        assert len(esito["fusioni"]) == 1

    def test_il_ricalcolo_non_fonde_niente(self, analizzato, store):
        """Separare è il default: finché l'utente non decide, i due tag restano
        due tag (spec §7)."""
        analizzato.post(ROTTA_RICALCOLO)

        valori = {t.valore for t in fascicolo_di(store).tags.values()}
        assert {"Mario Rossi", "M. Rossi"} <= valori


class TestDecisione:
    def test_fondi_unisce_sotto_il_segnaposto_piu_vecchio(self, analizzato, store):
        proposta = analizzato.post(ROTTA_RICALCOLO).json()["fusioni"][0]

        risposta = analizzato.post(
            ROTTA_DECISIONE,
            json={"fusione_id": proposta["fusione_id"], "decisione": "fondi"},
        )

        assert risposta.status_code == 200
        tabella = fascicolo_di(store).tags
        assert proposta["tag_b"] not in tabella
        assert tabella[proposta["tag_a"]].varianti == ("M. Rossi",)

    def test_dopo_la_fusione_le_occorrenze_sono_ricontate(self, analizzato, store):
        """Il segnaposto sopravvissuto copre ora due occorrenze: lasciarne una
        sola scritta mostrerebbe in revisione un conteggio che il testo
        mascherato smentisce."""
        proposta = analizzato.post(ROTTA_RICALCOLO).json()["fusioni"][0]

        analizzato.post(
            ROTTA_DECISIONE,
            json={"fusione_id": proposta["fusione_id"], "decisione": "fondi"},
        )

        assert fascicolo_di(store).tags[proposta["tag_a"]].occorrenze == 2

    def test_separa_lascia_i_due_tag_dove_sono(self, analizzato, store):
        proposta = analizzato.post(ROTTA_RICALCOLO).json()["fusioni"][0]

        analizzato.post(
            ROTTA_DECISIONE,
            json={"fusione_id": proposta["fusione_id"], "decisione": "separa"},
        )

        tabella = fascicolo_di(store).tags
        assert {proposta["tag_a"], proposta["tag_b"]} <= set(tabella)

    def test_una_coppia_decisa_non_si_ripropone(self, analizzato):
        proposta = analizzato.post(ROTTA_RICALCOLO).json()["fusioni"][0]
        analizzato.post(
            ROTTA_DECISIONE,
            json={"fusione_id": proposta["fusione_id"], "decisione": "separa"},
        )

        esito = analizzato.post(ROTTA_RICALCOLO).json()

        assert [f["fusione_id"] for f in esito["fusioni"]] == [proposta["fusione_id"]]
        assert esito["fusioni"][0]["risolta"] is True

    def test_la_seconda_decisione_sulla_stessa_coppia_e_un_conflitto(self, analizzato):
        """Arriva su un fascicolo che non è più quello che l'utente stava
        guardando: i due tag che la proposta nominava sono già stati uniti o
        lasciati stare."""
        proposta = analizzato.post(ROTTA_RICALCOLO).json()["fusioni"][0]
        corpo = {"fusione_id": proposta["fusione_id"], "decisione": "fondi"}
        analizzato.post(ROTTA_DECISIONE, json=corpo)

        risposta = analizzato.post(ROTTA_DECISIONE, json=corpo)

        assert risposta.status_code == 409

    def test_una_coppia_inesistente_e_un_404(self, analizzato):
        risposta = analizzato.post(
            ROTTA_DECISIONE, json={"fusione_id": "[PERSONA_8]+[PERSONA_9]", "decisione": "fondi"}
        )

        assert risposta.status_code == 404

    def test_una_decisione_inventata_e_rifiutata_dalla_validazione(self, analizzato):
        proposta = analizzato.post(ROTTA_RICALCOLO).json()["fusioni"][0]

        risposta = analizzato.post(
            ROTTA_DECISIONE,
            json={"fusione_id": proposta["fusione_id"], "decisione": "cancella"},
        )

        assert risposta.status_code == 422

    def test_la_fusione_annulla_l_approvazione(self, analizzato, store):
        """Spec §5: il testo mascherato cambia, quindi l'hash approvato non vale
        più. Senza questa riga si esporterebbe un testo diverso da quello
        firmato."""
        proposta = analizzato.post(ROTTA_RICALCOLO).json()["fusioni"][0]
        fascicolo = fascicolo_di(store)
        approva(fascicolo)

        analizzato.post(
            ROTTA_DECISIONE,
            json={"fusione_id": proposta["fusione_id"], "decisione": "fondi"},
        )

        assert fascicolo_di(store).state is State.PENDING_REVIEW
        assert fascicolo_di(store).approval_hash is None

    def test_la_risposta_e_la_forma_della_revisione(self, analizzato):
        """Come ogni toggle: la pagina si ridisegna con il codice che ha già."""
        proposta = analizzato.post(ROTTA_RICALCOLO).json()["fusioni"][0]

        esito = analizzato.post(
            ROTTA_DECISIONE,
            json={"fusione_id": proposta["fusione_id"], "decisione": "fondi"},
        ).json()

        assert set(esito) >= {"stato", "categorie", "documenti"}


def test_il_suggerimento_sopravvive_al_vault(analizzato, store):
    """Varianti e coda stanno nel formato v4: senza, riaprire un fascicolo
    riproporrebbe una fusione già decisa, o peggio la disferebbe."""
    proposta = analizzato.post(ROTTA_RICALCOLO).json()["fusioni"][0]
    analizzato.post(
        ROTTA_DECISIONE,
        json={"fusione_id": proposta["fusione_id"], "decisione": "fondi"},
    )
    blob = analizzato.post("/api/vault/salva", json={"password": "prova"}).content

    nuovo_store = SessionStore()
    app = crea_app(store=nuovo_store, rilevatore=RilevatoreFinto(sempre=[]))
    with TestClient(app, base_url=INDIRIZZO_DI_PROVA) as nuovo_client:
        nuovo_client.post(
            "/api/vault/apri",
            data={"password": "prova"},
            files={"file": ("f.vault", blob, "application/octet-stream")},
        )
        coda = nuovo_client.get(ROTTA_FUSIONI).json()["fusioni"]

    riaperto = nuovo_store.prendi(ID_FASCICOLO_ATTIVO)
    assert riaperto.tags[proposta["tag_a"]].varianti == ("M. Rossi",)
    assert [f["risolta"] for f in coda] == [True]
