"""Suggerire e applicare la fusione di due tag che forse sono la stessa cosa.

Modulo puro: riceve una tabella di tag e ne restituisce un'altra, non tocca il
fascicolo e non fa I/O. Chi chiama decide quando scrivere il risultato, e un
rifiuto non lascia mai una tabella a metà.

Principio guida (spec §7), che qui decide ogni riga: fondere per errore
corrompe i dati e rivela il nome di una persona al posto di un'altra; separare
per errore degrada soltanto la qualità della risposta dell'IA. Quindi separare
è il default, `suggerisci` non fonde niente, e solo una decisione dell'utente
può chiamare `fondi`.

**Cosa non c'è qui, e perché.** La coda bloccante di
`feat/p6-disambiguazione` — due persone diverse che si chiamano entrambe
«Mario Rossi» — non è stata portata: non è una scelta di implementazione da
rivedere, è che sul contratto attuale quei due omonimi sono **indistinguibili
per costruzione**, perché il modello restituisce valori e non posizioni e
`assegna_tag` deduplica per valore esatto. Riaprirla vuol dire cambiare il
contratto con il modello, non ritoccare questo file. Il limite è dichiarato
nella spec §16 e nella docstring di `analisi_completata`.
"""

from dataclasses import replace

from cryptocustode.core.models import Category, FusioneSuggerita, Tag
from cryptocustode.core.nomi import chiavi_equivalenti
from cryptocustode.core.placeholders import indice_di

CATEGORIE_CON_VARIANTI = {Category.PERSONA, Category.AZIENDA}
"""Le categorie per cui ha senso confrontare varianti di una scrittura.

Su un IBAN, un codice fiscale o un importo l'uguaglianza è esatta o non è: due
scritture diverse sono due dati diversi, e un'euristica sui token non ha alcun
titolo per accostarli.
"""


def _identificativo(tag_a: str, tag_b: str) -> str:
    return f"{tag_a}+{tag_b}"


def _in_ordine_di_anzianita(uno: Tag, altro: Tag) -> tuple[Tag, Tag]:
    """Il tag con l'indice più basso per primo: è quello che sopravvive.

    L'anzianità si legge dall'indice del segnaposto e non dall'ordine nella
    tabella, che una riapertura da vault o un ricalcolo potrebbero rimescolare.
    """
    return (uno, altro) if indice_di(uno.tag) <= indice_di(altro.tag) else (altro, uno)


def suggerisci(
    tabella: dict[str, Tag], gia_viste: list[FusioneSuggerita]
) -> list[FusioneSuggerita]:
    """Le coppie di tag che l'euristica sui nomi giudica equivalenti, meno
    quelle già in coda.

    Non fonde e non decide: restituisce proposte nuove, che chi chiama accoda.
    Una coppia già vista non si ripropone — risolta o no — perché l'analisi è
    rieseguibile e ogni clic su «Analizza» riaprirebbe altrimenti quello che
    l'utente ha già guardato.

    Il confronto è sui valori canonici: le varianti di un tag condividono con
    esso la forma normalizzata, altrimenti non sarebbero finite lì sotto.
    """
    aperte = {vista.fusione_id for vista in gia_viste}
    confrontabili = sorted(
        (tag for tag in tabella.values() if tag.categoria in CATEGORIE_CON_VARIANTI),
        key=lambda tag: (tag.categoria.value, indice_di(tag.tag)),
    )

    proposte: list[FusioneSuggerita] = []
    for posizione, primo in enumerate(confrontabili):
        for secondo in confrontabili[posizione + 1 :]:
            # Una persona e un'azienda con lo stesso nome restano due cose
            # diverse, e fonderle darebbe a una il segnaposto dell'altra.
            if primo.categoria is not secondo.categoria:
                continue
            if not chiavi_equivalenti(primo.valore, secondo.valore):
                continue
            vecchio, nuovo = _in_ordine_di_anzianita(primo, secondo)
            identificativo = _identificativo(vecchio.tag, nuovo.tag)
            if identificativo in aperte:
                continue
            aperte.add(identificativo)
            proposte.append(
                FusioneSuggerita(
                    fusione_id=identificativo,
                    categoria=primo.categoria,
                    tag_a=vecchio.tag,
                    tag_b=nuovo.tag,
                )
            )
    return proposte


def fondi(tabella: dict[str, Tag], tag_a: str, tag_b: str) -> dict[str, Tag]:
    """Unisce due tag sotto il più vecchio dei due, e restituisce una tabella nuova.

    **Quale segnaposto sopravvive non è indifferente.** Sopravvive quello con
    l'indice più basso, e l'altro resta bruciato: è il caso descritto dalla
    spec §5. Far sopravvivere il più recente cambierebbe il segnaposto di un
    dato che potrebbe essere già stato consegnato a un'IA esterna, e il testo
    che l'utente ha in mano parlerebbe di qualcun altro.

    I contatori non si toccano e non si riciclano: l'indice assorbito non torna
    più disponibile, per la stessa ragione.

    Le varianti si sommano, e fra loro entra anche il valore canonico del tag
    assorbito: un documento caricato dopo, che usi quella forma, finisce così
    sotto lo stesso segnaposto invece di aprire un terzo tag.

    I tre controlli stanno prima della prima scrittura: una fusione impossibile
    non lascia metà tabella riscritta.
    """
    if tag_a == tag_b:
        raise ValueError(
            f"una fusione richiede due tag distinti: {tag_a!r} non unisce niente"
        )
    mancanti = [chiave for chiave in (tag_a, tag_b) if chiave not in tabella]
    if mancanti:
        elenco = ", ".join(repr(chiave) for chiave in mancanti)
        raise ValueError(f"tag assenti dalla tabella, fusione impossibile: {elenco}")

    primo, secondo = tabella[tag_a], tabella[tag_b]
    if primo.categoria is not secondo.categoria:
        nomi = ", ".join(sorted({primo.categoria.value, secondo.categoria.value}))
        raise ValueError(
            f"i tag da fondere hanno categorie diverse ({nomi}): una persona e "
            "un'azienda con lo stesso nome restano due cose diverse, e fonderle "
            "darebbe a una il segnaposto dell'altra"
        )

    vecchio, assorbito = _in_ordine_di_anzianita(primo, secondo)
    # `dict.fromkeys` invece di un insieme: tiene l'ordine, e l'ordine finisce
    # nel vault e nei confronti dei test.
    varianti = tuple(
        dict.fromkeys(
            (*vecchio.varianti, assorbito.valore, *assorbito.varianti)
        )
    )

    fusa = dict(tabella)
    del fusa[assorbito.tag]
    fusa[vecchio.tag] = replace(vecchio, varianti=varianti)
    return fusa
