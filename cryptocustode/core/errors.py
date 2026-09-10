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
