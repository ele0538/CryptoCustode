"""`assegna_tag` e `tagga`: dai valori del modello al testo mascherato (spec §7)."""

from cryptocustode.core.models import Category, Rilevazione, StatoTag
from cryptocustode.core.tagga import assegna_tag

VUOTI: dict[Category, int] = {}


def _rilevazione(valore: str, categoria: Category = Category.PERSONA) -> Rilevazione:
    return Rilevazione(valore=valore, categoria=categoria)


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
