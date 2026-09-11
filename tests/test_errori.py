"""Tiene insieme la tabella degli errori della spec §13 e le eccezioni di
`cryptocustode/core/errors.py`.

L'elenco atteso non è più scritto a mano qui: viene letto dalla §13, che è il
documento che dichiara di essere l'autorità. Prima era una costante copiata, e
il test prometteva nel nome un controllo che non faceva — una classe aggiunta
alla spec e dimenticata nel codice passava in silenzio (issue #26).

Il prezzo è una dipendenza dal formato del markdown, ed è consapevole: se un
giorno la §13 cambia forma, `test_la_tabella_della_spec_resta_leggibile`
fallisce per primo e dice che è cambiato il documento, non il codice.
"""
import inspect
import re
from pathlib import Path

import pytest

from cryptocustode.core import errors
from cryptocustode.core.errors import CryptoCustodeError
from cryptocustode.core.ingest import config

RADICE = Path(__file__).resolve().parents[1]
SPEC = RADICE / "docs" / "superpowers" / "specs" / "2026-09-10-cryptocustode-design.md"

# L'intestazione che identifica la colonna delle eccezioni nella tabella della
# §13. Si cerca per nome e non per posizione: riordinare le colonne è il modo
# più probabile in cui quella tabella verrà toccata.
COLONNA_ERRORE = "Errore nel core"


def _celle(riga: str) -> list[str]:
    """Le celle di una riga di tabella markdown, senza i pipe di bordo."""
    return [cella.strip() for cella in riga.strip().strip("|").split("|")]


def _e_separatore(campi: list[str]) -> bool:
    """Vero per la riga `|---|---|` che separa intestazione e corpo, comprese le
    varianti con i due punti dell'allineamento."""
    return set("".join(campi)) <= set("-: ")


def _nome_nudo(cella: str) -> str:
    """Il nome della classe senza la decorazione del markdown: la §13 usa i
    backtick per i nomi e il grassetto per gli HTTP notevoli, e niente vieta che
    un giorno usi entrambi sulla stessa cella."""
    return cella.strip(" *`")


def _errori_dichiarati_dalla_spec() -> set[str]:
    """Le eccezioni nominate dalla tabella della §13.

    Legge solo le righe di tabella, quindi i paragrafi di motivazione che
    seguono — e che citano fra backtick `VaultUnreadable`, `CryptoCustodeError`
    e `KeyError` — non entrano nel conto. Fallisce a voce alta invece di
    restituire un insieme vuoto: un vuoto qui farebbe fallire il confronto più
    sotto, e la diagnosi partirebbe da `errors.py`, dove il problema non è.
    """
    testo = SPEC.read_text(encoding="utf-8")
    sezione = re.search(r"^## 13\..*?(?=^## |\Z)", testo, re.MULTILINE | re.DOTALL)
    assert sezione is not None, f"sezione §13 non trovata in {SPEC}"

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
            if COLONNA_ERRORE in campi:
                indice = campi.index(COLONNA_ERRORE)
            continue
        if _e_separatore(campi):
            nel_corpo = True
            continue
        if nel_corpo and indice < len(campi):
            nomi.add(_nome_nudo(campi[indice]))

    assert nomi, (
        f"nessuna riga letta dalla tabella della §13 di {SPEC}: "
        f"manca una tabella con la colonna {COLONNA_ERRORE!r}"
    )
    return nomi


NOMI_DALLA_SPEC = _errori_dichiarati_dalla_spec()


def test_la_tabella_della_spec_resta_leggibile():
    """Sorveglia il lettore, non il codice: se la §13 cambia formato o se la
    colonna letta scivola su un'altra, qui si vede subito, perché le celle delle
    altre colonne non sono nomi di classe."""
    assert all(nome.isidentifier() for nome in NOMI_DALLA_SPEC), NOMI_DALLA_SPEC


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
