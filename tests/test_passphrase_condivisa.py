"""Una passphrase sola per la chiave API e per i vault.

Prima c'erano due segreti: la passphrase che protegge la chiave Gemini sul
disco, e una password scelta sul momento per ogni `.vault`. Il proprietario del
prodotto ne ha chiesto uno solo — con il flusso nuovo il vault si salva a ogni
esportazione, e una password da inventare a ogni salvataggio è una password che
finisce scritta su un foglio accanto al computer.

**Il costo va detto qui, perché è qui che si paga.** Un segreto solo apre sia
la chiave sia i fascicoli archiviati, e chi cambia passphrase rende illeggibili
i vault salvati prima. Il secondo è mitigato in `rimetti.html`, che accetta una
passphrase diversa da quella corrente; il primo è la scelta, e resta.

Quello che questi test sorvegliano è la parte che si può rompere in silenzio:
che la passphrase resti in memoria abbastanza a lungo da servire al vault, e
che non finisca mai sul disco — dove sarebbe accanto alla chiave che protegge,
cioè in un file in cui la cifratura non proteggerebbe più niente.
"""

import pytest
from fastapi.testclient import TestClient

from cryptocustode.api.app import crea_app
from cryptocustode.api.routes_fascicolo import ID_FASCICOLO_ATTIVO
from cryptocustode.config.impostazioni import Impostazioni, leggi, scrivi
from cryptocustode.config.stato import Configurazione
from cryptocustode.core import vault
from cryptocustode.core.models import Document, fascicolo_vuoto
from cryptocustode.state.session import SessionStore

from tests.doppi import RilevatoreFinto

INDIRIZZO_DI_PROVA = "http://127.0.0.1:8765"
ROTTA_SALVA = "/api/vault/salva"
ROTTA_APRI = "/api/vault/apri"
ROTTA_SBLOCCA = "/api/config/sblocca"
ROTTA_CONFIG = "/api/config"

PASSPHRASE = "la passphrase della chiave"
CHIAVE = "AIza-una-chiave-di-prova"


@pytest.fixture
def percorso(tmp_path):
    return tmp_path / "config.json"


@pytest.fixture
def store():
    deposito = SessionStore()
    fascicolo = fascicolo_vuoto(ID_FASCICOLO_ATTIVO)
    fascicolo.documents.append(
        Document(
            doc_id="d1",
            filename="contratto.txt",
            text="Mario Rossi paga.",
            page_offsets=[0],
            sha256="sha-di-prova",
        )
    )
    deposito.salva(fascicolo)
    return deposito


def configurazione_con_chiave(percorso) -> Configurazione:
    """Una configurazione che ha già salvato una chiave, come dopo il primo giro."""
    configurazione = Configurazione(impostazioni=Impostazioni(), percorso_file=percorso)
    configurazione.aggiorna(
        modello="gemini-prova",
        prezzo_input=0.0,
        prezzo_output=0.0,
        valuta="USD",
        piano_attestato=True,
        chiave=CHIAVE,
        passphrase=PASSPHRASE,
    )
    return configurazione


def client_con(store, configurazione) -> TestClient:
    app = crea_app(
        store=store, rilevatore=RilevatoreFinto([]), configurazione=configurazione
    )
    return TestClient(app, base_url=INDIRIZZO_DI_PROVA)


# --- la passphrase in memoria ----------------------------------------------


def test_una_configurazione_appena_nata_non_ha_passphrase(percorso):
    """Nessun valore di comodo: `None` dice «non lo so», e chi ne ha bisogno
    deve chiederla all'utente invece di cifrare con una stringa vuota."""
    configurazione = Configurazione(impostazioni=Impostazioni(), percorso_file=percorso)

    assert configurazione.passphrase_corrente is None


def test_salvare_una_chiave_nuova_tiene_la_sua_passphrase(percorso):
    configurazione = configurazione_con_chiave(percorso)

    assert configurazione.passphrase_corrente == PASSPHRASE


def test_sbloccare_tiene_la_passphrase_con_cui_si_e_sbloccato(percorso):
    """È il caso normale: l'applicazione riparte, la chiave è sul disco, e la
    passphrase arriva dallo schermo di sblocco. Se non la trattenessimo qui,
    il primo salvataggio del fascicolo dovrebbe richiederla di nuovo."""
    configurazione_con_chiave(percorso)
    riavviata = Configurazione(percorso_file=percorso)
    assert riavviata.passphrase_corrente is None

    riavviata.sblocca(PASSPHRASE)

    assert riavviata.passphrase_corrente == PASSPHRASE


def test_una_passphrase_sbagliata_non_viene_trattenuta(percorso):
    """Trattenere il tentativo fallito farebbe cifrare i vault con una
    passphrase che non apre nemmeno la chiave: due segreti diversi senza che
    nessuno lo abbia deciso."""
    configurazione_con_chiave(percorso)
    riavviata = Configurazione(percorso_file=percorso)

    with pytest.raises(Exception):
        riavviata.sblocca("non è questa")

    assert riavviata.passphrase_corrente is None


def test_la_passphrase_non_finisce_sul_disco(percorso):
    """Il file di configurazione contiene la chiave **cifrata**: scriverci
    accanto la passphrase che la decifra renderebbe la cifratura un ornamento.
    """
    configurazione = configurazione_con_chiave(percorso)

    testo = percorso.read_text(encoding="utf-8")

    assert PASSPHRASE not in testo
    assert CHIAVE not in testo
    assert leggi(percorso).chiave is None


def test_la_passphrase_non_esce_dalla_rotta_della_configurazione(percorso, store):
    """`GET /api/config` dice se la chiave è pronta, non con che cosa si apre."""
    configurazione = configurazione_con_chiave(percorso)
    with client_con(store, configurazione) as client:
        corpo = client.get(ROTTA_CONFIG).json()

    assert PASSPHRASE not in str(corpo)
    assert "passphrase" not in corpo


# --- il vault che la riusa --------------------------------------------------


def test_il_vault_si_salva_senza_chiedere_una_password(percorso, store):
    """Il corpo senza `password` non è una dimenticanza: è il flusso nuovo, in
    cui l'esportazione salva il fascicolo da sé. Il blob deve aprirsi con la
    passphrase della configurazione, altrimenti si è cifrato con qualcosa che
    nessuno conosce."""
    configurazione = configurazione_con_chiave(percorso)
    with client_con(store, configurazione) as client:
        risposta = client.post(ROTTA_SALVA, json={})

    assert risposta.status_code == 200
    riaperto = vault.carica(risposta.content, PASSPHRASE)
    assert [d.filename for d in riaperto.documents] == ["contratto.txt"]


def test_una_password_esplicita_ha_ancora_la_precedenza(percorso, store):
    """Chi la manda vince: la rotta serve anche a chi vuole un vault chiuso con
    un segreto suo, e il ripiego non deve poterglielo togliere di mano."""
    configurazione = configurazione_con_chiave(percorso)
    with client_con(store, configurazione) as client:
        risposta = client.post(ROTTA_SALVA, json={"password": "un segreto solo mio"})

    assert risposta.status_code == 200
    assert vault.carica(risposta.content, "un segreto solo mio") is not None


def test_senza_passphrase_aperta_il_salvataggio_si_rifiuta(percorso, store):
    """Il rifiuto è l'unica risposta onesta: cifrare con una stringa vuota
    darebbe un file che *sembra* protetto. Il messaggio deve dire cosa fare,
    perché l'utente non ha idea di che cosa sia una passphrase «aperta»."""
    configurazione = Configurazione(impostazioni=Impostazioni(), percorso_file=percorso)
    with client_con(store, configurazione) as client:
        risposta = client.post(ROTTA_SALVA, json={})

    assert risposta.status_code == 409
    assert "passphrase" in risposta.json()["errore"].lower()


def test_il_vault_si_riapre_senza_ridigitare_la_passphrase(percorso, store):
    configurazione = configurazione_con_chiave(percorso)
    with client_con(store, configurazione) as client:
        blob = client.post(ROTTA_SALVA, json={}).content
        # Il fascicolo attivo non è più quello: riaprire deve rimetterlo al suo
        # posto, altrimenti il test passerebbe guardando il fascicolo di prima.
        store.salva(fascicolo_vuoto(ID_FASCICOLO_ATTIVO))

        risposta = client.post(
            ROTTA_APRI, files={"file": ("fascicolo.vault", blob)}
        )

    assert risposta.status_code == 200
    assert [d["filename"] for d in risposta.json()["documenti"]] == ["contratto.txt"]


def test_un_vault_vecchio_si_riapre_con_la_sua_passphrase(percorso, store):
    """La mitigazione della scelta: chi ha cambiato passphrase deve poter
    riaprire i fascicoli chiusi con quella di prima. Senza questa strada il
    cambio di passphrase distruggerebbe in silenzio tutto l'archivio."""
    fascicolo = store.prendi(ID_FASCICOLO_ATTIVO)
    vecchio = vault.salva(fascicolo, "la passphrase di una volta")
    configurazione = configurazione_con_chiave(percorso)
    with client_con(store, configurazione) as client:
        risposta = client.post(
            ROTTA_APRI,
            files={"file": ("vecchio.vault", vecchio)},
            data={"password": "la passphrase di una volta"},
        )

    assert risposta.status_code == 200
