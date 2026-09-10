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

    def test_omocodia_non_fa_esplodere_il_calcolo(self):
        # nell'omocodia alcune cifre diventano lettere: il CIN si calcola
        # sui 15 caratteri così come compaiono
        cin = cin_atteso("RSSMRAURMLNH5L1")
        assert cin.isalpha() and len(cin) == 1


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
