import pytest

from cryptocustode.core.errors import ScannedDocumentRejected
from cryptocustode.core.ingest.pdf_loader import carica_pdf
from tests.pdf_di_prova import TESTO_DI_PAGINA, pdf_cifrato, pdf_di_prova


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
    with pytest.raises(ScannedDocumentRejected, match=r"pagina 5\b"):
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


def test_pagina_di_copertina_con_poco_testo_e_un_logo_e_accettata():
    # Il caso per cui esiste FRAZIONE_IMMAGINE_MASSIMA: una copertina o pagina
    # di firme con poco testo e un logo piccolo (copertura ≈ 0.09) non è una
    # scansione, ed è l'unico test della suite che verifica il lato "accettato"
    # della soglia sull'area coperta da immagini.
    testo, offsets = carica_pdf(pdf_di_prova(["logo"]))
    assert len(offsets) == 1
    assert "Pag. 1" in testo


def test_pagina_di_testo_con_una_grande_immagine_e_accettata():
    testo, _ = carica_pdf(pdf_di_prova(["testo_immagine"]))
    assert "Contratto di locazione" in testo


def test_pdf_illeggibile_viene_respinto():
    with pytest.raises(ScannedDocumentRejected):
        carica_pdf(b"questi non sono i byte di un PDF")


def test_pdf_cifrato_viene_respinto():
    # Spec §16 limite 10. Non lo copre il test precedente: su byte cifrati
    # `fitz.open()` riesce, quindi l'`except` non scatta e l'unico controllo
    # che li intercetta è `needs_pass`. Senza questo test quel ramo non è
    # verificato da nulla.
    with pytest.raises(ScannedDocumentRejected, match=r"il PDF è protetto da password"):
        carica_pdf(pdf_cifrato())
