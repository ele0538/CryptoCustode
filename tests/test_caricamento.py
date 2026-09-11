"""Caricamento dei documenti dalla UI, coi rifiuti visibili all'utente (issue #3).

Questi test difendono due cose distinte:

1. che TXT e PDF digitali entrino davvero nel fascicolo col testo estratto;
2. che i rifiuti del motore — tetto dei 10, PDF scansionato, TXT non UTF-8,
   omonimia — arrivino allo schermo come messaggi in italiano con il dettaglio
   che serve a rimediare (pagina, offset, nome del file), invece di morire come
   500 con un traceback.

Il fascicolo è ispezionato **attraverso lo store**, non solo attraverso la
risposta HTTP: un rifiuto deve lasciare il fascicolo esattamente com'era, e la
risposta da sola non lo dimostra.
"""

import re

import pytest
from fastapi.testclient import TestClient

from cryptocustode.api.app import crea_app
from cryptocustode.api.routes_fascicolo import ID_FASCICOLO_ATTIVO
from cryptocustode.state.session import SessionStore
from tests.pdf_di_prova import pdf_di_prova

ROTTA = "/api/fascicolo/documenti"


def documenti_del(store: SessionStore):
    """I nomi dei documenti entrati nel fascicolo attivo, in ordine di arrivo.

    Restituisce `[]` anche quando il fascicolo non esiste ancora: la creazione è
    pigra (vedi `fascicolo_attivo`), quindi un rifiuto al primo caricamento
    lascia lo store vuoto. Per chi guarda da fuori i due casi sono lo stesso —
    nessun documento è entrato — e distinguerli qui renderebbe i test dei
    rifiuti dipendenti dall'ordine dei controlli dentro la route.

    Resta falsificabile: se la route smettesse di salvare il fascicolo, i test
    del percorso felice vedrebbero `[]` al posto dei nomi attesi.
    """
    try:
        fascicolo = store.prendi(ID_FASCICOLO_ATTIVO)
    except KeyError:
        return []
    return [documento.filename for documento in fascicolo.documents]


def carica(client: TestClient, nome: str, contenuto: bytes):
    """Un caricamento multipart, come lo fa la UI: un file per richiesta."""
    return client.post(ROTTA, files={"file": (nome, contenuto)})


@pytest.fixture
def store() -> SessionStore:
    """Lo store del test, passato all'app come seme.

    Senza il seme lo store sarebbe interno all'app e i test dovrebbero credere
    alla risposta HTTP sulla parola; con un `SessionStore` globale di modulo si
    passerebbero invece i fascicoli l'uno all'altro.
    """
    return SessionStore()


@pytest.fixture
def client(store):
    with TestClient(crea_app(store=store)) as client:
        yield client


def test_un_txt_utf8_entra_nel_fascicolo_col_testo_estratto(client, store):
    """Il primo criterio della issue #3. Se la route non salva il documento nel
    fascicolo attivo, la risposta può comunque dire 201 e l'utente crede di aver
    caricato: al momento dell'analisi il fascicolo è vuoto."""
    risposta = carica(client, "contratto.txt", "Il sig. Rossi è a Torino.".encode("utf-8"))

    assert risposta.status_code == 201
    assert documenti_del(store) == ["contratto.txt"]
    assert store.prendi(ID_FASCICOLO_ATTIVO).documents[0].text == "Il sig. Rossi è a Torino."


def test_un_pdf_digitale_entra_nel_fascicolo_col_testo_estratto(client, store):
    """Il PDF passa da un estrattore diverso dal TXT: una route che decodificasse
    tutto come testo supererebbe il test sul TXT e fallirebbe qui, perché i byte
    di un PDF non sono UTF-8 valido."""
    risposta = carica(client, "contratto.pdf", pdf_di_prova(["testo"]))

    assert risposta.status_code == 201
    assert documenti_del(store) == ["contratto.pdf"]
    assert "Contratto di locazione" in store.prendi(ID_FASCICOLO_ATTIVO).documents[0].text


def test_la_risposta_restituisce_il_testo_originale_estratto(client):
    """L'utente deve poter leggere che cosa è stato estratto dal file: è il solo
    modo di accorgersi che un PDF ha reso testo sbagliato o vuoto. È il testo
    **originale**, non il mascherato: l'invariante 3 della spec §4 vuole che il
    mascherato esca solo dal gate di esportazione.

    Il conteggio dei caratteri è contato a mano sulla frase, non chiesto al
    codice sotto test."""
    risposta = carica(client, "nota.txt", "Torino, 12 marzo.".encode("utf-8"))

    esito = risposta.json()
    assert esito["testo"] == "Torino, 12 marzo."
    assert esito["caratteri"] == 17
    assert esito["pagine"] == 1
    assert esito["documenti_nel_fascicolo"] == 1


def test_il_testo_mascherato_non_compare_nella_risposta_del_caricamento(client):
    """Invariante 3 della spec §4 e §4 «nessuna anteprima del mascherato prima
    dell'approvazione»: se la route servisse anche il mascherato, l'anteprima
    sarebbe copiabile e il gate di approvazione una formalità aggirabile."""
    risposta = carica(client, "nota.txt", "Il sig. Rossi è a Torino.".encode("utf-8"))

    corpo = risposta.text
    assert not re.search(r"\[[A-Z]+_\d+\]", corpo), (
        "nessun segnaposto deve comparire: il caricamento non maschera e non "
        f"mostra anteprime — {corpo[:200]}"
    )


# --- I rifiuti, che sono il titolo della issue ------------------------------
#
# La spec §13 mappa tutti e quattro a **422**, con un messaggio che dice cosa
# rimediare. Ogni test verifica due cose insieme, perché separate non dicono
# niente: che l'utente legga la ragione, e che il fascicolo sia rimasto com'era.
# Una route che rifiutasse dopo aver mutato il fascicolo darebbe un messaggio
# giusto e un fascicolo sbagliato.


def test_l_undicesimo_documento_e_rifiutato_e_il_fascicolo_resta_di_dieci(client, store):
    """Tetto di 10 documenti per fascicolo (spec §1). Il tetto vive in
    `aggiungi_documento`: una route che facesse `documents.append(...)` da sé
    lo aggirerebbe, e l'undicesimo entrerebbe in silenzio."""
    for numero in range(10):
        assert carica(client, f"doc{numero}.txt", b"testo").status_code == 201

    risposta = carica(client, "undicesimo.txt", b"testo")

    assert risposta.status_code == 422
    assert "10" in risposta.json()["errore"]
    assert len(documenti_del(store)) == 10
    assert "undicesimo.txt" not in documenti_del(store)


def test_un_pdf_scansionato_e_rifiutato_per_intero_con_la_pagina_colpevole(client, store):
    """Rifiuto dell'intero file, mai di una parte (spec §12), e l'utente deve
    sapere **quale** pagina: senza il numero non può né rifare la scansione né
    togliere la pagina. Qui la scansione è la terza di tre."""
    risposta = carica(client, "scansionato.pdf", pdf_di_prova(["testo", "testo", "immagine"]))

    assert risposta.status_code == 422
    assert "pagina 3" in risposta.json()["errore"]
    assert documenti_del(store) == [], "un rifiuto non deve lasciare traccia nel fascicolo"


def test_un_txt_non_utf8_e_rifiutato_con_la_posizione_del_byte_invalido(client, store):
    """La posizione serve a rimediare: dice dove guardare nel file. L'offset
    atteso è contato a mano — `Via Roma 1` sono dieci caratteri ASCII, indici da
    0 a 9, quindi il byte `0xff` sta all'offset 10 — e non chiesto al codice."""
    risposta = carica(client, "latino1.txt", "Via Roma 1".encode("ascii") + b"\xff")

    assert risposta.status_code == 422
    assert "offset 10" in risposta.json()["errore"]
    assert documenti_del(store) == []


def test_il_secondo_file_con_lo_stesso_nome_e_rifiutato_col_nome_nel_messaggio(client, store):
    """Due omonimi collasserebbero in una sola chiave del payload di export e
    l'utente riceverebbe un documento in meno senza errori (spec §8, issue #19).
    Il nome nel messaggio è ciò che gli permette di capire quale rinominare."""
    assert carica(client, "contratto.txt", b"primo").status_code == 201

    risposta = carica(client, "contratto.txt", b"secondo")

    assert risposta.status_code == 422
    assert "contratto.txt" in risposta.json()["errore"]
    assert documenti_del(store) == ["contratto.txt"]
    assert store.prendi(ID_FASCICOLO_ATTIVO).documents[0].text == "primo", (
        "il primo documento non deve essere sovrascritto dal secondo"
    )


def test_i_segnaposto_gia_presenti_sono_un_avviso_con_la_posizione_non_un_rifiuto(
    client, store
):
    """Spec §12: il documento entra, ma l'utente viene avvisato. Al ripristino
    quella stringa verrebbe interpretata come segnaposto e sostituita con dati
    veri, corrompendo il testo — e se qui fosse un rifiuto, un documento
    legittimo che cita un segnaposto non si potrebbe caricare affatto.

    La posizione attesa è contata a mano: `Il sig. ` sono otto caratteri, indici
    da 0 a 7, quindi la parentesi quadra sta all'offset 8."""
    risposta = carica(client, "citazione.txt", "Il sig. [PERSONA_1] è a Torino.".encode("utf-8"))

    assert risposta.status_code == 201
    assert documenti_del(store) == ["citazione.txt"], "l'avviso non è un rifiuto"
    assert risposta.json()["segnaposto_preesistenti"] == [
        {"posizione": 8, "segnaposto": "[PERSONA_1]"}
    ]


def test_un_documento_pulito_non_porta_avvisi_di_segnaposto(client):
    """Il controllo del controllo: senza questo, un avviso restituito sempre —
    anche a vuoto — passerebbe per un rilevamento funzionante, e la UI
    mostrerebbe un allarme a ogni caricamento finché nessuno ci crede più."""
    risposta = carica(client, "pulito.txt", "Nessun segnaposto qui.".encode("utf-8"))

    assert risposta.json()["segnaposto_preesistenti"] == []


def test_ogni_errore_di_dominio_ha_uno_stato_http_dichiarato():
    """La tabella della spec §13 vive in un posto solo, `STATO_HTTP`. Questo
    test è il guardiano di quel posto: un errore di dominio aggiunto senza la
    sua riga arriverebbe all'utente come 500 con un traceback, che è esattamente
    ciò che la §13 esiste per impedire.

    Il confronto è sulle sottoclassi vive di `CryptoCustodeError`, non su un
    elenco scritto a mano che si sgancerebbe dal codice."""
    from cryptocustode.api.app import STATO_HTTP
    from cryptocustode.core.errors import CryptoCustodeError

    def discendenti(classe):
        for figlia in classe.__subclasses__():
            yield figlia
            yield from discendenti(figlia)

    senza_stato = {
        errore.__name__ for errore in discendenti(CryptoCustodeError) if errore not in STATO_HTTP
    }
    assert senza_stato == set(), (
        "errori di dominio senza stato HTTP nella tabella della spec §13: "
        + ", ".join(sorted(senza_stato))
    )
