"""Vault cifrato: AES-256-GCM con chiave derivata via PBKDF2 (spec §10).

Fuori dal vault il fascicolo vive solo nella RAM del processo.
"""

import json
import os
from datetime import datetime, timezone

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from cryptocustode.core.errors import VaultUnreadable, VaultVersionNotSupported
from cryptocustode.core.models import (
    Category,
    Document,
    Fascicolo,
    State,
    StatoTag,
    Tag,
)

MAGIC = b"CCV1"
ITERAZIONI_KDF = 600_000
# Versione 3: `spans`, `entities` e `ambiguities` lasciano il posto alla
# tabella dei tag (spec §5 del 2026-09-14), perché il motore ad IA non lavora
# più per offset nel testo. È una rottura deliberata e non solo in avanti:
# leggere un blob v2 richiederebbe di tenere in vita `Span`, `Entity` e
# `Ambiguity` solo per tradurli, e non esiste alcun vault v2 reale da
# convertire — l'esportazione che lo avrebbe scritto arriva in fase 2.
VAULT_VERSION = 3

_LUNGHEZZA_SALT = 16
_LUNGHEZZA_NONCE = 12
_LUNGHEZZA_CHIAVE = 32
# magic 4 + iterazioni 4 + salt 16: sono i byte autenticati come associated data.
_FINE_INTESTAZIONE_AUTENTICATA = 24
_FINE_INTESTAZIONE = _FINE_INTESTAZIONE_AUTENTICATA + _LUNGHEZZA_NONCE

# Un solo messaggio per password errata e file danneggiato: distinguerli direbbe
# a chi ci prova che la password è l'unico ostacolo rimasto (spec §13).
_MESSAGGIO_ILLEGGIBILE = "password errata o file danneggiato"


def _deriva_chiave(password: str, salt: bytes, iterazioni: int) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=_LUNGHEZZA_CHIAVE,
        salt=salt,
        iterations=iterazioni,
    )
    return kdf.derive(password.encode("utf-8"))


def _a_dizionario(fascicolo: Fascicolo) -> dict:
    return {
        "vault_version": VAULT_VERSION,
        "fascicolo_id": fascicolo.fascicolo_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "documents": [
            {
                "doc_id": d.doc_id,
                "filename": d.filename,
                "text": d.text,
                "page_offsets": list(d.page_offsets),
                "sha256": d.sha256,
            }
            for d in fascicolo.documents
        ],
        "tags": [
            {
                "tag": t.tag,
                "categoria": t.categoria.value,
                "valore": t.valore,
                "occorrenze": t.occorrenze,
                "stato": t.stato.value,
            }
            for t in fascicolo.tags.values()
        ],
        "analizzati": sorted(fascicolo.analizzati),
        "category_enabled": {
            categoria.value: attiva for categoria, attiva in fascicolo.category_enabled.items()
        },
        "state": fascicolo.state.value,
        "approval_hash": fascicolo.approval_hash,
        # Nell'elenco della spec §10: senza i contatori gli indici dei
        # segnaposto verrebbero riciclati dopo una riapertura (spec §7).
        "counters": {
            categoria.value: valore for categoria, valore in fascicolo.counters.items()
        },
    }


def _verifica_versione(versione: object) -> None:
    """Rifiuta un vault scritto da una versione diversa da questa, in entrambe
    le direzioni.

    Un formato più nuovo va rifiutato *prima* che ne esista uno che si limita
    ad aggiungere chiavi, perché quello verrebbe caricato ignorandole in
    silenzio e l'utente non saprebbe di aver perso qualcosa (issue #17).

    Un formato più vecchio, a partire dalla versione 3, non è più leggibile:
    è una rottura deliberata rispetto alla promessa fatta dalla spec §10 del
    2026-09-10. Tenerla avrebbe voluto dire mantenere in vita `Span`, `Entity`
    e `Ambiguity` solo per tradurli nella tabella dei tag, e non esiste alcun
    vault v2 reale da convertire: l'esportazione che lo avrebbe scritto arriva
    solo in fase 2. Il messaggio lo dice all'utente in chiaro, invece di farlo
    incappare in una diagnosi incomprensibile più a valle.

    Una versione che non è un intero è un payload corrotto, non un formato:
    `ValueError` la fa ricadere nel messaggio indistinguibile di `carica`. Il
    caso `bool` è escluso a mano perché in Python `isinstance(True, int)` è
    vero, e un `"vault_version": true` passerebbe per la versione 1.
    """
    if isinstance(versione, bool) or not isinstance(versione, int):
        raise ValueError(f"vault_version non è un intero: {versione!r}")
    if versione > VAULT_VERSION:
        raise VaultVersionNotSupported(
            f"questo vault usa il formato {versione}, mentre questa versione di "
            f"CryptoCustode ne legge al massimo {VAULT_VERSION}: aggiorna "
            "l'applicazione per aprirlo"
        )
    if versione < VAULT_VERSION:
        raise VaultVersionNotSupported(
            f"questo vault è in formato {versione} e CryptoCustode legge solo "
            f"il formato {VAULT_VERSION}: il formato è cambiato quando il "
            "motore è passato all'IA, e i fascicoli vecchi vanno rianalizzati."
        )


def _da_dizionario(dati: dict) -> Fascicolo:
    _verifica_versione(dati["vault_version"])
    return Fascicolo(
        fascicolo_id=dati["fascicolo_id"],
        documents=[
            Document(
                doc_id=d["doc_id"],
                filename=d["filename"],
                text=d["text"],
                page_offsets=list(d["page_offsets"]),
                sha256=d["sha256"],
            )
            for d in dati["documents"]
        ],
        tags={
            t["tag"]: Tag(
                tag=t["tag"],
                categoria=Category(t["categoria"]),
                valore=t["valore"],
                occorrenze=t["occorrenze"],
                stato=StatoTag(t["stato"]),
            )
            for t in dati["tags"]
        },
        analizzati=set(dati["analizzati"]),
        category_enabled={
            Category(nome): attiva for nome, attiva in dati["category_enabled"].items()
        },
        state=State(dati["state"]),
        approval_hash=dati["approval_hash"],
        counters={Category(nome): valore for nome, valore in dati["counters"].items()},
    )


def salva(fascicolo: Fascicolo, password: str) -> bytes:
    """Serializza e cifra l'intero fascicolo.

    Salt e nonce sono casuali a ogni salvataggio, quindi due salvataggi dello
    stesso fascicolo producono blob diversi: è voluto.
    """
    salt = os.urandom(_LUNGHEZZA_SALT)
    nonce = os.urandom(_LUNGHEZZA_NONCE)
    intestazione_autenticata = (
        MAGIC + ITERAZIONI_KDF.to_bytes(4, "big") + salt
    )
    chiave = _deriva_chiave(password, salt, ITERAZIONI_KDF)
    testo_in_chiaro = json.dumps(_a_dizionario(fascicolo), ensure_ascii=False).encode(
        "utf-8"
    )
    cifrato = AESGCM(chiave).encrypt(nonce, testo_in_chiaro, intestazione_autenticata)
    return intestazione_autenticata + nonce + cifrato


def carica(blob: bytes, password: str) -> Fascicolo:
    """Decifra un vault e ricostruisce il fascicolo.

    Solleva `VaultUnreadable` per qualunque motivo di fallimento, con lo stesso
    messaggio in tutti i casi tranne uno: un vault scritto in un formato
    diverso da quello letto qui — più vecchio o più nuovo — solleva
    `VaultVersionNotSupported`, che ne è una sottoclasse e porta un messaggio
    proprio. Quell'unica eccezione si raggiunge solo *dopo* una decifratura
    riuscita, quindi non dice nulla a chi non ha già la password (issue #17).
    """
    if len(blob) <= _FINE_INTESTAZIONE or blob[:4] != MAGIC:
        raise VaultUnreadable(_MESSAGGIO_ILLEGGIBILE)
    intestazione_autenticata = blob[:_FINE_INTESTAZIONE_AUTENTICATA]
    iterazioni = int.from_bytes(blob[4:8], "big")
    salt = blob[8:_FINE_INTESTAZIONE_AUTENTICATA]
    nonce = blob[_FINE_INTESTAZIONE_AUTENTICATA:_FINE_INTESTAZIONE]
    cifrato = blob[_FINE_INTESTAZIONE:]
    try:
        chiave = _deriva_chiave(password, salt, iterazioni)
        testo_in_chiaro = AESGCM(chiave).decrypt(
            nonce, cifrato, intestazione_autenticata
        )
        return _da_dizionario(json.loads(testo_in_chiaro.decode("utf-8")))
    except (InvalidTag, ValueError, KeyError, UnicodeDecodeError) as errore:
        raise VaultUnreadable(_MESSAGGIO_ILLEGGIBILE) from errore
