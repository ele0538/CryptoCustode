"""Vault applicato: salva, riapri, riprendi la revisione (issue #9, issue #51).

Il motore crittografico e la serializzazione esistono da prima e hanno i loro
test in `tests/test_vault.py`: qui si prova il cablaggio all'applicazione, che
è l'unica parte che mancava: quando si salva, cosa torna indietro, e cosa
succede se la password è sbagliata.

Il giro passa dal `SessionStore`, e non da `vault.salva`/`vault.carica` chiamate
a mano, perché è proprio lì che stava il difetto che la issue #51 denuncia: il
vault funzionava e dall'applicazione non ci si arrivava.

L'approvazione e l'esportazione non hanno ancora una route su questo ramo (la
#7 vive su `feat/p6-disambiguazione`): questi test le richiamano direttamente
da `state/session.py`, come fa `tests/test_export.py`.
"""

import pytest
from fastapi.testclient import TestClient

from cryptocustode.api.app import crea_app
from cryptocustode.api.routes_fascicolo import ID_FASCICOLO_ATTIVO
from cryptocustode.core import vault
from cryptocustode.core.models import Category, Rilevazione, StatoTag
from cryptocustode.state.session import SessionStore, approva, export_sanitized_text

from tests.doppi import RilevatoreFinto, accendi

INDIRIZZO_DI_PROVA = "http://127.0.0.1:8765"
ROTTA_DOCUMENTI = "/api/fascicolo/documenti"
ROTTA_ANALISI = "/api/fascicolo/analisi"
ROTTA_SALVA = "/api/vault/salva"
ROTTA_APRI = "/api/vault/apri"

PASSWORD = "una password di prova"
UNO = "Il sig. Mario Rossi paga 1.200,00 euro."
DUE = "Anche Anna Bianchi lo conferma."

MARIO = Rilevazione(valore="Mario Rossi", categoria=Category.PERSONA)
ANNA = Rilevazione(valore="Anna Bianchi", categoria=Category.PERSONA)


@pytest.fixture
def rilevatore() -> RilevatoreFinto:
    """Risponde per testo, così un secondo documento non eredita le rilevazioni
    del primo: serve al test dei contatori, che carica due documenti e vuole due
    tag distinti."""
    return RilevatoreFinto({UNO: [MARIO], DUE: [ANNA]})


@pytest.fixture
def store() -> SessionStore:
    return SessionStore()


@pytest.fixture
def client(store, rilevatore):
    app = crea_app(store=store, rilevatore=rilevatore)
    with TestClient(app, base_url=INDIRIZZO_DI_PROVA) as client:
        yield client


def carica(client: TestClient, nome: str, testo: str):
    return client.post(
        ROTTA_DOCUMENTI, files={"file": (nome, testo.encode("utf-8"), "text/plain")}
    )


def fascicolo_di(store: SessionStore):
    return store.prendi(ID_FASCICOLO_ATTIVO)


def apri_su(client: TestClient, blob: bytes, password: str = PASSWORD):
    return client.post(
        ROTTA_APRI,
        data={"password": password},
        files={"file": ("f.vault", blob, "application/octet-stream")},
    )


def analizzato(client: TestClient, store: SessionStore, nome: str, testo: str):
    """Carica, analizza e accende PERSONA.

    L'accensione è necessaria: dal 2026-09-14 un fascicolo nuovo non maschera
    niente, quindi senza questa riga `export_sanitized_text` restituirebbe il
    testo in chiaro e il confronto prima/dopo la riapertura passerebbe anche
    contro un vault che perde tutta la tabella dei tag.
    """
    carica(client, nome, testo)
    client.post(ROTTA_ANALISI)
    accendi(fascicolo_di(store), Category.PERSONA)


def test_salva_risponde_con_un_blob_scaricabile(client, store):
    analizzato(client, store, "doc.txt", UNO)

    risposta = client.post(ROTTA_SALVA, json={"password": PASSWORD})

    assert risposta.status_code == 200
    assert risposta.headers["content-type"] == "application/octet-stream"
    assert "attachment" in risposta.headers["content-disposition"]
    assert risposta.content[:4] == vault.MAGIC


def test_il_blob_non_contiene_il_testo_in_chiaro(client, store):
    """La promessa della spec §2 decisione 5, verificata sui byte che escono
    davvero dalla route e non su quelli che `vault.salva` restituisce: è la
    route il punto in cui il fascicolo lascia il processo."""
    analizzato(client, store, "doc.txt", UNO)

    blob = client.post(ROTTA_SALVA, json={"password": PASSWORD}).content

    assert b"Mario Rossi" not in blob
    assert b"1.200,00" not in blob


def test_giro_completo_salva_riapri_esporta(client, store, rilevatore):
    """Il test che dice se la issue #51 è chiusa: il testo mascherato che si
    esporta dopo la riapertura è identico a quello di prima."""
    analizzato(client, store, "doc.txt", UNO)
    fascicolo = fascicolo_di(store)
    approva(fascicolo)
    testo_prima = export_sanitized_text(ID_FASCICOLO_ATTIVO, store)

    blob = client.post(ROTTA_SALVA, json={"password": PASSWORD}).content

    nuovo_store = SessionStore()
    app = crea_app(store=nuovo_store, rilevatore=rilevatore)
    with TestClient(app, base_url=INDIRIZZO_DI_PROVA) as nuovo_client:
        riapertura = apri_su(nuovo_client, blob)
        assert riapertura.status_code == 200
        assert riapertura.json()["stato"] == "APPROVED"

    testo_dopo = export_sanitized_text(ID_FASCICOLO_ATTIVO, nuovo_store)
    assert testo_dopo == testo_prima
    assert "[PERSONA_1]" in testo_dopo["doc.txt"]


def test_riapertura_restituisce_la_forma_della_revisione(client, store, rilevatore):
    """La pagina si ridisegna con la stessa risposta che rendono i toggle: se
    la forma divergesse, il JavaScript andrebbe scritto due volte."""
    analizzato(client, store, "doc.txt", UNO)
    blob = client.post(ROTTA_SALVA, json={"password": PASSWORD}).content

    nuovo_store = SessionStore()
    app = crea_app(store=nuovo_store, rilevatore=rilevatore)
    with TestClient(app, base_url=INDIRIZZO_DI_PROVA) as nuovo_client:
        esito = apri_su(nuovo_client, blob).json()

    fascicolo = nuovo_store.prendi(ID_FASCICOLO_ATTIVO)
    assert esito["documenti"][0]["filename"] == "doc.txt"
    assert esito["stato"] == fascicolo.state.value
    assert esito["categorie"][0]["categoria"] == Category.PERSONA.value
    assert esito["categorie"][0]["attiva"] is True


def test_la_tabella_dei_tag_sopravvive_alla_riapertura(client, store, rilevatore):
    """Il tag, il suo valore, le occorrenze e lo stato: è ciò che il formato v3
    ha messo al posto di span ed entità, ed è ciò che si perde per primo se la
    serializzazione dimentica un campo."""
    analizzato(client, store, "doc.txt", UNO)
    prima = dict(fascicolo_di(store).tags)
    blob = client.post(ROTTA_SALVA, json={"password": PASSWORD}).content

    nuovo_store = SessionStore()
    app = crea_app(store=nuovo_store, rilevatore=rilevatore)
    with TestClient(app, base_url=INDIRIZZO_DI_PROVA) as nuovo_client:
        apri_su(nuovo_client, blob)

    dopo = nuovo_store.prendi(ID_FASCICOLO_ATTIVO).tags
    assert dopo == prima
    assert dopo["[PERSONA_1]"].valore == "Mario Rossi"
    assert dopo["[PERSONA_1]"].stato is StatoTag.APPLICATO


def test_il_fascicolo_riaperto_prende_l_id_attivo(client, store, rilevatore):
    """Il vincolo scritto nella docstring di `fascicolo_attivo`: un fascicolo
    riaperto sotto il proprio id non verrebbe trovato, e il primo caricamento
    successivo ne creerebbe uno vuoto facendo sparire il lavoro in silenzio."""
    analizzato(client, store, "doc.txt", UNO)
    blob = client.post(ROTTA_SALVA, json={"password": PASSWORD}).content

    nuovo_store = SessionStore()
    app = crea_app(store=nuovo_store, rilevatore=rilevatore)
    with TestClient(app, base_url=INDIRIZZO_DI_PROVA) as nuovo_client:
        apri_su(nuovo_client, blob)
        # Il secondo documento deve atterrare nel fascicolo riaperto, non in
        # uno nuovo: se l'id fosse sbagliato, qui ne nascerebbe un altro.
        carica(nuovo_client, "doc2.txt", DUE)

    assert nuovo_store.contiene(ID_FASCICOLO_ATTIVO)
    nomi = [d.filename for d in nuovo_store.prendi(ID_FASCICOLO_ATTIVO).documents]
    assert nomi == ["doc.txt", "doc2.txt"]


def test_riapertura_non_ricicla_i_contatori(client, store, rilevatore):
    """Un tag nuovo dopo la riapertura prende l'indice successivo: nessuno di
    quelli esistenti cambia segnaposto (criterio 3 della issue #9).

    Senza i contatori nel vault, `Anna Bianchi` ripartirebbe da `[PERSONA_1]` e
    si prenderebbe il segnaposto di `Mario Rossi`: il testo già consegnato a
    un'IA esterna parlerebbe di due persone diverse con lo stesso nome.
    """
    analizzato(client, store, "doc.txt", UNO)
    blob = client.post(ROTTA_SALVA, json={"password": PASSWORD}).content

    nuovo_store = SessionStore()
    app = crea_app(store=nuovo_store, rilevatore=rilevatore)
    with TestClient(app, base_url=INDIRIZZO_DI_PROVA) as nuovo_client:
        apri_su(nuovo_client, blob)
        carica(nuovo_client, "doc2.txt", DUE)
        nuovo_client.post(ROTTA_ANALISI)

    tags = nuovo_store.prendi(ID_FASCICOLO_ATTIVO).tags
    per_valore = {tag.valore: tag.tag for tag in tags.values()}
    assert per_valore["Mario Rossi"] == "[PERSONA_1]"
    assert per_valore["Anna Bianchi"] == "[PERSONA_2]"


def test_il_documento_riaperto_non_viene_rianalizzato(client, store, rilevatore):
    """`analizzati` è nel vault perché ogni rianalisi è una chiamata a Gemini
    pagata due volte per un risultato che si ha già (issue #39)."""
    analizzato(client, store, "doc.txt", UNO)
    blob = client.post(ROTTA_SALVA, json={"password": PASSWORD}).content

    nuovo_store = SessionStore()
    secondo_rilevatore = RilevatoreFinto({UNO: [MARIO], DUE: [ANNA]})
    app = crea_app(store=nuovo_store, rilevatore=secondo_rilevatore)
    with TestClient(app, base_url=INDIRIZZO_DI_PROVA) as nuovo_client:
        apri_su(nuovo_client, blob)
        nuovo_client.post(ROTTA_ANALISI)

    assert secondo_rilevatore.chiamate == []


def test_password_errata_da_lo_stesso_verdetto_del_file_manomesso(client, store):
    """Distinguere i due casi direbbe a chi ci prova che la password è l'unico
    ostacolo rimasto (spec §13)."""
    analizzato(client, store, "doc.txt", UNO)
    blob = client.post(ROTTA_SALVA, json={"password": PASSWORD}).content

    con_password_sbagliata = apri_su(client, blob, password="sbagliata")
    manomesso = bytearray(blob)
    manomesso[-1] ^= 0xFF
    con_file_manomesso = apri_su(client, bytes(manomesso))

    assert con_password_sbagliata.status_code == 422
    assert con_file_manomesso.status_code == 422
    assert con_password_sbagliata.json() == con_file_manomesso.json()


def test_versione_futura_ha_un_messaggio_proprio(client, store, monkeypatch):
    """Un vault scritto da una versione più nuova non è un file danneggiato, e
    dirlo con lo stesso messaggio manderebbe l'utente a cercare una password
    che funziona benissimo."""
    analizzato(client, store, "doc.txt", UNO)
    monkeypatch.setattr(vault, "VAULT_VERSION", vault.VAULT_VERSION + 1)
    blob = client.post(ROTTA_SALVA, json={"password": PASSWORD}).content
    monkeypatch.undo()

    risposta = apri_su(client, blob)

    assert risposta.status_code == 422
    assert risposta.json()["errore"] != "password errata o file danneggiato"


def test_un_fascicolo_aperto_non_lascia_residui_del_precedente(client, store, rilevatore):
    """La riapertura sostituisce il fascicolo, non ci si fonde dentro.

    È il caso che si sbaglia scrivendo la route con un `update` invece di una
    sostituzione: l'utente aprirebbe un vault e si troverebbe i documenti di
    due fascicoli diversi mescolati, senza alcun errore.
    """
    analizzato(client, store, "doc.txt", UNO)
    blob = client.post(ROTTA_SALVA, json={"password": PASSWORD}).content

    nuovo_store = SessionStore()
    app = crea_app(store=nuovo_store, rilevatore=rilevatore)
    with TestClient(app, base_url=INDIRIZZO_DI_PROVA) as nuovo_client:
        carica(nuovo_client, "altro.txt", DUE)
        esito = apri_su(nuovo_client, blob).json()

    nomi = [documento["filename"] for documento in esito["documenti"]]
    assert nomi == ["doc.txt"]
