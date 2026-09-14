import pytest

from cryptocustode.core.errors import FascicoloNotFound
from cryptocustode.core.models import Category, Document, Rilevazione, State, fascicolo_vuoto
from cryptocustode.core.tagga import assegna_tag
from cryptocustode.state.session import (
    SessionStore,
    analisi_completata,
    approva,
    export_sanitized_text,
    registra_mutazione,
)


def fascicolo_analizzato():
    """Un fascicolo con un documento e un tag, pronto da approvare."""
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
    rilevazioni = [Rilevazione(valore="Mario Rossi", categoria=Category.PERSONA)]
    fascicolo.tags, fascicolo.counters = assegna_tag(
        rilevazioni, fascicolo.tags, fascicolo.counters
    )
    analisi_completata(fascicolo)
    return fascicolo


def test_un_fascicolo_nuovo_e_in_draft():
    assert fascicolo_vuoto("f1").state is State.DRAFT


def test_approvare_un_fascicolo_in_draft_e_rifiutato():
    # Senza questo controllo un DRAFT mai analizzato firmerebbe l'hash del
    # testo non ancora mascherato, e l'export lo restituirebbe verbatim.
    fascicolo = fascicolo_vuoto("f1")
    with pytest.raises(ValueError):
        approva(fascicolo)
    assert fascicolo.state is State.DRAFT
    assert fascicolo.approval_hash is None


def test_l_analisi_porta_in_pending_review():
    fascicolo = fascicolo_vuoto("f1")
    analisi_completata(fascicolo)
    assert fascicolo.state is State.PENDING_REVIEW


def test_l_approvazione_porta_in_approved():
    fascicolo = fascicolo_analizzato()
    approva(fascicolo)
    assert fascicolo.state is State.APPROVED


def test_l_approvazione_salva_l_hash():
    fascicolo = fascicolo_analizzato()
    approva(fascicolo)
    assert fascicolo.approval_hash is not None
    assert len(fascicolo.approval_hash) == 64


def test_l_approvazione_e_deterministica():
    primo, secondo = fascicolo_analizzato(), fascicolo_analizzato()
    approva(primo)
    approva(secondo)
    assert primo.approval_hash == secondo.approval_hash


def test_approva_senza_ambiguita_da_controllare():
    """La coda delle ambiguità non esiste più: con il contratto B due
    occorrenze della stessa stringa sono lo stesso tag per costruzione, quindi
    non c'è più un momento in cui due entità distinte esistano (spec §5)."""
    fascicolo = fascicolo_analizzato()
    approva(fascicolo)
    assert fascicolo.state is State.APPROVED
    assert fascicolo.approval_hash is not None


def test_una_mutazione_dopo_l_approvazione_riporta_in_pending_review():
    # TC-06.
    fascicolo = fascicolo_analizzato()
    approva(fascicolo)
    registra_mutazione(fascicolo)
    assert fascicolo.state is State.PENDING_REVIEW


def test_una_mutazione_dopo_l_approvazione_cancella_l_hash():
    fascicolo = fascicolo_analizzato()
    approva(fascicolo)
    registra_mutazione(fascicolo)
    assert fascicolo.approval_hash is None


def test_una_mutazione_in_pending_review_non_cambia_nulla():
    fascicolo = fascicolo_analizzato()
    registra_mutazione(fascicolo)
    assert fascicolo.state is State.PENDING_REVIEW


def test_una_mutazione_in_draft_non_cambia_nulla():
    fascicolo = fascicolo_vuoto("f1")
    registra_mutazione(fascicolo)
    assert fascicolo.state is State.DRAFT


def test_il_fascicolo_inesistente_lo_dice_in_italiano_e_cita_l_id():
    # La riga della spec §13 chiede il messaggio con l'id: senza, chi legge il
    # log sa che un fascicolo manca ma non quale.
    with pytest.raises(FascicoloNotFound, match="non esiste: f-ignoto"):
        SessionStore().prendi("f-ignoto")


def test_dal_gate_dell_export_esce_un_errore_di_dominio():
    # È il motivo per cui la issue #16 esiste: il KeyError nudo dello store
    # usciva dalla risoluzione dell'id, oggi il primo dei tre controlli della
    # §8, e attraversava `export_sanitized_text` senza che nessuno lo
    # riconoscesse; il layer HTTP lo tradurrebbe in un 500 invece del 404
    # della §13.
    with pytest.raises(FascicoloNotFound):
        export_sanitized_text("f-ignoto", SessionStore())


def test_il_docstring_del_gate_elenca_i_tre_controlli_nell_ordine_reale():
    # Guardia della issue #25. Il docstring enumerava due controlli mentre la
    # funzione ne fa tre, e quello taciuto era il primo che può fallire: chi
    # leggeva la funzione dal suo docstring non sapeva che la risoluzione
    # dell'id fa parte del gate. Un'enumerazione che non conta come il corpo è
    # peggio di nessuna enumerazione, perché sembra completa.
    docstring = export_sanitized_text.__doc__
    assert "Tre controlli" in docstring
    ordine = [docstring.index(voce) for voce in ("fascicolo_id", "APPROVED", "hash")]
    assert ordine == sorted(ordine), (
        "il docstring deve nominare risoluzione dell'id, stato e hash in "
        "quest'ordine, che è quello in cui il corpo li esegue"
    )


def test_lo_store_dice_di_non_avere_un_fascicolo_che_non_ha():
    # Chiedere "c'è?" non deve costare un'eccezione: chi decide se creare il
    # fascicolo al primo caricamento ha bisogno di una lettura, non di un
    # segnale di controllo travestito da errore (issue #3).
    assert SessionStore().contiene("f-ignoto") is False


def test_lo_store_dice_di_avere_il_fascicolo_che_ha_salvato():
    store = SessionStore()
    store.salva(fascicolo_vuoto("f1"))
    assert store.contiene("f1") is True
