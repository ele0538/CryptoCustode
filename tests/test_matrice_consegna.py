"""I sei casi della matrice della consegna e il test anti-fuga generico (spec §14)."""

import pytest

from cryptocustode.core.entities import analizza_documento
from cryptocustode.core.errors import (
    ExportNotAllowed,
    ScannedDocumentRejected,
    UnknownPlaceholder,
)
from cryptocustode.core.ingest.loader import aggiungi_documento, costruisci_documento
from cryptocustode.core.models import Category, State, fascicolo_vuoto
from cryptocustode.core.unmask import ripristina
from cryptocustode.state.session import (
    SessionStore,
    analisi_completata,
    approva,
    export_sanitized_text,
    registra_mutazione,
)
from tests.pdf_di_prova import pdf_di_prova

TESTO_RICCO = (
    "Il contratto è firmato da Mario Rossi, codice fiscale RSSMRA85M01H501Q, "
    "con IBAN IT60X0542811101000000123456 e P. IVA 12345678903. "
    "Recapito: Cell. 3401234567, mario.rossi@esempio.it."
)


def fascicolo_con(testo: str, nome: str = "contratto.txt", usa_ner: bool = False):
    fascicolo = fascicolo_vuoto("f1")
    documento = costruisci_documento(nome, testo.encode("utf-8"))
    aggiungi_documento(fascicolo, documento)
    analizza_documento(fascicolo, documento, usa_ner=usa_ner)
    analisi_completata(fascicolo)
    return fascicolo


def store_con(fascicolo):
    store = SessionStore()
    store.salva(fascicolo)
    return store


@pytest.mark.lento
def test_anti_fuga_nessun_valore_del_dizionario_compare_nell_esportato():
    """Il test più importante della suite, e i suoi limiti onesti.

    Prova che ogni valore effettivamente rilevato è assente dal testo
    esportato, e che le categorie che questa fixture pianta deliberatamente
    (CF, IBAN, P. IVA, email, telefono, persona) sono state davvero rilevate
    — non solo che il dizionario, qualunque cosa contenga, non fuga. Non può
    provare l'assenza di valori che il motore non ha mai rilevato: se una
    categoria futura sfugge al rilevamento, questo test non se ne accorge.
    Per questo gira con `usa_ner=True`: senza la gamba statistica, PERSONA
    non verrebbe mai prodotta e la sua assenza non entrerebbe mai in
    dizionario, restando indimostrata invece che verificata.
    """
    fascicolo = fascicolo_con(TESTO_RICCO, usa_ner=True)
    approva(fascicolo)
    esportato = export_sanitized_text("f1", store_con(fascicolo))
    testo_esportato = "\n".join(esportato.values())
    assert fascicolo.entities, "il fascicolo deve avere almeno un'entità, altrimenti il test non prova nulla"
    categorie_rilevate = {entita.category for entita in fascicolo.entities.values()}
    categorie_pianificate = {
        Category.CF,
        Category.IBAN,
        Category.PIVA,
        Category.EMAIL,
        Category.TELEFONO,
        Category.PERSONA,
    }
    mancanti = categorie_pianificate - categorie_rilevate
    assert not mancanti, (
        "la fixture pianta queste categorie apposta per essere rilevate; se "
        f"mancano ({mancanti}) il ciclo sottostante quantifica su meno di "
        "quanto promesso e il test non proverebbe più nulla per loro"
    )
    for entita in fascicolo.entities.values():
        assert entita.canonical_value not in testo_esportato
        for variante in entita.variants:
            assert variante not in testo_esportato


def test_TC_01_pdf_con_una_pagina_scansionata_su_cinque_viene_rifiutato():
    contenuto = pdf_di_prova(["testo", "testo", "testo", "testo", "immagine"])
    with pytest.raises(ScannedDocumentRejected, match="5"):
        costruisci_documento("scansione.pdf", contenuto)


@pytest.mark.lento
def test_TC_02_cf_con_cin_errato_non_diventa_un_codice_fiscale():
    # RSSMRA85M01H501A ha il CIN sbagliato: la regola lo scarta. Può restare
    # un'entità NER se il modello lo interpreta come nome, ma non un CF.
    fascicolo = fascicolo_con(
        "Il codice fiscale è RSSMRA85M01H501A.", usa_ner=True
    )
    categorie = {entita.category for entita in fascicolo.entities.values()}
    assert Category.CF not in categorie


@pytest.mark.lento
def test_TC_03_due_documenti_con_lo_stesso_nome_e_nessun_cf_bloccano_l_approvazione():
    fascicolo = fascicolo_vuoto("f1")
    for indice, testo in enumerate(
        ["Il conduttore Mario Rossi firma.", "Il garante Mario Rossi firma."]
    ):
        documento = costruisci_documento(f"doc{indice}.txt", testo.encode("utf-8"))
        aggiungi_documento(fascicolo, documento)
        analizza_documento(fascicolo, documento, usa_ner=True)
    analisi_completata(fascicolo)
    assert any(a.blocca_approvazione for a in fascicolo.ambiguities)


def test_TC_04_export_in_stato_draft_e_negato():
    fascicolo = fascicolo_vuoto("f1")
    assert fascicolo.state is State.DRAFT
    with pytest.raises(ExportNotAllowed):
        export_sanitized_text("f1", store_con(fascicolo))


def test_TC_05_risposta_con_un_segnaposto_inesistente_interrompe_il_ripristino():
    fascicolo = fascicolo_con(TESTO_RICCO)
    with pytest.raises(UnknownPlaceholder, match=r"\[PERSONA_99\]"):
        ripristina("Rispondo a [PERSONA_99].", fascicolo.entities)


def test_TC_06_una_mutazione_dopo_l_approvazione_riporta_in_pending_e_nega_l_export():
    fascicolo = fascicolo_con(TESTO_RICCO)
    approva(fascicolo)
    assert fascicolo.state is State.APPROVED
    registra_mutazione(fascicolo)
    assert fascicolo.state is State.PENDING_REVIEW
    with pytest.raises(ExportNotAllowed):
        export_sanitized_text("f1", store_con(fascicolo))
