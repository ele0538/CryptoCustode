"""Fa rispettare gli invarianti 1 e 2 della spec §4: core/ non conosce HTTP né
lo stato, e `core/mask.py` non tocca filesystem, orologio né random."""
import ast
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]
CORE = RADICE / "cryptocustode" / "core"

VIETATI = {
    "fastapi",
    "uvicorn",
    "starlette",
    "cryptocustode.state",
}

# Invariante 2 della spec §4: `mask.py` deve essere deterministica, perché
# `approval_hash` va ricalcolato identico in fase di esportazione. Un import di
# orologio, random o filesystem farebbe fallire quel confronto a caso e il
# controllo di integrità diventerebbe rumore invece di una difesa. L'invariante
# era vera di fatto ma non sorvegliata da nessun test.
VIETATI_IN_MASK = {
    "os",
    "pathlib",
    "random",
    "secrets",
    "time",
    "datetime",
    "uuid",
    "io",
}


def _e_vietato(nome: str, vietati: set[str]) -> bool:
    """Vero se `nome` è un modulo vietato, o un suo sotto-modulo."""
    return any(nome == vietato or nome.startswith(vietato + ".") for vietato in vietati)


def _base_import_relativo(livello: int, pacchetto: list[str]) -> str:
    """Risolve il pacchetto base (nome assoluto puntato) di un `ImportFrom`
    relativo con `level = livello`. `livello == 0` è un import assoluto."""
    if livello == 0:
        return ""
    troncamento = livello - 1
    segmenti = pacchetto[: len(pacchetto) - troncamento] if troncamento else pacchetto
    return ".".join(segmenti)


def nomi_vietati_in(
    sorgente: str, pacchetto: list[str], vietati: set[str] | None = None
) -> set[str]:
    """Restituisce i nomi importati da `sorgente` che violano l'invariante di
    purezza.

    `pacchetto` è la lista dei segmenti del pacchetto che contiene il file
    sorgente (per esempio ["cryptocustode", "core"]): serve a risolvere gli
    import relativi (`from .` / `from ..`) in nomi assoluti prima del
    confronto con l'insieme dei vietati.

    `vietati` permette di stringere l'insieme su un singolo modulo — è così che
    `mask.py` ottiene il suo divieto aggiuntivo su filesystem, orologio e
    random — riusando questo unico rilevatore invece di un secondo visitatore
    dell'albero sintattico.
    """
    if vietati is None:
        vietati = VIETATI
    albero = ast.parse(sorgente)
    importati: set[str] = set()
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                importati.add(alias.name)
        elif isinstance(nodo, ast.ImportFrom):
            base = _base_import_relativo(nodo.level, pacchetto)
            if nodo.module:
                modulo = f"{base}.{nodo.module}" if base else nodo.module
            else:
                modulo = base
            if modulo:
                importati.add(modulo)
                for alias in nodo.names:
                    importati.add(f"{modulo}.{alias.name}")
    return {nome for nome in importati if _e_vietato(nome, vietati)}


def pacchetto_del_file(percorso: Path) -> list[str]:
    """Il pacchetto di un file: il suo percorso relativo alla radice meno l'ultimo segmento."""
    return list(percorso.relative_to(RADICE).parts[:-1])


def test_core_non_importa_http_ne_stato():
    violazioni = []
    for percorso in sorted(CORE.rglob("*.py")):
        sorgente = percorso.read_text(encoding="utf-8")
        pacchetto = pacchetto_del_file(percorso)
        for nome in sorted(nomi_vietati_in(sorgente, pacchetto)):
            violazioni.append(f"{percorso.relative_to(RADICE)} importa {nome}")
    assert violazioni == [], "core/ deve restare puro:\n" + "\n".join(violazioni)


def test_mask_non_importa_filesystem_orologio_ne_random():
    """Invariante 2 della spec §4. Il gate di integrità dell'esportazione
    ricalcola l'hash sul testo mascherato e lo confronta con `approval_hash`:
    se la mascheratura non fosse deterministica, quel confronto fallirebbe a
    caso e l'unica difesa contro una mutazione dopo l'approvazione cadrebbe."""
    percorso = CORE / "mask.py"
    trovati = nomi_vietati_in(
        percorso.read_text(encoding="utf-8"),
        pacchetto_del_file(percorso),
        VIETATI | VIETATI_IN_MASK,
    )
    assert trovati == set(), (
        "core/mask.py deve restare deterministica, ma importa: "
        + ", ".join(sorted(trovati))
    )


def test_il_divieto_su_mask_rileva_un_import_di_orologio():
    """Controllo del controllo: senza questo, un divieto scritto male
    passerebbe per un invariante rispettato."""
    trovati = nomi_vietati_in(
        "from datetime import datetime\n", PACCHETTO_DI_PROVA, VIETATI | VIETATI_IN_MASK
    )
    assert trovati == {"datetime", "datetime.datetime"}


def test_il_divieto_su_mask_non_riguarda_gli_altri_moduli_di_core():
    """`entities.py` usa `uuid` per gli identificativi e resta legittimo: il
    divieto aggiuntivo è di `mask.py`, non di tutto `core/`."""
    assert nomi_vietati_in("import uuid\n", PACCHETTO_DI_PROVA) == set()


# --- Test della funzione pura nomi_vietati_in --------------------------------
#
# Questi test coprono i quattro stili di import che la versione precedente del
# test (basata su ast.walk + confronto esatto con VIETATI) non rilevava:
# `from pacchetto import stato`, `import pacchetto.stato.sotto`,
# `from ..stato import X`, `from .. import stato`. Più i casi che già
# funzionavano e due casi negativi di controllo.

PACCHETTO_DI_PROVA = ["cryptocustode", "core"]


def test_rileva_import_assoluto_fastapi():
    assert nomi_vietati_in("import fastapi\n", PACCHETTO_DI_PROVA) == {"fastapi"}


def test_rileva_import_assoluto_uvicorn():
    assert nomi_vietati_in("import uvicorn\n", PACCHETTO_DI_PROVA) == {"uvicorn"}


def test_rileva_from_import_assoluto_su_sottomodulo():
    trovati = nomi_vietati_in(
        "from starlette.responses import JSONResponse\n", PACCHETTO_DI_PROVA
    )
    assert trovati, "deve rilevare l'import di un sottomodulo di starlette"


def test_rileva_from_import_di_sibling_assoluto():
    """`from cryptocustode import state`: il nome vietato è l'alias importato,
    non il modulo di partenza (che è solo `cryptocustode`)."""
    trovati = nomi_vietati_in("from cryptocustode import state\n", PACCHETTO_DI_PROVA)
    assert trovati == {"cryptocustode.state"}


def test_rileva_import_assoluto_con_sottomoduli_multipli():
    """`import cryptocustode.state.store`: nessuna uguaglianza esatta con
    "cryptocustode.state" è possibile, serve il confronto per prefisso."""
    trovati = nomi_vietati_in("import cryptocustode.state.store\n", PACCHETTO_DI_PROVA)
    assert trovati == {"cryptocustode.state.store"}


def test_rileva_from_import_relativo_a_due_punti():
    """`from ..state import State`: l'import relativo va risolto con il
    prefisso del pacchetto assoluto prima del confronto."""
    trovati = nomi_vietati_in("from ..state import State\n", PACCHETTO_DI_PROVA)
    assert trovati == {"cryptocustode.state", "cryptocustode.state.State"}


def test_rileva_import_relativo_del_pacchetto_sibling():
    """`from .. import state`: nodo.module è None, il nome vietato è l'alias
    importato, non il modulo di partenza (che qui non esiste nemmeno)."""
    trovati = nomi_vietati_in("from .. import state\n", PACCHETTO_DI_PROVA)
    assert trovati == {"cryptocustode.state"}


def test_non_vieta_import_di_moduli_interni_a_core():
    trovati = nomi_vietati_in(
        "from cryptocustode.core.models import Span\n", PACCHETTO_DI_PROVA
    )
    assert trovati == set()


def test_non_vieta_import_del_pacchetto_radice():
    trovati = nomi_vietati_in("import cryptocustode\n", PACCHETTO_DI_PROVA)
    assert trovati == set()


# Issue #18, voce 2. `from __future__ import annotations` è la PEP 563: rende
# ogni annotazione una stringa. Da Python 3.14 (PEP 649/749) le annotazioni sono
# già valutate pigramente, quindi la future import non serve più — e non è
# neutrale, perché chi le legge riceve stringhe invece di oggetti: `@dataclass`
# in `core/models.py` e i modelli Pydantic delle route ci lavorano sopra.
# Il repo non ha né linter né CI, quindi senza questa guardia la riga rientra al
# primo file nuovo scritto da chi la #18 non l'ha letta, e nessuno se ne accorge.
PACKAGE = RADICE / "cryptocustode"
TEST = RADICE / "tests"


def ha_future_annotations(sorgente: str) -> bool:
    for nodo in ast.walk(ast.parse(sorgente)):
        if isinstance(nodo, ast.ImportFrom) and nodo.module == "__future__":
            if any(alias.name == "annotations" for alias in nodo.names):
                return True
    return False


def test_nessun_modulo_reintroduce_la_future_import_delle_annotazioni():
    # Anche tests/: l'insieme trattato dalla #18 comprendeva
    # tests/pdf_di_prova.py, che è un helper e non un test, e la riga può
    # rientrare da lì come da qualsiasi modulo del package.
    colpevoli = [
        percorso.relative_to(RADICE).as_posix()
        for radice in (PACKAGE, TEST)
        for percorso in sorted(radice.rglob("*.py"))
        if ha_future_annotations(percorso.read_text(encoding="utf-8"))
    ]
    assert colpevoli == []

def test_la_guardia_sulla_future_import_sa_rilevarla():
    # Senza questo, la guardia sopra passerebbe anche se smettesse di guardare:
    # una lista vuota è il risultato atteso e anche il risultato di un controllo
    # rotto. Qui si prova che il rilevatore distingue davvero i due casi.
    assert ha_future_annotations("from __future__ import annotations")
    assert ha_future_annotations("from __future__ import annotations, division")
    assert not ha_future_annotations("from __future__ import division")
    assert not ha_future_annotations("import annotations")
