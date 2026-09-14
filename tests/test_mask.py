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


# --- Ordinamento dei documenti dentro l'hash --------------------------------
#
# `tests/test_mask.py` è stato riscritto da capo durante la fase IA, e con lui
# sono spariti i test che seguono: `hash_approvazione` ordina ancora per
# `(filename, doc_id)`, e quel correttivo del doc_id era già stato aggiunto
# come revisione in una fase precedente di questo stesso progetto. Senza un
# test a difenderlo, qualcuno potrebbe toglierlo senza che nessuno se ne
# accorga — ed è l'unica cosa che sta fra «l'utente ha approvato questo
# testo» ed «esce dall'esportazione».


def test_l_hash_non_dipende_dall_ordine_di_inserimento_dei_documenti():
    """L'ordinamento per `(filename, doc_id)` dentro `hash_approvazione` rende
    il digest indipendente dall'ordine di caricamento: senza, due sessioni che
    caricano gli stessi documenti in ordine diverso otterrebbero due hash
    diversi per lo stesso contenuto approvato, e il controllo di integrità
    diventerebbe rumore."""
    rilevazioni = [Rilevazione(valore="Mario Rossi", categoria=Category.PERSONA)]

    fascicolo_a = fascicolo_vuoto("f1")
    fascicolo_a.documents.append(_documento("d1", "a.txt", "Mario Rossi paga."))
    fascicolo_a.documents.append(_documento("d2", "b.txt", "Mario Rossi firma."))
    fascicolo_a.tags, fascicolo_a.counters = assegna_tag(
        rilevazioni, fascicolo_a.tags, fascicolo_a.counters
    )

    fascicolo_b = fascicolo_vuoto("f1")
    fascicolo_b.documents.append(_documento("d2", "b.txt", "Mario Rossi firma."))
    fascicolo_b.documents.append(_documento("d1", "a.txt", "Mario Rossi paga."))
    fascicolo_b.tags, fascicolo_b.counters = assegna_tag(
        rilevazioni, fascicolo_b.tags, fascicolo_b.counters
    )

    assert hash_approvazione(fascicolo_a) == hash_approvazione(fascicolo_b)


def test_due_documenti_con_lo_stesso_nome_si_ordinano_per_doc_id():
    """Il correttivo del `doc_id` nell'ordinamento: due documenti con lo
    stesso `filename` sono un caso legittimo (l'omonimia non è più
    intercettata nella corsia IA, spec §16 limite noto 2), e senza il
    tiebreak si ordinerebbero secondo l'ordine in cui `sorted` li ha trovati
    in lista — cioè l'ordine di inserimento — vanificando la proprietà appena
    sopra proprio nel caso in cui il nome file non basta a distinguerli."""
    rilevazioni = [Rilevazione(valore="Mario Rossi", categoria=Category.PERSONA)]

    fascicolo_a = fascicolo_vuoto("f1")
    fascicolo_a.documents.append(_documento("d2", "a.txt", "Mario Rossi firma qui."))
    fascicolo_a.documents.append(_documento("d1", "a.txt", "Mario Rossi paga qui."))
    fascicolo_a.tags, fascicolo_a.counters = assegna_tag(
        rilevazioni, fascicolo_a.tags, fascicolo_a.counters
    )

    fascicolo_b = fascicolo_vuoto("f1")
    fascicolo_b.documents.append(_documento("d1", "a.txt", "Mario Rossi paga qui."))
    fascicolo_b.documents.append(_documento("d2", "a.txt", "Mario Rossi firma qui."))
    fascicolo_b.tags, fascicolo_b.counters = assegna_tag(
        rilevazioni, fascicolo_b.tags, fascicolo_b.counters
    )

    assert hash_approvazione(fascicolo_a) == hash_approvazione(fascicolo_b)


def test_l_hash_e_esadecimale_a_64_caratteri():
    """SHA-256 in forma esadecimale: 32 byte, due cifre esadecimali per byte."""
    digest = hash_approvazione(_fascicolo())
    assert len(digest) == 64
    assert all(carattere in "0123456789abcdef" for carattere in digest)
