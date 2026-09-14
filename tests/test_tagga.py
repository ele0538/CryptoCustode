"""`assegna_tag` e `tagga`: dai valori del modello al testo mascherato (spec §7)."""

from dataclasses import replace

from cryptocustode.core.models import Category, Rilevazione, StatoTag
from cryptocustode.core.tagga import assegna_tag, conta_occorrenze, tagga

VUOTI: dict[Category, int] = {}


def _rilevazione(valore: str, categoria: Category = Category.PERSONA) -> Rilevazione:
    return Rilevazione(valore=valore, categoria=categoria)


def _tabella(*valori_e_categorie) -> dict:
    rilevazioni = [Rilevazione(valore=v, categoria=c) for v, c in valori_e_categorie]
    tabella, _ = assegna_tag(rilevazioni, {}, VUOTI)
    return tabella


class TestAssegnaTag:
    def test_un_valore_riceve_un_tag_della_sua_categoria(self):
        tabella, contatori = assegna_tag([_rilevazione("Mario Rossi")], {}, VUOTI)
        assert list(tabella) == ["[PERSONA_1]"]
        assert tabella["[PERSONA_1]"].valore == "Mario Rossi"
        assert tabella["[PERSONA_1]"].categoria is Category.PERSONA
        assert contatori[Category.PERSONA] == 1

    def test_il_tag_nasce_non_trovato(self):
        """Se il valore compaia davvero nel testo lo sa solo `tagga`."""
        tabella, _ = assegna_tag([_rilevazione("Mario Rossi")], {}, VUOTI)
        assert tabella["[PERSONA_1]"].stato is StatoTag.NON_TROVATO
        assert tabella["[PERSONA_1]"].occorrenze == 0

    def test_lo_stesso_valore_nominato_due_volte_e_un_tag_solo(self):
        tabella, contatori = assegna_tag(
            [_rilevazione("Mario Rossi"), _rilevazione("Mario Rossi")], {}, VUOTI
        )
        assert list(tabella) == ["[PERSONA_1]"]
        assert contatori[Category.PERSONA] == 1

    def test_un_valore_gia_in_tabella_non_consuma_un_indice_nuovo(self):
        """La stabilità fra documenti: il secondo file che nomina Mario Rossi
        riceve il tag che aveva il primo (spec §5)."""
        tabella, contatori = assegna_tag([_rilevazione("Mario Rossi")], {}, VUOTI)
        tabella, contatori = assegna_tag(
            [_rilevazione("Mario Rossi"), _rilevazione("Luigi Bianchi")],
            tabella,
            contatori,
        )
        assert sorted(tabella) == ["[PERSONA_1]", "[PERSONA_2]"]
        assert tabella["[PERSONA_1]"].valore == "Mario Rossi"
        assert tabella["[PERSONA_2]"].valore == "Luigi Bianchi"

    def test_categorie_diverse_hanno_contatori_indipendenti(self):
        tabella, _ = assegna_tag(
            [
                _rilevazione("Mario Rossi", Category.PERSONA),
                _rilevazione("ACME s.r.l.", Category.AZIENDA),
            ],
            {},
            VUOTI,
        )
        assert sorted(tabella) == ["[AZIENDA_1]", "[PERSONA_1]"]

    def test_la_numerazione_non_dipende_dall_ordine_di_arrivo(self):
        """Il modello elenca in un ordine suo, che può cambiare fra due
        chiamate: la numerazione no, altrimenti l'hash di approvazione
        cambierebbe senza che sia cambiato niente."""
        avanti, _ = assegna_tag(
            [_rilevazione("Mario Rossi"), _rilevazione("Bianchi")], {}, VUOTI
        )
        indietro, _ = assegna_tag(
            [_rilevazione("Bianchi"), _rilevazione("Mario Rossi")], {}, VUOTI
        )
        assert {t.tag: t.valore for t in avanti.values()} == {
            t.tag: t.valore for t in indietro.values()
        }

    def test_a_parita_di_lunghezza_decide_l_alfabeto(self):
        avanti, _ = assegna_tag(
            [_rilevazione("Bianchi"), _rilevazione("Azzurri")], {}, VUOTI
        )
        assert avanti["[PERSONA_1]"].valore == "Azzurri"
        assert avanti["[PERSONA_2]"].valore == "Bianchi"

    def test_gli_indici_non_si_riciclano(self):
        """`counters` cresce e non torna indietro: un testo esportato ieri non
        deve contenere un tag che oggi significa un'altra persona (spec §5)."""
        _, contatori = assegna_tag([_rilevazione("Mario Rossi")], {}, VUOTI)
        tabella, contatori = assegna_tag([_rilevazione("Luigi Bianchi")], {}, contatori)
        assert list(tabella) == ["[PERSONA_2]"]

    def test_il_valore_vuoto_viene_scartato(self):
        """Un valore vuoto troverebbe un'occorrenza a ogni offset del testo."""
        tabella, _ = assegna_tag([_rilevazione("")], {}, VUOTI)
        assert tabella == {}

    def test_non_muta_gli_argomenti(self):
        tabella_iniziale: dict = {}
        contatori_iniziali: dict = {}
        assegna_tag([_rilevazione("Mario Rossi")], tabella_iniziale, contatori_iniziali)
        assert tabella_iniziale == {}
        assert contatori_iniziali == {}


class TestTagga:
    def test_sostituisce_il_valore_col_suo_tag(self):
        tabella = _tabella(("Mario Rossi", Category.PERSONA))
        assert tagga("Il sig. Mario Rossi paga.", tabella).mascherato == (
            "Il sig. [PERSONA_1] paga."
        )

    def test_sostituisce_tutte_le_occorrenze(self):
        tabella = _tabella(("Mario Rossi", Category.PERSONA))
        risultato = tagga("Mario Rossi e ancora Mario Rossi.", tabella)
        assert risultato.mascherato == "[PERSONA_1] e ancora [PERSONA_1]."
        assert len(risultato.regioni) == 2

    def test_il_valore_piu_lungo_rivendica_per_primo(self):
        """Senza l'ordinamento per lunghezza, `Rossi` verrebbe taggato dentro
        `Mario Rossi` e produrrebbe `Mario [PERSONA_2]`."""
        tabella = _tabella(
            ("Mario Rossi", Category.PERSONA), ("Rossi", Category.PERSONA)
        )
        assert tagga("Mario Rossi.", tabella).mascherato == "[PERSONA_1]."

    def test_il_valore_corto_prende_solo_le_occorrenze_che_restano(self):
        tabella = _tabella(
            ("Mario Rossi", Category.PERSONA), ("Rossi", Category.PERSONA)
        )
        mascherato = tagga("Mario Rossi e il dott. Rossi.", tabella).mascherato
        assert mascherato == "[PERSONA_1] e il dott. [PERSONA_2]."

    def test_una_sottostringa_dentro_una_parola_piu_lunga_viene_comunque_presa(self):
        """`Rossi` dentro `Rossini` è un falso positivo del modello, non di
        `tagga`: la ricerca è letterale e non conosce i confini di parola. Il
        test fissa il comportamento perché sia una scelta visibile e non una
        sorpresa — chi vorrà cambiarlo saprà cosa sta cambiando."""
        tabella = _tabella(("Rossi", Category.PERSONA))
        assert tagga("Rossini canta.", tabella).mascherato == "[PERSONA_1]ni canta."

    def test_la_ricerca_e_sensibile_alle_maiuscole(self):
        """La controparte del vincolo di letteralità imposto al modello: senza
        confronto esatto l'identità del round-trip non varrebbe, perché al
        ripristino tornerebbe il valore con la grafia sbagliata."""
        tabella = _tabella(("Mario Rossi", Category.PERSONA))
        assert tagga("ROSSI MARIO paga.", tabella).mascherato == "ROSSI MARIO paga."

    def test_un_valore_assente_lascia_il_testo_intatto(self):
        tabella = _tabella(("Luigi Bianchi", Category.PERSONA))
        risultato = tagga("Mario Rossi paga.", tabella)
        assert risultato.mascherato == "Mario Rossi paga."
        assert risultato.regioni == []

    def test_le_regioni_si_riferiscono_al_testo_originale(self):
        tabella = _tabella(("Mario Rossi", Category.PERSONA))
        testo = "Il sig. Mario Rossi paga."
        regione = tagga(testo, tabella).regioni[0]
        assert testo[regione.start:regione.end] == "Mario Rossi"
        assert regione.tag == "[PERSONA_1]"

    def test_le_regioni_sono_ordinate_per_inizio(self):
        tabella = _tabella(
            ("Mario Rossi", Category.PERSONA), ("ACME s.r.l.", Category.AZIENDA)
        )
        regioni = tagga("ACME s.r.l. paga a Mario Rossi.", tabella).regioni
        assert [r.start for r in regioni] == sorted(r.start for r in regioni)

    def test_e_deterministica(self):
        tabella = _tabella(
            ("Mario Rossi", Category.PERSONA), ("Rossi", Category.PERSONA)
        )
        testo = "Mario Rossi, poi Rossi, poi Mario Rossi."
        assert tagga(testo, tabella).mascherato == tagga(testo, tabella).mascherato

    def test_il_testo_vuoto_non_esplode(self):
        assert tagga("", _tabella(("Mario Rossi", Category.PERSONA))).mascherato == ""


class TestContaOccorrenze:
    def test_un_tag_trovato_diventa_applicato(self):
        tabella = _tabella(("Mario Rossi", Category.PERSONA))
        aggiornata = conta_occorrenze(tabella, [tagga("Mario Rossi.", tabella)])
        assert aggiornata["[PERSONA_1]"].stato is StatoTag.APPLICATO
        assert aggiornata["[PERSONA_1]"].occorrenze == 1

    def test_somma_le_occorrenze_di_tutti_i_documenti(self):
        tabella = _tabella(("Mario Rossi", Category.PERSONA))
        mascherature = [
            tagga("Mario Rossi e Mario Rossi.", tabella),
            tagga("Ancora Mario Rossi.", tabella),
        ]
        assert conta_occorrenze(tabella, mascherature)["[PERSONA_1]"].occorrenze == 3

    def test_un_tag_che_nessun_documento_contiene_resta_non_trovato(self):
        """Il caso della §7: il modello ha normalizzato il valore. Il tag resta
        visibile, perché ignorarlo lascerebbe il dato in chiaro in silenzio."""
        tabella = _tabella(("Mario Rossi", Category.PERSONA))
        aggiornata = conta_occorrenze(tabella, [tagga("ROSSI MARIO.", tabella)])
        assert aggiornata["[PERSONA_1]"].stato is StatoTag.NON_TROVATO
        assert aggiornata["[PERSONA_1]"].occorrenze == 0

    def test_non_riaccende_un_tag_spento_dall_utente(self):
        """Spegnere un tag è una decisione dell'utente sulla riservatezza: un
        conteggio non può revocarla. Senza questa guardia, ricalcolare le
        occorrenze dopo un toggle rimetterebbe in maschera un dato che l'utente
        ha chiesto di lasciare in chiaro."""
        tabella = _tabella(("Mario Rossi", Category.PERSONA))
        spenta = {
            chiave: replace(tag, stato=StatoTag.DISATTIVATO)
            for chiave, tag in tabella.items()
        }
        aggiornata = conta_occorrenze(spenta, [tagga("Mario Rossi.", spenta)])
        assert aggiornata["[PERSONA_1]"].stato is StatoTag.DISATTIVATO

    def test_non_muta_la_tabella_ricevuta(self):
        tabella = _tabella(("Mario Rossi", Category.PERSONA))
        conta_occorrenze(tabella, [tagga("Mario Rossi.", tabella)])
        assert tabella["[PERSONA_1]"].occorrenze == 0
