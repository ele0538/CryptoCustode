"""I doppi condivisi dalla suite.

Vivono in un modulo e non in `conftest.py` perché sono classi importabili per
nome, non fixture: un test che ne vuole uno lo costruisce con gli argomenti che
gli servono, invece di ricevere quello che la fixture ha deciso.
"""

from cryptocustode.core.errors import AIResponseInvalid
from cryptocustode.core.models import Category, Rilevazione
from cryptocustode.core.tagga import assegna_tag


class RilevatoreFinto:
    """Un `Rilevatore` che risponde quello che il test gli ha detto.

    `rilevazioni_per_testo` risponde in base al testo ricevuto; `sempre`
    risponde la stessa cosa a chiunque. Passarli entrambi è legittimo: vince la
    voce per testo, e `sempre` fa da risposta predefinita.
    """

    def __init__(
        self,
        rilevazioni_per_testo: dict[str, list[Rilevazione]] | None = None,
        sempre: list[Rilevazione] | None = None,
    ) -> None:
        self._per_testo = rilevazioni_per_testo or {}
        self._sempre = sempre
        self.chiamate: list[str] = []

    def rileva(self, testo: str) -> list[Rilevazione]:
        self.chiamate.append(testo)
        if testo in self._per_testo:
            return list(self._per_testo[testo])
        return list(self._sempre) if self._sempre is not None else []


class RilevatoreCheFallisceSuAlcuniTesti:
    """Un `Rilevatore` che risponde normalmente ai testi che conosce e
    solleva `AIResponseInvalid` — come farebbe il client vero su una risposta
    fuori schema (spec §6) — su ogni altro testo.

    Serve a provare che un fallimento a **metà** di un'analisi con più
    documenti lascia il fascicolo intatto: `RilevatoreFinto` non fa al caso,
    perché non solleva mai. E il fallimento deve poter arrivare su un
    documento che non è il primo, altrimenti il test passerebbe anche contro
    una rotta che scrivesse il fascicolo dopo ogni documento invece che a
    fine giro.
    """

    def __init__(self, rilevazioni_per_testo: dict[str, list[Rilevazione]]) -> None:
        self._per_testo = rilevazioni_per_testo

    def rileva(self, testo: str) -> list[Rilevazione]:
        if testo not in self._per_testo:
            raise AIResponseInvalid("la risposta del modello non rispetta lo schema")
        return list(self._per_testo[testo])


def accendi(fascicolo, *categorie: Category) -> None:
    """Accende il mascheramento delle categorie indicate, o di tutte se non ne
    indichi nessuna.

    Dal 2026-09-14 un fascicolo nuovo non maschera niente (spec §2,
    emendamento alla decisione 4): si parte da zero e si accende ciò che
    serve. Prima il mascheramento era il default, quindi un test che voleva
    vedere del testo mascherato non doveva dire nulla; adesso deve dirlo, e
    questo helper glielo fa dire in una riga invece che in tre.

    Non è una scorciatoia per aggirare il default: è la traduzione, dentro un
    test, del clic che l'utente fa sull'interruttore.
    """
    for categoria in categorie or tuple(Category):
        fascicolo.category_enabled[categoria] = True


def _genera_placeholder(tabella, contatori, categoria: Category, valore: str):
    """Il rimpiazzo di `prossimo_placeholder`, cancellata con `core/entities.py`.

    `assegna_tag` è il generatore vero: qui gli si passa una `Rilevazione` di
    un valore mai visto prima, cosicché produca sempre un segnaposto nuovo per
    `categoria`, e si legge la stringa del tag dalla tabella che restituisce.
    """
    nuova, contati = assegna_tag(
        [Rilevazione(valore=valore, categoria=categoria)], tabella, contatori
    )
    generato = next(tag.tag for tag in nuova.values() if tag.valore == valore)
    return generato, nuova, contati
