"""Quanto di un fascicolo uscirà in chiaro dall'esportazione (issue #53).

Modulo puro: legge un fascicolo e restituisce dei numeri. Non maschera, non
impedisce e non decide — l'utente ha il diritto di esportare un documento che
non contiene niente da nascondere, e un gate che glielo negasse sarebbe un
prodotto diverso da quello deciso in `33521f7`.

Serve perché la pagina possa **dirlo prima del clic**. Il difetto della #53 non
è che la mascheratura sbagli: maschera esattamente ciò che le si dice. È che
l'utente non ha modo di sapere quanto ha lasciato scoperto finché non legge il
testo esportato, e a quel punto lo ha già negli appunti.

Il conteggio passa da `tabella_attiva` e non da una lettura propria di
`category_enabled`: chiunque debba sapere se un dato esce in chiaro deve
leggerlo da un posto solo, altrimenti la pagina mostra acceso ciò che
l'esportazione lascia spento. È lo stesso vincolo che la docstring di
`tabella_attiva` si impone.
"""

from cryptocustode.core.mask import tabella_attiva
from cryptocustode.core.models import Fascicolo


def esposizione(fascicolo: Fascicolo) -> dict:
    """Quante occorrenze usciranno in chiaro, quante mascherate, e da quali
    categorie viene l'esposizione.

    **Occorrenze e non tag.** «Tre dati in chiaro» e «un dato ripetuto tre
    volte» sono la stessa quantità di testo che esce dalla porta, e a chi
    esporta interessa quanto esce, non quante righe ha la tabella.

    I tag `NON_TROVATO` non contano da nessuna delle due parti: il modello ha
    nominato un valore che nel testo non compare alla lettera, quindi non c'è
    niente da mascherare e niente che esca. Contarli gonfierebbe l'allarme con
    dati che nel documento non ci sono, e un allarme gonfio si impara a
    ignorare. Qui basta leggere `occorrenze`, che per loro è zero.

    Le categorie escono ordinate dalla più esposta, e a parità di conteggio in
    ordine alfabetico: chi legge una riga sola deve leggere per prima la
    categoria che espone di più, e due ridisegni dello stesso fascicolo non
    devono scambiare l'ordine sotto gli occhi di chi guarda.
    """
    attivi = tabella_attiva(fascicolo)

    in_chiaro = 0
    mascherati = 0
    per_categoria: dict[str, int] = {}
    for chiave, tag in fascicolo.tags.items():
        if not tag.occorrenze:
            continue
        if chiave in attivi:
            mascherati += tag.occorrenze
            continue
        in_chiaro += tag.occorrenze
        nome = tag.categoria.value
        per_categoria[nome] = per_categoria.get(nome, 0) + tag.occorrenze

    return {
        "in_chiaro": in_chiaro,
        "mascherati": mascherati,
        "categorie": [
            {"categoria": nome, "quanti": quanti}
            for nome, quanti in sorted(
                per_categoria.items(), key=lambda voce: (-voce[1], voce[0])
            )
        ],
    }
