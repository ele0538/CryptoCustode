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


def tagga(testo: str, tabella: dict[str, Tag]) -> Mascheratura:
    """Sostituisce nel testo i valori della tabella con i rispettivi tag.

    La ricerca è **esatta**: sensibile a maiuscole, accenti, punteggiatura e
    spaziatura, senza alcuna normalizzazione. È la controparte del vincolo di
    letteralità imposto al modello nella §6, e ciò che rende vera l'identità
    `unmask(tagga(testo, tabella).mascherato, mappa) == testo` della §8: se qui
    si accettasse una corrispondenza approssimata, al ripristino tornerebbe un
    valore diverso da quello che c'era, e il round-trip non sarebbe più
    un'identità ma una somiglianza.

    Un valore più lungo rivendica prima di uno più corto, e un valore corto non
    può rivendicare dentro una regione già presa: è ciò che impedisce a `Rossi`
    di finire dentro `Mario Rossi`.
    """
    rivendicate: list[Regione] = []
    occupato = [False] * len(testo)

    for tag in sorted(tabella.values(), key=lambda t: _ordine_totale(t.valore)):
        if not tag.valore:
            continue
        inizio = 0
        while True:
            trovato = testo.find(tag.valore, inizio)
            if trovato == -1:
                break
            fine = trovato + len(tag.valore)
            if any(occupato[trovato:fine]):
                # Sovrapposta a una regione già presa da un valore più lungo:
                # si riparte dal carattere successivo, perché l'occorrenza
                # buona potrebbe cominciare dentro quella scartata.
                inizio = trovato + 1
                continue
            occupato[trovato:fine] = [True] * (fine - trovato)
            rivendicate.append(Regione(start=trovato, end=fine, tag=tag.tag))
            inizio = fine

    rivendicate.sort(key=lambda regione: regione.start)

    # Da destra a sinistra: così ogni sostituzione lascia validi gli offset di
    # quelle ancora da applicare (spec §9 del 2026-09-10).
    mascherato = testo
    for regione in reversed(rivendicate):
        mascherato = mascherato[: regione.start] + regione.tag + mascherato[regione.end :]

    return Mascheratura(
        mascherato=mascherato,
        tags=list(tabella.values()),
        regioni=rivendicate,
    )


def conta_occorrenze(
    tabella: dict[str, Tag], mascherature: list[Mascheratura]
) -> dict[str, Tag]:
    """Aggiorna occorrenze e stato sull'insieme dei documenti del fascicolo.

    Quante volte un dato compaia, e se compaia affatto, è una proprietà del
    fascicolo: `tagga` lavora su un documento per volta e non può saperlo.

    I tag `DISATTIVATO` restano tali. Spegnere un tag è una decisione
    dell'utente sulla riservatezza, e un conteggio non ha titolo per revocarla:
    senza questa guardia, il primo ricalcolo dopo un toggle rimetterebbe in
    maschera un dato che l'utente ha chiesto di lasciare in chiaro.
    """
    quante: dict[str, int] = {}
    for mascheratura in mascherature:
        for regione in mascheratura.regioni:
            quante[regione.tag] = quante.get(regione.tag, 0) + 1

    aggiornata: dict[str, Tag] = {}
    for chiave, tag in tabella.items():
        if tag.stato is StatoTag.DISATTIVATO:
            aggiornata[chiave] = tag
            continue
        totale = quante.get(tag.tag, 0)
        aggiornata[chiave] = replace(
            tag,
            occorrenze=totale,
            stato=StatoTag.APPLICATO if totale else StatoTag.NON_TROVATO,
        )
    return aggiornata
