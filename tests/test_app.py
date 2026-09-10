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

from fastapi.testclient import TestClient

from cryptocustode.api.app import avvia, crea_app


def test_la_home_serve_la_pagina_html_con_il_nome_dell_app():
    """La slice esiste per dimostrare che l'ossatura HTTP c'è: se la route `/`
    manca, o punta a un file inesistente, qui arriva 404 o 500 invece di 200.

    Il tipo di contenuto è parte del contratto: servita come `text/plain` la
    pagina arriverebbe comunque 200, e il browser mostrerebbe il sorgente HTML
    all'utente invece della UI."""
    with TestClient(crea_app()) as client:
        risposta = client.get("/")

    assert risposta.status_code == 200
    assert risposta.headers["content-type"].startswith("text/html")
    assert "CryptoCustode" in risposta.text


def test_ogni_risorsa_referenziata_dalla_pagina_e_servita():
    """Una risorsa referenziata e non servita non fa fallire la GET di `/`: la
    pagina arriva comunque 200 e resta muta sotto gli occhi dell'utente. Questo
    test estrae i riferimenti dalla pagina e li chiede davvero, così un mount
    dimenticato o un file rinominato falliscono qui."""
    with TestClient(crea_app()) as client:
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
