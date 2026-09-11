"""Facciata dell'ingresso: da byte a `Document`, e da `Document` a fascicolo."""

import hashlib
import uuid

from cryptocustode.core.errors import DuplicateFilename, FascicoloFull
from cryptocustode.core.ingest.pdf_loader import carica_pdf
from cryptocustode.core.ingest.txt_loader import carica_txt
from cryptocustode.core.models import Document, Fascicolo
from cryptocustode.core.placeholders import SEGNAPOSTO


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
    """Aggiunge il documento al fascicolo, se c'è posto e il nome è libero.

    I controlli precedono la mutazione: un rifiuto lascia il fascicolo esattamente
    com'era.

    Il nome deve essere libero perché il payload dell'export è indicizzato per
    nome file (spec §8): due omonimi — lo stesso file caricato due volte, o due
    file diversi con lo stesso nome presi da cartelle diverse — collasserebbero
    in una sola chiave e l'utente riceverebbe un documento in meno senza alcun
    errore (issue #19). Il rifiuto rende quel silenzio impossibile.
    """
    if len(fascicolo.documents) >= Fascicolo.MAX_DOCUMENTI:
        raise FascicoloFull(
            f"massimo {Fascicolo.MAX_DOCUMENTI} documenti per fascicolo"
        )
    if any(presente.filename == documento.filename for presente in fascicolo.documents):
        raise DuplicateFilename(
            "attento: hai caricato due file uguali o con lo stesso nome "
            f"({documento.filename}), il secondo non è stato caricato: "
            "rinominalo e riprova"
        )
    fascicolo.documents.append(documento)
