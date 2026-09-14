"""I doppi condivisi dalla suite.

Vivono in un modulo e non in `conftest.py` perché sono classi importabili per
nome, non fixture: un test che ne vuole uno lo costruisce con gli argomenti che
gli servono, invece di ricevere quello che la fixture ha deciso.
"""

from cryptocustode.core.models import Rilevazione


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
