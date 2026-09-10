import hashlib

import pytest

from cryptocustode.core.errors import FascicoloFull, InvalidEncoding
from cryptocustode.core.ingest.loader import (
    aggiungi_documento,
    costruisci_documento,
    segnaposto_preesistenti,
)
from cryptocustode.core.models import Fascicolo, fascicolo_vuoto
from tests.pdf_di_prova import pdf_di_prova


def documento(indice: int):
    return costruisci_documento(f"doc{indice}.txt", b"Testo di prova.")


def test_txt_viene_riconosciuto_dall_estensione():
    doc = costruisci_documento("contratto.txt", "Torino".encode("utf-8"))
    assert doc.text == "Torino"
    assert doc.filename == "contratto.txt"


def test_pdf_viene_riconosciuto_dall_estensione():
    doc = costruisci_documento("contratto.pdf", pdf_di_prova(["testo"]))
    assert "Contratto di locazione" in doc.text


def test_l_estensione_e_insensibile_alle_maiuscole():
    doc = costruisci_documento("CONTRATTO.TXT", b"Torino")
    assert doc.text == "Torino"


def test_estensione_sconosciuta_viene_trattata_come_txt():
    # Un file senza estensione nota è tentato come testo: se non è UTF-8
    # l'errore arriva dal caricatore TXT, che è il comportamento voluto.
    with pytest.raises(InvalidEncoding):
        costruisci_documento("appunti", "perch\xe8".encode("latin-1"))


def test_sha256_e_dei_byte_originali():
    contenuto = "Torino".encode("utf-8")
    doc = costruisci_documento("a.txt", contenuto)
    assert doc.sha256 == hashlib.sha256(contenuto).hexdigest()


def test_i_doc_id_sono_distinti():
    primo = costruisci_documento("a.txt", b"uno")
    secondo = costruisci_documento("b.txt", b"due")
    assert primo.doc_id != secondo.doc_id


def test_il_txt_ha_un_solo_offset_di_pagina():
    doc = costruisci_documento("a.txt", b"Torino")
    assert doc.page_offsets == [0]


def test_dieci_documenti_entrano():
    fascicolo = fascicolo_vuoto("f1")
    for indice in range(Fascicolo.MAX_DOCUMENTI):
        aggiungi_documento(fascicolo, documento(indice))
    assert len(fascicolo.documents) == 10


def test_l_undicesimo_documento_viene_rifiutato():
    fascicolo = fascicolo_vuoto("f1")
    for indice in range(Fascicolo.MAX_DOCUMENTI):
        aggiungi_documento(fascicolo, documento(indice))
    with pytest.raises(FascicoloFull, match="10"):
        aggiungi_documento(fascicolo, documento(99))


def test_il_rifiuto_non_lascia_il_fascicolo_alterato():
    fascicolo = fascicolo_vuoto("f1")
    for indice in range(Fascicolo.MAX_DOCUMENTI):
        aggiungi_documento(fascicolo, documento(indice))
    with pytest.raises(FascicoloFull):
        aggiungi_documento(fascicolo, documento(99))
    assert len(fascicolo.documents) == 10


def test_nessun_segnaposto_preesistente_in_un_testo_normale():
    assert segnaposto_preesistenti("Il conduttore firma il contratto.") == []


def test_segnaposto_preesistente_viene_segnalato_con_la_posizione():
    testo = "Il conduttore [PERSONA_1] firma."
    assert segnaposto_preesistenti(testo) == [(14, "[PERSONA_1]")]


def test_piu_segnaposto_preesistenti_in_ordine():
    testo = "[IBAN_2] e poi [PERSONA_10]"
    assert segnaposto_preesistenti(testo) == [(0, "[IBAN_2]"), (15, "[PERSONA_10]")]


def test_un_quasi_segnaposto_non_viene_segnalato():
    # La forma canonica è [MAIUSCOLE_CIFRE]: queste non lo sono.
    assert segnaposto_preesistenti("[persona_1] e [PERSONA] e [1_PERSONA]") == []
