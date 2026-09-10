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

    def test_iban_seguito_da_parola_maiuscola_riconosciuto(self):
        # la coda vorace ingloba " PRESSO": il ritaglio guidato dal checksum
        # deve restituire il solo IBAN, non scartare tutto il match
        testo = "IBAN IT60X0542811101000000123456 PRESSO BANCA ESEMPIO"
        assert valori(testo, Category.IBAN) == ["IT60X0542811101000000123456"]

    def test_iban_a_gruppi_di_quattro_riconosciuto(self):
        testo = "IBAN IT60 X054 2811 1010 0000 0123 456 come da mandato"
        assert valori(testo, Category.IBAN) == ["IT60 X054 2811 1010 0000 0123 456"]

    def test_iban_a_gruppi_seguito_da_parola_maiuscola_riconosciuto(self):
        testo = "IBAN IT60 X054 2811 1010 0000 0123 456 PRESSO BANCA"
        assert valori(testo, Category.IBAN) == ["IT60 X054 2811 1010 0000 0123 456"]


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

    def test_piva_con_parola_chiave_abbreviata_riconosciuta(self):
        assert valori("Fornitore con p.i. 12345678903 registrato", Category.PIVA) == [
            "12345678903"
        ]

    def test_numero_con_prefisso_0039_riconosciuto(self):
        assert valori("Chiamare 0039 340 1234567 subito", Category.TELEFONO) == [
            "0039 340 1234567"
        ]

    def test_0039_senza_numero_nazionale_non_e_un_prefisso(self):
        # undici cifre nude che iniziano per 0039 non si certificano da sole
        assert Category.TELEFONO not in categorie("Ordine 00391234567 spedito")


class TestLunghezzaTelefono:
    """Spec §6: lunghezza complessiva 9-11 cifre."""

    def test_telefono_troppo_corto_ignorato(self):
        assert Category.TELEFONO not in categorie("Tel. 01123456")

    def test_telefono_troppo_lungo_ignorato(self):
        assert Category.TELEFONO not in categorie("Tel. 012312345678")

    def test_fisso_di_lunghezza_valida_riconosciuto(self):
        assert valori("Tel. 011 1234567 interno 4", Category.TELEFONO) == ["011 1234567"]


class TestMaiuscoleObbligatorie:
    """`re.IGNORECASE` serve ai testi tutti in maiuscolo, ma le iniziali della
    sequenza di nomi devono restare maiuscole davvero."""

    def test_indirizzo_tutto_maiuscolo_riconosciuto(self):
        assert valori("Residente in VIA GARIBALDI 42 Torino", Category.INDIRIZZO) == [
            "VIA GARIBALDI 42"
        ]

    def test_via_email_non_e_un_indirizzo(self):
        assert Category.INDIRIZZO not in categorie("Contattato via email dal cliente")

    def test_azienda_con_suffisso_societario(self):
        # il \b finale esclude il punto di chiusura della sigla
        testo = "Fattura emessa da Alfa Costruzioni S.r.l. per il servizio"
        assert valori(testo, Category.AZIENDA) == ["Alfa Costruzioni S.r.l"]

    def test_parola_comune_spa_non_e_un_azienda(self):
        assert Category.AZIENDA not in categorie("Il nuovo centro benessere spa apre domani")


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

    def test_importo_non_aggancia_la_coda_di_un_numero_piu_lungo(self):
        # spec §6: o l'importo è preso per intero o non è preso, mai a metà
        trovati = valori("Totale 12345 EUR da versare", Category.IMPORTO)
        assert trovati in ([], ["12345 EUR"])

    def test_dati_catastali_con_foglio_abbreviato(self):
        trovati = valori("Immobile al fg 12 mappale 345", Category.CATASTO)
        assert trovati == ["fg 12 mappale 345"]

    def test_indirizzo_con_cap_e_comune(self):
        testo = "Residente in Via Giuseppe Garibaldi 42, 10121 Torino."
        assert valori(testo, Category.INDIRIZZO) == ["Via Giuseppe Garibaldi 42, 10121 Torino"]

    def test_numero_pratica_senza_punto_finale(self):
        assert valori("Pratica 2024/ABC-77.", Category.PRATICA) == ["Pratica 2024/ABC-77"]


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
