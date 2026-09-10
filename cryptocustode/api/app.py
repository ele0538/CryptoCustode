"""Ossatura HTTP dell'applicazione locale (spec §2 decisione 1, spec §4).

`api/` può importare `core/` e `state/`; l'invariante 1 della spec §4 vieta il
verso opposto ed è sorvegliato da `tests/test_architettura.py`.

Il server e l'apertura del browser entrano in `avvia` come parametri con un
default di produzione. Non è un'astrazione per i test: sono le due sole cose di
questo modulo che non si possono osservare da dentro il processo — una blocca
il thread, l'altra lancia un programma esterno — e il vincolo di sicurezza da
dimostrare (l'ascolto sul solo loopback) vive proprio negli argomenti che il
server riceve.

Due superfici restano esposte di proposito, e conviene dirlo perché nessuna
delle due è stata chiesta: `/static` serve l'intera cartella `ui/`, quindi
`/static/index.html` è la stessa pagina di `/`; e `/docs` con `/openapi.json`
restano attivi, perché lo schema è comodo per provare le route del gate di
esportazione. Entrambe sono accettabili soltanto perché l'ascolto è sul solo
loopback: il giorno in cui questa app venisse esposta, vanno chiuse.
"""

from __future__ import annotations

import socket
import webbrowser
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

HOST = "127.0.0.1"
PORTA = 8765
INDIRIZZO = f"http://{HOST}:{PORTA}/"

UI = Path(__file__).resolve().parents[1] / "ui"
PAGINA = UI / "index.html"

AlPronto = Callable[[], None]
"""Cosa fare quando l'app entra in servizio. In produzione apre il browser."""

Apri = Callable[[str], object]
"""Apre un indirizzo nel browser dell'utente. In produzione `webbrowser.open`."""

Esegui = Callable[[FastAPI, str, int], None]
"""Serve l'app bloccando il chiamante. In produzione `esegui_uvicorn`."""


class PortaOccupata(RuntimeError):
    """La porta locale è già in uso: un altro programma, o un'altra istanza."""


def crea_app(al_pronto: AlPronto | None = None) -> FastAPI:
    """L'app HTTP: serve la pagina della UI e i suoi file statici.

    `al_pronto` viene chiamato quando l'app entra in servizio, non quando viene
    creata: è l'aggancio con cui `avvia` apre la scheda del browser soltanto a
    server pronto. Chi crea l'app per interrogarla — i test, e in futuro altre
    route — lo lascia assente e non apre nulla.
    """

    @asynccontextmanager
    async def ciclo_di_vita(app: FastAPI):
        if al_pronto is not None:
            al_pronto()
        yield

    app = FastAPI(title="CryptoCustode", lifespan=ciclo_di_vita)
    app.mount("/static", StaticFiles(directory=UI), name="static")

    @app.get("/", include_in_schema=False)
    def pagina() -> FileResponse:
        return FileResponse(PAGINA, media_type="text/html")

    return app


def apri_ascolto(host: str, porta: int) -> socket.socket:
    """Mette in ascolto il socket del server, o solleva `PortaOccupata`.

    Nessun `SO_REUSEADDR`: su Windows permette di legare una porta già in uso,
    e accorgersi che è occupata è metà del lavoro di questa funzione.
    """
    presa = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        presa.bind((host, porta))
    except OSError as errore:
        presa.close()
        raise PortaOccupata(
            f"la porta {porta} di {host} è già occupata: chiudi il programma "
            "che la usa — o l'altra istanza di CryptoCustode — e riprova"
        ) from errore
    presa.listen()
    return presa


def esegui_uvicorn(app: FastAPI, host: str, porta: int) -> None:
    """Il default di produzione di `Esegui`. Blocca finché il server vive.

    Il socket viene legato qui e non da uvicorn, e la ragione riguarda entrambe
    le volte in cui la scheda del browser può arrivare nel momento sbagliato:

    - uvicorn esegue il ciclo di vita dell'app **prima** di legare la porta
      (`Server.startup` fa `await self.lifespan.startup()` e solo dopo
      `loop.create_server`), quindi l'aggancio che apre la scheda scatterebbe
      su un socket non ancora in ascolto;
    - con la porta occupata, il bind fallirebbe **dopo** quell'apertura:
      l'utente vedrebbe la pagina di un altro programma — o un errore di
      connessione — mentre CryptoCustode è già terminato.

    Legando prima, la scheda non può precedere il server, e `PortaOccupata`
    arriva prima che si apra qualsiasi cosa.
    """
    with apri_ascolto(host, porta) as presa:
        # Ricevendo un socket già legato, uvicorn salta la sua riga «Uvicorn
        # running on ...» (`Server.startup` la stampa solo quando lega da sé,
        # dando per scontato che chi passa i socket abbia già informato). Senza
        # questa stampa, chi non vede aprirsi la scheda — nessun browser
        # predefinito, per esempio — non saprebbe dove andare.
        print(
            f"CryptoCustode è in ascolto su http://{host}:{porta}/ — CTRL+C per chiudere",
            flush=True,
        )
        uvicorn.Server(uvicorn.Config(app, host=host, port=porta)).run(sockets=[presa])


def avvia(*, esegui: Esegui = esegui_uvicorn, apri: Apri = webbrowser.open) -> None:
    """Avvia l'applicazione: ascolto sul solo loopback e scheda del browser.

    `HOST` non è configurabile dall'esterno di proposito. Un fascicolo contiene
    dati personali di terzi e l'applicazione non ha autenticazione: legarla a
    `0.0.0.0` li offrirebbe a chiunque sia sulla stessa rete.
    """
    app = crea_app(al_pronto=lambda: apri(INDIRIZZO))
    esegui(app, HOST, PORTA)
