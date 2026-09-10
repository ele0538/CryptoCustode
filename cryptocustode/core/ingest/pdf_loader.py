"""Estrazione dei PDF con PyMuPDF e verdetto di scansione (spec §12)."""

from __future__ import annotations

import fitz

from cryptocustode.core.errors import ScannedDocumentRejected
from cryptocustode.core.ingest.config import (
    CARATTERI_MINIMI_PAGINA,
    FRAZIONE_IMMAGINE_MASSIMA,
)


def _frazione_coperta_da_immagini(pagina: fitz.Page) -> float:
    """Area delle immagini della pagina diviso l'area della pagina.

    I blocchi di tipo 1 del dizionario sono le immagini; il loro bbox è già in
    coordinate di pagina, quindi le aree sono confrontabili senza conversioni.
    """
    area_pagina = pagina.rect.get_area()
    if area_pagina == 0:
        return 0.0
    area_immagini = sum(
        fitz.Rect(blocco["bbox"]).get_area()
        for blocco in pagina.get_text("dict")["blocks"]
        if blocco["type"] == 1
    )
    return area_immagini / area_pagina


def _e_scansione(pagina: fitz.Page) -> bool:
    """La tabella del verdetto della spec §12, riga per riga."""
    caratteri = len(pagina.get_text("text").strip())
    frazione = _frazione_coperta_da_immagini(pagina)
    if caratteri == 0:
        # Immagine senza testo: è una scansione. Pagina bianca senza immagini:
        # non contiene nulla da proteggere, quindi passa.
        return frazione > 0
    return caratteri < CARATTERI_MINIMI_PAGINA and frazione > FRAZIONE_IMMAGINE_MASSIMA


def carica_pdf(contenuto: bytes) -> tuple[str, list[int]]:
    """Estrae il testo di un PDF e gli offset di inizio di ogni pagina.

    Solleva `ScannedDocumentRejected` se anche una sola pagina è una scansione,
    o se il file non è leggibile: il rifiuto riguarda l'intero file, mai una
    parte (spec §12). I PDF cifrati rientrano fra i non leggibili (spec §16.10).
    """
    try:
        documento = fitz.open(stream=contenuto, filetype="pdf")
    except Exception as errore:
        raise ScannedDocumentRejected(
            "documento bloccato: il PDF non è leggibile o è protetto da password"
        ) from errore

    try:
        if documento.needs_pass:
            raise ScannedDocumentRejected(
                "documento bloccato: il PDF è protetto da password"
            )
        pezzi: list[str] = []
        offsets: list[int] = []
        lunghezza = 0
        for numero, pagina in enumerate(documento, start=1):
            if _e_scansione(pagina):
                raise ScannedDocumentRejected(
                    f"documento bloccato: la pagina {numero} è una scansione, "
                    "il file non è stato caricato"
                )
            testo_pagina = pagina.get_text("text")
            offsets.append(lunghezza)
            pezzi.append(testo_pagina)
            lunghezza += len(testo_pagina)
        return "".join(pezzi), offsets
    finally:
        documento.close()
