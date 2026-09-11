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
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from cryptocustode.api.routes_fascicolo import crea_router
from cryptocustode.core.errors import (
    CryptoCustodeError,
    DuplicateFilename,
    ExportNotAllowed,
    FascicoloFull,
    IntegrityError,
    InvalidEncoding,
    MalformedPlaceholder,
    ScannedDocumentRejected,
    UnknownPlaceholder,
    UnresolvedAmbiguities,
    VaultUnreadable,
)
from cryptocustode.state.session import SessionStore

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


STATO_HTTP: dict[type[CryptoCustodeError], int] = {
    InvalidEncoding: 422,
    ScannedDocumentRejected: 422,
    FascicoloFull: 422,
    DuplicateFilename: 422,
    ExportNotAllowed: 409,
    IntegrityError: 409,
    UnresolvedAmbiguities: 409,
    UnknownPlaceholder: 422,
    MalformedPlaceholder: 422,
    VaultUnreadable: 422,
}
"""La tabella della spec §13, trascritta una volta sola.

Sta qui e non dentro le route perché è un contratto dell'applicazione, non di
un endpoint: ripetuta in ogni handler divergerebbe al primo che dimentica una
riga. `tests/test_caricamento.py` fa rispettare che ogni errore di dominio
abbia la sua riga, così un errore nuovo non può arrivare all'utente come 500.

Il 409 al posto del 403 per l'export negato è lo scostamento consapevole
dichiarato dalla §13: la risorsa è nello stato sbagliato, non manca un
permesso. Le righe del 409 non hanno ancora una route che le solleva — sono il
contratto che le issue dell'approvazione e dell'esportazione erediteranno.
"""


def rispondi_all_errore_di_dominio(richiesta: Request, errore: Exception) -> JSONResponse:
    """Traduce un errore di dominio nella sua risposta HTTP (spec §13).

    Il messaggio dell'errore arriva all'utente così com'è: i messaggi del core
    sono già in italiano e già portano il dettaglio che serve a rimediare — il
    numero di pagina della scansione, l'offset del byte invalido, il nome del
    file duplicato. Riscriverli qui significherebbe averne due versioni che
    divergono.
    """
    return JSONResponse(
        status_code=STATO_HTTP.get(type(errore), 500), content={"errore": str(errore)}
    )


def crea_app(
    *, al_pronto: AlPronto | None = None, store: SessionStore | None = None
) -> FastAPI:
    """L'app HTTP: serve la pagina della UI, i suoi statici e le route del fascicolo.

    `al_pronto` viene chiamato quando l'app entra in servizio, non quando viene
    creata: è l'aggancio con cui `avvia` apre la scheda del browser soltanto a
    server pronto. Chi crea l'app per interrogarla — i test, e in futuro altre
    route — lo lascia assente e non apre nulla.

    `store` è il secondo seme: in produzione ogni avvio parte da uno store
    vuoto, e chi costruisce l'app per interrogarla passa il proprio così da
    poter guardare il fascicolo invece di credere alla risposta HTTP sulla
    parola. Non è un singleton di modulo di proposito: due app dello stesso
    processo non devono condividere il fascicolo.
    """
    if store is None:
        store = SessionStore()

    @asynccontextmanager
    async def ciclo_di_vita(app: FastAPI):
        if al_pronto is not None:
            al_pronto()
        yield

    app = FastAPI(title="CryptoCustode", lifespan=ciclo_di_vita)
    app.mount("/static", StaticFiles(directory=UI), name="static")
    app.include_router(crea_router(store))
    app.add_exception_handler(CryptoCustodeError, rispondi_all_errore_di_dominio)

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
