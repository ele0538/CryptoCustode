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


class TestConnettiviNelNome:
    """Ruling 14: dentro un odonimo o una ragione sociale i connettivi minuscoli
    ("dei", "del", "della", "di") sono ammessi, ma almeno una parola con
    l'iniziale maiuscola resta obbligatoria."""

    def test_indirizzo_con_articolo_prima_del_nome(self):
        testo = "Residente in Via dei Mille 5, 10121 Torino."
        assert valori(testo, Category.INDIRIZZO) == ["Via dei Mille 5, 10121 Torino"]

    def test_indirizzo_con_preposizione_articolata_maschile(self):
        testo = "Residente in Piazza del Popolo 12 Roma"
        assert valori(testo, Category.INDIRIZZO) == ["Piazza del Popolo 12"]

    def test_indirizzo_con_preposizione_articolata_femminile(self):
        testo = "Residente in Corso della Repubblica 3"
        assert valori(testo, Category.INDIRIZZO) == ["Corso della Repubblica 3"]

    def test_indirizzo_tutto_maiuscolo_con_connettivo_riconosciuto(self):
        # `re.IGNORECASE` vale anche sui connettivi: "DEI" resta ammesso
        assert valori("Residente in VIA DEI MILLE 5", Category.INDIRIZZO) == ["VIA DEI MILLE 5"]

    def test_azienda_con_connettivo_conserva_la_prima_parola(self):
        # la troncatura da correggere restituiva "Roma S.p.A", lasciando in
        # chiaro il resto della ragione sociale
        testo = "Fattura da Banca di Fontechiara S.p.A. per il servizio"
        trovati = valori(testo, Category.AZIENDA)
        assert len(trovati) == 1
        assert trovati[0].endswith("Banca di Fontechiara S.p.A")

    def test_via_email_non_produce_alcuno_span(self):
        # i connettivi non bastano da soli: senza una parola maiuscola nella
        # sequenza non c'è nessun indirizzo, di nessuna categoria
        assert trova_per_regole("Contattato via email dal cliente", "d1") == []

    def test_centro_benessere_spa_non_produce_alcuno_span(self):
        assert trova_per_regole("Il nuovo centro benessere spa apre domani", "d1") == []


class TestCivicoECap:
    """Spec §6: civico *e* CAP sono entrambi facoltativi. Senza civico le cinque
    cifre del CAP devono restare intere dentro lo span."""

    def test_cap_senza_civico_resta_intero(self):
        testo = "Residente in Via Roma 10121 Torino"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 10121 Torino"]

    def test_cap_senza_civico_dopo_la_virgola_resta_intero(self):
        testo = "Residente in Via Giuseppe Garibaldi, 10121 Torino."
        assert valori(testo, Category.INDIRIZZO) == ["Via Giuseppe Garibaldi, 10121 Torino"]


class TestConnettiviAggiuntiEInizialeAccentata:
    """Rulings 17 e 18: le famiglie di connettivi che mancavano ("dello", "de'",
    "de", "allo", "alla", "agli", "ai", "al") e l'iniziale maiuscola accentata.
    Senza di esse odonimi italiani comunissimi non producevano alcuno span, e
    l'indirizzo finiva in chiaro all'AI esterna."""

    def test_indirizzo_con_dello_include_civico_e_cap(self):
        testo = "Residente in Via dello Sport 5, 10121 Torino."
        assert valori(testo, Category.INDIRIZZO) == ["Via dello Sport 5, 10121 Torino"]

    def test_indirizzo_con_dello_dopo_toponimo_composto(self):
        testo = "Residente in Viale dello Stadio 3"
        assert valori(testo, Category.INDIRIZZO) == ["Viale dello Stadio 3"]

    def test_indirizzo_con_de_apostrofato(self):
        # né `dei` né `d'` coprono `de'`
        testo = "Residente in Via de' Tornabuoni 5, 50123 Firenze."
        assert valori(testo, Category.INDIRIZZO) == ["Via de' Tornabuoni 5, 50123 Firenze"]

    def test_indirizzo_con_preposizione_articolata_ai(self):
        assert valori("Residente in Via ai Prati 7", Category.INDIRIZZO) == ["Via ai Prati 7"]

    def test_indirizzo_con_preposizione_articolata_al(self):
        testo = "Residente in Via al Castello 9"
        assert valori(testo, Category.INDIRIZZO) == ["Via al Castello 9"]

    def test_indirizzo_con_de_dentro_il_nome_arriva_al_civico(self):
        # la troncatura da correggere si fermava a "Via Giovanni Battista" e
        # lasciava "de Rossi 10" in chiaro, civico compreso
        testo = "Residente in Via Giovanni Battista de Rossi 10"
        assert valori(testo, Category.INDIRIZZO) == ["Via Giovanni Battista de Rossi 10"]

    def test_indirizzo_con_iniziale_maiuscola_accentata(self):
        assert valori("Residente in Via Élia 4", Category.INDIRIZZO) == ["Via Élia 4"]

    def test_indirizzo_con_toponimo_e_nome_accentati(self):
        testo = "Abita in Località Èboli 2"
        assert valori(testo, Category.INDIRIZZO) == ["Località Èboli 2"]

    def test_i_soli_connettivi_non_producono_indirizzo(self):
        # invariante del giro 1: almeno una parola con l'iniziale maiuscola
        # resta obbligatoria, anche col vocabolario dei connettivi allargato
        assert Category.INDIRIZZO not in categorie("Contattato via email dal cliente")
        assert trova_per_regole("via dei del della di da il lo la le", "d1") == []
        assert trova_per_regole("via dello de' de allo alla agli ai al", "d1") == []

    def test_iniziale_minuscola_dopo_apostrofo_resta_rifiutata(self):
        # l'intervallo allargato resta case-sensitive grazie a `(?-i:...)`
        assert trova_per_regole("Residente in Via d'azeglio 5", "d1") == []


class TestConnettiviAlleESul:
    """Ruling C1: le famiglie `all'`/`alle` e `sul`/`sulla` mancavano da
    `CONNETTIVI`. La fuga era totale — "Via alle Fonti 7" non produceva alcuno
    span — oppure parziale e corruttiva: su "Via all'Aeroporto 3, 10121 Torino"
    restavano in chiaro il toponimo e il CAP."""

    def test_indirizzo_con_alle(self):
        assert valori("Residente in Via alle Fonti 7", Category.INDIRIZZO) == [
            "Via alle Fonti 7"
        ]

    def test_indirizzo_con_all_apostrofato_include_civico_e_cap(self):
        testo = "Residente in Via all'Aeroporto 3, 10121 Torino."
        assert valori(testo, Category.INDIRIZZO) == [
            "Via all'Aeroporto 3, 10121 Torino"
        ]

    def test_indirizzo_con_sul(self):
        assert valori("Residente in Via sul Mare 8", Category.INDIRIZZO) == [
            "Via sul Mare 8"
        ]

    def test_indirizzo_con_sulla(self):
        assert valori("Residente in Via sulla Collina 2", Category.INDIRIZZO) == [
            "Via sulla Collina 2"
        ]

    def test_indirizzo_con_sugli(self):
        assert valori("Residente in Via sugli Orti 6", Category.INDIRIZZO) == [
            "Via sugli Orti 6"
        ]

    def test_le_nuove_famiglie_da_sole_non_producono_span(self):
        # l'invariante del giro 1 vale anche col vocabolario allargato: almeno
        # una parola con l'iniziale maiuscola resta obbligatoria
        assert trova_per_regole("via all alle sul sulla sui", "d1") == []
        assert Category.INDIRIZZO not in categorie("Contattato via email dal cliente")

    def test_azienda_con_connettivo_alle(self):
        # `CONNETTIVI` è condiviso con AZIENDA: il vocabolario allargato deve
        # valere anche per le ragioni sociali
        testo = "Fattura da Cooperativa alle Ginestre S.r.l. per il servizio"
        trovati = valori(testo, Category.AZIENDA)
        assert len(trovati) == 1
        assert trovati[0].endswith("Cooperativa alle Ginestre S.r.l")

    def test_azienda_con_connettivo_sul(self):
        testo = "Fattura da Albergo sul Lago S.p.A. per il soggiorno"
        trovati = valori(testo, Category.AZIENDA)
        assert len(trovati) == 1
        assert trovati[0].endswith("Albergo sul Lago S.p.A")


class TestSuffissoDelCivico:
    """Ruling I1: il suffisso del civico ("12/A", "12 bis", "12-14") tagliava
    lo span a metà e con esso si perdeva l'aggancio del CAP, lasciando in
    chiaro suffisso, CAP e comune."""

    def test_civico_con_lettera_dopo_slash_include_cap_e_comune(self):
        testo = "Residente in Via Roma 12/A, 10121 Torino"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12/A, 10121 Torino"]

    def test_civico_con_lettera_dopo_abbreviazione_numero(self):
        assert valori("Residente in Via Roma n. 12/B", Category.INDIRIZZO) == [
            "Via Roma n. 12/B"
        ]

    def test_civico_con_bis_include_cap_e_comune(self):
        testo = "Residente in Via Roma 12 bis, 10121 Torino"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12 bis, 10121 Torino"]

    def test_civico_a_intervallo_include_cap_e_comune(self):
        testo = "Residente in Via Roma 12-14, 10121 Torino"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12-14, 10121 Torino"]

    def test_civico_con_lettera_attaccata_resta_riconosciuto(self):
        testo = "Residente in Via Roma 12A, 10121 Torino"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12A, 10121 Torino"]

    def test_il_cap_senza_civico_resta_protetto_dal_lookahead(self):
        # regressione: il gruppo del civico non deve mangiare le cifre del CAP
        assert valori("Residente in Via Roma 10121 Torino", Category.INDIRIZZO) == [
            "Via Roma 10121 Torino"
        ]


class TestTelefonoAGruppi:
    """Ruling I2: la spec §6 elenca i separatori senza limitarne il numero, ma
    le due forme nazionali ne ammettevano una e due, quindi i numeri scritti a
    gruppi non producevano alcuno span nemmeno con la parola chiave accanto."""

    def test_fisso_a_quattro_gruppi(self):
        assert valori("Tel. 011 123 45 67", Category.TELEFONO) == ["011 123 45 67"]

    def test_cellulare_a_quattro_gruppi(self):
        assert valori("Cell. 340 123 45 67", Category.TELEFONO) == ["340 123 45 67"]

    def test_fisso_con_prefisso_a_due_cifre(self):
        assert valori("Tel. 02 1234 5678", Category.TELEFONO) == ["02 1234 5678"]

    def test_cellulare_a_gruppi_di_quattro_e_tre(self):
        assert valori("Cell. 340 1234 567", Category.TELEFONO) == ["340 1234 567"]

    def test_fisso_con_prefisso_fra_parentesi(self):
        assert valori("Tel. (011) 1234567", Category.TELEFONO) == ["(011) 1234567"]

    def test_fisso_con_separatori_misti(self):
        assert valori("Tel. 011/123.45.67", Category.TELEFONO) == ["011/123.45.67"]

    def test_il_numero_non_scavalca_uno_spazio_per_inglobare_una_data(self):
        # le ripetizioni sono pigre e chiuse da `\b`: se la corsa di cifre
        # arrivasse fino alla data, il conteggio sballerebbe e il numero
        # sparirebbe del tutto invece di essere mascherato
        testo = "Tel. 011 1234567 14/03/2024"
        assert valori(testo, Category.TELEFONO) == ["011 1234567"]
        assert valori(testo, Category.DATA) == ["14/03/2024"]

    def test_il_validatore_respinge_ancora_le_cifre_troppo_poche(self):
        # `_telefono_plausibile` resta il tetto: 8 cifre sono sotto la soglia
        # della spec §6, con o senza separatori
        assert Category.TELEFONO not in categorie("Tel. 01123456")
        assert Category.TELEFONO not in categorie("Tel. 011 12 34 5")

    def test_il_validatore_respinge_ancora_le_cifre_troppe(self):
        assert Category.TELEFONO not in categorie("Tel. 012312345678")


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

    def test_importo_cifre_nude_seguite_da_valuta_riconosciuto(self):
        # ruling 13: run di 4+ cifre senza separatori, ramo cifre-poi-valuta
        assert valori("12345 EUR", Category.IMPORTO) == ["12345 EUR"]

    def test_importo_valuta_seguita_da_cifre_nude_riconosciuto(self):
        # ruling 13: run di 4+ cifre senza separatori, ramo valuta-poi-cifre
        assert valori("€12345", Category.IMPORTO) == ["€12345"]

    def test_importo_con_separatori_dopo_valuta_resta_intero(self):
        # regressione sull'ordine dell'alternanza: il raggruppamento a
        # migliaia deve restare il primo ramo, altrimenti "12.345,67"
        # degrada a "12" sul ramo delle cifre libere
        assert valori("12.345,67 EUR", Category.IMPORTO) == ["12.345,67 EUR"]

    def test_importo_con_separatori_prima_delle_cifre_resta_intero(self):
        # stessa regressione dell'ordine dell'alternanza, ramo valuta-poi-cifre
        assert valori("€ 12.345,67", Category.IMPORTO) == ["€ 12.345,67"]

    def test_dati_catastali_con_foglio_abbreviato(self):
        trovati = valori("Immobile al fg 12 mappale 345", Category.CATASTO)
        assert trovati == ["fg 12 mappale 345"]

    def test_indirizzo_con_cap_e_comune(self):
        testo = "Residente in Via Giuseppe Garibaldi 42, 10121 Torino."
        assert valori(testo, Category.INDIRIZZO) == ["Via Giuseppe Garibaldi 42, 10121 Torino"]

    def test_numero_pratica_senza_punto_finale(self):
        assert valori("Pratica 2024/ABC-77.", Category.PRATICA) == ["Pratica 2024/ABC-77"]


class TestImportoSeguitoDalSimbolo:
    """Ruling C2: `\\b` stava dopo tutta l'alternanza della valuta, quindi il
    ramo del simbolo pretendeva un carattere di parola subito dopo `€`, che è
    l'inverso dell'intenzione. La forma più comune di un importo in un
    contratto italiano — cifre, spazio, `€` — non produceva alcuno span, e
    IMPORTO è mascherata di default (decisione 4)."""

    def test_importo_attaccato_al_simbolo(self):
        assert valori("Totale 1.250,00€", Category.IMPORTO) == ["1.250,00€"]

    def test_importo_separato_dal_simbolo(self):
        assert valori("Totale 1.250,00 €", Category.IMPORTO) == ["1.250,00 €"]

    def test_importo_intero_attaccato_al_simbolo(self):
        assert valori("Canone mensile 800€", Category.IMPORTO) == ["800€"]

    def test_importo_col_simbolo_in_mezzo_alla_frase(self):
        assert valori("IVA su 1.000,00 € netti", Category.IMPORTO) == ["1.000,00 €"]

    def test_eurodollaro_non_e_un_importo(self):
        # il confine serve, e resta, sulle sole forme alfabetiche
        assert Category.IMPORTO not in categorie("Cambio eurodollaro 1000 in salita")
        assert Category.IMPORTO not in categorie("Cambio eurodollaro1000 in salita")

    def test_cifre_attaccate_alla_sigla_restano_un_importo(self):
        # il confine sulle forme alfabetiche è "nessuna lettera dopo", non
        # `\b`: con `\b` questa forma avrebbe smesso di produrre uno span
        assert valori("Totale EUR100 netti", Category.IMPORTO) == ["EUR100"]
        assert valori("Totale 1.250,00EUR netti", Category.IMPORTO) == ["1.250,00EUR"]


class TestConfineDestroDeiDecimali:
    """Ruling I3: senza confine a destra i decimali venivano troncati a due
    cifre e la terza restava in chiaro accanto a un importo storpiato
    ("Canone di [IMPORTO]8 mensili"). Il lookahead da solo trasformava però
    la corruzione in un'assenza di span (una fuga: l'importo restava tutto
    in chiaro). Ruling 22: la spec §6 non pone un limite alle cifre
    decimali, quindi il gruppo decimale è stato allargato a `\\d+` — un
    importo a tre decimali è una tariffa legittima e va mascherato per
    intero. Il confine a destra resta invariato e continua a respingere le
    forme malformate."""

    def test_tre_decimali_non_producono_un_importo_troncato(self):
        assert valori("Canone di € 12.345,678 mensili", Category.IMPORTO) == ["€ 12.345,678"]

    def test_tariffa_a_tre_decimali_non_produce_un_importo_troncato(self):
        assert valori("Prezzo € 0,505 per kWh", Category.IMPORTO) == ["€ 0,505"]

    def test_due_decimali_restano_riconosciuti(self):
        assert valori("Canone di € 1.250,00 mensili.", Category.IMPORTO) == ["€ 1.250,00"]
        assert valori("12.345,67 EUR", Category.IMPORTO) == ["12.345,67 EUR"]

    def test_decimali_con_cifre_dopo_il_punto_restano_malformati(self):
        # il confine a destra `(?![\d.,]*\d)` non è cambiato: una forma
        # incoerente coi separatori (virgola decimale seguita da un punto
        # con altre cifre) resta respinta, non troncata
        assert valori("€ 1,2.3", Category.IMPORTO) == []


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
