import pytest

from cryptocustode.core.detect.validators import (
    cf_valido,
    cin_atteso,
    iban_valido,
    piva_valida,
)


class TestCodiceFiscale:
    def test_cin_calcolato_a_mano(self):
        # dispari 78 + pari 42 = 120; 120 % 26 = 16; chr(65+16) = 'Q'
        assert cin_atteso("RSSMRA85M01H501") == "Q"

    def test_cf_con_cin_corretto(self):
        assert cf_valido("RSSMRA85M01H501Q") is True

    def test_cf_con_cin_errato_e_rifiutato(self):
        # TC-02 della consegna
        assert cf_valido("RSSMRA85M01H501Z") is False

    def test_cf_minuscolo_accettato(self):
        assert cf_valido("rssmra85m01h501q") is True

    @pytest.mark.parametrize("valore", ["", "RSSMRA85M01H501", "RSSMRA85M01H501QQ", "1234567890123456"])
    def test_lunghezza_o_forma_errata(self, valore):
        assert cf_valido(valore) is False

    def test_cin_omocodico_calcolato_a_mano(self):
        # Corpo omocodico RSSMRAURMLNH5L1: alle posizioni 7-8 ("UR"), 10-11
        # ("LN") e 13-15 ("5L1") compaiono lettere al posto delle cifre che
        # avrebbe un codice fiscale piano (nell'omocodia L=0, N=2, ...).
        #
        # Calcolo a mano da _DISPARI (posizioni dispari, 1-based) e _PARI
        # (posizioni pari), lette carattere per carattere da validators.py:
        #
        # pos  car  tabella   valore
        #  1    R   DISPARI      8
        #  2    S   PARI        18
        #  3    S   DISPARI     12
        #  4    M   PARI        12
        #  5    R   DISPARI      8
        #  6    A   PARI         0
        #  7    U   DISPARI     16
        #  8    R   PARI        17
        #  9    M   DISPARI     18
        # 10    L   PARI        11
        # 11    N   DISPARI     20
        # 12    H   PARI         7
        # 13    5   DISPARI     13
        # 14    L   PARI        11
        # 15    1   DISPARI      0
        #
        # somma posizioni dispari (1,3,5,7,9,11,13,15):
        #   8 + 12 + 8 + 16 + 18 + 20 + 13 + 0 = 95
        # somma posizioni pari (2,4,6,8,10,12,14):
        #   18 + 12 + 0 + 17 + 11 + 7 + 11 = 76
        # totale = 95 + 76 = 171; 171 % 26 = 15; chr(65 + 15) = 'P'
        #
        # Controllo di discriminazione (a mano, non testato qui): scambiando
        # _DISPARI e _PARI sulle stesse posizioni si ottiene un totale diverso
        # (167, cifra di controllo 11) e quindi un carattere diverso ('L'
        # invece di 'P'): uno scambio delle tabelle altererebbe il risultato
        # atteso da questo test, quindi lo farebbe fallire.
        assert cin_atteso("RSSMRAURMLNH5L1") == "P"
        assert cf_valido("RSSMRAURMLNH5L1P") is True
        assert cf_valido("RSSMRAURMLNH5L1Z") is False


class TestPartitaIva:
    def test_piva_valida(self):
        assert piva_valida("12345678903") is True

    def test_piva_con_cifra_di_controllo_errata(self):
        assert piva_valida("12345678900") is False

    def test_prefisso_it_accettato(self):
        assert piva_valida("IT12345678903") is True

    @pytest.mark.parametrize("valore", ["", "1234567890", "123456789012", "1234567890A"])
    def test_lunghezza_o_forma_errata(self, valore):
        assert piva_valida(valore) is False


class TestChecksumSuCodiciSpaziati:
    """Issue #37: il checksum si calcola sul valore **normalizzato** — senza
    spazi né trattini — così allargare i separatori ammessi dalle regex non
    allenta la verifica. Allargare il riconoscimento perdendo il controllo
    sarebbe lo scambio peggiore possibile, e questi test lo escludono
    provando che nelle forme nuove un codice sbagliato resta sbagliato.

    Un valore che *comincia o finisce* con un separatore, invece, non è il
    codice e viene rifiutato anche quando la sua forma normalizzata sarebbe
    valida. Non è pignoleria: il ritaglio progressivo di `rules.py` taglia
    all'ultimo separatore, quindi su una coppia di spazi produce un candidato
    con lo spazio in fondo, e la lunghezza del candidato accettato decide dove
    finisce lo span. Accettarlo farebbe coprire allo span un carattere che nel
    codice non c'è.
    """

    def test_iban_col_trattino_valido(self):
        assert iban_valido("IT60-X054-2811-1010-0000-0123-456") is True

    def test_iban_col_trattino_e_cifra_alterata_rifiutato(self):
        assert iban_valido("IT60-X054-2811-1010-0000-0123-457") is False

    def test_iban_col_doppio_spazio_valido(self):
        assert iban_valido("IT60  X054  2811 1010 0000 0123 456") is True

    def test_iban_col_doppio_spazio_e_cifra_alterata_rifiutato(self):
        assert iban_valido("IT60  X054  2811 1010 0000 0123 457") is False

    def test_cf_a_gruppi_valido(self):
        assert cf_valido("RSSMRA 85M01 H501Q") is True

    def test_cf_a_gruppi_col_cin_errato_rifiutato(self):
        assert cf_valido("RSSMRA 85M01 H501Z") is False

    def test_cf_col_trattino_valido(self):
        assert cf_valido("RSSMRA-85M01-H501Q") is True

    @pytest.mark.parametrize(
        "valore",
        [
            "IT60 X054 2811 1010 0000 0123 456 ",
            " IT60 X054 2811 1010 0000 0123 456",
            "IT60-X054-2811-1010-0000-0123-456-",
            "-IT60-X054-2811-1010-0000-0123-456",
        ],
    )
    def test_iban_coi_separatori_ai_bordi_rifiutato(self, valore):
        assert iban_valido(valore) is False

    @pytest.mark.parametrize(
        "valore",
        ["RSSMRA85M01H501Q ", " RSSMRA85M01H501Q", "RSSMRA-85M01-H501Q-"],
    )
    def test_cf_coi_separatori_ai_bordi_rifiutato(self, valore):
        assert cf_valido(valore) is False


class TestIban:
    def test_iban_italiano_valido(self):
        assert iban_valido("IT60X0542811101000000123456") is True

    def test_iban_con_cifra_alterata(self):
        assert iban_valido("IT60X0542811101000000123457") is False

    def test_spazi_ignorati(self):
        assert iban_valido("IT60 X054 2811 1010 0000 0123 456") is True

    @pytest.mark.parametrize("valore", ["", "IT60", "XX00X0542811101000000123456"])
    def test_forma_errata(self, valore):
        assert iban_valido(valore) is False
