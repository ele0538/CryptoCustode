"""Facciata dell'ingresso: da byte a `Document`, e da `Document` a fascicolo."""

from __future__ import annotations

import hashlib
import re
import uuid

from cryptocustode.core.errors import FascicoloFull
from cryptocustode.core.ingest.pdf_loader import carica_pdf
from cryptocustode.core.ingest.txt_loader import carica_txt
from cryptocustode.core.models import Document, Fascicolo

# La forma canonica di un segnaposto (spec §7). La stessa regex vive in
# core/unmask.py per il verso opposto: qui serve ad avvisare che il testo in
# ingresso ne contiene già uno.
SEGNAPOSTO = re.compile(r"\[[A-Z]+_\d+\]")


def segnaposto_preesistenti(testo: str) -> list[tuple[int, str]]:
    """Le occorrenze di segnaposto già presenti nel testo caricato.

    Non è un rifiuto: è un avviso. Al ripristino una di queste stringhe verrebbe
    interpretata come segnaposto e sostituita con dati veri, corrompendo il testo
    (spec §12), quindi l'utente deve saperlo prima di approvare.
    """
    return [(trovato.start(), trovato.group(0)) for trovato in SEGNAPOSTO.finditer(testo)]


def costruisci_documento(filename: str, contenuto: bytes) -> Document:
    """Trasforma i byte di un file in un `Document`.

    Il dispatch è per estensione: `.pdf` passa da PyMuPDF, tutto il resto è
    tentato come testo UTF-8. `sha256` è il digest dei byte originali, non del
    testo estratto, così due caricamenti dello stesso file si riconoscono anche
    se l'estrazione cambiasse.
    """
    if filename.lower().endswith(".pdf"):
        testo, page_offsets = carica_pdf(contenuto)
    else:
        testo, page_offsets = carica_txt(contenuto), [0]
    return Document(
        doc_id=f"d_{uuid.uuid4().hex[:12]}",
        filename=filename,
        text=testo,
        page_offsets=page_offsets,
        sha256=hashlib.sha256(contenuto).hexdigest(),
    )


def aggiungi_documento(fascicolo: Fascicolo, documento: Document) -> None:
    """Aggiunge il documento al fascicolo, se c'è posto.

    Il controllo precede la mutazione: un rifiuto lascia il fascicolo esattamente
    com'era.
    """
    if len(fascicolo.documents) >= Fascicolo.MAX_DOCUMENTI:
        raise FascicoloFull(
            f"massimo {Fascicolo.MAX_DOCUMENTI} documenti per fascicolo"
        )
    fascicolo.documents.append(documento)
