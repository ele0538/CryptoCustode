"""Ripristino della risposta dell'IA: dai segnaposto ai valori veri (spec §11)."""

from __future__ import annotations

import re

from cryptocustode.core.errors import MalformedPlaceholder, UnknownPlaceholder
from cryptocustode.core.models import Entity

# Passo 2: la forma canonica.
SEGNAPOSTO = re.compile(r"\[[A-Z]+_\d+\]")

# Passo 3: la forma permissiva, che cattura anche i quasi-segnaposto storpiati
# dall'IA. Tutto ciò che questa trova e la severa no è un'alterazione.
QUASI_SEGNAPOSTO = re.compile(r"\[[A-Za-z]+[_\-\s]?\d*\]?")


def _alterazioni(risposta: str) -> list[str]:
    """I frammenti che somigliano a un segnaposto senza esserlo.

    Il confronto è per posizione: un frammento è un'alterazione se la regex
    severa non produce, allo stesso offset, esattamente la stessa stringa.
    """
    canonici = {
        trovato.start(): trovato.group(0) for trovato in SEGNAPOSTO.finditer(risposta)
    }
    return [
        trovato.group(0)
        for trovato in QUASI_SEGNAPOSTO.finditer(risposta)
        if canonici.get(trovato.start()) != trovato.group(0)
    ]


def ripristina(risposta: str, entities: dict[str, Entity]) -> str:
    """Sostituisce i segnaposto della risposta con i valori canonici.

    Nessun ripristino parziale, in nessun caso: se anche un solo segnaposto è
    alterato o sconosciuto la funzione solleva e non restituisce nulla. Un testo
    in cui l'utente non sa quali segnaposto siano stati risolti e quali no è
    peggio di un errore (spec §11).
    """
    alterati = _alterazioni(risposta)
    if alterati:
        elenco = ", ".join(repr(frammento) for frammento in alterati)
        raise MalformedPlaceholder(
            f"segnaposto alterati, ripristino interrotto: {elenco}"
        )

    dizionario = {entita.placeholder: entita.canonical_value for entita in entities.values()}
    trovati = [trovato.group(0) for trovato in SEGNAPOSTO.finditer(risposta)]
    sconosciuti = sorted({t for t in trovati if t not in dizionario})
    if sconosciuti:
        elenco = ", ".join(sconosciuti)
        raise UnknownPlaceholder(
            "segnaposto non riconosciuto o appartenente a un'altra sessione, "
            f"ripristino interrotto: {elenco}"
        )

    ripristinato = risposta
    # Lunghezza decrescente, come richiede la spec §11 passo 5. Con la forma
    # attuale dei segnaposto è difesa in profondità e non un requisito attivo:
    # la parentesi di chiusura fa già sì che nessun segnaposto sia sottostringa
    # di un altro ("[PERSONA_1]" non compare in "[PERSONA_10]"). Resta qui
    # perché se un domani il formato perdesse il terminatore, è l'ordinamento
    # a evitare che resti uno 0 orfano.
    for segnaposto in sorted(dizionario, key=len, reverse=True):
        ripristinato = ripristinato.replace(segnaposto, dizionario[segnaposto])
    return ripristinato
