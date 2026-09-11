"""La forma canonica dei segnaposto, dichiarata una volta sola (spec §7).

Il formato è un invariante della spec che vive su due versi opposti: qualcuno
lo *scrive* (la mascheratura, tramite `costruisci_segnaposto`) e qualcuno lo
*legge* (il ripristino in `core/unmask.py`, l'avviso sul testo in ingresso in
`core/ingest/loader.py`, tramite `SEGNAPOSTO`). Finché i due versi erano
dichiarati separatamente potevano divergere in silenzio: un generatore che
avesse emesso `[PERSONA-1]` avrebbe fatto morire ogni ripristino con
`MalformedPlaceholder` senza che un solo test se ne accorgesse (issue #20).

Qui costruttore e regex stanno accanto, e `tests/test_placeholders.py` li
salda: quello che il costruttore produce, la regex lo deve riconoscere.
"""

import re

# La forma severa: parentesi quadre, categoria in maiuscolo, trattino basso,
# indice decimale. La parentesi di chiusura non è decorativa — è ciò che
# impedisce a "[PERSONA_1]" di essere sottostringa di "[PERSONA_10]" durante la
# sostituzione del ripristino (spec §11, passo 5).
SEGNAPOSTO = re.compile(r"\[[A-Z]+_\d+\]")


def costruisci_segnaposto(categoria: str, indice: int) -> str:
    """Il segnaposto di una categoria a un dato indice.

    `categoria` è il valore dell'enum `Category`, non l'enum: questo modulo
    possiede un formato, non conosce il dominio, e resta una foglia senza
    dipendenze interne.
    """
    return f"[{categoria}_{indice}]"
