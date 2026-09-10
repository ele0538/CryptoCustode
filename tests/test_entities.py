import pytest

from cryptocustode.core.entities import (
    analizza_documento,
    chiavi_equivalenti,
    normalizza,
    prossimo_placeholder,
)
from cryptocustode.core.models import (
    AmbiguityKind,
    Category,
    Document,
    Source,
    Span,
    fascicolo_vuoto,
)


def documento(doc_id: str, testo: str) -> Document:
    return Document(doc_id=doc_id, filename=f"{doc_id}.txt", text=testo,
                    page_offsets=[0], sha256="x")


class TestNormalizzazione:
    def test_rimuove_titoli_e_uniforma(self):
        assert normalizza("Sig. Mario  Rossi") == normalizza("mario rossi")

    def test_rimuove_titoli_femminili_e_professionali(self):
        for titolo in ["Sig.ra", "Dott.ssa", "Avv.", "Ing.", "Geom.", "Rag."]:
            assert normalizza(f"{titolo} Anna Bianchi") == normalizza("anna bianchi")

    def test_uniforma_spazi_multipli(self):
        assert normalizza("Mario   Rossi") == "mario rossi"


class TestEuristiche:
    def test_ordine_dei_token_indifferente(self):
        assert chiavi_equivalenti("Rossi Mario", "Mario Rossi") is True

    def test_iniziale_compatibile(self):
        assert chiavi_equivalenti("M. Rossi", "Mario Rossi") is True

    def test_iniziale_incompatibile(self):
        assert chiavi_equivalenti("G. Rossi", "Mario Rossi") is False

    def test_cognomi_diversi_non_equivalenti(self):
        assert chiavi_equivalenti("Mario Rossi", "Mario Bianchi") is False


class TestSegnaposto:
    def test_indice_incrementale_per_tipo(self):
        f = fascicolo_vuoto("f1")
        assert prossimo_placeholder(f, Category.PERSONA) == "[PERSONA_1]"
        assert prossimo_placeholder(f, Category.PERSONA) == "[PERSONA_2]"
        assert prossimo_placeholder(f, Category.IBAN) == "[IBAN_1]"

    def test_gli_indici_non_vengono_riciclati(self):
        f = fascicolo_vuoto("f1")
        prossimo_placeholder(f, Category.PERSONA)
        prossimo_placeholder(f, Category.PERSONA)
        f.entities.clear()  # come se un'entità fosse stata fusa via
        assert prossimo_placeholder(f, Category.PERSONA) == "[PERSONA_3]"


class TestAggregazione:
    def test_stesso_valore_nello_stesso_documento_e_una_sola_entita(self):
        f = fascicolo_vuoto("f1")
        doc = documento("d1", "IBAN IT60X0542811101000000123456 e ancora "
                              "IT60X0542811101000000123456.")
        analizza_documento(f, doc, usa_ner=False)
        iban = [e for e in f.entities.values() if e.category is Category.IBAN]
        assert len(iban) == 1
        assert len([s for s in f.spans if s.category is Category.IBAN]) == 2

    def test_stesso_valore_in_documenti_diversi_usa_lo_stesso_segnaposto(self):
        f = fascicolo_vuoto("f1")
        for doc_id in ("d1", "d2"):
            analizza_documento(
                f, documento(doc_id, "Bonifico su IT60X0542811101000000123456."),
                usa_ner=False,
            )
        iban = [e for e in f.entities.values() if e.category is Category.IBAN]
        assert len(iban) == 1
        assert iban[0].placeholder == "[IBAN_1]"

    def test_valori_diversi_ottengono_segnaposto_diversi(self):
        f = fascicolo_vuoto("f1")
        analizza_documento(
            f,
            documento("d1", "Email mario@esempio.it e anna@esempio.it."),
            usa_ner=False,
        )
        email = sorted(
            e.placeholder for e in f.entities.values() if e.category is Category.EMAIL
        )
        assert email == ["[EMAIL_1]", "[EMAIL_2]"]

    def test_gli_span_risultanti_non_si_sovrappongono(self):
        f = fascicolo_vuoto("f1")
        analizza_documento(
            f,
            documento("d1", "CF RSSMRA85M01H501Q, P. IVA 12345678903, "
                            "firmato il 14/03/2024 per € 1.250,00."),
            usa_ner=False,
        )
        ordinati = sorted(f.spans, key=lambda s: s.start)
        for precedente, successivo in zip(ordinati, ordinati[1:]):
            assert precedente.end <= successivo.start

    def test_ogni_span_ha_una_entita(self):
        f = fascicolo_vuoto("f1")
        analizza_documento(f, documento("d1", "P. IVA 12345678903."), usa_ner=False)
        for span in f.spans:
            assert span.entity_id in f.entities

    @pytest.mark.lento
    def test_il_percorso_di_default_unisce_regole_e_ner(self):
        """`usa_ner=True` è il default e il percorso di produzione: è qui che
        regole e NER confluiscono in un solo insieme di entità. Ogni altro test
        lo evita per non caricare il modello, quindi senza questo non verrebbe
        mai eseguito."""
        f = fascicolo_vuoto("f1")
        analizza_documento(f, documento(
            "d1", "Il presente contratto è sottoscritto da Mario Rossi, "
                  "IBAN IT60X0542811101000000123456.",
        ))
        persone = [e for e in f.entities.values() if e.category is Category.PERSONA]
        iban = [e for e in f.entities.values() if e.category is Category.IBAN]
        assert any("Rossi" in e.canonical_value for e in persone)
        assert len(iban) == 1
        assert {s.source for s in f.spans} >= {Source.NER, Source.RULE}
        for span in f.spans:
            assert span.entity_id in f.entities


class TestOmonimi:
    def _fascicolo_con_omonimo(self):
        f = fascicolo_vuoto("f1")
        for doc_id in ("d1", "d2"):
            doc = documento(doc_id, "Contratto con Giuseppe Verdi.")
            analizza_documento(f, doc, usa_ner=False)
            # simulo l'esito del NER senza caricare il modello
            inizio = doc.text.index("Giuseppe Verdi")
            _registra_manuale(f, doc, inizio, inizio + len("Giuseppe Verdi"))
        return f

    def test_omonimia_senza_cf_apre_una_ambiguita_bloccante(self):
        from cryptocustode.core.entities import risolvi_ambiguita_omonimia
        f = self._fascicolo_con_omonimo()
        risolvi_ambiguita_omonimia(f)
        bloccanti = [a for a in f.ambiguities if a.blocca_approvazione]
        assert len(bloccanti) == 1
        assert bloccanti[0].kind is AmbiguityKind.SAME_NAME_NO_CF


class TestSuggerimentiDiFusione:
    """`chiavi_equivalenti` è un suggerimento, non una fusione: deve arrivare
    all'utente come ambiguità non bloccante (spec §7)."""

    def _fascicolo_con(self, *nomi: str):
        f = fascicolo_vuoto("f1")
        for indice, nome in enumerate(nomi, start=1):
            doc = documento(f"d{indice}", f"Delega firmata da {nome} in data odierna.")
            analizza_documento(f, doc, usa_ner=False)
            # simulo l'esito del NER senza caricare il modello
            inizio = doc.text.index(nome)
            _registra_manuale(f, doc, inizio, inizio + len(nome))
        return f

    def test_variante_del_nome_apre_un_suggerimento_non_bloccante(self):
        from cryptocustode.core.entities import suggerisci_fusioni
        f = self._fascicolo_con("M. Rossi", "Mario Rossi")
        assert len(f.entities) == 2, "le due varianti restano entità separate"
        suggerisci_fusioni(f)
        assert len(f.ambiguities) == 1
        suggerimento = f.ambiguities[0]
        assert suggerimento.kind is AmbiguityKind.HEURISTIC_MERGE_SUGGESTION
        assert suggerimento.category is Category.PERSONA
        assert sorted(suggerimento.candidate_entity_ids) == sorted(f.entities)
        assert suggerimento.blocca_approvazione is False

    def test_nomi_incompatibili_non_generano_suggerimenti(self):
        from cryptocustode.core.entities import suggerisci_fusioni
        f = self._fascicolo_con("Mario Rossi", "Anna Bianchi")
        suggerisci_fusioni(f)
        assert f.ambiguities == []

    def test_persona_e_azienda_non_si_suggeriscono_a_vicenda(self):
        """I due nomi sono equivalenti per l'euristica: a tenerli separati deve
        essere la categoria, non il caso."""
        from cryptocustode.core.entities import (
            aggiungi_span_manuale,
            suggerisci_fusioni,
        )
        f = fascicolo_vuoto("f1")
        doc = documento(
            "d1", "Il socio Rossi Mario conferisce alla ditta Mario Rossi "
                  "il ramo d'azienda.",
        )
        for nome, categoria in (
            ("Rossi Mario", Category.PERSONA),
            ("Mario Rossi", Category.AZIENDA),
        ):
            inizio = doc.text.index(nome)
            aggiungi_span_manuale(f, doc, inizio, inizio + len(nome), categoria)
        assert chiavi_equivalenti("Rossi Mario", "Mario Rossi") is True
        suggerisci_fusioni(f)
        assert f.ambiguities == []

    def test_il_suggerimento_non_viene_duplicato(self):
        from cryptocustode.core.entities import suggerisci_fusioni
        f = self._fascicolo_con("Rossi Mario", "Mario Rossi")
        suggerisci_fusioni(f)
        suggerisci_fusioni(f)
        assert len(f.ambiguities) == 1

    def test_le_due_code_convivono(self):
        """Omonimie e suggerimenti scrivono nella stessa lista: nessuno dei due
        deve nascondere o duplicare le ambiguità dell'altro, in qualunque
        ordine vengano invocati (li chiamerà il piano 2)."""
        from cryptocustode.core.entities import (
            risolvi_ambiguita_omonimia,
            suggerisci_fusioni,
        )
        f = self._fascicolo_con("M. Rossi", "Mario Rossi")
        for indice in (3, 4):  # lo stesso nome in due documenti: omonimia
            doc = documento(f"d{indice}", "Atto con Giuseppe Verdi.")
            inizio = doc.text.index("Giuseppe Verdi")
            _registra_manuale(f, doc, inizio, inizio + len("Giuseppe Verdi"))
        for _ in range(2):
            suggerisci_fusioni(f)
            risolvi_ambiguita_omonimia(f)
        assert sorted(a.kind for a in f.ambiguities) == [
            AmbiguityKind.HEURISTIC_MERGE_SUGGESTION, AmbiguityKind.SAME_NAME_NO_CF,
        ]
        assert [a.blocca_approvazione for a in f.ambiguities].count(True) == 1


def _registra_manuale(fascicolo, documento, inizio, fine):
    """Aggiunge uno span PERSONA come se l'utente lo avesse selezionato a mano."""
    from cryptocustode.core.entities import aggiungi_span_manuale
    aggiungi_span_manuale(fascicolo, documento, inizio, fine, Category.PERSONA)
