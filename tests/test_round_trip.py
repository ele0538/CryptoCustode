"""L'identità della spec §8: mascherare e ripristinare riporta all'originale.

È il test più importante della suite. Se `tagga` sbagliasse un offset, o
`unmask` cambiasse la forma del segnaposto, o i due divergessero su cosa sia un
tag, questo test cade prima di qualunque altro — e cade in memoria, senza rete
e senza costo.
"""

import pytest

from cryptocustode.core.models import Category, Rilevazione
from cryptocustode.core.tagga import assegna_tag, dizionario_di, tagga
from cryptocustode.core.unmask import ripristina

# Testi senza segnaposto preesistenti: uno `[PERSONA_1]` già scritto nel
# documento originale verrebbe risolto dal ripristino, ed è il caso che
# `segnaposto_preesistenti` avvisa al caricamento (spec §12 del 2026-09-10).
CASI = [
    (
        "Il sig. Mario Rossi, C.F. RSSMRA80A01H501U, paga 1.200,00 euro.",
        [
            ("Mario Rossi", Category.PERSONA),
            ("RSSMRA80A01H501U", Category.CF),
            ("1.200,00 euro", Category.IMPORTO),
        ],
    ),
    (
        "Mario Rossi e il dott. Rossi firmano per ACME s.r.l.",
        [
            ("Mario Rossi", Category.PERSONA),
            ("Rossi", Category.PERSONA),
            ("ACME s.r.l.", Category.AZIENDA),
        ],
    ),
    ("Nessun dato personale in questo testo.", []),
    ("", [("Mario Rossi", Category.PERSONA)]),
    (
        "Mario Rossi\nMario Rossi\nMario Rossi\n",
        [("Mario Rossi", Category.PERSONA)],
    ),
]


@pytest.mark.parametrize("testo, valori", CASI)
def test_mascherare_e_ripristinare_riporta_all_originale(testo, valori):
    rilevazioni = [Rilevazione(valore=v, categoria=c) for v, c in valori]
    tabella, _ = assegna_tag(rilevazioni, {}, {})
    mascherato = tagga(testo, tabella).mascherato
    assert ripristina(mascherato, dizionario_di(tabella)) == testo


@pytest.mark.parametrize("testo, valori", CASI)
def test_nessun_valore_applicato_sopravvive_nel_mascherato(testo, valori):
    """Il test anti-fuga della §14, nella forma che la §8 gli dà ora."""
    rilevazioni = [Rilevazione(valore=v, categoria=c) for v, c in valori]
    tabella, _ = assegna_tag(rilevazioni, {}, {})
    risultato = tagga(testo, tabella)
    taggati = {regione.tag for regione in risultato.regioni}
    for tag in tabella.values():
        if tag.tag in taggati:
            assert tag.valore not in risultato.mascherato
