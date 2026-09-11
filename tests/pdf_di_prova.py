"""Costruisce PDF di prova con PyMuPDF.

La spec §14 vieta di committare binari nel repo: ogni PDF usato dai test nasce
qui, riproducibile e ispezionabile.
"""

import fitz

# Testo abbondante: supera comodamente CARATTERI_MINIMI_PAGINA.
TESTO_DI_PAGINA = (
    "Contratto di locazione stipulato fra le parti in data odierna. "
    "Il conduttore dichiara di aver preso visione dell'immobile."
)


def _pagina_di_testo(documento: fitz.Document, testo: str = TESTO_DI_PAGINA) -> None:
    pagina = documento.new_page()
    pagina.insert_textbox(fitz.Rect(50, 50, 545, 400), testo, fontsize=11)


def _pagina_immagine(documento: fitz.Document, copertura: float = 1.0) -> None:
    """Pagina senza testo, coperta da un'immagine grigia: è una scansione."""
    pagina = documento.new_page()
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 200), False)
    pixmap.clear_with(128)
    riquadro = fitz.Rect(
        0, 0, pagina.rect.width * copertura, pagina.rect.height * copertura
    )
    pagina.insert_image(riquadro, pixmap=pixmap)


def _pagina_bianca(documento: fitz.Document) -> None:
    documento.new_page()


def _pagina_raster_con_testo_residuo(documento: fitz.Document) -> None:
    """Poco testo e immagine su gran parte della pagina: terza riga della tabella."""
    pagina = documento.new_page()
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 200), False)
    pixmap.clear_with(200)
    pagina.insert_image(pagina.rect, pixmap=pixmap)
    pagina.insert_textbox(fitz.Rect(50, 700, 545, 780), "Pag. 1", fontsize=9)


def _pagina_logo(documento: fitz.Document) -> None:
    """Poco testo e un logo piccolo: il caso limite che l'euristica deve
    accettare, quarta riga della tabella (copertura ≈ 0.09, 6 caratteri)."""
    _pagina_immagine(documento, copertura=0.3)
    documento[-1].insert_textbox(fitz.Rect(50, 700, 545, 780), "Pag. 1", fontsize=9)


def _pagina_testo_con_immagine_grande(documento: fitz.Document) -> None:
    """Testo abbondante più un'immagine che copre quasi tutta la pagina: la
    presenza di un'immagine grande da sola non deve bloccare una pagina con
    testo vero."""
    pagina = documento.new_page()
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 200), False)
    pixmap.clear_with(128)
    pagina.insert_image(pagina.rect, pixmap=pixmap)
    pagina.insert_textbox(fitz.Rect(50, 50, 545, 400), TESTO_DI_PAGINA, fontsize=11)


COSTRUTTORI = {
    "testo": _pagina_di_testo,
    "immagine": _pagina_immagine,
    "bianca": _pagina_bianca,
    "raster": _pagina_raster_con_testo_residuo,
    "logo": _pagina_logo,
    "testo_immagine": _pagina_testo_con_immagine_grande,
}


def pdf_di_prova(pagine: list[str]) -> bytes:
    """Costruisce un PDF con una pagina per ogni voce di `pagine`.

    Le voci ammesse sono le chiavi di COSTRUTTORI.
    """
    documento = fitz.open()
    for tipo in pagine:
        COSTRUTTORI[tipo](documento)
    contenuto = documento.tobytes()
    documento.close()
    return contenuto


def pdf_cifrato() -> bytes:
    """Un PDF protetto da password, per il limite 10 della spec §16.

    Verificato sulla macchina: `fitz.open()` su questi byte **non** solleva, e
    `needs_pass` vale 1. È l'unico modo di intercettarlo — caricarne una pagina
    solleverebbe `ValueError("document closed or encrypted")`, cioè un errore
    grezzo invece del messaggio italiano che la spec §13 pretende.
    """
    documento = fitz.open()
    _pagina_di_testo(documento)
    contenuto = documento.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="segreto", owner_pw="segreto"
    )
    documento.close()
    return contenuto
