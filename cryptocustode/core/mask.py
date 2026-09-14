"""Mascheratura e hash canonico di approvazione.

Modulo deliberatamente puro: nessuna I/O, nessun orologio, nessun random. Se
mascherare lo stesso fascicolo due volte producesse output diversi, il
confronto con `approval_hash` fallirebbe a caso e il controllo di integrità
diventerebbe rumore invece di una difesa (spec §4, invariante 2).
"""

import hashlib

from cryptocustode.core.models import Document, Fascicolo, StatoTag, Tag
from cryptocustode.core.tagga import tagga


def tabella_attiva(fascicolo: Fascicolo) -> dict[str, Tag]:
    """I tag che verranno davvero sostituiti.

    Due interruttori indipendenti, letti in `and`: lo stato del singolo tag e
    quello della sua categoria (spec §5 del 2026-09-10). Tenerli distinti dà
    una risposta ovvia alla domanda "spengo la categoria e poi la riaccendo:
    che fine fanno i tag che avevo spento a mano?" — restano spenti.

    È l'erede di `span_attivo`, e vive qui per la stessa ragione per cui
    viveva qui quello: chiunque debba sapere se un dato esce in chiaro deve
    leggerlo da un posto solo, altrimenti la UI mostra acceso ciò che
    l'esportazione lascia spento.
    """
    return {
        chiave: tag
        for chiave, tag in fascicolo.tags.items()
        if tag.stato is not StatoTag.DISATTIVATO
        and fascicolo.category_enabled.get(tag.categoria, True)
    }


def maschera_documento(fascicolo: Fascicolo, documento: Document) -> str:
    return tagga(documento.text, tabella_attiva(fascicolo)).mascherato


def hash_approvazione(fascicolo: Fascicolo) -> str:
    """SHA-256 su una serializzazione canonica dei testi mascherati.

    I documenti sono ordinati per nome file e ciascuno emette
    `filename\\n<lunghezza>\\n<testo>`. La lunghezza esplicita rende la
    concatenazione non ambigua, così due fascicoli diversi non possono
    produrre lo stesso digest (spec §8 del 2026-09-10).
    """
    digest = hashlib.sha256()
    for documento in sorted(fascicolo.documents, key=lambda d: (d.filename, d.doc_id)):
        mascherato = maschera_documento(fascicolo, documento)
        blocco = f"{documento.filename}\n{len(mascherato)}\n{mascherato}"
        digest.update(blocco.encode("utf-8"))
    return digest.hexdigest()
