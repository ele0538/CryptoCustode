import pytest

from cryptocustode.core.detect.rules import trova_per_regole
from cryptocustode.core.models import Category, Source


def categorie(testo: str) -> set[Category]:
    return {s.category for s in trova_per_regole(testo, "d1")}


def valori(testo: str, categoria: Category) -> list[str]:
    return [testo[s.start:s.end] for s in trova_per_regole(testo, "d1") if s.category is categoria]


class TestChecksum:
    def test_cf_valido_riconosciuto(self):
        assert valori("Codice fiscale RSSMRA85M01H501Q.", Category.CF) == ["RSSMRA85M01H501Q"]

    def test_cf_con_cin_errato_ignorato(self):
        # TC-02: la regola non lo prende, resterà eventualmente al NER
        assert Category.CF not in categorie("Codice fiscale RSSMRA85M01H501Z.")

    def test_iban_valido_riconosciuto(self):
        testo = "Bonifico su IT60X0542811101000000123456 entro il termine."
        assert valori(testo, Category.IBAN) == ["IT60X0542811101000000123456"]

    def test_iban_con_cifra_alterata_ignorato(self):
        assert Category.IBAN not in categorie("Bonifico su IT60X0542811101000000123457.")


class TestRequisitoDiContesto:
    def test_piva_con_parola_chiave_riconosciuta(self):
        assert valori("P. IVA 12345678903", Category.PIVA) == ["12345678903"]

    def test_piva_con_prefisso_it_riconosciuta(self):
        assert valori("Fattura a IT12345678903", Category.PIVA) == ["IT12345678903"]

    def test_undici_cifre_nude_non_diventano_piva(self):
        # senza contesto ogni numero lungo diventerebbe un dato personale
        assert Category.PIVA not in categorie("Il totale delle unità è 12345678903 pezzi.")

    def test_cellulare_con_parola_chiave_riconosciuto(self):
        assert valori("Cell. 3401234567", Category.TELEFONO) == ["3401234567"]

    def test_numero_con_prefisso_internazionale_riconosciuto(self):
        assert valori("Chiamare +39 340 1234567", Category.TELEFONO) == ["+39 340 1234567"]

    def test_numero_nudo_senza_contesto_ignorato(self):
        assert Category.TELEFONO not in categorie("La particella misura 3401234567 centimetri.")


class TestAltreCategorie:
    def test_email(self):
        assert valori("Scrivere a mario.rossi@esempio.it subito.", Category.EMAIL) == [
            "mario.rossi@esempio.it"
        ]

    def test_data_numerica(self):
        assert valori("Firmato il 14/03/2024 a Torino.", Category.DATA) == ["14/03/2024"]

    def test_data_testuale_italiana(self):
        assert valori("Firmato il 14 marzo 2024 a Torino.", Category.DATA) == ["14 marzo 2024"]

    def test_data_inesistente_ignorata(self):
        assert Category.DATA not in categorie("Il numero 31/02/2024 non è una data.")

    def test_importo_con_simbolo(self):
        assert valori("Canone di € 1.250,00 mensili.", Category.IMPORTO) == ["€ 1.250,00"]

    def test_importo_con_valuta_dopo(self):
        assert valori("Canone di 1.250,00 EUR mensili.", Category.IMPORTO) == ["1.250,00 EUR"]

    def test_dati_catastali(self):
        trovati = valori("Immobile al foglio 12 particella 345 sub 2.", Category.CATASTO)
        assert len(trovati) == 1
        assert "foglio 12" in trovati[0] and "345" in trovati[0]

    def test_numero_pratica(self):
        trovati = valori("Pratica n. 2024/ABC-77 in corso.", Category.PRATICA)
        assert len(trovati) == 1
        assert "2024/ABC-77" in trovati[0]

    def test_indirizzo_con_civico(self):
        trovati = valori("Residente in Via Giuseppe Garibaldi 42, Torino.", Category.INDIRIZZO)
        assert len(trovati) == 1
        assert trovati[0].startswith("Via Giuseppe Garibaldi")

    def test_cap_da_solo_non_e_un_indirizzo(self):
        assert Category.INDIRIZZO not in categorie("Il codice 10121 non basta.")


class TestFormaDegliSpan:
    def test_gli_span_sono_prodotti_dalle_regole(self):
        for span in trova_per_regole("P. IVA 12345678903", "d1"):
            assert span.source is Source.RULE
            assert span.doc_id == "d1"
            assert span.entity_id == ""

    def test_span_id_deterministico(self):
        testo = "Codice fiscale RSSMRA85M01H501Q."
        primi = [s.span_id for s in trova_per_regole(testo, "d1")]
        secondi = [s.span_id for s in trova_per_regole(testo, "d1")]
        assert primi == secondi

    def test_gli_offset_puntano_al_testo_giusto(self):
        testo = "Codice fiscale RSSMRA85M01H501Q."
        span = trova_per_regole(testo, "d1")[0]
        assert testo[span.start:span.end] == "RSSMRA85M01H501Q"
