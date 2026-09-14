"""Mascheratura di un documento del fascicolo e hash di approvazione (spec §9)."""

from dataclasses import replace

from cryptocustode.core.mask import hash_approvazione, maschera_documento, tabella_attiva
from cryptocustode.core.models import Category, Document, Rilevazione, StatoTag, fascicolo_vuoto
from cryptocustode.core.tagga import assegna_tag


def _documento(doc_id: str, filename: str, testo: str) -> Document:
    return Document(
        doc_id=doc_id, filename=filename, text=testo, page_offsets=[0], sha256="x"
    )


def _fascicolo(testo="Il sig. Mario Rossi paga.", valori=(("Mario Rossi", Category.PERSONA),)):
    fascicolo = fascicolo_vuoto("f1")
    fascicolo.documents.append(_documento("d1", "a.txt", testo))
    rilevazioni = [Rilevazione(valore=v, categoria=c) for v, c in valori]
    fascicolo.tags, fascicolo.counters = assegna_tag(
        rilevazioni, fascicolo.tags, fascicolo.counters
    )
    return fascicolo


def test_maschera_il_documento():
    fascicolo = _fascicolo()
    assert maschera_documento(fascicolo, fascicolo.documents[0]) == (
        "Il sig. [PERSONA_1] paga."
    )


def test_un_tag_spento_lascia_il_dato_in_chiaro():
    fascicolo = _fascicolo()
    fascicolo.tags["[PERSONA_1]"] = replace(
        fascicolo.tags["[PERSONA_1]"], stato=StatoTag.DISATTIVATO
    )
    assert maschera_documento(fascicolo, fascicolo.documents[0]) == (
        "Il sig. Mario Rossi paga."
    )


def test_una_categoria_spenta_lascia_il_dato_in_chiaro():
    fascicolo = _fascicolo()
    fascicolo.category_enabled[Category.PERSONA] = False
    assert maschera_documento(fascicolo, fascicolo.documents[0]) == (
        "Il sig. Mario Rossi paga."
    )


def test_i_due_interruttori_sono_indipendenti():
    """Riaccendere la categoria non riaccende i tag spenti a mano: le due
    decisioni si leggono in `and`, come `span_attivo` faceva prima (spec §5)."""
    fascicolo = _fascicolo()
    fascicolo.tags["[PERSONA_1]"] = replace(
        fascicolo.tags["[PERSONA_1]"], stato=StatoTag.DISATTIVATO
    )
    fascicolo.category_enabled[Category.PERSONA] = False
    fascicolo.category_enabled[Category.PERSONA] = True
    assert "[PERSONA_1]" not in tabella_attiva(fascicolo)


def test_l_hash_e_deterministico():
    assert hash_approvazione(_fascicolo()) == hash_approvazione(_fascicolo())


def test_l_hash_cambia_se_cambia_il_mascherato():
    prima = hash_approvazione(_fascicolo())
    dopo_fascicolo = _fascicolo()
    dopo_fascicolo.category_enabled[Category.PERSONA] = False
    assert hash_approvazione(dopo_fascicolo) != prima
