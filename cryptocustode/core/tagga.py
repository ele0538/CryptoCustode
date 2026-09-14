"""Dai valori rilevati al testo mascherato (spec §7 del 2026-09-14).

Modulo puro come `mask.py`, e per la stessa ragione: `hash_approvazione` lo
attraversa, quindi un tagging non deterministico farebbe fallire a caso il
confronto con `approval_hash` e il controllo d'integrità diventerebbe rumore.
Il non determinismo del modello sta a monte e non entra qui: queste funzioni
ricevono una lista di valori, non un documento da interpretare.

La divisione in due funzioni non è cosmetica. I tag sono **di fascicolo** —
lo stesso nome deve avere lo stesso segnaposto in tutti i documenti, altrimenti
il testo che l'utente consegna a un'IA di terze parti non è coerente con sé
stesso — mentre il testo mascherato è **di documento**.
"""

from dataclasses import replace

from cryptocustode.core.models import (
    Category,
    Mascheratura,
    Regione,
    Rilevazione,
    StatoTag,
    Tag,
)
from cryptocustode.core.placeholders import costruisci_segnaposto


def _ordine_totale(valore: str) -> tuple[int, str]:
    """Lunghezza decrescente, poi alfabetico crescente.

    La lunghezza serve alla correttezza: `Rossi` non deve prendersi il posto
    dentro `Mario Rossi`. L'alfabetico serve alla riproducibilità: due valori
    lunghi uguali devono ordinarsi sempre allo stesso modo, qualunque sia
    l'ordine in cui il modello li ha elencati.
    """
    return (-len(valore), valore)


def assegna_tag(
    rilevazioni: list[Rilevazione],
    tabella: dict[str, Tag],
    contatori: dict[Category, int],
) -> tuple[dict[str, Tag], dict[Category, int]]:
    """Estende la tabella dei tag con i valori che non ci sono ancora.

    Restituisce copie nuove e non muta gli argomenti: chi chiama decide quando
    scrivere il risultato nel fascicolo, e un fallimento a metà non lascia la
    tabella in uno stato intermedio.

    I nuovi valori vengono numerati in ordine totale (`_ordine_totale`), non
    nell'ordine in cui il modello li ha elencati.
    """
    nuova = dict(tabella)
    contati = dict(contatori)
    gia_presenti = {tag.valore for tag in nuova.values()}

    inediti: list[Rilevazione] = []
    for rilevazione in rilevazioni:
        if not rilevazione.valore or rilevazione.valore in gia_presenti:
            continue
        gia_presenti.add(rilevazione.valore)
        inediti.append(rilevazione)

    for rilevazione in sorted(inediti, key=lambda r: _ordine_totale(r.valore)):
        indice = contati.get(rilevazione.categoria, 0) + 1
        contati[rilevazione.categoria] = indice
        segnaposto = costruisci_segnaposto(rilevazione.categoria.value, indice)
        nuova[segnaposto] = Tag(
            tag=segnaposto,
            categoria=rilevazione.categoria,
            valore=rilevazione.valore,
            occorrenze=0,
            stato=StatoTag.NON_TROVATO,
        )
    return nuova, contati
