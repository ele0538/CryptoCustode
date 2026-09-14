"""Le impostazioni dell'utente e il conto di quanto costa Gemini.

Vive fuori da `core/`: legge e scrive su disco, e `core/` deve restare puro
(spec §4, invariante 1). `api/` può importarlo, il verso opposto no.

**La chiave API non sta mai in chiaro su disco.** È cifrata con AES-256-GCM e
una chiave derivata con PBKDF2 dalla passphrase dell'utente, cioè lo stesso
schema del vault. Le primitive sono ripetute qui invece di essere importate da
`core/vault.py` per una ragione sola: lì l'unità cifrata è un `Fascicolo`
intero, e piegare quella funzione a cifrare anche una stringa avrebbe legato il
formato del vault al formato della configurazione — due file che cambiano per
ragioni diverse e che nessuno vuole dover far evolvere insieme.

Il resto della configurazione — modello e prezzi — **non** è cifrato, ed è
deliberato: non è un segreto, e tenerlo leggibile permette di correggere a mano
un prezzo sbagliato senza passare dall'applicazione.
"""

import base64
import json
import os
from dataclasses import dataclass, replace
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

MODELLO_PREDEFINITO = "gemini-3.8-flash"
"""Il modello proposto al primo avvio, non un valore imposto.

Era una costante in `ai/prompt.py` e ora è solo il default di un campo: il
senso della configurazione è poter mettere un modello più economico o più
capace senza toccare il codice.
"""

ITERAZIONI_KDF = 600_000
_LUNGHEZZA_SALT = 16
_LUNGHEZZA_NONCE = 12
_LUNGHEZZA_CHIAVE = 32
_MAGIC = b"CCK1"
_FINE_INTESTAZIONE_AUTENTICATA = 24
_FINE_INTESTAZIONE = _FINE_INTESTAZIONE_AUTENTICATA + _LUNGHEZZA_NONCE

MESSAGGIO_ILLEGGIBILE = "passphrase errata, o configurazione danneggiata"
"""Un messaggio solo per i due casi, come nel vault: distinguerli direbbe a chi
ci prova che la passphrase è l'unico ostacolo rimasto."""


class ConfigurazioneIlleggibile(Exception):
    """La passphrase non apre la chiave, o il file è rovinato."""


@dataclass(frozen=True)
class Consumo:
    """Token spesi e quanto sono costati.

    I token si sommano, il costo si **ricalcola** dai prezzi correnti invece di
    essere accumulato: un costo accumulato congelerebbe per sempre il prezzo in
    vigore al momento della chiamata, e al primo cambio di listino il totale
    storico diventerebbe un numero che non corrisponde a niente — né al vecchio
    prezzo né al nuovo. Coi token grezzi il conto si può sempre rifare.
    """

    token_input: int = 0
    token_output: int = 0
    chiamate: int = 0

    def piu(self, altro: "Consumo") -> "Consumo":
        return Consumo(
            token_input=self.token_input + altro.token_input,
            token_output=self.token_output + altro.token_output,
            chiamate=self.chiamate + altro.chiamate,
        )

    def costo(self, prezzo_input: float, prezzo_output: float) -> float:
        """Il costo, coi prezzi espressi **per milione di token**.

        Per milione e non per token perché è così che i listini dei fornitori
        sono scritti: chiedere all'utente di dividere per un milione prima di
        incollare un numero è il genere di conversione in cui si sbaglia di tre
        ordini di grandezza senza accorgersene.
        """
        return (
            self.token_input * prezzo_input + self.token_output * prezzo_output
        ) / 1_000_000


@dataclass(frozen=True)
class Impostazioni:
    """Cosa l'utente ha scelto. La chiave in chiaro non viene mai serializzata."""

    modello: str = MODELLO_PREDEFINITO
    prezzo_input: float = 0.0
    prezzo_output: float = 0.0
    valuta: str = "USD"
    piano_attestato: bool = False
    """L'utente dichiara che la chiave e' di un progetto con fatturazione attiva.

    Sta qui e non solo nell'ambiente perche' e' una dichiarazione dell'utente,
    e l'utente ora parla con la pagina. Resta una dichiarazione e non una
    verifica: l'API non espone il piano di fatturazione, quindi l'applicazione
    non ha modo di controllarlo. Serve comunque — obbliga a leggere perche' il
    piano gratuito non va bene — e ora e' il **rilevatore** a pretenderla,
    cioe' il punto immediatamente prima che un documento parta davvero.
    """
    chiave: str | None = None
    """La chiave API in chiaro, **solo in memoria**: su disco va il blob cifrato."""
    chiave_cifrata: bytes | None = None
    totale: Consumo = Consumo()

    @property
    def pronta(self) -> bool:
        """Se c'è una chiave utilizzabile **adesso**.

        Non «se ne esiste una su disco»: una chiave cifrata che nessuno ha
        ancora sbloccato non fa partire nessuna analisi, e confondere i due
        casi farebbe promettere alla pagina un'analisi che fallirebbe.
        """
        return bool(self.chiave)


def cartella() -> Path:
    """Dove vive la configurazione: nel profilo dell'utente, non nel repo.

    Nel repo sarebbe condivisa da chiunque cloni il progetto, ed è esattamente
    ciò che non deve succedere a una chiave API: il programma è destinato a
    essere distribuito, quindi ognuno deve avere la propria.
    """
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "CryptoCustode"
    return Path.home() / ".config" / "cryptocustode"


def percorso() -> Path:
    return cartella() / "config.json"


def _deriva_chiave(passphrase: str, salt: bytes, iterazioni: int) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=_LUNGHEZZA_CHIAVE,
        salt=salt,
        iterations=iterazioni,
    )
    return kdf.derive(passphrase.encode("utf-8"))


def cifra_segreto(segreto: str, passphrase: str) -> bytes:
    """Cifra una stringa. Salt e nonce nuovi a ogni chiamata, quindi due
    cifrature dello stesso segreto danno blob diversi: è voluto."""
    salt = os.urandom(_LUNGHEZZA_SALT)
    nonce = os.urandom(_LUNGHEZZA_NONCE)
    intestazione = _MAGIC + ITERAZIONI_KDF.to_bytes(4, "big") + salt
    chiave = _deriva_chiave(passphrase, salt, ITERAZIONI_KDF)
    cifrato = AESGCM(chiave).encrypt(nonce, segreto.encode("utf-8"), intestazione)
    return intestazione + nonce + cifrato


def decifra_segreto(blob: bytes, passphrase: str) -> str:
    if len(blob) <= _FINE_INTESTAZIONE or blob[:4] != _MAGIC:
        raise ConfigurazioneIlleggibile(MESSAGGIO_ILLEGGIBILE)
    intestazione = blob[:_FINE_INTESTAZIONE_AUTENTICATA]
    iterazioni = int.from_bytes(blob[4:8], "big")
    salt = blob[8:_FINE_INTESTAZIONE_AUTENTICATA]
    nonce = blob[_FINE_INTESTAZIONE_AUTENTICATA:_FINE_INTESTAZIONE]
    cifrato = blob[_FINE_INTESTAZIONE:]
    try:
        chiave = _deriva_chiave(passphrase, salt, iterazioni)
        return AESGCM(chiave).decrypt(nonce, cifrato, intestazione).decode("utf-8")
    except (InvalidTag, ValueError, UnicodeDecodeError) as errore:
        raise ConfigurazioneIlleggibile(MESSAGGIO_ILLEGGIBILE) from errore


def leggi(percorso_file: Path | None = None) -> Impostazioni:
    """Le impostazioni su disco, **con la chiave ancora cifrata**.

    Un file assente non è un errore: è il primo avvio, e la risposta giusta
    sono le impostazioni predefinite. Un file rovinato invece lo è, e non viene
    silenziosamente sostituito dai default: sovrascriverlo butterebbe via il
    totale storico e la chiave cifrata di chi magari ha solo copiato male il
    file.
    """
    file = percorso_file or percorso()
    if not file.exists():
        return Impostazioni()
    try:
        dati = json.loads(file.read_text(encoding="utf-8"))
        cifrata = dati.get("chiave_cifrata")
        totale = dati.get("totale", {})
        return Impostazioni(
            modello=dati.get("modello", MODELLO_PREDEFINITO),
            prezzo_input=float(dati.get("prezzo_input", 0.0)),
            prezzo_output=float(dati.get("prezzo_output", 0.0)),
            valuta=dati.get("valuta", "USD"),
            piano_attestato=bool(dati.get("piano_attestato", False)),
            chiave_cifrata=base64.b64decode(cifrata) if cifrata else None,
            totale=Consumo(
                token_input=int(totale.get("token_input", 0)),
                token_output=int(totale.get("token_output", 0)),
                chiamate=int(totale.get("chiamate", 0)),
            ),
        )
    except (json.JSONDecodeError, ValueError, TypeError, AttributeError) as errore:
        raise ConfigurazioneIlleggibile(
            f"il file di configurazione {file} non si legge: {errore}"
        ) from errore


def scrivi(impostazioni: Impostazioni, percorso_file: Path | None = None) -> None:
    """Salva su disco. La chiave in chiaro resta in memoria e non viene scritta.

    Scrive su un file d'appoggio e poi rinomina: un'interruzione a metà
    scrittura lascerebbe altrimenti un JSON troncato, cioè — per `leggi` — una
    configurazione illeggibile con dentro il totale storico e la chiave.
    """
    file = percorso_file or percorso()
    file.parent.mkdir(parents=True, exist_ok=True)
    dati = {
        "modello": impostazioni.modello,
        "prezzo_input": impostazioni.prezzo_input,
        "prezzo_output": impostazioni.prezzo_output,
        "valuta": impostazioni.valuta,
        "piano_attestato": impostazioni.piano_attestato,
        "totale": {
            "token_input": impostazioni.totale.token_input,
            "token_output": impostazioni.totale.token_output,
            "chiamate": impostazioni.totale.chiamate,
        },
    }
    if impostazioni.chiave_cifrata is not None:
        dati["chiave_cifrata"] = base64.b64encode(impostazioni.chiave_cifrata).decode()
    appoggio = file.with_name(file.name + ".parziale")
    appoggio.write_text(json.dumps(dati, ensure_ascii=False, indent=2), encoding="utf-8")
    appoggio.replace(file)


def con_chiave_nuova(
    impostazioni: Impostazioni, chiave: str, passphrase: str
) -> Impostazioni:
    """Le stesse impostazioni con una chiave nuova, cifrata e pronta in memoria."""
    return replace(
        impostazioni, chiave=chiave, chiave_cifrata=cifra_segreto(chiave, passphrase)
    )


def sbloccata(impostazioni: Impostazioni, passphrase: str) -> Impostazioni:
    """Le stesse impostazioni con la chiave decifrata in memoria."""
    if impostazioni.chiave_cifrata is None:
        raise ConfigurazioneIlleggibile(
            "non c'è nessuna chiave salvata da sbloccare: inseriscine una"
        )
    return replace(
        impostazioni, chiave=decifra_segreto(impostazioni.chiave_cifrata, passphrase)
    )
