"""Vault cifrato: AES-256-GCM con chiave derivata via PBKDF2 (spec §10).

Fuori dal vault il fascicolo vive solo nella RAM del processo.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from cryptocustode.core.errors import VaultUnreadable
from cryptocustode.core.models import (
    Ambiguity,
    AmbiguityKind,
    Category,
    Document,
    Entity,
    Fascicolo,
    Source,
    Span,
    State,
)

MAGIC = b"CCV1"
ITERAZIONI_KDF = 600_000
# Versione 2: le entità non portano più il campo `cf` (spec §7, issue #12). Un
# blob di versione 1 resta leggibile — la chiave `cf` in più viene ignorata —
# ma la politica sulle versioni diverse dalla corrente la fissa la issue #17.
VAULT_VERSION = 2

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
        "spans": [
            {
                "span_id": s.span_id,
                "doc_id": s.doc_id,
                "start": s.start,
                "end": s.end,
                "category": s.category.value,
                "source": s.source.value,
                "entity_id": s.entity_id,
                "enabled": s.enabled,
            }
            for s in fascicolo.spans
        ],
        "entities": {
            chiave: {
                "entity_id": e.entity_id,
                "category": e.category.value,
                "placeholder": e.placeholder,
                "canonical_value": e.canonical_value,
                # I set non sono serializzabili in JSON: ordinati per rendere il
                # blob riproducibile a parità di contenuto.
                "variants": sorted(e.variants),
            }
            for chiave, e in fascicolo.entities.items()
        },
        "category_enabled": {
            categoria.value: attiva for categoria, attiva in fascicolo.category_enabled.items()
        },
        "ambiguities": [
            {
                "ambiguity_id": a.ambiguity_id,
                "kind": a.kind.value,
                "category": a.category.value,
                "candidate_entity_ids": list(a.candidate_entity_ids),
                "occurrence_span_ids": list(a.occurrence_span_ids),
                "resolved": a.resolved,
            }
            for a in fascicolo.ambiguities
        ],
        "state": fascicolo.state.value,
        "approval_hash": fascicolo.approval_hash,
        # Nell'elenco della spec §10: senza i contatori gli indici dei
        # segnaposto verrebbero riciclati dopo una riapertura (spec §7).
        "counters": {
            categoria.value: valore for categoria, valore in fascicolo.counters.items()
        },
    }


def _da_dizionario(dati: dict) -> Fascicolo:
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
        spans=[
            Span(
                span_id=s["span_id"],
                doc_id=s["doc_id"],
                start=s["start"],
                end=s["end"],
                category=Category(s["category"]),
                source=Source(s["source"]),
                entity_id=s["entity_id"],
                enabled=s["enabled"],
            )
            for s in dati["spans"]
        ],
        entities={
            chiave: Entity(
                entity_id=e["entity_id"],
                category=Category(e["category"]),
                placeholder=e["placeholder"],
                canonical_value=e["canonical_value"],
                variants=set(e["variants"]),
            )
            for chiave, e in dati["entities"].items()
        },
        category_enabled={
            Category(nome): attiva for nome, attiva in dati["category_enabled"].items()
        },
        ambiguities=[
            Ambiguity(
                ambiguity_id=a["ambiguity_id"],
                kind=AmbiguityKind(a["kind"]),
                category=Category(a["category"]),
                candidate_entity_ids=list(a["candidate_entity_ids"]),
                occurrence_span_ids=list(a["occurrence_span_ids"]),
                resolved=a["resolved"],
            )
            for a in dati["ambiguities"]
        ],
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
    messaggio in tutti i casi.
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
