"""Il formato dei segnaposto ha un solo proprietario, e questi test lo tengono
saldato ai suoi consumatori (spec §7, issue #20).

Il difetto che questi test chiudono non è la duplicazione in sé: è che fosse
invisibile. Con il formato dichiarato in tre punti, un generatore che emettesse
`[PERSONA-1]` avrebbe fatto morire ogni ripristino in produzione con
`MalformedPlaceholder` lasciando la suite verde.
"""
import pytest

from cryptocustode.core.ingest.loader import segnaposto_preesistenti
from cryptocustode.core.models import Category, Rilevazione
from cryptocustode.core.placeholders import SEGNAPOSTO, costruisci_segnaposto
from cryptocustode.core.tagga import assegna_tag
from cryptocustode.core.unmask import ripristina


def _genera_placeholder(tabella, contatori, categoria, valore):
    """Il rimpiazzo di `prossimo_placeholder`, cancellata con `core/entities.py`.

    `assegna_tag` è il generatore vero: qui gli si passa una `Rilevazione` di
    un valore mai visto prima, cosicché produca sempre un segnaposto nuovo per
    `categoria`, e si legge la stringa del tag dalla tabella che restituisce.
    """
    nuova, contati = assegna_tag(
        [Rilevazione(valore=valore, categoria=categoria)], tabella, contatori
    )
    generato = next(tag.tag for tag in nuova.values() if tag.valore == valore)
    return generato, nuova, contati


def test_il_costruttore_produce_la_forma_canonica():
    """La forma della spec §7, fissata alla lettera: parentesi quadre,
    categoria in maiuscolo, trattino basso, indice."""
    assert costruisci_segnaposto("PERSONA", 1) == "[PERSONA_1]"


def test_la_regex_severa_riconosce_la_forma_canonica():
    assert SEGNAPOSTO.fullmatch("[PERSONA_1]")


@pytest.mark.parametrize(
    "vicino",
    ["[persona_1]", "[PERSONA-1]", "[PERSONA 1]", "[PERSONA]", "[1_PERSONA]",
     "[PERSONA_1", "PERSONA_1]"],
)
def test_la_regex_severa_rifiuta_le_forme_vicine(vicino):
    """La severità è il punto: tutto ciò che non è la forma canonica deve
    restare fuori, perché è la regex permissiva del ripristino a raccoglierlo
    e a fermare la sostituzione (spec §11)."""
    assert not SEGNAPOSTO.fullmatch(vicino)


# --- Il giro chiuso: quello che il generatore scrive, i lettori lo leggono ----
#
# Questi test non guardano una costante, guardano il giro. Sono loro a rendere
# visibile un cambio di formato: se `costruisci_segnaposto` smettesse di
# accordarsi con `SEGNAPOSTO`, qui si rompe il giro, non in produzione.


@pytest.mark.parametrize("categoria", list(Category))
def test_ogni_categoria_generata_e_riconosciuta_dalla_regex_severa(categoria):
    """Il generatore vero (`assegna_tag`), non una stringa scritta a mano, per
    tutte le categorie della spec e non solo per PERSONA."""
    tabella, contatori = {}, {}
    for indice in range(11):
        generato, tabella, contatori = _genera_placeholder(
            tabella, contatori, categoria, f"valore-{indice}"
        )
        assert SEGNAPOSTO.fullmatch(generato), (
            f"il generatore ha prodotto {generato!r}, che la regex severa non "
            "riconosce: ogni ripristino morirebbe con MalformedPlaceholder"
        )


def test_un_segnaposto_generato_attraversa_il_ripristino():
    """Il giro completo attraverso il consumatore vero: `ripristina` non deve
    mai vedere come alterato un segnaposto che abbiamo generato noi."""
    generato, _, _ = _genera_placeholder({}, {}, Category.PERSONA, "Mario Rossi")
    dizionario = {generato: "Mario Rossi"}
    assert ripristina(f"Firmato da {generato}.", dizionario) == "Firmato da Mario Rossi."


def test_un_segnaposto_generato_viene_segnalato_nel_testo_in_ingresso():
    """L'altro lettore: l'avviso sul testo caricato (spec §12) deve riconoscere
    la stessa forma che la mascheratura produce."""
    generato, _, _ = _genera_placeholder({}, {}, Category.IBAN, "IT60X0000000000000000000000")
    assert segnaposto_preesistenti(f"bonifico su {generato} oggi") == [
        (12, generato)
    ]
