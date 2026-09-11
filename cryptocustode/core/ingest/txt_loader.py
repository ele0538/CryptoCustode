"""Decodifica dei TXT: UTF-8 strict e nient'altro (spec §12)."""

from cryptocustode.core.errors import InvalidEncoding


def carica_txt(contenuto: bytes) -> str:
    """Decodifica `contenuto` come UTF-8 strict.

    Nessun fallback ad altre codifiche: una decodifica errata altera i caratteri,
    i checksum di CF e IBAN smettono di tornare, e i dati sensibili passerebbero
    inosservati in silenzio (spec §12).
    """
    try:
        return contenuto.decode("utf-8")
    except UnicodeDecodeError as errore:
        raise InvalidEncoding(
            f"codifica non valida: il byte all'offset {errore.start} "
            "non fa parte di una sequenza UTF-8 valida"
        ) from errore
