"""Fa rispettare l'invariante 1 della spec: core/ non conosce HTTP né lo stato."""
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


def moduli_importati(percorso: Path) -> set[str]:
    """Restituisce i nomi dei moduli importati da un file Python."""
    albero = ast.parse(percorso.read_text(encoding="utf-8"))
    nomi: set[str] = set()
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                nomi.add(alias.name)
                nomi.add(alias.name.split(".")[0])
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            nomi.add(nodo.module)
            nomi.add(nodo.module.split(".")[0])
    return nomi


def test_core_non_importa_http_ne_stato():
    violazioni = []
    for percorso in sorted(CORE.rglob("*.py")):
        for modulo in sorted(moduli_importati(percorso) & VIETATI):
            violazioni.append(f"{percorso.relative_to(RADICE)} importa {modulo}")
    assert violazioni == [], "core/ deve restare puro:\n" + "\n".join(violazioni)
