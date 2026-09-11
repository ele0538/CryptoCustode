"""Il tetto alla dimensione dei caricamenti (issue #27).

Difende l'invariante della §10 — fuori dal vault il fascicolo vive **solo**
nella RAM del processo — nel punto in cui la #3 l'aveva lasciata violabile:
alzare `spool_max_size` a 64 MiB ha tolto di mezzo i documenti di dimensione
normale, ma un caricamento più grande rotolava ancora in un file **in chiaro**
nella cartella temporanea, e niente lo rifiutava.

Il controllo non può vivere nel corpo della route. `max_part_size` di starlette
è verificato solo nel ramo delle parti che non sono file (`formparsers.py`,
`on_part_data`): quando `carica_documento` riceve il suo `UploadFile` i byte
sono già stati scritti. Un `if len(contenuto) > TETTO` dopo `await read()`
sarebbe un rifiuto a danno già fatto. Perciò questi test guardano il rifiuto
**prima** del parser, e il più importante non guarda la risposta HTTP ma la
cartella temporanea.
"""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.formparsers import MultiPartParser

from cryptocustode.api.app import (
    DIMENSIONE_MASSIMA_IN_MEMORIA,
    TETTO_RICHIESTA,
    crea_app,
)
from cryptocustode.core.errors import UploadTooLarge
from cryptocustode.state.session import SessionStore

ROTTA = "/api/fascicolo/documenti"
INDIRIZZO_DI_PROVA = "http://127.0.0.1:8765"
TETTO_DI_PROVA = 2048
"""Un tetto piccolo passato all'app: i test provano il *meccanismo*, non il
valore di produzione, e spostare megabyte per dimostrarlo renderebbe la suite
lenta senza dimostrare niente di più."""


@pytest.fixture
def store() -> SessionStore:
    return SessionStore()


@pytest.fixture
def client(store):
    app = crea_app(store=store, tetto_richiesta=TETTO_DI_PROVA)
    with TestClient(app, base_url=INDIRIZZO_DI_PROVA) as client:
        yield client


def carica(client: TestClient, nome: str, contenuto: bytes):
    return client.post(ROTTA, files={"file": (nome, contenuto)})


def test_un_caricamento_oltre_il_tetto_e_rifiutato_con_413(client):
    risposta = carica(client, "grosso.txt", b"x" * (TETTO_DI_PROVA + 1))
    assert risposta.status_code == 413


def test_il_messaggio_del_rifiuto_e_in_italiano_e_dice_il_tetto(client):
    risposta = carica(client, "grosso.txt", b"x" * (TETTO_DI_PROVA + 1))
    messaggio = risposta.json()["errore"]
    assert "troppo grande" in messaggio
    assert str(TETTO_DI_PROVA) in messaggio


def test_un_caricamento_sotto_il_tetto_passa(client, store):
    # Senza questo, un tetto messo a zero passerebbe tutti gli altri test.
    risposta = carica(client, "piccolo.txt", "Torino".encode("utf-8"))
    assert risposta.status_code == 201


def test_il_rifiuto_non_fa_mai_toccare_il_disco_al_caricamento(client, monkeypatch):
    """Il test che conta: rende la §10 falsificabile invece che una promessa.

    Guarda il **momento** in cui i byte passerebbero dalla RAM al disco, non la
    cartella temporanea a richiesta finita. La differenza non è accademica:
    `SpooledTemporaryFile` cancella il proprio file alla chiusura, quindi una
    cartella vuota alla fine è compatibile con un file scritto, letto e
    rimosso nel frattempo — cioè col dato in chiaro finito su disco. Un test
    che guarda dopo non distingue i due casi e passa comunque (verificato: lo
    faceva, a middleware spento).

    `rollover` è il punto esatto del passaggio. Spiarlo, invece di ispezionare
    il filesystem, rende l'asserzione insensibile a dove il file venga scritto
    e a quanto in fretta sparisca.

    La soglia di spool viene abbassata sotto il payload perché con i 64 MiB di
    produzione nessun carico di prova la supererebbe: senza questa riga il test
    dimostrerebbe soltanto che 8 KiB sono meno di 64 MiB.
    """
    rollover_chiamati = []
    originale = tempfile.SpooledTemporaryFile.rollover

    def rollover_spiato(self):
        rollover_chiamati.append(True)
        return originale(self)

    monkeypatch.setattr(tempfile.SpooledTemporaryFile, "rollover", rollover_spiato)
    monkeypatch.setattr(MultiPartParser, "spool_max_size", 512)

    carica(client, "grosso.txt", b"x" * (TETTO_DI_PROVA * 4))

    assert rollover_chiamati == []


def test_la_spia_del_disco_vede_davvero_un_rollover(client, monkeypatch):
    """Senza questo, il test sopra sarebbe verde anche se la spia non spiasse.

    Una lista vuota è insieme il risultato atteso e il risultato di uno
    strumento rotto. Qui il caricamento sta **sotto** il tetto — quindi non
    viene rifiutato — ma sopra la soglia di spool abbassata: i byte toccano il
    disco davvero, e la spia deve vederlo.

    È anche la dimostrazione che il difetto di questa issue esisteva: è il
    comportamento del prodotto prima del tetto, riprodotto in piccolo.
    """
    rollover_chiamati = []
    originale = tempfile.SpooledTemporaryFile.rollover

    def rollover_spiato(self):
        rollover_chiamati.append(True)
        return originale(self)

    monkeypatch.setattr(tempfile.SpooledTemporaryFile, "rollover", rollover_spiato)
    monkeypatch.setattr(MultiPartParser, "spool_max_size", 512)

    risposta = carica(client, "medio.txt", b"x" * (TETTO_DI_PROVA - 512))

    assert risposta.status_code == 201
    assert rollover_chiamati != []


def test_il_tetto_sta_sotto_la_soglia_oltre_la_quale_si_scrive_su_disco():
    # Il rapporto fra i due numeri è la ragione per cui il rifiuto arriva in
    # tempo: se il tetto superasse la soglia di spool, una richiesta ammessa
    # potrebbe comunque rotolare su disco e il rifiuto arriverebbe dopo la
    # scrittura, cioè troppo tardi.
    assert TETTO_RICHIESTA <= DIMENSIONE_MASSIMA_IN_MEMORIA


def test_una_richiesta_senza_content_length_e_rifiutata(client):
    # Senza `Content-Length` non si può decidere prima di leggere, e leggere
    # per contare è esattamente ciò che questa issue vieta. Si rifiuta:
    # davanti a un'invariante di riservatezza il dubbio si chiude, non si apre.
    risposta = client.post(
        ROTTA,
        content=iter([b"x" * 64]),
        headers={"Content-Type": "multipart/form-data; boundary=x"},
    )
    assert risposta.status_code == 413


def test_l_errore_del_tetto_e_un_errore_di_dominio():
    # Deve passare dal gate della §13 come tutti gli altri, non essere un
    # caso speciale del layer HTTP: è ciò che gli fa avere un messaggio in
    # italiano e una riga nella tabella.
    assert issubclass(UploadTooLarge, Exception)
    from cryptocustode.api.app import STATO_HTTP

    assert STATO_HTTP[UploadTooLarge] == 413
