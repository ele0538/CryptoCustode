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
    Category,
    Document,
    State,
    StatoTag,
    Tag,
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
    fascicolo.tags["[PERSONA_1]"] = Tag(
        tag="[PERSONA_1]",
        categoria=Category.PERSONA,
        valore="Mario Rossi",
        occorrenze=2,
        stato=StatoTag.APPLICATO,
    )
    fascicolo.analizzati.add("d1")
    fascicolo.counters[Category.PERSONA] = 1
    fascicolo.category_enabled[Category.DATA] = False
    fascicolo.state = State.PENDING_REVIEW
    return fascicolo


def test_round_trip_conserva_il_fascicolo():
    originale = fascicolo_popolato()
    ricaricato = vault.carica(vault.salva(originale, PASSWORD), PASSWORD)
    assert ricaricato.fascicolo_id == originale.fascicolo_id
    assert ricaricato.documents == originale.documents
    assert ricaricato.state == originale.state
    assert ricaricato.tags == originale.tags
    assert ricaricato.analizzati == originale.analizzati


def test_il_round_trip_conserva_la_tabella_dei_tag():
    # Costruiamo i tag come letterali invece di passare per `assegna_tag`: il
    # vault deve rileggere qualunque `Tag` valido, non solo quelli che quella
    # funzione produce, e qui copriamo due categorie diverse più uno stato
    # DISATTIVATO per esercitare davvero il round-trip dell'enum.
    fascicolo = fascicolo_vuoto("f1")
    fascicolo.tags = {
        "[PERSONA_1]": Tag(
            tag="[PERSONA_1]",
            categoria=Category.PERSONA,
            valore="Mario Rossi",
            occorrenze=2,
            stato=StatoTag.APPLICATO,
        ),
        "[INDIRIZZO_1]": Tag(
            tag="[INDIRIZZO_1]",
            categoria=Category.INDIRIZZO,
            valore="Via Roma 1",
            occorrenze=1,
            stato=StatoTag.DISATTIVATO,
        ),
    }
    fascicolo.counters = {Category.PERSONA: 1, Category.INDIRIZZO: 1}
    fascicolo.analizzati.add("d1")
    riletto = vault.carica(vault.salva(fascicolo, PASSWORD), PASSWORD)
    assert riletto.tags == fascicolo.tags
    assert riletto.counters == fascicolo.counters
    assert riletto.analizzati == {"d1"}


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


def test_un_vault_di_formato_precedente_non_e_leggibile():
    """La §10 del 2026-09-10 prometteva che un formato più vecchio restasse
    leggibile. La promessa cade qui, ed è una rottura deliberata: leggere un
    vault v2 richiederebbe di tenere in vita `Span`, `Entity` e `Ambiguity`
    solo per tradurli, e non esiste alcun vault v2 reale — l'esportazione che
    li avrebbe scritti arriva in fase 2. Il messaggio lo dice all'utente invece
    di fallire con una diagnosi incomprensibile."""
    with pytest.raises(VaultVersionNotSupported):
        vault._verifica_versione(2)


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
