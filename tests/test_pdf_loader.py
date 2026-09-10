import pytest

from cryptocustode.core.errors import ScannedDocumentRejected
from cryptocustode.core.ingest.pdf_loader import carica_pdf
from tests.pdf_di_prova import TESTO_DI_PAGINA, pdf_di_prova


def test_pdf_di_solo_testo_viene_estratto():
    testo, _ = carica_pdf(pdf_di_prova(["testo", "testo"]))
    assert "Contratto di locazione" in testo
    assert testo.count("Contratto di locazione") == 2


def test_gli_offset_segnano_l_inizio_di_ogni_pagina():
    testo, offsets = carica_pdf(pdf_di_prova(["testo", "testo", "testo"]))
    assert len(offsets) == 3
    assert offsets[0] == 0
    # Ogni offset cade dentro il testo e in ordine crescente.
    assert offsets == sorted(offsets)
    assert offsets[-1] < len(testo)


def test_l_offset_della_seconda_pagina_punta_al_suo_testo():
    testo, offsets = carica_pdf(pdf_di_prova(["testo", "testo"]))
    assert testo[offsets[1]:].startswith(TESTO_DI_PAGINA[:20])


def test_pagina_immagine_senza_testo_viene_respinta():
    with pytest.raises(ScannedDocumentRejected):
        carica_pdf(pdf_di_prova(["immagine"]))


def test_il_rifiuto_indica_il_numero_di_pagina():
    # Quattro pagine di testo e una scansione in quinta posizione (TC-01).
    with pytest.raises(ScannedDocumentRejected, match="5"):
        carica_pdf(pdf_di_prova(["testo", "testo", "testo", "testo", "immagine"]))


def test_il_rifiuto_riguarda_l_intero_file():
    # Nessuna elaborazione parziale: anche con quattro pagine buone su cinque
    # la funzione solleva invece di restituire il testo delle pagine accettate.
    with pytest.raises(ScannedDocumentRejected):
        carica_pdf(pdf_di_prova(["testo", "immagine", "testo"]))


def test_pagina_bianca_senza_immagini_e_accettata():
    testo, offsets = carica_pdf(pdf_di_prova(["testo", "bianca"]))
    assert "Contratto di locazione" in testo
    assert len(offsets) == 2


def test_pagina_raster_con_testo_residuo_viene_respinta():
    with pytest.raises(ScannedDocumentRejected):
        carica_pdf(pdf_di_prova(["raster"]))


def test_pdf_illeggibile_viene_respinto():
    with pytest.raises(ScannedDocumentRejected):
        carica_pdf(b"questi non sono i byte di un PDF")
