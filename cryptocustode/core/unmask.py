"""Ripristino della risposta dell'IA: dai segnaposto ai valori veri (spec §11)."""

import re

from cryptocustode.core.errors import MalformedPlaceholder, UnknownPlaceholder

# (nessun import di modelli: questo modulo lavora su stringhe)

# Passo 2: la forma canonica. Arriva dal modulo che la possiede e non da una
# copia locale, così non può divergere in silenzio dalla forma con cui la
# mascheratura genera i segnaposto (issue #20).
from cryptocustode.core.placeholders import SEGNAPOSTO

# Passo 3: la forma permissiva, che cattura anche i quasi-segnaposto storpiati
# dall'IA. Tutto ciò che questa trova e la severa no è un'alterazione. Resta
# qui perché è una regola del ripristino, non una dichiarazione del formato.
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


def ripristina(risposta: str, dizionario: dict[str, str]) -> str:
    """Sostituisce i segnaposto della risposta con i valori reali.

    `dizionario` è la mappa `tag → valore`, non più un dizionario di entità:
    questo modulo non ha bisogno di conoscere i tipi del dominio, e ricevendo
    stringhe resta identico sia che la mappa venga da un fascicolo vivo sia che
    venga da un vault riaperto (`core/tagga.dizionario_di`).

    Nessun ripristino parziale, in nessun caso: se anche un solo segnaposto è
    alterato o sconosciuto la funzione solleva e non restituisce nulla. Un
    testo in cui l'utente non sa quali segnaposto siano stati risolti e quali
    no è peggio di un errore (spec §11).
    """
    alterati = _alterazioni(risposta)
    if alterati:
        elenco = ", ".join(repr(frammento) for frammento in alterati)
        raise MalformedPlaceholder(
            f"segnaposto alterati, ripristino interrotto: {elenco}"
        )

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
