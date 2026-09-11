import json
import os

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from cryptocustode.core import vault
from cryptocustode.core.errors import (
    VaultUnreadable,
    VaultVersionNotSupported,
)
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
    # Due asserzioni separate, non una sola su tutto il segmento [8:36]: un
    # salt costante con un nonce casuale farebbe comunque passare il
    # confronto unico, perché la differenza del nonce basterebbe da sola.
    fascicolo = fascicolo_popolato()
    primo = vault.salva(fascicolo, PASSWORD)
    secondo = vault.salva(fascicolo, PASSWORD)
    assert primo[8:24] != secondo[8:24]  # salt
    assert primo[24:36] != secondo[24:36]  # nonce
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


def test_intestazione_non_autenticata_come_associated_data_non_apre_il_vault():
    # Se l'intestazione non fosse passata come AAD a AESGCM, un blob riassemblato
    # con la stessa chiave/nonce ma un'intestazione diversa da quella usata in
    # cifratura aprirebbe comunque: il tag verificherebbe solo il ciphertext.
    # Costruiamo qui, a mano, esattamente quel blob: stesso salt e nonce di un
    # salvataggio vero, ma cifrato con AAD vuoto anziché con l'intestazione.
    fascicolo = fascicolo_popolato()
    salt = os.urandom(16)
    nonce = os.urandom(12)
    chiave = vault._deriva_chiave(PASSWORD, salt, vault.ITERAZIONI_KDF)
    testo_in_chiaro = json.dumps(
        vault._a_dizionario(fascicolo), ensure_ascii=False
    ).encode("utf-8")
    cifrato = AESGCM(chiave).encrypt(nonce, testo_in_chiaro, b"")
    intestazione = vault.MAGIC + vault.ITERAZIONI_KDF.to_bytes(4, "big") + salt
    blob = intestazione + nonce + cifrato
    with pytest.raises(VaultUnreadable):
        vault.carica(blob, PASSWORD)


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


def _blob_con_versione(monkeypatch, versione):
    """Un vault scritto come se `VAULT_VERSION` fosse `versione`.

    Usa il codice di scrittura vero invece di forgiare il JSON a mano: se un
    giorno il formato cambia, questi test cambiano con lui.
    """
    monkeypatch.setattr(vault, "VAULT_VERSION", versione)
    blob = vault.salva(fascicolo_popolato(), PASSWORD)
    monkeypatch.undo()
    return blob


def test_una_versione_futura_viene_rifiutata(monkeypatch):
    """Il pericolo vero è un formato futuro che si limita ad *aggiungere*
    chiavi: senza guardia il codice di oggi lo caricherebbe ignorandole in
    silenzio, e l'utente non saprebbe di aver perso qualcosa (issue #17)."""
    blob = _blob_con_versione(monkeypatch, vault.VAULT_VERSION + 1)
    with pytest.raises(VaultVersionNotSupported):
        vault.carica(blob, PASSWORD)


def test_il_messaggio_della_versione_futura_e_distinto(monkeypatch):
    """Distinguere qui non rivela nulla: si arriva a leggere la versione solo
    dopo che password e integrità hanno già retto (spec §13)."""
    blob = _blob_con_versione(monkeypatch, 99)
    with pytest.raises(VaultVersionNotSupported) as errore:
        vault.carica(blob, PASSWORD)
    messaggio = str(errore.value)
    assert messaggio != vault._MESSAGGIO_ILLEGGIBILE
    assert "99" in messaggio
    assert str(vault.VAULT_VERSION) in messaggio


def test_una_versione_piu_vecchia_si_carica_ancora(monkeypatch):
    """La guardia chiude solo in avanti: un vault scritto prima resta apribile,
    altrimenti aggiornare l'app butterebbe via il lavoro dell'utente."""
    blob = _blob_con_versione(monkeypatch, 1)
    assert vault.carica(blob, PASSWORD).fascicolo_id == "f1"


def test_un_vault_v1_con_cf_di_troppo_si_carica_ignorando_la_chiave(monkeypatch):
    """La promessa scritta accanto a `VAULT_VERSION = 2`: i vault della v1
    portano un `cf` per entità, caduto con l'emendamento della §7 (issue #12),
    e devono restare leggibili."""
    originale = vault._a_dizionario

    def con_cf(fascicolo):
        dati = originale(fascicolo)
        dati["vault_version"] = 1
        for entita in dati["entities"].values():
            entita["cf"] = "RSSMRC80A01H501W"
        return dati

    monkeypatch.setattr(vault, "_a_dizionario", con_cf)
    blob = vault.salva(fascicolo_popolato(), PASSWORD)
    monkeypatch.undo()
    ricaricato = vault.carica(blob, PASSWORD)
    assert ricaricato.entities["e1"].canonical_value == "Mario Rossi"
    assert not hasattr(ricaricato.entities["e1"], "cf")


def test_una_versione_non_intera_e_illeggibile(monkeypatch):
    """Un confronto fra str e int solleverebbe `TypeError`, che non è fra gli
    errori catturati da `carica` e uscirebbe nudo dal core rompendo il
    contratto del docstring. Vale come payload corrotto, col messaggio
    indistinguibile che gli altri corrotti hanno."""
    blob = _blob_con_versione(monkeypatch, "due")
    with pytest.raises(VaultUnreadable) as errore:
        vault.carica(blob, PASSWORD)
    assert str(errore.value) == vault._MESSAGGIO_ILLEGGIBILE


def test_una_versione_booleana_e_illeggibile(monkeypatch):
    """`isinstance(True, int)` è vero in Python, quindi senza un controllo
    esplicito un `"vault_version": true` passerebbe per la versione 1 e il
    vault verrebbe caricato: proprio il "frainteso invece di rifiutato" che
    questa guardia esiste per impedire."""
    blob = _blob_con_versione(monkeypatch, True)
    with pytest.raises(VaultUnreadable) as errore:
        vault.carica(blob, PASSWORD)
    assert str(errore.value) == vault._MESSAGGIO_ILLEGGIBILE
