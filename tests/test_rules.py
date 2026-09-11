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


class TestCodiciSpaziati:
    """Issue #37: IBAN e codice fiscale come appaiono nei documenti veri.

    Tre forme, un'unica radice: il separatore ammesso fra i gruppi. L'IBAN col
    trattino è come lo mostrano gestionali e home banking; l'IBAN col doppio
    spazio è quello che produce un copia-incolla da un PDF o da una tabella
    allineata; il CF a gruppi è la forma dei moduli a caselle, dove ogni gruppo
    sta in un riquadro e l'estrazione restituisce spazi. Nessuna delle tre
    produceva alcuno span, e IBAN e CF restavano interi in chiaro nel testo
    mandato all'IA — la fuga con la conseguenza più diretta fra quelle aperte.

    Due invarianti reggono la correzione e sono provate qui sotto:

    - il **checksum resta il cancello**, calcolato sul valore normalizzato
      (senza spazi né trattini): allargare il riconoscimento senza allargare
      la verifica sarebbe lo scambio peggiore possibile;
    - lo **span copre il codice come appare nel testo**, separatori compresi,
      altrimenti il mascheramento lascerebbe in chiaro i frammenti che lo span
      non copre. Cosa finisca nel dizionario è deciso e provato in
      `tests/test_entities.py::TestRipristinoDeiCodiciSpaziati`.
    """

    def test_iban_col_trattino_riconosciuto(self):
        testo = "Bonifico su IT60-X054-2811-1010-0000-0123-456 presso la banca."
        assert valori(testo, Category.IBAN) == ["IT60-X054-2811-1010-0000-0123-456"]

    def test_iban_col_doppio_spazio_riconosciuto(self):
        testo = "Bonifico su IT60  X054  2811 1010 0000 0123 456 presso la banca."
        assert valori(testo, Category.IBAN) == ["IT60  X054  2811 1010 0000 0123 456"]

    def test_cf_a_gruppi_riconosciuto(self):
        testo = "Codice fiscale RSSMRA 85M01 H501Q del contribuente."
        assert valori(testo, Category.CF) == ["RSSMRA 85M01 H501Q"]

    def test_iban_a_gruppo_unico_resta_riconosciuto(self):
        # controprova della issue: la forma che già funzionava non regredisce
        testo = "Bonifico su IT60 X0542811101000000123456 presso la banca."
        assert valori(testo, Category.IBAN) == ["IT60 X0542811101000000123456"]


class TestIlChecksumRestaIlCancelloSuiCodiciSpaziati:
    """Il controllo si sposta sul valore normalizzato, non sparisce: nelle
    forme nuove un codice con una cifra alterata deve restare fuori esattamente
    come nella forma compatta."""

    def test_iban_col_trattino_e_cifra_alterata_scartato(self):
        testo = "Bonifico su IT60-X054-2811-1010-0000-0123-457 presso la banca."
        assert Category.IBAN not in categorie(testo)

    def test_iban_col_doppio_spazio_e_cifra_alterata_scartato(self):
        testo = "Bonifico su IT60  X054  2811 1010 0000 0123 457 presso la banca."
        assert Category.IBAN not in categorie(testo)

    def test_cf_a_gruppi_col_cin_errato_scartato(self):
        # TC-02 della consegna, nella forma del modulo a caselle
        testo = "Codice fiscale RSSMRA 85M01 H501Z del contribuente."
        assert Category.CF not in categorie(testo)


class TestVoracitaDeiCodiciSpaziati:
    """Una guardia per ogni forma aggiunta. Ammettere il trattino fra gruppi
    alfanumerici apre la regex a codici che IBAN non sono, e ammettere il
    doppio spazio apre un modo nuovo di sbagliare il *confine* dello span: il
    ritaglio di `rules.py` taglia all'ultimo separatore, quindi su una coppia
    di spazi lascerebbe il primo attaccato in fondo al valore."""

    def test_lo_span_col_trattino_si_ferma_al_codice(self):
        # la coda vorace ingloba "-BENEFICIARIO": il ritaglio guidato dal
        # checksum deve restituire il solo IBAN, non scartare tutto il match
        testo = "IBAN IT60-X054-2811-1010-0000-0123-456-BENEFICIARIO ROSSI"
        assert valori(testo, Category.IBAN) == ["IT60-X054-2811-1010-0000-0123-456"]

    def test_lo_span_col_doppio_spazio_non_si_porta_dietro_il_separatore(self):
        # il ritaglio taglia *all'ultimo* separatore, quindi il candidato
        # intermedio qui è "...456 " con uno spazio in fondo, e il suo valore
        # normalizzato è un IBAN valido. È `iban_valido` a rifiutare un valore
        # che comincia o finisce con un separatore: senza quel rifiuto lo span
        # coprirebbe un carattere che nel codice non c'è e il segnaposto
        # finirebbe attaccato alla parola dopo.
        testo = "IBAN IT60  X054  2811 1010 0000 0123 456  PRESSO BANCA"
        assert valori(testo, Category.IBAN) == ["IT60  X054  2811 1010 0000 0123 456"]

    def test_un_codice_col_trattino_che_iban_non_e_non_produce_span(self):
        testo = "Il lotto AB12-CDEF-3456-7890-1234 è stato spedito."
        assert Category.IBAN not in categorie(testo)

    def test_il_separatore_del_cf_sta_solo_fra_i_tre_gruppi(self):
        # la guardia più importante del CF. Se il separatore fosse ammesso fra
        # un carattere e l'altro invece che fra i tre gruppi del modulo a
        # caselle, questo supererebbe il checksum — il valore normalizzato
        # *è* un codice fiscale valido — e lo span coprirebbe diciassette
        # caratteri che codice fiscale non sono.
        testo = "Codice fiscale RSSMRA85M0 1H501Q del contribuente."
        assert Category.CF not in categorie(testo)

    def test_il_primo_gruppo_del_cf_non_si_aggancia_alla_parola_precedente(self):
        # il separatore dopo le prime sei lettere apre la regex a partire da
        # qualunque parola di sei maiuscole: se una di quelle partenze
        # producesse un match, essendo più a sinistra vincerebbe su `finditer`
        # e il codice fiscale vero resterebbe senza span.
        testo = "MODULO RSSMRA85M01H501Q depositato."
        assert valori(testo, Category.CF) == ["RSSMRA85M01H501Q"]

    def test_il_separatore_e_limitato_a_due_spazi(self):
        # Il confine scelto, col suo costo dichiarato. Uno spazio, due (il
        # copia-incolla da PDF) o un trattino sono raggruppamento; oltre è
        # impaginazione, e incollare due celle diverse di una tabella
        # produrrebbe uno span che copre anche il vuoto fra loro. Il costo è
        # che un codice separato da tre spazi resta in chiaro: allargare
        # ancora è una decisione che vuole le sue misure, non un ritocco.
        # L'a capo dentro un codice è un'altra famiglia (issue #36, il loader)
        # e qui non si tocca: il separatore ammette al più *un* a capo, come
        # prima della correzione.
        assert Category.IBAN not in categorie(
            "Bonifico su IT60   X054   2811 1010 0000 0123 456 presso la banca."
        )
        assert Category.CF not in categorie(
            "Codice fiscale RSSMRA   85M01 H501Q del contribuente."
        )


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


class TestVariantiDelleParoleDiContesto:
    """Il valore e' gia' validato dal checksum: se cade, cade sulla parola chiave.

    Ogni caso qui ha la sua controprova in `TestRequisitoDiContesto` con la
    forma che funzionava gia', sullo **stesso** numero: e' la dimostrazione che
    non c'entra il valore (issue #32).
    """

    def test_codice_fiscale_di_societa_riconosciuto(self):
        # il codice fiscale di una societa' ha la forma della P.IVA, ed e' la
        # dicitura piu' comune nei documenti italiani
        assert valori("Ditta con Codice Fiscale 12345678903 attiva.", Category.PIVA) == [
            "12345678903"
        ]

    def test_cf_abbreviato_riconosciuto(self):
        assert valori("Ditta con C.F. 12345678903 attiva.", Category.PIVA) == ["12345678903"]

    def test_cod_fisc_riconosciuto(self):
        assert valori("Ditta con Cod. Fisc. 12345678903 attiva.", Category.PIVA) == [
            "12345678903"
        ]

    def test_partita_iva_puntata_riconosciuta(self):
        assert valori("Ditta con Partita I.V.A. 12345678903 attiva.", Category.PIVA) == [
            "12345678903"
        ]

    def test_piva_attaccata_riconosciuta(self):
        assert valori("Ditta con PIVA 12345678903 attiva.", Category.PIVA) == ["12345678903"]

    def test_recapito_telefonico_riconosciuto(self):
        assert valori("Recapito telefonico: 3401234567", Category.TELEFONO) == ["3401234567"]

    def test_utenza_telefonica_riconosciuta(self):
        testo = "Utenza telefonica 011 1234567 intestata al cliente."
        assert valori(testo, Category.TELEFONO) == ["011 1234567"]

    def test_telefoni_al_plurale_riconosciuto(self):
        assert valori("Telefoni: 011 1234567", Category.TELEFONO) == ["011 1234567"]

    def test_telefax_riconosciuto(self):
        assert valori("Telefax: 011 1234567", Category.TELEFONO) == ["011 1234567"]

    def test_telef_abbreviato_riconosciuto(self):
        assert valori("Telef. 011 1234567", Category.TELEFONO) == ["011 1234567"]

    def test_cellulari_al_plurale_riconosciuto(self):
        assert valori("Recapiti cellulari: 3401234567", Category.TELEFONO) == ["3401234567"]


class TestIlValidatoreRestaIlCancello:
    """Le guardie della #32: la parola chiave apre la porta, il checksum
    decide chi entra. Allargare la prima non deve allentare il secondo."""

    def test_piva_con_checksum_errato_resta_fuori_con_la_chiave_nuova(self):
        assert Category.PIVA not in categorie("Ditta con Codice Fiscale 12345678901 attiva.")

    def test_numero_troppo_corto_resta_fuori_con_la_chiave_nuova(self):
        assert Category.TELEFONO not in categorie("Recapito telefonico: 12345")

    def test_tel_dentro_una_parola_non_fa_contesto(self):
        # `tel` resta parola intera: non deve agganciarsi dentro `hotel`
        assert Category.TELEFONO not in categorie("Fattura hotel 3401234567 del mese.")

    def test_una_parola_che_comincia_per_tel_non_fa_contesto(self):
        # il prefisso ammesso e' `telefon`, non `tel`: "numero di telaio" e'
        # una dicitura reale dei documenti dei veicoli e non parla di telefoni
        assert Category.TELEFONO not in categorie("Numero di telaio 3401234567 del veicolo.")


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


class TestSuffissoDelCivicoNonSiAggancia:
    """Issue #29: il suffisso a lettera sola del ruling I1 ammetteva *lo spazio
    da solo* come separatore, quindi si agganciava a qualunque lettera isolata
    dopo il civico — un'abbreviazione, una congiunzione, una preposizione — e
    non solo alla lettera che del civico fa davvero parte.

    Il rimedio ovvio, pretendere sempre il separatore, è stato misurato e
    scartato: toglie "Via Roma 12 A, 10121 Torino", indirizzo italiano reale
    che prima funzionava, e con lui CAP e comune tornano in chiaro. Chiudeva
    una voracità aprendo sei fughe, e nessun test lo mostrava — è il motivo per
    cui `test_il_suffisso_maiuscolo_separato_da_spazio_resta` esiste.

    Quello che distingue un suffisso vero da una lettera di passaggio non è
    solo il separatore: è anche il caso della lettera e ciò che le sta a
    destra. Separata da spazio, la maiuscola vale per convenzione ("12 A"); la
    minuscola vale solo se lì l'indirizzo finisce davvero — virgola, fine riga
    o del testo, o il CAP subito dopo.

    La correzione sta sul suffisso e non fra le parole chiave dell'interno: `p`
    è una chiave di una lettera sola, ambigua con `pagina` e con qualunque
    altra iniziale, e ammetterla allargherebbe la voracità invece di ridurla —
    oltre a non chiudere il difetto, che si presenta anche senza `p.`."""

    def test_una_lettera_isolata_seguita_da_punto_non_entra_nello_span(self):
        # `p.` è un'abbreviazione di "piano": lo span si mangiava la `p`
        # ("Via Roma 12 p"), quindi restituiva un civico storpiato. Ora il
        # suffisso non si aggancia e il civico resta intero.
        #
        # LIMITE NOTO, dichiarato: CAP e comune restano in chiaro lo stesso,
        # perché `p.` non è fra le parole chiave ammesse fra civico e CAP e
        # aggiungercelo è stato scartato con motivo (vedi il docstring). Questo
        # test chiude la voracità sulla `p`, non la fuga del CAP: quella resta
        # aperta e va decisa a parte.
        testo = "Via Roma 12 p. 2, 10121 Torino"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12"]

    def test_la_congiunzione_dopo_il_civico_non_entra_nello_span(self):
        # voracità pura: la `e` non è un dato personale e lo span la mascherava
        testo = "Il piano regolatore di Via Roma 12 e stato approvato"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12"]

    def test_la_preposizione_dopo_il_civico_non_entra_nello_span(self):
        # stessa famiglia: ogni lettera isolata dopo il numero valeva come
        # suffisso, anche quando introduce la frase invece dell'indirizzo
        assert valori("Abita in Via Roma 12 a Torino", Category.INDIRIZZO) == [
            "Via Roma 12"
        ]

    def test_la_minuscola_seguita_da_un_numero_breve_non_e_un_suffisso(self):
        # è il test che tiene fermo `\d{5}` invece di `\d` nel contesto a
        # destra: con le cifre generiche "12 o 14" tornerebbe a dare
        # "Via Roma 12 o". Dopo un suffisso vero vengono le cinque cifre del
        # CAP, non un secondo civico.
        testo = "Via Roma 12 o 14 del quartiere"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12"]

    # --- guardie: le forme reali del suffisso non devono regredire -----------
    # è il motivo per cui il suffisso esiste (ruling I1): se la restrizione le
    # togliesse, il gruppo del CAP tornerebbe a non agganciarsi e resterebbero
    # in chiaro suffisso, CAP e comune — il difetto che I1 aveva chiuso.

    def test_il_suffisso_maiuscolo_separato_da_spazio_resta(self):
        # LA guardia che mancava. "Via Roma 12 A" è un indirizzo italiano
        # reale, nessun test lo copriva, e per questo una correzione che lo
        # rompeva lasciava la suite verde.
        testo = "Residente in Via Roma 12 A, 10121 Torino"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12 A, 10121 Torino"]

    def test_il_suffisso_maiuscolo_separato_da_spazio_senza_virgola(self):
        testo = "Residente in Via Roma 12 A 10121 Torino"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12 A 10121 Torino"]

    def test_il_suffisso_maiuscolo_separato_da_spazio_con_l_interno(self):
        # la forma composta: il suffisso separato da spazio *e* un complemento
        # fra civico e CAP. È qui che si vede perché la maiuscola vale da sola,
        # senza pretendere anche il contesto a destra: pretendendolo, questa
        # riga perde CAP e comune.
        testo = "Residente in Via Roma 12 A int. 3, 10121 Torino"
        assert valori(testo, Category.INDIRIZZO) == [
            "Via Roma 12 A int. 3, 10121 Torino"
        ]

    def test_il_suffisso_maiuscolo_in_un_documento_tutto_maiuscolo(self):
        # i documenti estratti da PDF sono spesso tutti maiuscoli, e il repo ha
        # già test su indirizzi così ("VIA GARIBALDI 42")
        testo = "RESIDENTE IN VIA ROMA 12 A, 10121 TORINO"
        assert valori(testo, Category.INDIRIZZO) == ["VIA ROMA 12 A, 10121 TORINO"]

    def test_il_suffisso_minuscolo_separato_da_spazio_prima_della_virgola(self):
        # la minuscola non è esclusa: le si chiede solo che lì l'indirizzo
        # finisca davvero
        testo = "Residente in Via Roma 12 a, 10121 Torino"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12 a, 10121 Torino"]

    def test_il_suffisso_minuscolo_separato_da_spazio_prima_del_cap(self):
        testo = "Residente in Via Roma 12 a 10121 Torino"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12 a 10121 Torino"]

    def test_il_suffisso_minuscolo_a_fine_riga(self):
        # nei documenti estratti l'indirizzo chiude una riga molto più spesso
        # che il documento: se "fine indirizzo" fosse solo la fine del testo,
        # questa riga perderebbe il suffisso
        testo = "Residente in Via Roma 12 a\nTorino"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12 a"]

    def test_il_suffisso_attaccato_al_civico_resta(self):
        testo = "Residente in Via Roma 12A, 10121 Torino"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12A, 10121 Torino"]

    def test_il_suffisso_dopo_la_barra_resta(self):
        testo = "Residente in Via Roma 12/A, 10121 Torino"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12/A, 10121 Torino"]

    def test_il_suffisso_dopo_la_barra_spaziata_resta(self):
        # con la barra la lettera è dichiarata parte del civico da chi ha
        # scritto il documento: né il caso né il contesto a destra contano
        testo = "Residente in Via Roma 12 / a, 10121 Torino"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12 / a, 10121 Torino"]

    def test_il_suffisso_dopo_il_trattino_resta(self):
        testo = "Residente in Via Roma 12-A, 10121 Torino"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12-A, 10121 Torino"]

    def test_il_suffisso_a_parola_resta(self):
        # "bis" ha il proprio ramo e lo spazio gli è indispensabile: la
        # restrizione sul suffisso a lettera sola non deve toccarlo
        testo = "Residente in Via Roma 12 bis, 10121 Torino"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12 bis, 10121 Torino"]

    def test_il_civico_a_intervallo_resta(self):
        testo = "Residente in Via Roma 12-14, 10121 Torino"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12-14, 10121 Torino"]


class TestInternoDelCivico:
    """Issue #15: fra il civico e il CAP l'indirizzo italiano infila
    spessissimo l'interno ("Via Roma 12 int. 3, 10121 Torino"). Il gruppo del
    CAP pretende le cinque cifre subito dopo il civico: con l'interno in mezzo
    non si agganciava e, essendo facoltativo, si arrendeva senza consumare
    nulla. Lo span si fermava a "Via Roma 12" e CAP e comune restavano in
    chiaro nel testo esportato."""

    def test_interno_abbreviato_include_cap_e_comune(self):
        testo = "Residente in Via Roma 12 int. 3, 10121 Torino"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12 int. 3, 10121 Torino"]

    def test_interno_scritto_per_intero_include_cap_e_comune(self):
        testo = "Residente in Via Roma 12 interno 3, 10121 Torino"
        assert valori(testo, Category.INDIRIZZO) == [
            "Via Roma 12 interno 3, 10121 Torino"
        ]

    def test_interno_senza_virgola_prima_del_cap(self):
        testo = "Residente in Via Roma 12 int. 3 10121 Torino"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12 int. 3 10121 Torino"]

    def test_interno_con_lettera_al_posto_del_numero(self):
        testo = "Residente in Via Roma 12 int. B, 10121 Torino"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12 int. B, 10121 Torino"]

    def test_interno_senza_cap_resta_dentro_lo_span(self):
        # l'interno è parte dell'indirizzo anche quando il CAP non c'è: se
        # restasse fuori sarebbe un dato personale in chiaro accanto a uno
        # span che lo lambisce
        assert valori("Residente in Via Roma 12 int. 3", Category.INDIRIZZO) == [
            "Via Roma 12 int. 3"
        ]

    def test_scala_e_interno_insieme_includono_cap_e_comune(self):
        # la forma composta "sc. B int. 3" è la stessa fuga: fra il civico e il
        # CAP ci sono due complementi invece di uno
        testo = "Residente in Via Roma 12 sc. B int. 3, 10121 Torino"
        assert valori(testo, Category.INDIRIZZO) == [
            "Via Roma 12 sc. B int. 3, 10121 Torino"
        ]

    def test_scala_scritta_per_intero_include_cap_e_comune(self):
        testo = "Residente in Via Roma 12 scala B, 10121 Torino"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12 scala B, 10121 Torino"]

    def test_lo_span_si_ferma_al_comune(self):
        # un indirizzo vorace che si mangia il testo attorno è un difetto
        # peggiore di quello corretto qui: il gruppo dell'interno non deve
        # aprire la strada oltre il comune
        testo = "Residente in Via Roma 12 int. 3, 10121 Torino presso lo studio Bianchi"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12 int. 3, 10121 Torino"]

    def test_la_parola_chiave_senza_identificativo_non_allunga_lo_span(self):
        # "interno" è anche un aggettivo comunissimo: senza l'identificativo
        # breve obbligatorio il gruppo si porterebbe dietro della prosa
        testo = "Villa in Via Roma 12, interno completamente ristrutturato"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12"]

    def test_la_parola_chiave_dell_interno_deve_essere_intera(self):
        # `(?!\w)` dopo la parola chiave: senza di lui `sc` si aggancerebbe al
        # prefisso di un'altra parola e lo span inghiottirebbe testo che
        # nell'indirizzo non c'entra nulla ("Via Roma 12 sca")
        testo = "Residente in Via Roma 12 sca 5, 10121 Torino"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12"]

    def test_l_identificativo_dell_interno_non_mangia_le_cifre_del_cap(self):
        # stesso confine `(?!\d)` del civico: senza di lui l'identificativo si
        # prenderebbe quattro delle cinque cifre del CAP ("int. 1012") e
        # l'ultima resterebbe in chiaro accanto a un indirizzo storpiato. O il
        # CAP entra intero nello span, o non entra: mai a metà.
        testo = "Residente in Via Roma 12 int. 10121 Torino"
        assert valori(testo, Category.INDIRIZZO) in (
            ["Via Roma 12"],
            ["Via Roma 12 int. 10121 Torino"],
        )

    def test_la_parola_chiave_da_sola_non_produce_un_indirizzo(self):
        # invariante dei giri precedenti: il toponimo resta obbligatorio, e il
        # vocabolario allargato non lo aggira
        assert Category.INDIRIZZO not in categorie("Il vano interno 3 misura 12 metri")


class TestPianoDelCivico:
    """Issue #22: stessa fuga della #15, con `piano` al posto di `int.`. La #15
    ha aperto il gruppo fra civico e CAP a interno e scala e si è fermata lì;
    `piano` è la forma vicina rimasta fuori, ed è comune negli indirizzi
    italiani almeno quanto `int.`. Senza di lui
    "Via Roma 12 int. 3 piano 2, 10121 Torino" si fermava a
    "Via Roma 12 int. 3" e CAP e comune restavano in chiaro nel testo
    esportato; "Via Roma 12 piano 2, 10121 Torino", senza interno, si fermava
    a "Via Roma 12".

    La correzione ha la forma della #15 — parola chiave obbligatoria e intera,
    identificativo breve col proprio confine, ripetizioni limitate — e non
    allenta l'adiacenza pretesa dal gruppo del CAP: allentarla renderebbe
    l'indirizzo vorace su testo che non gli appartiene, difetto peggiore di
    quello chiuso qui. Le guardie in coda sono quelle che tengono ferma questa
    scelta."""

    def test_il_piano_dopo_l_interno_include_cap_e_comune(self):
        testo = "Via Roma 12 int. 3 piano 2, 10121 Torino"
        assert valori(testo, Category.INDIRIZZO) == [
            "Via Roma 12 int. 3 piano 2, 10121 Torino"
        ]

    def test_il_piano_senza_interno_include_cap_e_comune(self):
        # il difetto si vede anche senza interno: fra il civico e il CAP basta
        # un complemento qualsiasi perché il gruppo del CAP non si agganci
        testo = "Via Roma 12 piano 2, 10121 Torino"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12 piano 2, 10121 Torino"]

    def test_il_piano_senza_virgola_prima_del_cap(self):
        testo = "Via Roma 12 piano 2 10121 Torino"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12 piano 2 10121 Torino"]

    def test_il_piano_con_lettera_al_posto_del_numero(self):
        testo = "Residente in Via Roma 12 piano A, 10121 Torino"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12 piano A, 10121 Torino"]

    def test_il_piano_senza_cap_resta_dentro_lo_span(self):
        # come per l'interno: il piano è parte dell'indirizzo anche quando il
        # CAP non c'è, e lasciarlo fuori sarebbe un dato in chiaro accanto a
        # uno span che lo lambisce
        assert valori("Residente in Via Roma 12 piano 2", Category.INDIRIZZO) == [
            "Via Roma 12 piano 2"
        ]

    # --- guardie anti-vorace -------------------------------------------------
    # `piano` non è solo una parte dell'indirizzo: è una parola comunissima nel
    # senso di progetto ("piano regolatore", "piano casa") e un sostantivo che
    # regge un aggettivo ("piano nobile"). Se il gruppo si accontentasse di
    # trovare la parola, o ammettesse del testo qualunque dopo di lei, lo span
    # si porterebbe dietro della prosa: un indirizzo vorace è un difetto
    # peggiore di un indirizzo troncato, perché maschera testo che non è un
    # dato personale e lo fa sparire dal documento.

    def test_il_piano_come_parola_comune_non_allunga_lo_span(self):
        # nel senso di progetto: l'identificativo breve obbligatorio è quello
        # che tiene fuori "di ristrutturazione approvato"
        testo = "Villa in Via Roma 12, piano di ristrutturazione approvato"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12"]

    def test_il_piano_nobile_non_porta_dentro_la_prosa(self):
        # "piano nobile" è la forma che smaschera l'adiacenza allentata: con un
        # `[^,]*` o un `.{0,20}` fra civico e CAP lo span inghiottirebbe
        # l'aggettivo *e* la coda con CAP e comune. Qui l'indirizzo preferisce
        # troncarsi: il piano senza identificativo breve non entra, e il CAP
        # non si aggancia.
        testo = "Residente in Via Roma 12 piano nobile, 10121 Torino"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12"]

    def test_lo_span_col_piano_si_ferma_al_comune(self):
        # il gruppo nuovo non deve aprire la strada oltre il comune, esattamente
        # come quello dell'interno
        testo = "Residente in Via Roma 12 piano 2, 10121 Torino presso lo studio Bianchi"
        assert valori(testo, Category.INDIRIZZO) == [
            "Via Roma 12 piano 2, 10121 Torino"
        ]

    def test_il_piano_di_una_frase_che_segue_l_indirizzo_resta_fuori(self):
        # il piano sta *fra* civico e CAP, non dopo il comune: una frase che
        # segue l'indirizzo e contiene "piano 2" non deve riaprire lo span già
        # chiuso sul comune
        testo = "Residente in Via Roma 12, 10121 Torino, piano 2 del progetto"
        assert valori(testo, Category.INDIRIZZO) == ["Via Roma 12, 10121 Torino"]

    def test_il_piano_da_solo_non_produce_un_indirizzo(self):
        # invariante dei giri precedenti: il toponimo resta obbligatorio, e il
        # vocabolario allargato non lo aggira
        assert Category.INDIRIZZO not in categorie(
            "Il piano 2 del progetto misura 12 metri"
        )


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


class TestCodaDelPrefissoInternazionale:
    """Issue #14, prima fuga: il ramo `+39`/`0039` era vorace e senza `\\b` in
    coda, così su un numero seguito da una data si mangiava la prima cifra
    della data ("+39 340 123456 1"). Il conteggio restava dentro i 9-11 della
    spec §6, quindi il validatore accettava, e la priorità P2 del telefono
    faceva scartare a `risolvi` l'intero span DATA: mascherato, il testo
    diventava "[TELEFONO_1]4/03/2024" e **la data restava in chiaro**."""

    def test_il_prefisso_piu_39_non_ingloba_la_cifra_della_data(self):
        testo = "Tel. +39 340 123456 14/03/2024"
        assert valori(testo, Category.TELEFONO) == ["+39 340 123456"]
        assert valori(testo, Category.DATA) == ["14/03/2024"]

    def test_il_prefisso_0039_non_ingloba_la_cifra_della_data(self):
        # stessa alternativa, stessa coda: `0039` è l'altro ramo dello stesso
        # gruppo e senza `\\b` sbaglia allo stesso modo
        testo = "Tel. 0039 340 123456 14/03/2024"
        assert valori(testo, Category.TELEFONO) == ["0039 340 123456"]
        assert valori(testo, Category.DATA) == ["14/03/2024"]

    def test_il_prefisso_internazionale_riconosce_ancora_dieci_cifre(self):
        # il confine chiude la coda, non la accorcia: un cellulare con dieci
        # cifre nazionali resta intero
        assert valori("Tel. +39 340 1234567", Category.TELEFONO) == ["+39 340 1234567"]


class TestFissoAGruppiCorti:
    """Issue #14, seconda fuga: i fissi con prefisso a due cifre scritti a
    gruppi corti — Milano e Roma, i due prefissi più diffusi d'Italia — non
    producevano **nessuno** span pur avendo la parola chiave accanto.

    Il ramo dei fissi era pigro con minimo 6, e il minimo di un prefisso a due
    cifre è quindi 2+6 = 8 cifre: sotto il pavimento di 9 di
    `_telefono_plausibile`. Il conteggio giusto c'era nel testo, ma la corsa
    pigra si fermava al primo `\\b` utile e non lo raggiungeva mai. Il
    percorso di ritaglio, che avrebbe potuto rimediare, era morto: il
    pavimento era uno solo, tarato sulla lunghezza dell'IBAN, e nessun
    candidato telefonico lo supera.

    La corsa è ora vorace — come quella dell'IBAN, e per la stessa ragione: si
    prende il più possibile e si lascia al validatore il compito di dire dove
    finisce il valore. Perché quel compito sia eseguibile il ritaglio è stato
    riaperto due volte: il pavimento è per categoria, e il taglio cade su
    qualunque separatore e non solo sugli spazi."""

    def test_fisso_di_milano_a_gruppi_di_due(self):
        assert valori("Tel. 02 12 34 56 78", Category.TELEFONO) == ["02 12 34 56 78"]

    def test_fisso_di_roma_a_gruppi_di_due(self):
        assert valori("Tel. 06 12 34 56 78", Category.TELEFONO) == ["06 12 34 56 78"]

    def test_il_prefisso_a_quattro_cifre_con_sei_cifre_resta_riconosciuto(self):
        # il minimo della ripetizione, 6, è tarato sul prefisso più lungo: con
        # un prefisso a quattro cifre sono esattamente le sei cifre che
        # restano. La voracità non deve accorciare questo caso limite, che
        # senza le due cifre del prefisso lungo scenderebbe sotto la soglia.
        assert valori("Tel. 0331 123456", Category.TELEFONO) == ["0331 123456"]

    def test_il_fisso_piu_corto_ammesso_resta_riconosciuto(self):
        # nove cifre esatte, il pavimento della spec §6: qui il prefisso lungo
        # e il minimo della ripetizione non stanno insieme nel conteggio, e a
        # far tornare i conti è l'arretramento del prefisso
        assert valori("Tel. 0331 12345", Category.TELEFONO) == ["0331 12345"]
        assert valori("Tel. 011 123456", Category.TELEFONO) == ["011 123456"]

    def test_il_ritaglio_riporta_la_coda_vorace_dentro_il_conteggio(self):
        # con la corsa vorace il numero arriva a inglobare le due cifre del
        # giorno ("011 1234567 14", dodici cifre): è il ritaglio per categoria
        # a restituire la data al proprio span. Con il pavimento dell'IBAN
        # questo candidato è lungo 14 caratteri, il ritaglio si arrende e il
        # numero sparisce del tutto.
        testo = "Tel. 011 1234567 14/03/2024"
        assert valori(testo, Category.TELEFONO) == ["011 1234567"]
        assert valori(testo, Category.DATA) == ["14/03/2024"]

    def test_il_ritaglio_taglia_anche_dove_il_separatore_non_e_uno_spazio(self):
        # la coda vorace non si attacca solo attraverso uno spazio: se il
        # numero è seguito da altre cifre separate da "/" o "-", il taglio
        # all'ultimo *spazio* cadeva prima del numero, il candidato scendeva a
        # tre cifre e il numero spariva del tutto — la stessa fuga totale che
        # la correzione deve chiudere. Il ritaglio taglia quindi anche sui
        # separatori che la regex ammette dentro il valore.
        assert valori("Tel. 011 1234567/14", Category.TELEFONO) == ["011 1234567"]
        assert valori("Tel. 011 1234567-14", Category.TELEFONO) == ["011 1234567"]

    def test_il_pavimento_piu_basso_non_fa_passare_le_cifre_troppo_poche(self):
        # il pavimento scende a 9 perché 9 cifre senza separatori sono la forma
        # più corta che un numero valido può avere: il ritaglio ora gira anche
        # per il telefono, ma non deve accettare nulla sotto la soglia della
        # spec §6
        assert Category.TELEFONO not in categorie("Tel. 02 12 34 56")
        assert Category.TELEFONO not in categorie("Tel. 06 1234 56")

    def test_il_ritaglio_non_fabbrica_un_telefono_da_una_cifratura_lunga(self):
        # dodici cifre a gruppi non sono un numero di telefono: la corsa vorace
        # le prende tutte, il validatore le respinge e il ritaglio le accorcia
        # fino al prefisso, senza mai trovare un candidato plausibile
        assert Category.TELEFONO not in categorie("Tel. 0123 45678901")
        assert Category.TELEFONO not in categorie("Tel. 0123 4567 8901 2345")


class TestAltreCategorie:
    def test_email(self):
        assert valori("Scrivere a mario.rossi@example.com subito.", Category.EMAIL) == [
            "mario.rossi@example.com"
        ]

    def test_email_con_trattino_nel_dominio(self):
        # Il trattino nelle etichette di dominio è ammesso dalla regex
        # ([A-Za-z0-9.\-]+) e fino a oggi era esercitato solo di rimbalzo, da
        # una fixture di tests/test_documenti_di_verifica.py. Una fixture però
        # la si riscrive senza sapere che cosa stava sorvegliando: qui la
        # copertura diventa deliberata e ha un nome che lo dice.
        assert valori("Scrivere a info@posta-esempio.example.com subito.", Category.EMAIL) == [
            "info@posta-esempio.example.com"
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
