"""Il confine fra il dominio e il modello linguistico (spec §4, invariante 1).

Qui vive la sola cosa che `core/` deve sapere del rilevamento: che esiste
qualcuno capace di guardare un testo e dire quali dati sensibili contiene.
Chi sia — Gemini, un doppio di test, un domani un modello locale — non entra in
`core/`, e il test di architettura lo fa rispettare vietando sotto `core/` gli
import di `httpx`, `requests` e `google`.

`runtime_checkable` esiste perché i test possano affermare la conformità di un
doppio con un `isinstance`: senza, la conformità sarebbe un'opinione, e un
cambio di firma la romperebbe in silenzio ovunque il doppio è usato.
"""

from typing import Protocol, runtime_checkable

from cryptocustode.core.models import Rilevazione


@runtime_checkable
class Rilevatore(Protocol):
    """Guarda un testo, dice quali dati sensibili contiene."""

    def rileva(self, testo: str) -> list[Rilevazione]:
        """Le rilevazioni trovate nel testo.

        Ogni `valore` deve essere una sottostringa letterale di `testo`.
        Un'implementazione che non riesce a garantirlo non è in errore: i
        valori che non si trovano diventano tag `NON_TROVATO` (spec §7).

        Solleva `AIUnavailable` se il servizio non risponde e
        `AIResponseInvalid` se risponde male: in entrambi i casi il fascicolo
        del chiamante deve restare intatto.
        """
        ...
