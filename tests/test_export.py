import pytest

from cryptocustode.core.errors import ExportNotAllowed, IntegrityError
from cryptocustode.core.models import (
    Category,
    Document,
    Entity,
    Source,
    Span,
    State,
    fascicolo_vuoto,
)
from cryptocustode.state.session import (
    SessionStore,
    analisi_completata,
    approva,
    export_sanitized_text,
)


def fascicolo_approvato():
    fascicolo = fascicolo_vuoto("f1")
    fascicolo.documents.append(
        Document(
            doc_id="d1",
            filename="contratto.txt",
            text="Mario Rossi abita a Torino.",
            page_offsets=[0],
            sha256="a" * 64,
        )
    )
    fascicolo.spans.append(
        Span(
            span_id="s1",
            doc_id="d1",
            start=0,
            end=11,
            category=Category.PERSONA,
            source=Source.NER,
            entity_id="e1",
        )
    )
    fascicolo.entities["e1"] = Entity(
        entity_id="e1",
        category=Category.PERSONA,
        placeholder="[PERSONA_1]",
        canonical_value="Mario Rossi",
    )
    analisi_completata(fascicolo)
    approva(fascicolo)
    return fascicolo


def store_con(fascicolo):
    store = SessionStore()
    store.salva(fascicolo)
    return store


def test_lo_store_restituisce_quello_che_ha_salvato():
    fascicolo = fascicolo_approvato()
    assert store_con(fascicolo).prendi("f1") is fascicolo


def test_lo_store_solleva_su_un_id_sconosciuto():
    with pytest.raises(KeyError):
        SessionStore().prendi("inesistente")


def test_export_in_stato_approved_restituisce_il_testo_mascherato():
    fascicolo = fascicolo_approvato()
    payload = export_sanitized_text("f1", store_con(fascicolo))
    assert payload == {"contratto.txt": "[PERSONA_1] abita a Torino."}


def test_export_in_draft_e_negato():
    # TC-04.
    fascicolo = fascicolo_vuoto("f1")
    with pytest.raises(ExportNotAllowed):
        export_sanitized_text("f1", store_con(fascicolo))


def test_export_in_pending_review_e_negato():
    fascicolo = fascicolo_vuoto("f1")
    analisi_completata(fascicolo)
    with pytest.raises(ExportNotAllowed):
        export_sanitized_text("f1", store_con(fascicolo))


def test_testo_cambiato_dopo_l_approvazione_solleva_integrity_error():
    fascicolo = fascicolo_approvato()
    # Lo stato resta APPROVED perché nessuno ha chiamato registra_mutazione:
    # è precisamente il caso che il secondo controllo esiste per intercettare.
    fascicolo.entities["e1"].placeholder = "[PERSONA_2]"
    with pytest.raises(IntegrityError):
        export_sanitized_text("f1", store_con(fascicolo))


def test_il_payload_non_contiene_il_testo_originale():
    fascicolo = fascicolo_approvato()
    payload = export_sanitized_text("f1", store_con(fascicolo))
    assert "Mario Rossi" not in payload["contratto.txt"]


def test_il_payload_ha_solo_i_nomi_dei_file_come_chiavi():
    fascicolo = fascicolo_approvato()
    payload = export_sanitized_text("f1", store_con(fascicolo))
    assert set(payload) == {"contratto.txt"}
    assert all(isinstance(valore, str) for valore in payload.values())


def test_lo_stato_resta_approved_dopo_un_export():
    fascicolo = fascicolo_approvato()
    export_sanitized_text("f1", store_con(fascicolo))
    assert fascicolo.state is State.APPROVED
