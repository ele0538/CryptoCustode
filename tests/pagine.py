"""Quali pagine ci sono, e quali script carica ognuna.

Prima la UI era un documento solo e i test lo nominavano: `index.html` e
`app.js`, scritti a mano in sei punti. Dal 2026-09-14 i documenti sono tre, e
scriverli a mano significherebbe che la pagina aggiunta domani non sarà coperta
da nessuno dei controlli strutturali — e non lo sarà **in silenzio**, perché un
test che non guarda un file non fallisce mai.

Qui l'elenco si scopre: le pagine sono i `.html` della cartella `ui/`, e gli
script di ciascuna sono quelli che la pagina stessa dichiara. Aggiungere una
schermata basta a farla entrare nei controlli.
"""

import re
from pathlib import Path

from cryptocustode.api.app import UI


def pagine() -> list[Path]:
    """I documenti serviti all'utente, in ordine stabile."""
    trovate = sorted(UI.glob("*.html"))
    assert trovate, f"nessuna pagina HTML in {UI}"
    return trovate


def script_di(pagina: Path) -> list[Path]:
    """Gli script che quella pagina carica, nell'ordine in cui li carica.

    L'ordine conta: `comune.js` definisce `window.cc`, e un file che lo usasse
    prima troverebbe `undefined`. I test che eseguono il codice devono caricarli
    nella stessa sequenza in cui lo fa il browser.
    """
    testo = pagina.read_text(encoding="utf-8")
    nomi = re.findall(r'<script src="/static/([^"]+)"', testo)
    return [UI / nome for nome in nomi]


def coppie() -> list[tuple[Path, list[Path]]]:
    """Ogni pagina con i suoi script: il parametro dei test strutturali."""
    return [(pagina, script_di(pagina)) for pagina in pagine()]


def tutti_gli_script() -> list[Path]:
    """Ogni script della UI, anche quelli che nessuna pagina carica.

    La differenza rispetto a `script_di` è voluta: un file dimenticato nella
    cartella non rompe niente, ma `node --check` costa nulla e un file morto
    che non compila è un file morto che qualcuno rianimerà.
    """
    return sorted(UI.glob("*.js"))
