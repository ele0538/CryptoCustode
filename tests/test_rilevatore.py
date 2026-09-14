"""Il confine fra `core/` e il modello (spec §4, invariante 1)."""

from cryptocustode.core.models import Category, Rilevazione
from cryptocustode.core.rilevatore import Rilevatore

from tests.doppi import RilevatoreFinto


def test_il_doppio_soddisfa_il_protocollo():
    """`Protocol` è runtime-checkable: senza questo test la conformità del
    doppio resterebbe un'opinione, e un cambio di firma la romperebbe in
    silenzio in tutti i test che lo usano."""
    assert isinstance(RilevatoreFinto(sempre=[]), Rilevatore)


def test_il_doppio_risponde_per_testo():
    finto = RilevatoreFinto(
        rilevazioni_per_testo={
            "Mario Rossi paga.": [
                Rilevazione(valore="Mario Rossi", categoria=Category.PERSONA)
            ]
        }
    )
    assert finto.rileva("Mario Rossi paga.") == [
        Rilevazione(valore="Mario Rossi", categoria=Category.PERSONA)
    ]


def test_il_doppio_su_un_testo_non_previsto_non_trova_niente():
    assert RilevatoreFinto(rilevazioni_per_testo={}).rileva("qualunque cosa") == []


def test_il_doppio_registra_le_chiamate():
    """Serve ai test di rianalisi: dimostrare che un documento già analizzato
    non ripaga una seconda chiamata."""
    finto = RilevatoreFinto(sempre=[])
    finto.rileva("a")
    finto.rileva("b")
    assert finto.chiamate == ["a", "b"]
