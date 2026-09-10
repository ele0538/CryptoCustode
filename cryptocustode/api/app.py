"""Ossatura HTTP dell'applicazione locale (spec §2 decisione 1, spec §4).

`api/` può importare `core/` e `state/`; l'invariante 1 della spec §4 vieta il
verso opposto ed è sorvegliato da `tests/test_architettura.py`.

Il server e l'apertura del browser entrano in `avvia` come parametri con un
default di produzione. Non è un'astrazione per i test: sono le due sole cose di
questo modulo che non si possono osservare da dentro il processo — una blocca
il thread, l'altra lancia un programma esterno — e il vincolo di sicurezza da
dimostrare (l'ascolto sul solo loopback) vive proprio negli argomenti che il
server riceve.
"""

from __future__ import annotations

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

Apri = Callable[[str], object]
"""Apre un indirizzo nel browser dell'utente. In produzione `webbrowser.open`."""

Esegui = Callable[[FastAPI, str, int], None]
"""Serve l'app bloccando il chiamante. In produzione `esegui_uvicorn`."""


def crea_app(al_pronto: Callable[[], None] | None = None) -> FastAPI:
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


def esegui_uvicorn(app: FastAPI, host: str, porta: int) -> None:
    """Il default di produzione di `Esegui`. Blocca finché il server vive."""
    uvicorn.run(app, host=host, port=porta)


def avvia(*, esegui: Esegui = esegui_uvicorn, apri: Apri = webbrowser.open) -> None:
    """Avvia l'applicazione: ascolto sul solo loopback e scheda del browser.

    `HOST` non è configurabile dall'esterno di proposito. Un fascicolo contiene
    dati personali di terzi e l'applicazione non ha autenticazione: legarla a
    `0.0.0.0` li offrirebbe a chiunque sia sulla stessa rete.
    """
    app = crea_app(al_pronto=lambda: apri(f"http://{HOST}:{PORTA}/"))
    esegui(app, HOST, PORTA)
