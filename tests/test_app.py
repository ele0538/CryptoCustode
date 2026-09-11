"""Ossatura HTTP dell'applicazione locale (spec §2 decisione 1).

Questi test difendono tre cose distinte, e vale la pena dire quali sono perché
la terza è una proprietà di sicurezza e non una comodità:

1. la pagina della UI esiste e viene servita, con le sue risorse;
2. la scheda del browser si apre da sola, e non prima che l'app risponda;
3. l'ascolto resta sul loopback.

Il punto 3 è verificato sugli argomenti che `avvia` passa davvero al server, non
sul valore della costante `HOST`: un fascicolo contiene dati personali di terzi,
e un bind su `0.0.0.0` li offrirebbe a chiunque sia sulla stessa rete. Una
asserzione su `HOST == "127.0.0.1"` passerebbe anche se nessuno la usasse.
"""

import re
import socket

import pytest
from fastapi.testclient import TestClient

import cryptocustode.__main__ as comando
from cryptocustode.api import app as modulo
from cryptocustode.api.app import (
    PortaOccupata,
    apri_ascolto,
    avvia,
    crea_app,
    esegui_uvicorn,
)

INDIRIZZO_DI_PROVA = "http://127.0.0.1:8765"
"""L'app controlla l'intestazione `Host` e accetta solo il loopback, quindi
il `base_url` di default del TestClient (`http://testserver`) verrebbe
rifiutato con un 400. Mettere "testserver" fra gli host consentiti avrebbe
significato portare un valore di prova dentro la configurazione di
produzione; questa costante lo tiene dove deve stare."""


def test_la_home_serve_la_pagina_html_con_il_nome_dell_app():
    """La slice esiste per dimostrare che l'ossatura HTTP c'è: se la route `/`
    manca, o punta a un file inesistente, qui arriva 404 o 500 invece di 200.

    Il tipo di contenuto è parte del contratto: servita come `text/plain` la
    pagina arriverebbe comunque 200, e il browser mostrerebbe il sorgente HTML
    all'utente invece della UI."""
    with TestClient(crea_app(), base_url=INDIRIZZO_DI_PROVA) as client:
        risposta = client.get("/")

    assert risposta.status_code == 200
    assert risposta.headers["content-type"].startswith("text/html")
    assert "<h1>CryptoCustode</h1>" in risposta.text


def test_ogni_risorsa_referenziata_dalla_pagina_e_servita():
    """Una risorsa referenziata e non servita non fa fallire la GET di `/`: la
    pagina arriva comunque 200 e resta muta sotto gli occhi dell'utente. Questo
    test estrae i riferimenti dalla pagina e li chiede davvero, così un mount
    dimenticato o un file rinominato falliscono qui."""
    with TestClient(crea_app(), base_url=INDIRIZZO_DI_PROVA) as client:
        pagina = client.get("/").text
        riferimenti = re.findall(r'(?:href|src)="(/[^"]+)"', pagina)

        assert riferimenti, "la pagina deve referenziare il CSS e lo script della UI"
        for riferimento in riferimenti:
            assert client.get(riferimento).status_code == 200, riferimento


def test_avvia_lega_il_server_al_solo_loopback():
    """`0.0.0.0` esporrebbe in rete locale un fascicolo di dati personali."""
    passati = []

    avvia(esegui=lambda app, host, porta: passati.append((host, porta)), apri=lambda url: None)

    assert [host for host, _ in passati] == ["127.0.0.1"]


def test_avvia_apre_il_browser_sull_indirizzo_su_cui_il_server_ascolta():
    """L'indirizzo atteso è derivato da quello che il server ha ricevuto, non
    dalla costante `INDIRIZZO`: se le due cose divergono — per esempio perché
    la porta è stata cambiata in un posto solo — la scheda si aprirebbe su una
    connessione rifiutata, e questo test lo intercetta."""
    aperti = []
    ascolto = []

    def esegui(app, host, porta):
        ascolto.append((host, porta))
        with TestClient(app):  # il server porta su l'app: è lì che scatta l'apertura
            pass

    avvia(esegui=esegui, apri=aperti.append)

    host, porta = ascolto[0]
    assert aperti == [f"http://{host}:{porta}/"]


def test_l_apertura_del_browser_scatta_all_avvio_dell_app_non_alla_creazione():
    """Aprire la scheda prima che l'app risponda mostrerebbe all'utente un
    errore di connessione invece della UI. L'apertura è agganciata al ciclo di
    vita dell'app, quindi alla sola creazione non deve essere ancora avvenuta."""
    eventi = []

    app = crea_app(al_pronto=lambda: eventi.append("pronto"))

    assert eventi == [], "crea_app non deve aprire niente: l'app non ascolta ancora"
    with TestClient(app):
        assert eventi == ["pronto"]


def test_il_comando_di_avvio_punta_alla_funzione_che_avvia_l_app():
    """`python -m cryptocustode` è la promessa centrale della slice, e nessun
    test la toccava: con un nome sbagliato nell'import di `__main__` la suite
    restava verde e il comando moriva con `ImportError` in faccia all'utente.

    Importare il modulo non avvia niente: la guardia `__name__ == "__main__"`
    non scatta sotto import."""
    assert comando.avvia is modulo.avvia


def test_il_socket_del_server_ascolta_sull_host_richiesto():
    """L'ultimo pezzo del bind. `avvia` passa `127.0.0.1` al server, ma è qui
    che quell'indirizzo diventa un socket: un `bind` che ignorasse l'argomento
    e legasse `0.0.0.0` esporrebbe il fascicolo in rete con la suite verde.

    La porta 0 la sceglie il sistema fra quelle libere, così il test non
    litiga con un'istanza dell'app eventualmente in esecuzione."""
    with apri_ascolto("127.0.0.1", 0) as presa:
        assert presa.getsockname()[0] == "127.0.0.1"


def sostituisci_uvicorn(monkeypatch, sonda=None) -> dict:
    """Mette al posto di uvicorn un doppio che registra e **non blocca**.

    È l'unico doppio della suite, e serve perché `esegui_uvicorn` è il confine
    oltre il quale dal processo non si osserva più niente: `run` non ritorna
    finché il server vive. Sono sostituiti tutti e tre i modi di entrare in
    uvicorn — `Config`, `Server` e `run` — così un adattatore che ne prendesse
    un altro (per esempio tornando al vecchio `uvicorn.run`, che lega la porta
    da sé) lascia il registro vuoto e fa fallire le asserzioni, invece di
    avviare un server vero e appendere la suite per sempre.

    `sonda`, se data, riceve il socket consegnato al server mentre `run` è in
    corso: è l'unico momento in cui quel socket è ancora aperto.
    """
    registrate = {}

    class ConfigurazioneFinta:
        def __init__(self, app, host, port):
            registrate["configurazione"] = (host, port)

    class ServerFinto:
        def __init__(self, config):
            pass

        def run(self, sockets=None):
            registrate["ascolto"] = sockets[0].getsockname()[:2]
            if sonda is not None:
                sonda(sockets[0])

    monkeypatch.setattr(modulo.uvicorn, "Config", ConfigurazioneFinta)
    monkeypatch.setattr(modulo.uvicorn, "Server", ServerFinto)
    monkeypatch.setattr(
        modulo.uvicorn, "run", lambda *a, **k: registrate.setdefault("scorciatoia", (a, k))
    )
    return registrate


def test_il_server_riceve_un_socket_gia_in_ascolto_sulla_porta_richiesta(monkeypatch):
    """Le due cose che l'adattatore deve fare, e che una sua mutazione
    romperebbe in silenzio: passare al server l'host e la porta che ha
    ricevuto, e consegnargli un socket **già in ascolto** — il presupposto su
    cui poggia l'apertura della scheda del browser.

    L'ascolto non è dedotto dal codice: la sonda apre davvero una connessione
    al socket consegnato, che un `bind` senza `listen` rifiuterebbe."""
    accettate = []

    def prova_a_connettersi(presa):
        with socket.create_connection(presa.getsockname()[:2], timeout=2):
            accettate.append(presa.getsockname()[:2])

    registrate = sostituisci_uvicorn(monkeypatch, sonda=prova_a_connettersi)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sonda:
        sonda.bind(("127.0.0.1", 0))  # una porta libera, la sceglie il sistema
        porta = sonda.getsockname()[1]

    esegui_uvicorn(crea_app(), "127.0.0.1", porta)

    assert registrate.get("configurazione") == ("127.0.0.1", porta)
    assert registrate.get("ascolto") == ("127.0.0.1", porta)
    assert accettate == [("127.0.0.1", porta)], "il socket consegnato non era in ascolto"


def test_una_porta_occupata_ferma_l_avvio_prima_di_aprire_il_browser(monkeypatch):
    """Se fosse uvicorn a legare la porta, con la porta occupata il ciclo di
    vita dell'app partirebbe — quindi si aprirebbe la scheda — e solo dopo
    fallirebbe il bind: l'utente vedrebbe la pagina di un altro programma
    mentre CryptoCustode è già morto, con la spiegazione in una console che
    magari non guarda.

    La porta qui è occupata per davvero, da un socket in ascolto; uvicorn è
    sostituito perché se il bind riuscisse contro le attese questo test deve
    fallire, non restare appeso a un server vero."""
    aperture = []
    sostituisci_uvicorn(monkeypatch)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupante:
        occupante.bind(("127.0.0.1", 0))
        occupante.listen()
        porta = occupante.getsockname()[1]

        with pytest.raises(PortaOccupata) as errore:
            esegui_uvicorn(
                crea_app(al_pronto=lambda: aperture.append("scheda")), "127.0.0.1", porta
            )

    assert str(porta) in str(errore.value), "il messaggio deve dire quale porta è occupata"
    assert aperture == [], "niente scheda del browser se il server non parte"


def test_l_indirizzo_finisce_sulla_console_per_chi_non_vede_la_scheda(monkeypatch, capsys):
    """Se il browser non si apre — nessun browser predefinito, una scheda
    chiusa per sbaglio — la console è l'unico posto dove leggere l'indirizzo.
    Uvicorn non lo stampa più da quando riceve un socket già legato, quindi lo
    stampa `esegui_uvicorn`: se smettesse, l'utente resterebbe senza."""
    sostituisci_uvicorn(monkeypatch)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sonda:
        sonda.bind(("127.0.0.1", 0))
        porta = sonda.getsockname()[1]

    esegui_uvicorn(crea_app(), "127.0.0.1", porta)

    assert f"http://127.0.0.1:{porta}/" in capsys.readouterr().out
