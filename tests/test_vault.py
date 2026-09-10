import pytest

from cryptocustode.core import vault
from cryptocustode.core.errors import VaultUnreadable
from cryptocustode.core.models import (
    Ambiguity,
    AmbiguityKind,
    Category,
    Document,
    Entity,
    Source,
    Span,
    State,
    fascicolo_vuoto,
)

PASSWORD = "una password di prova"


def fascicolo_popolato():
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
            span_id="d1:0-11:PERSONA",
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
        variants={"Mario Rossi", "M. Rossi"},
        cf=None,
    )
    fascicolo.ambiguities.append(
        Ambiguity(
            ambiguity_id="a1",
            kind=AmbiguityKind.SAME_NAME_NO_CF,
            category=Category.PERSONA,
            candidate_entity_ids=["e1"],
            occurrence_span_ids=["d1:0-11:PERSONA"],
        )
    )
    fascicolo.counters[Category.PERSONA] = 1
    fascicolo.category_enabled[Category.DATA] = False
    fascicolo.state = State.PENDING_REVIEW
    return fascicolo


def test_round_trip_conserva_il_fascicolo():
    originale = fascicolo_popolato()
    ricaricato = vault.carica(vault.salva(originale, PASSWORD), PASSWORD)
    assert ricaricato.fascicolo_id == originale.fascicolo_id
    assert ricaricato.documents == originale.documents
    assert ricaricato.spans == originale.spans
    assert ricaricato.state == originale.state


def test_round_trip_conserva_le_entita_con_le_varianti():
    originale = fascicolo_popolato()
    ricaricato = vault.carica(vault.salva(originale, PASSWORD), PASSWORD)
    entita = ricaricato.entities["e1"]
    assert entita.canonical_value == "Mario Rossi"
    assert entita.variants == {"Mario Rossi", "M. Rossi"}
    assert entita.category is Category.PERSONA


def test_round_trip_conserva_le_ambiguita():
    ricaricato = vault.carica(vault.salva(fascicolo_popolato(), PASSWORD), PASSWORD)
    assert len(ricaricato.ambiguities) == 1
    assert ricaricato.ambiguities[0].kind is AmbiguityKind.SAME_NAME_NO_CF
    assert ricaricato.ambiguities[0].blocca_approvazione is True


def test_round_trip_conserva_i_contatori():
    # Senza i contatori gli indici dei segnaposto verrebbero riciclati dopo una
    # riapertura, e [PERSONA_1] finirebbe a una persona diversa (spec §7).
    ricaricato = vault.carica(vault.salva(fascicolo_popolato(), PASSWORD), PASSWORD)
    assert ricaricato.counters[Category.PERSONA] == 1


def test_round_trip_conserva_gli_interruttori_di_categoria():
    ricaricato = vault.carica(vault.salva(fascicolo_popolato(), PASSWORD), PASSWORD)
    assert ricaricato.category_enabled[Category.DATA] is False
    assert ricaricato.category_enabled[Category.PERSONA] is True


def test_l_intestazione_ha_la_forma_della_spec():
    blob = vault.salva(fascicolo_popolato(), PASSWORD)
    assert blob[:4] == vault.MAGIC
    assert int.from_bytes(blob[4:8], "big") == vault.ITERAZIONI_KDF
    # magic 4 + iterazioni 4 + salt 16 + nonce 12 = 36 byte di intestazione.
    assert len(blob) > 36


def test_due_salvataggi_usano_salt_e_nonce_diversi():
    fascicolo = fascicolo_popolato()
    primo = vault.salva(fascicolo, PASSWORD)
    secondo = vault.salva(fascicolo, PASSWORD)
    assert primo[8:36] != secondo[8:36]
    assert primo != secondo


def test_il_testo_in_chiaro_non_compare_nel_blob():
    blob = vault.salva(fascicolo_popolato(), PASSWORD)
    assert b"Mario Rossi" not in blob
    assert b"Torino" not in blob


def test_password_errata_non_apre_il_vault():
    blob = vault.salva(fascicolo_popolato(), PASSWORD)
    with pytest.raises(VaultUnreadable):
        vault.carica(blob, "password sbagliata")


def test_ciphertext_manomesso_non_apre_il_vault():
    blob = bytearray(vault.salva(fascicolo_popolato(), PASSWORD))
    blob[-1] ^= 0xFF
    with pytest.raises(VaultUnreadable):
        vault.carica(bytes(blob), PASSWORD)


def test_abbassare_le_iterazioni_nell_intestazione_non_apre_il_vault():
    # L'intestazione è associated data: modificarla fa fallire la verifica del tag.
    blob = bytearray(vault.salva(fascicolo_popolato(), PASSWORD))
    blob[4:8] = (1000).to_bytes(4, "big")
    with pytest.raises(VaultUnreadable):
        vault.carica(bytes(blob), PASSWORD)


def test_magic_sbagliato_viene_respinto():
    blob = bytearray(vault.salva(fascicolo_popolato(), PASSWORD))
    blob[:4] = b"XXXX"
    with pytest.raises(VaultUnreadable):
        vault.carica(bytes(blob), PASSWORD)


def test_blob_troncato_viene_respinto():
    with pytest.raises(VaultUnreadable):
        vault.carica(b"CCV1", PASSWORD)


def test_il_messaggio_non_distingue_password_da_manomissione():
    blob = vault.salva(fascicolo_popolato(), PASSWORD)
    with pytest.raises(VaultUnreadable) as errata:
        vault.carica(blob, "password sbagliata")
    manomesso = bytearray(blob)
    manomesso[-1] ^= 0xFF
    with pytest.raises(VaultUnreadable) as corrotto:
        vault.carica(bytes(manomesso), PASSWORD)
    assert str(errata.value) == str(corrotto.value)
