"""Gli errori di dominio della spec §13.

I nomi restano in inglese come i tipi di dominio; i messaggi che li accompagnano
sono in italiano perché arrivano all'utente.
"""


class CryptoCustodeError(Exception):
    """Base di tutti gli errori di dominio, così un chiamante può catturarli
    tutti insieme senza elencarli."""


class InvalidEncoding(CryptoCustodeError):
    """TXT che non è UTF-8 valido."""


class ScannedDocumentRejected(CryptoCustodeError):
    """PDF con almeno una pagina che è una scansione."""


class FascicoloFull(CryptoCustodeError):
    """Undicesimo documento in un fascicolo."""


class DuplicateFilename(CryptoCustodeError):
    """Secondo documento con un nome file già presente nel fascicolo.

    Non è un capriccio: il payload dell'export è indicizzato per nome file
    (spec §8), quindi due omonimi collasserebbero in una sola chiave e l'utente
    riceverebbe un documento in meno senza alcun errore (issue #19). Il rifiuto
    all'ingresso è ciò che rende quel payload onesto.
    """


class FascicoloNotFound(CryptoCustodeError):
    """Fascicolo chiesto allo store con un id che non vi corrisponde.

    Esiste perché lo store non lasci uscire il `KeyError` del dizionario che lo
    indicizza: quel KeyError non è un `CryptoCustodeError`, esce dal primo dei
    tre controlli della §8 e attraversa il gate dell'export senza che nessuno
    lo riconosca; il layer HTTP lo tradurrebbe in un 500 al posto del 404 della
    §13 (issue #16).
    """


class ExportNotAllowed(CryptoCustodeError):
    """Esportazione richiesta con il fascicolo in uno stato diverso da APPROVED."""


class IntegrityError(CryptoCustodeError):
    """Il testo mascherato è cambiato dopo l'approvazione."""


class UnresolvedAmbiguities(CryptoCustodeError):
    """Approvazione richiesta con ambiguità bloccanti ancora aperte."""


class UnknownPlaceholder(CryptoCustodeError):
    """Segnaposto ben formato ma estraneo al dizionario del fascicolo."""


class MalformedPlaceholder(CryptoCustodeError):
    """Frammento che somiglia a un segnaposto senza esserlo."""


class VaultUnreadable(CryptoCustodeError):
    """Password errata o file danneggiato: i due casi non si distinguono."""


class VaultVersionNotSupported(VaultUnreadable):
    """Vault scritto da una versione più recente dell'applicazione.

    Sottoclasse e non fratello di `VaultUnreadable`: un vault che non si sa
    leggere *è* illeggibile, quindi chi cattura il genitore continua a
    funzionare, e chi vuole distinguere il caso può prenderlo per nome.

    È l'unico fallimento del vault con un messaggio proprio, e non contraddice
    la regola della §13 sul messaggio indistinguibile: il numero di versione
    vive dentro il payload cifrato, quindi per arrivare a leggerlo servono già
    la password giusta e il file integro. Dirlo a quel punto non rivela nulla a
    chi è ancora fuori (issue #17).
    """


class UploadTooLarge(CryptoCustodeError):
    """Caricamento più grande del tetto, rifiutato prima di leggerlo.

    È l'unico errore della §13 che nasce fuori dal core, e non per comodità:
    quando la route riceve il suo `UploadFile` i byte del file sono già stati
    scritti nella cartella temporanea, perché starlette controlla
    `max_part_size` solo per le parti che non sono file. Un rifiuto emesso lì
    arriverebbe a danno già fatto, quindi il controllo precede il parser e vive
    nel layer HTTP — ma l'errore resta di dominio, così passa dal gate della
    §13 come tutti gli altri e l'utente riceve un messaggio in italiano invece
    di un 500.
    """
