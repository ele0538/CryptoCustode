"""Suggerimento di fusione fra tag, sul modello a tag (issue #51).

È la metà della disambiguazione di `feat/p6-disambiguazione` che sopravvive al
passaggio a Gemini. L'altra metà — l'omonimia bloccante, due persone diverse
che si chiamano entrambe «Mario Rossi» — non è portabile e non è portata:
`assegna_tag` deduplica per valore esatto e il modello non restituisce offset,
quindi due omonimi sono **un tag solo per costruzione**, e non c'è niente da
separare. Resta il limite noto 2 della spec §16.

Qui si prova il contrario: due tag distinti che forse sono la stessa cosa.
`[PERSONA_1] "Mario Rossi"` e `[PERSONA_2] "M. Rossi"` oggi vanno all'IA
esterna come due persone diverse, ed è un peggioramento della risposta che
l'utente può sanare — se vuole lui, perché fondere per errore è l'errore caro
(spec §7).
"""

import pytest

from cryptocustode.core.fusioni import CATEGORIE_CON_VARIANTI, fondi, suggerisci
from cryptocustode.core.models import Category, FusioneSuggerita, StatoTag, Tag
from cryptocustode.core.tagga import dizionario_di, tagga


def tag(segnaposto: str, categoria: Category, valore: str, *varianti: str) -> Tag:
    return Tag(
        tag=segnaposto,
        categoria=categoria,
        valore=valore,
        occorrenze=1,
        stato=StatoTag.APPLICATO,
        varianti=tuple(varianti),
    )


def tabella(*tags: Tag) -> dict[str, Tag]:
    return {t.tag: t for t in tags}


MARIO = tag("[PERSONA_1]", Category.PERSONA, "Mario Rossi")
M_ROSSI = tag("[PERSONA_2]", Category.PERSONA, "M. Rossi")
ANNA = tag("[PERSONA_3]", Category.PERSONA, "Anna Bianchi")


class TestSuggerisci:
    def test_due_scritture_equivalenti_aprono_un_suggerimento(self):
        proposte = suggerisci(tabella(MARIO, M_ROSSI), [])

        assert len(proposte) == 1
        assert {proposte[0].tag_a, proposte[0].tag_b} == {"[PERSONA_1]", "[PERSONA_2]"}
        assert proposte[0].categoria is Category.PERSONA
        assert proposte[0].risolta is False

    def test_nomi_diversi_non_aprono_niente(self):
        assert suggerisci(tabella(MARIO, ANNA), []) == []

    def test_una_persona_e_un_azienda_restano_due_cose_diverse(self):
        """Fonderle darebbe a una il segnaposto dell'altra, ed è esattamente il
        danno che la spec §7 dichiara irreversibile."""
        azienda = tag("[AZIENDA_1]", Category.AZIENDA, "Mario Rossi")

        assert suggerisci(tabella(MARIO, azienda), []) == []

    @pytest.mark.parametrize(
        "categoria", sorted(set(Category) - CATEGORIE_CON_VARIANTI, key=lambda c: c.value)
    )
    def test_le_categorie_senza_varianti_non_si_confrontano(self, categoria):
        """Su un IBAN, un CF o un importo l'uguaglianza è esatta o non è: due
        scritture diverse sono due dati diversi, e un'euristica sui token non
        ha alcun titolo per accostarli."""
        uno = tag("[X_1]".replace("X", categoria.value), categoria, "AB 12")
        due = tag("[X_2]".replace("X", categoria.value), categoria, "12 AB")

        assert suggerisci(tabella(uno, due), []) == []

    def test_un_suggerimento_gia_aperto_non_si_ripropone(self):
        """L'analisi è rieseguibile: senza questa guardia ogni clic su
        «Analizza» riaprirebbe le coppie che l'utente ha già deciso."""
        prima = suggerisci(tabella(MARIO, M_ROSSI), [])

        assert suggerisci(tabella(MARIO, M_ROSSI), prima) == []

    def test_una_coppia_gia_decisa_resta_chiusa(self):
        deciso = FusioneSuggerita(
            fusione_id="[PERSONA_1]+[PERSONA_2]",
            categoria=Category.PERSONA,
            tag_a="[PERSONA_1]",
            tag_b="[PERSONA_2]",
            risolta=True,
        )

        assert suggerisci(tabella(MARIO, M_ROSSI), [deciso]) == []

    def test_l_identificativo_e_deterministico(self):
        """Non un UUID: due esecuzioni sullo stesso fascicolo devono produrre
        gli stessi identificativi, altrimenti la pagina aperta dall'utente
        manderebbe indietro un id che non esiste più dopo una rianalisi."""
        una = suggerisci(tabella(MARIO, M_ROSSI), [])
        altra = suggerisci(tabella(MARIO, M_ROSSI), [])

        assert una[0].fusione_id == altra[0].fusione_id
        assert una[0].fusione_id == "[PERSONA_1]+[PERSONA_2]"

    def test_la_coppia_e_ordinata_per_indice(self):
        """`tag_a` è sempre il segnaposto più vecchio: è quello che
        sopravvivrebbe alla fusione, e mostrarli in ordine sparso farebbe
        sembrare arbitrario quale dei due resta."""
        proposte = suggerisci(tabella(M_ROSSI, MARIO), [])

        assert proposte[0].tag_a == "[PERSONA_1]"
        assert proposte[0].tag_b == "[PERSONA_2]"


class TestFondi:
    def test_il_segnaposto_piu_vecchio_sopravvive(self):
        """Spec §5: `[PERSONA_2]` finisce in `[PERSONA_1]`, e il 2 resta
        bruciato. Far sopravvivere il più recente cambierebbe il segnaposto di
        un dato già consegnato a un'IA esterna."""
        fusa = fondi(tabella(MARIO, M_ROSSI), "[PERSONA_1]", "[PERSONA_2]")

        assert set(fusa) == {"[PERSONA_1]"}
        assert fusa["[PERSONA_1]"].valore == "Mario Rossi"

    def test_il_valore_assorbito_diventa_una_variante(self):
        fusa = fondi(tabella(MARIO, M_ROSSI), "[PERSONA_1]", "[PERSONA_2]")

        assert fusa["[PERSONA_1]"].varianti == ("M. Rossi",)

    def test_le_varianti_si_sommano(self):
        """Un documento caricato dopo, che usi la forma assorbita, finisce
        sotto lo stesso segnaposto invece di aprire un terzo tag."""
        con_variante = tag("[PERSONA_1]", Category.PERSONA, "Mario Rossi", "Rossi Mario")
        altro = tag("[PERSONA_2]", Category.PERSONA, "M. Rossi", "M Rossi")

        fusa = fondi(tabella(con_variante, altro), "[PERSONA_1]", "[PERSONA_2]")

        assert set(fusa["[PERSONA_1]"].varianti) == {"Rossi Mario", "M. Rossi", "M Rossi"}

    def test_l_ordine_degli_argomenti_non_decide_chi_sopravvive(self):
        """Chi sopravvive lo dice l'indice, non l'ordine in cui la richiesta è
        arrivata: una UI che invertisse i due campi non deve poter bruciare il
        segnaposto sbagliato."""
        fusa = fondi(tabella(MARIO, M_ROSSI), "[PERSONA_2]", "[PERSONA_1]")

        assert set(fusa) == {"[PERSONA_1]"}

    def test_fondere_categorie_diverse_e_rifiutato(self):
        azienda = tag("[AZIENDA_1]", Category.AZIENDA, "Mario Rossi")

        with pytest.raises(ValueError, match="categorie diverse"):
            fondi(tabella(MARIO, azienda), "[PERSONA_1]", "[AZIENDA_1]")

    def test_fondere_un_tag_assente_e_rifiutato(self):
        with pytest.raises(ValueError, match="assenti"):
            fondi(tabella(MARIO), "[PERSONA_1]", "[PERSONA_9]")

    def test_fondere_un_tag_con_se_stesso_e_rifiutato(self):
        with pytest.raises(ValueError, match="due tag distinti"):
            fondi(tabella(MARIO), "[PERSONA_1]", "[PERSONA_1]")

    def test_un_rifiuto_non_lascia_tracce(self):
        """I controlli stanno tutti prima della prima mutazione: una fusione
        impossibile non deve lasciare metà tabella riscritta."""
        originale = tabella(MARIO, M_ROSSI)
        copia = dict(originale)

        with pytest.raises(ValueError):
            fondi(originale, "[PERSONA_1]", "[PERSONA_9]")

        assert originale == copia

    def test_la_tabella_di_partenza_non_viene_mutata(self):
        originale = tabella(MARIO, M_ROSSI)

        fondi(originale, "[PERSONA_1]", "[PERSONA_2]")

        assert set(originale) == {"[PERSONA_1]", "[PERSONA_2]"}


class TestVariantiNelTesto:
    """Il punto in cui la fusione diventa visibile: `tagga` deve sostituire
    anche le varianti, altrimenti il suggerimento accettato non cambierebbe una
    virgola del testo consegnato."""

    def test_la_variante_prende_il_segnaposto_del_tag(self):
        fusa = fondi(tabella(MARIO, M_ROSSI), "[PERSONA_1]", "[PERSONA_2]")

        esito = tagga("Mario Rossi e M. Rossi firmano.", fusa)

        assert esito.mascherato == "[PERSONA_1] e [PERSONA_1] firmano."

    def test_le_occorrenze_della_variante_sono_regioni_del_tag(self):
        fusa = fondi(tabella(MARIO, M_ROSSI), "[PERSONA_1]", "[PERSONA_2]")

        esito = tagga("Mario Rossi e M. Rossi firmano.", fusa)

        assert [regione.tag for regione in esito.regioni] == ["[PERSONA_1]"] * 2

    def test_il_valore_piu_lungo_rivendica_per_primo_anche_fra_varianti(self):
        """La regola che impedisce a «Rossi» di finire dentro «Mario Rossi»
        deve valere sull'insieme di valori e varianti, non su un valore per
        tag: ordinare i tag e poi guardare la sola `valore` lascerebbe una
        variante corta mordere dentro una lunga di un altro tag."""
        lungo = tag("[PERSONA_1]", Category.PERSONA, "Mario Rossi")
        corto = tag("[PERSONA_2]", Category.PERSONA, "Anna Neri", "Rossi")

        esito = tagga("Mario Rossi paga.", tabella(lungo, corto))

        assert esito.mascherato == "[PERSONA_1] paga."

    def test_il_dizionario_di_ripristino_porta_il_valore_canonico(self):
        """Ed è la perdita dichiarata della fusione: la variante non torna come
        era scritta, torna come il valore canonico. È il senso stesso di aver
        detto che sono la stessa persona."""
        fusa = fondi(tabella(MARIO, M_ROSSI), "[PERSONA_1]", "[PERSONA_2]")

        assert dizionario_di(fusa) == {"[PERSONA_1]": "Mario Rossi"}
