"""L'unico punto dell'applicazione che parla con la rete (spec §4).

La chiamata vera è un **parametro**, non un import nascosto nel corpo: il test
inietta una funzione che restituisce una stringa, la produzione inietta quella
che costruisce il client di `google.genai`. Non serve una libreria di mock, e
soprattutto nessun test della suite predefinita può finire in rete per
distrazione — l'invariante 5 della §4 diventa una proprietà della struttura
invece di una promessa.
"""

import json
import os
from typing import Callable

from cryptocustode.ai.prompt import MODELLO, SCHEMA_RILEVAZIONI, istruzioni
from cryptocustode.core.errors import (
    AIKeyMissing,
    AIResponseInvalid,
    AIUnavailable,
)
from cryptocustode.core.models import Category, Rilevazione

VARIABILE_CHIAVE = "CRYPTOCUSTODE_GEMINI_API_KEY"

Chiamata = Callable[[str, str, str, dict, str], str]
"""`(modello, istruzioni, testo, schema, chiave) -> JSON grezzo`.

La chiave passa come parametro e non si rilegge dall'ambiente dentro la
chiamata: `RilevatoreGemini` è già la fonte della chiave — ricevuta nel
costruttore o letta lì da `VARIABILE_CHIAVE` — e chi costruisce il
rilevatore con una chiave esplicita si aspetta che sia quella a essere usata,
non una seconda lettura indipendente dell'ambiente che potrebbe non
combaciare (o non esistere).
"""


def chiamata_reale(modello: str, sistema: str, testo: str, schema: dict, chiave: str) -> str:
    """La chiamata di produzione. Importa `google.genai` qui dentro e non in
    testa al modulo, così chi costruisce un `RilevatoreGemini` con una
    `chiama` propria — cioè ogni test — non ha bisogno che l'SDK sia
    installato."""
    from google import genai
    from google.genai import types

    cliente = genai.Client(api_key=chiave)
    risposta = cliente.models.generate_content(
        model=modello,
        contents=testo,
        config=types.GenerateContentConfig(
            system_instruction=sistema,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0,
        ),
    )
    return risposta.text


class RilevatoreGemini:
    """Il `Rilevatore` di produzione (spec §6)."""

    def __init__(
        self,
        chiave: str | None = None,
        modello: str = MODELLO,
        chiama: Chiamata | None = None,
    ) -> None:
        self._chiave = chiave if chiave is not None else os.environ.get(VARIABILE_CHIAVE)
        self._modello = modello
        self._chiama = chiama if chiama is not None else chiamata_reale

    def rileva(self, testo: str) -> list[Rilevazione]:
        """Le rilevazioni di Gemini su questo testo.

        Il controllo sulla chiave precede la chiamata: scoprire che manca dopo
        aver spedito significherebbe aver mandato il documento in rete per
        niente.

        Il messaggio di `AIUnavailable` cita solo `type(errore).__name__` e non
        `str(errore)`: il testo di un'eccezione di trasporto può contenere
        l'URL della richiesta fallita, e l'API REST di Google accetta la
        chiave anche come parametro `?key=` nell'URL — interpolare `str(errore)`
        rischierebbe di mettere la chiave nel corpo di una risposta 503, cioè
        sotto gli occhi dell'utente e nei log del browser, il che viola per
        costruzione il vincolo che la chiave non compaia mai in un messaggio
        d'errore. Il traceback completo, con l'eccezione originale, resta nel
        log del server grazie a `from errore`: lì la chiave non è comunque più
        esposta di quanto già sia.
        """
        if not self._chiave:
            raise AIKeyMissing(
                f"la variabile d'ambiente {VARIABILE_CHIAVE} non è impostata: "
                "senza chiave di Gemini l'analisi non può partire. La chiave "
                "deve appartenere a un progetto con fatturazione attiva, "
                "perché sul piano gratuito i termini di Gemini vietano l'invio "
                "di dati personali."
            )
        try:
            grezza = self._chiama(
                self._modello, istruzioni(), testo, SCHEMA_RILEVAZIONI, self._chiave
            )
        except Exception as errore:
            raise AIUnavailable(
                "il servizio di analisi non è raggiungibile, il fascicolo è "
                f"intatto: riprova. Tipo di errore: {type(errore).__name__}."
            ) from errore
        return _traduci(grezza)


def _traduci(grezza: str) -> list[Rilevazione]:
    """Dal JSON grezzo alle rilevazioni, rifiutando tutto ciò che non torna.

    Lo schema è una *richiesta* al fornitore, non una garanzia: se la risposta
    lo viola, accettarla significherebbe far entrare nel fascicolo una
    categoria che non esiste, o un valore che non è una stringa, e scoprirlo
    più tardi sotto forma di eccezione in un punto che non c'entra.
    """
    try:
        dati = json.loads(grezza)
    except (json.JSONDecodeError, TypeError) as errore:
        raise AIResponseInvalid(
            "il modello ha risposto in un formato non valido, il fascicolo è "
            f"intatto: {errore}"
        ) from errore

    if not isinstance(dati, list):
        raise AIResponseInvalid(
            "il modello doveva rispondere con una lista di rilevazioni e ha "
            f"risposto con {type(dati).__name__}, il fascicolo è intatto"
        )

    rilevazioni: list[Rilevazione] = []
    for indice, voce in enumerate(dati):
        if not isinstance(voce, dict):
            raise AIResponseInvalid(
                f"la voce {indice} della risposta non è un oggetto, il "
                "fascicolo è intatto"
            )
        valore = voce.get("valore")
        categoria = voce.get("categoria")
        if not isinstance(valore, str) or not isinstance(categoria, str):
            raise AIResponseInvalid(
                f"la voce {indice} della risposta non ha `valore` e "
                "`categoria` come stringhe, il fascicolo è intatto"
            )
        try:
            rilevazioni.append(
                Rilevazione(valore=valore, categoria=Category(categoria))
            )
        except ValueError as errore:
            raise AIResponseInvalid(
                f"la voce {indice} della risposta dichiara la categoria "
                f"{categoria!r}, che non esiste: il fascicolo è intatto"
            ) from errore
    return rilevazioni
