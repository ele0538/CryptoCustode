"""Tiene insieme le tabelle degli errori delle due spec e le eccezioni di
`cryptocustode/core/errors.py`.

L'elenco atteso non è più scritto a mano qui: viene letto dalla §13 della spec
del 2026-09-10 e dalla §12 della spec del 2026-09-14, che sono i documenti che
dichiarano di essere l'autorità. Prima era una costante copiata, e il test
prometteva nel nome un controllo che non faceva — una classe aggiunta alla
spec e dimenticata nel codice passava in silenzio (issue #26).

Il prezzo è una dipendenza dal formato del markdown, ed è consapevole: se un
giorno una di quelle tabelle cambia forma,
`test_la_tabella_della_spec_resta_leggibile` fallisce per prima e dice che è
cambiato il documento, non il codice.
"""
import inspect
import re
from pathlib import Path

import pytest

from cryptocustode.core import errors
from cryptocustode.core.errors import CryptoCustodeError
from cryptocustode.core.ingest import config

RADICE = Path(__file__).resolve().parents[1]
SPEC_BASE = RADICE / "docs" / "superpowers" / "specs" / "2026-09-10-cryptocustode-design.md"
SPEC_IA = RADICE / "docs" / "superpowers" / "specs" / "2026-09-14-motore-ia-esporta-importa.md"

# La colonna cambia nome fra le due tabelle: la §13 dice "Errore nel core", la
# §12 dice "Errore". Si cerca per nome e non per posizione, perché riordinare
# le colonne è il modo più probabile in cui quelle tabelle verranno toccate.
TABELLE = ((SPEC_BASE, "13", "Errore nel core"), (SPEC_IA, "12", "Errore"))

RITIRATI: set[str] = set()
"""Errori ritirati dalle spec ma ancora presenti nel codice.

Resta vuoto di proposito. La §12 della spec del 2026-09-14 manda in pensione
`UnresolvedAmbiguities` insieme al sottosistema che lo generava (§5), ma
quella classe è ancora definita in `errors.py` e ancora usata da
`cryptocustode/state/session.py` — è territorio del task 10, non di questo.
Se la togliessimo di qui, la toglieremmo dall'insieme atteso mentre il codice
la ha ancora, e il confronto di uguaglianza più sotto fallirebbe subito per un
motivo sbagliato. `UnresolvedAmbiguities` entrerà qui quando il task 10 la
rimuoverà davvero dal codice.
"""


def _celle(riga: str) -> list[str]:
    """Le celle di una riga di tabella markdown, senza i pipe di bordo."""
    return [cella.strip() for cella in riga.strip().strip("|").split("|")]


def _e_separatore(campi: list[str]) -> bool:
    """Vero per la riga `|---|---|` che separa intestazione e corpo, comprese le
    varianti con i due punti dell'allineamento."""
    return set("".join(campi)) <= set("-: ")


def _nome_nudo(cella: str) -> str:
    """Il nome della classe senza la decorazione del markdown: le tabelle usano
    i backtick per i nomi e il grassetto per gli HTTP notevoli, e niente vieta
    che un giorno usino entrambi sulla stessa cella."""
    return cella.strip(" *`")


def _errori_di_tabella(percorso: Path, sezione_numero: str, colonna: str) -> set[str]:
    """Le eccezioni nominate dalla tabella di una sezione di una spec.

    Legge solo le righe di tabella, quindi i paragrafi di motivazione che
    seguono — e che citano fra backtick nomi di classi che non sono nella
    tabella — non entrano nel conto. Fallisce a voce alta invece di
    restituire un insieme vuoto: un vuoto qui farebbe fallire il confronto più
    sotto, e la diagnosi partirebbe da `errors.py`, dove il problema non è.
    """
    testo = percorso.read_text(encoding="utf-8")
    sezione = re.search(
        rf"^## {sezione_numero}\..*?(?=^## |\Z)", testo, re.MULTILINE | re.DOTALL
    )
    assert sezione is not None, f"sezione §{sezione_numero} non trovata in {percorso}"

    nomi: set[str] = set()
    indice: int | None = None
    nel_corpo = False
    for riga in sezione.group(0).splitlines():
        if not riga.lstrip().startswith("|"):
            # Fine della tabella: una tabella successiva dovrà ripresentare la
            # propria intestazione per essere letta.
            indice, nel_corpo = None, False
            continue
        campi = _celle(riga)
        if indice is None:
            if colonna in campi:
                indice = campi.index(colonna)
            continue
        if _e_separatore(campi):
            nel_corpo = True
            continue
        if nel_corpo and indice < len(campi):
            nomi.add(_nome_nudo(campi[indice]))

    assert nomi, (
        f"nessuna riga letta dalla tabella della §{sezione_numero} di {percorso}: "
        f"manca una tabella con la colonna {colonna!r}"
    )
    return nomi


def _errori_dichiarati_dalle_spec() -> set[str]:
    dichiarati: set[str] = set()
    for percorso, sezione, colonna in TABELLE:
        dichiarati |= _errori_di_tabella(percorso, sezione, colonna)
    return dichiarati - RITIRATI


NOMI_DALLA_SPEC = _errori_dichiarati_dalle_spec()


@pytest.mark.parametrize("percorso, sezione, colonna", TABELLE)
def test_la_tabella_della_spec_resta_leggibile(percorso, sezione, colonna):
    """Se un giorno una di queste tabelle cambia forma, questo test fallisce
    per primo e dice che è cambiato il documento, non il codice."""
    assert _errori_di_tabella(percorso, sezione, colonna)


def test_esistono_tutti_gli_errori_della_spec():
    definiti = {
        nome
        for nome, oggetto in inspect.getmembers(errors, inspect.isclass)
        if issubclass(oggetto, CryptoCustodeError) and oggetto is not CryptoCustodeError
    }
    assert definiti == NOMI_DALLA_SPEC


@pytest.mark.parametrize("nome", sorted(NOMI_DALLA_SPEC))
def test_ogni_errore_deriva_dalla_base(nome):
    assert issubclass(getattr(errors, nome), CryptoCustodeError)


def test_la_base_deriva_da_exception():
    assert issubclass(CryptoCustodeError, Exception)


def test_un_errore_conserva_il_messaggio():
    errore = errors.FascicoloFull("massimo 10 documenti per fascicolo")
    assert str(errore) == "massimo 10 documenti per fascicolo"


def test_soglie_del_verdetto_di_scansione():
    # Valori della tabella della spec §12. Vivono in un modulo di configurazione
    # perché siano ritoccabili senza toccare la logica.
    assert config.CARATTERI_MINIMI_PAGINA == 40
    assert config.FRAZIONE_IMMAGINE_MASSIMA == 0.5
