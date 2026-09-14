"""L'euristica sui nomi: quando due scritture possono indicare la stessa cosa.

Modulo puro e test puri: nessun fascicolo, nessuna rete, nessun modello. È la
metà della disambiguazione di `feat/p6-disambiguazione` che sopravvive al
passaggio a Gemini, perché confronta stringhe e non ha mai avuto bisogno degli
offset che il modello non restituisce.

**Queste funzioni non fondono niente.** Producono un suggerimento che l'utente
accetta o ignora, ed è la traduzione in codice del principio della spec §7:
fondere per errore rivela il nome di una persona al posto di un'altra, separare
per errore degrada soltanto la qualità della risposta dell'IA. Quindi separare
è il default, e l'euristica non decide.
"""

import pytest

from cryptocustode.core.nomi import TITOLI, chiavi_equivalenti, normalizza


class TestNormalizza:
    def test_il_titolo_e_gli_spazi_non_contano(self):
        assert normalizza("Sig. Mario  Rossi") == normalizza("mario rossi")

    @pytest.mark.parametrize("titolo", TITOLI)
    def test_ogni_titolo_riconosciuto_viene_tolto(self, titolo):
        assert normalizza(f"{titolo} Anna Bianchi") == normalizza("anna bianchi")

    def test_le_corse_di_spazi_si_collassano(self):
        assert normalizza("Mario   Rossi") == "mario rossi"

    def test_i_titoli_impilati_se_ne_vanno_tutti(self):
        """«Spett.le Sig. Rossi» ne ha due: toglierne uno solo lascerebbe una
        chiave che non combacia con nessun'altra scrittura dello stesso nome."""
        assert normalizza("Spett.le Sig. Rossi") == "rossi"

    def test_un_titolo_da_solo_si_riduce_a_niente(self):
        """È il caso che obbliga chi chiama a guardarsi dalla chiave vuota: due
        valori diversi che si normalizzano entrambi a "" non sono equivalenti,
        sono entrambi illeggibili."""
        assert normalizza("Sig.") == ""

    def test_la_normalizzazione_e_solo_una_chiave_di_confronto(self):
        """Il valore originale non va mai perso: è quello che `tagga` cerca nel
        testo carattere per carattere, e un valore normalizzato nel dizionario
        ripristinerebbe un nome in minuscolo e senza titolo al posto di quello
        vero."""
        assert normalizza("Sig. Mario Rossi") != "Sig. Mario Rossi"


class TestChiaviEquivalenti:
    def test_l_ordine_dei_token_non_conta(self):
        assert chiavi_equivalenti("Rossi Mario", "Mario Rossi") is True

    def test_un_iniziale_puntata_combacia_con_il_nome_intero(self):
        assert chiavi_equivalenti("M. Rossi", "Mario Rossi") is True

    def test_un_iniziale_diversa_non_combacia(self):
        assert chiavi_equivalenti("G. Rossi", "Mario Rossi") is False

    def test_cognomi_diversi_non_combaciano(self):
        assert chiavi_equivalenti("Mario Rossi", "Mario Bianchi") is False

    def test_un_numero_di_token_diverso_non_combacia(self):
        """«Mario Rossi» e «Mario Rossi Bianchi» possono benissimo essere due
        persone, e suggerirne la fusione spingerebbe verso l'errore che la
        spec §7 dichiara il più caro."""
        assert chiavi_equivalenti("Mario Rossi", "Mario Rossi Bianchi") is False

    def test_la_chiave_vuota_non_equivale_a_niente(self):
        """Senza questa guardia due titoli nudi si fonderebbero fra loro, e
        peggio: qualunque valore che si riduce a "" diventerebbe equivalente a
        ogni altro."""
        assert chiavi_equivalenti("Sig.", "Dott.") is False
        assert chiavi_equivalenti("", "Mario Rossi") is False

    def test_e_riflessiva_e_simmetrica(self):
        """Un suggerimento che dipendesse dall'ordine degli argomenti aprirebbe
        due volte la stessa coppia, una per verso."""
        assert chiavi_equivalenti("Mario Rossi", "Mario Rossi") is True
        assert chiavi_equivalenti("M. Rossi", "Mario Rossi") is chiavi_equivalenti(
            "Mario Rossi", "M. Rossi"
        )

    def test_il_titolo_non_sposta_il_verdetto(self):
        assert chiavi_equivalenti("Sig. Mario Rossi", "mario   rossi") is True
