"""L'identità della spec §8: mascherare e ripristinare riporta all'originale.

È il test più importante della suite. Se `tagga` sbagliasse un offset, o
`unmask` cambiasse la forma del segnaposto, o i due divergessero su cosa sia un
tag, questo test cade prima di qualunque altro — e cade in memoria, senza rete
e senza costo.
"""

import pytest

from cryptocustode.core.fusioni import fondi
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


# --- L'unica eccezione all'identità, e sta scritta qui perché si veda ---------


def test_dopo_una_fusione_la_variante_torna_come_il_valore_canonico():
    """La fusione rompe l'identità della §8, di proposito e solo dove l'utente
    ha deciso che la rompesse.

    Accettare un suggerimento significa dire che «M. Rossi» e «Mario Rossi»
    sono la stessa persona. Da quel momento le due scritture condividono un
    segnaposto, e il ripristino ha un solo valore da rimettere al suo posto: il
    canonico. Il testo ripristinato non è più identico all'originale.

    **Non è un difetto della mascheratura ed è confinato.** Vale solo per i tag
    che l'utente ha fuso di persona, il round-trip di tutto il resto resta
    un'identità (i casi parametrici qui sopra), e soprattutto vale sulla
    ricostruzione del documento originale — non su ciò che serve davvero, che è
    ripristinare la *risposta* dell'IA esterna, dove il segnaposto va sostituito
    con il nome vero della persona e non con l'abbreviazione che compariva in
    una riga del contratto.

    Il giorno in cui si volesse anche l'identità sul documento, servirebbe
    tenere per ogni occorrenza la scrittura che aveva — cioè gli offset che il
    modello non restituisce. È lo stesso muro dell'omonimia (spec §16).
    """
    testo = "Mario Rossi firma. Anche M. Rossi firma."
    tabella, _ = assegna_tag(
        [
            Rilevazione(valore="Mario Rossi", categoria=Category.PERSONA),
            Rilevazione(valore="M. Rossi", categoria=Category.PERSONA),
        ],
        {},
        {},
    )
    vecchio = next(t.tag for t in tabella.values() if t.valore == "Mario Rossi")
    nuovo = next(t.tag for t in tabella.values() if t.valore == "M. Rossi")

    fusa = fondi(tabella, vecchio, nuovo)
    mascherato = tagga(testo, fusa).mascherato
    ripristinato = ripristina(mascherato, dizionario_di(fusa))

    assert mascherato == f"{vecchio} firma. Anche {vecchio} firma."
    assert ripristinato == "Mario Rossi firma. Anche Mario Rossi firma."
    assert ripristinato != testo


def test_senza_fusioni_l_identita_resta_intatta():
    """Il contrappeso del test qui sopra: le varianti nascono vuote, quindi
    nessun fascicolo perde l'identità della §8 senza che l'utente l'abbia
    chiesto."""
    testo = "Mario Rossi firma. Anche M. Rossi firma."
    tabella, _ = assegna_tag(
        [
            Rilevazione(valore="Mario Rossi", categoria=Category.PERSONA),
            Rilevazione(valore="M. Rossi", categoria=Category.PERSONA),
        ],
        {},
        {},
    )

    assert all(tag.varianti == () for tag in tabella.values())
    mascherato = tagga(testo, tabella).mascherato
    assert ripristina(mascherato, dizionario_di(tabella)) == testo
