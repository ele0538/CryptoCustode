"""La configurazione viva del processo, e il registratore di cosa si è speso.

Un oggetto solo, e non due, perché le due cose sono legate da un'invariante che
separandole andrebbe sorvegliata a mano: **il costo si calcola coi prezzi che
stanno in queste impostazioni**. Un contatore che vivesse per conto suo
verrebbe letto insieme a impostazioni che nel frattempo qualcuno ha cambiato, e
il totale mostrato sarebbe la somma di token veri e prezzi di un altro momento.

Non è un singleton di modulo, per la stessa ragione per cui non lo sono
`SessionStore` e il rilevatore: due app nello stesso processo — cioè ogni test
che ne costruisce una — non devono condividere né la chiave né il conto.
"""

from dataclasses import replace
from pathlib import Path

from cryptocustode.config.impostazioni import (
    Consumo,
    Impostazioni,
    con_chiave_nuova,
    leggi,
    sbloccata,
    scrivi,
)


class Configurazione:
    """Le impostazioni correnti più quanto si è consumato.

    `sessione` è il consumo da quando l'applicazione è partita; il totale
    storico vive dentro `impostazioni.totale` e viene scritto su disco a ogni
    chiamata registrata. Sono due numeri diversi e servono a due domande
    diverse: «quanto mi è costato quello che sto facendo adesso» e «quanto ho
    speso da quando uso questo programma».
    """

    def __init__(
        self,
        impostazioni: Impostazioni | None = None,
        percorso_file: Path | None = None,
    ) -> None:
        self._percorso = percorso_file
        self.impostazioni = (
            impostazioni if impostazioni is not None else leggi(percorso_file)
        )
        self.sessione = Consumo()

    # --- lettura, per chi deve chiamare Gemini ------------------------------

    @property
    def modello(self) -> str:
        return self.impostazioni.modello

    @property
    def chiave(self) -> str | None:
        return self.impostazioni.chiave

    @property
    def pronta(self) -> bool:
        return self.impostazioni.pronta

    @property
    def piano_attestato(self) -> bool:
        return self.impostazioni.piano_attestato

    # --- scrittura ----------------------------------------------------------

    def registra(self, token_input: int, token_output: int) -> None:
        """Somma una chiamata al conto di sessione e al totale storico.

        Persiste subito invece che alla chiusura: l'applicazione si chiude
        premendo CTRL+C o la X della finestra, cioè senza passare da nessun
        punto in cui si potrebbe salvare. Un totale scritto solo all'uscita
        sarebbe un totale che si perde quasi sempre.
        """
        una = Consumo(token_input=token_input, token_output=token_output, chiamate=1)
        self.sessione = self.sessione.piu(una)
        self.impostazioni = replace(
            self.impostazioni, totale=self.impostazioni.totale.piu(una)
        )
        self._salva()

    def aggiorna(
        self,
        *,
        modello: str,
        prezzo_input: float,
        prezzo_output: float,
        valuta: str,
        piano_attestato: bool = False,
        chiave: str | None = None,
        passphrase: str | None = None,
    ) -> None:
        """Cambia modello e prezzi, e — se ne arriva una — la chiave.

        La chiave si cambia solo insieme a una passphrase: cifrarla con una
        passphrase vuota darebbe un file che sembra protetto e non lo è.
        """
        nuove = replace(
            self.impostazioni,
            modello=modello,
            prezzo_input=prezzo_input,
            prezzo_output=prezzo_output,
            valuta=valuta,
            piano_attestato=piano_attestato,
        )
        if chiave:
            if not passphrase:
                raise ValueError(
                    "per salvare la chiave serve una passphrase: "
                    "è quella che la protegge sul disco"
                )
            nuove = con_chiave_nuova(nuove, chiave, passphrase)
        self.impostazioni = nuove
        self._salva()

    def sblocca(self, passphrase: str) -> None:
        """Decifra la chiave salvata e la tiene in memoria per questa sessione."""
        self.impostazioni = sbloccata(self.impostazioni, passphrase)

    def _salva(self) -> None:
        scrivi(self.impostazioni, self._percorso)

    # --- il riassunto che la pagina mostra ----------------------------------

    def consumo(self) -> dict:
        """Sessione e totale, ciascuno coi suoi token e il suo costo."""
        prezzi = (self.impostazioni.prezzo_input, self.impostazioni.prezzo_output)
        return {
            "valuta": self.impostazioni.valuta,
            "prezzi_impostati": any(prezzo > 0 for prezzo in prezzi),
            "sessione": _riga(self.sessione, *prezzi),
            "totale": _riga(self.impostazioni.totale, *prezzi),
        }


def _riga(consumo: Consumo, prezzo_input: float, prezzo_output: float) -> dict:
    return {
        "chiamate": consumo.chiamate,
        "token_input": consumo.token_input,
        "token_output": consumo.token_output,
        "costo": consumo.costo(prezzo_input, prezzo_output),
    }
