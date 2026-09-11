import inspect

import pytest

from cryptocustode.core import errors
from cryptocustode.core.errors import CryptoCustodeError
from cryptocustode.core.ingest import config

# I nomi sono quelli della tabella della spec §13, in inglese come i tipi di dominio.
NOMI_ATTESI = {
    "InvalidEncoding",
    "ScannedDocumentRejected",
    "FascicoloFull",
    "DuplicateFilename",
    "ExportNotAllowed",
    "IntegrityError",
    "UnresolvedAmbiguities",
    "UnknownPlaceholder",
    "MalformedPlaceholder",
    "VaultUnreadable",
    "VaultVersionNotSupported",
}


def test_esistono_tutti_gli_errori_della_spec():
    definiti = {
        nome
        for nome, oggetto in inspect.getmembers(errors, inspect.isclass)
        if issubclass(oggetto, CryptoCustodeError) and oggetto is not CryptoCustodeError
    }
    assert definiti == NOMI_ATTESI


@pytest.mark.parametrize("nome", sorted(NOMI_ATTESI))
def test_ogni_errore_deriva_dalla_base(nome):
    assert issubclass(getattr(errors, nome), CryptoCustodeError)


def test_la_base_deriva_da_exception():
    assert issubclass(CryptoCustodeError, Exception)


def test_un_errore_conserva_il_messaggio():
    errore = errors.FascicoloFull("massimo 10 documenti per fascicolo")
    assert str(errore) == "massimo 10 documenti per fascicolo"


def test_soglie_del_verdetto_di_scansione():
    # Valori della tabella della spec §12. Vivono in un modulo di configurazione
    # perché siano ritoccabili senza toccare la logica.
    assert config.CARATTERI_MINIMI_PAGINA == 40
    assert config.FRAZIONE_IMMAGINE_MASSIMA == 0.5
