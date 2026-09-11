from dataclasses import fields

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
    Entity,
    Source,
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
            documento("d1", "Email mario@example.com e anna@example.com."),
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

    def test_seconda_analisi_dello_stesso_documento_rifiutata(self):
        """`analizza_documento` non è idempotente: una seconda passata
        duplicherebbe gli span e la mascheratura, applicando due sostituzioni
        allo stesso intervallo, troncherebbe il documento dal primo segnaposto
        in poi. Il rifiuto è esplicito (ruling I4)."""
        f = fascicolo_vuoto("f1")
        doc = documento("d1", "Bonifico su IT60X0542811101000000123456 il 14/03/2024.")
        analizza_documento(f, doc, usa_ner=False)
        primi = list(f.spans)
        with pytest.raises(ValueError) as errore:
            analizza_documento(f, doc, usa_ner=False)
        assert "d1" in str(errore.value)
        assert f.spans == primi, "il rifiuto non deve lasciare tracce"

    def test_analisi_di_un_secondo_documento_resta_permessa(self):
        # il rifiuto è per documento, non per fascicolo: un fascicolo con
        # dieci documenti va analizzato documento per documento
        f = fascicolo_vuoto("f1")
        for doc_id in ("d1", "d2"):
            analizza_documento(f, documento(doc_id, "P. IVA 12345678903."),
                               usa_ner=False)
        assert {s.doc_id for s in f.spans} == {"d1", "d2"}

    def test_span_di_soli_titoli_restano_entita_distinte(self):
        """`normalizza("Sig.")` è la stringa vuota: senza guardia sulla chiave
        vuota due span di solo titolo si riconoscerebbero a vicenda e
        finirebbero sotto lo stesso segnaposto, così al ripristino uno dei due
        tornerebbe col valore dell'altro."""
        from cryptocustode.core.entities import aggiungi_span_manuale
        f = fascicolo_vuoto("f1")
        doc = documento("d1", "Il Sig. Rossi e il Sig. Bianchi firmano.")
        f.documents.append(doc)
        primo = doc.text.index("Sig.")
        secondo = doc.text.index("Sig.", primo + 1)
        a = aggiungi_span_manuale(f, doc, primo, primo + 4, Category.PERSONA)
        b = aggiungi_span_manuale(f, doc, secondo, secondo + 4, Category.PERSONA)
        assert normalizza("Sig.") == ""
        assert a.entity_id != b.entity_id
        assert len(f.entities) == 2

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


class TestAggiungiSpanManuale:
    """`aggiungi_span_manuale` è il punto d'ingresso pubblico per il tagging
    manuale del piano 2: qui arrivano interi scelti a mano da una persona,
    quindi vanno convalidati prima di fidarsene (spec §7)."""

    def _fascicolo_con_doc(self, testo="Mario Rossi vive a Torino."):
        f = fascicolo_vuoto("f1")
        doc = documento("d1", testo)
        f.documents.append(doc)
        return f, doc

    def test_range_invertito_solleva_errore(self):
        from cryptocustode.core.entities import aggiungi_span_manuale
        f, doc = self._fascicolo_con_doc()
        with pytest.raises(ValueError) as errore:
            aggiungi_span_manuale(f, doc, 10, 5, Category.PERSONA)
        assert "10" in str(errore.value)
        assert "5" in str(errore.value)

    def test_range_a_lunghezza_zero_solleva_errore(self):
        from cryptocustode.core.entities import aggiungi_span_manuale
        f, doc = self._fascicolo_con_doc()
        with pytest.raises(ValueError):
            aggiungi_span_manuale(f, doc, 5, 5, Category.PERSONA)

    def test_fine_oltre_la_fine_del_testo_solleva_errore(self):
        from cryptocustode.core.entities import aggiungi_span_manuale
        f, doc = self._fascicolo_con_doc()
        fine_richiesta = len(doc.text) + 5
        with pytest.raises(ValueError) as errore:
            aggiungi_span_manuale(f, doc, 0, fine_richiesta, Category.PERSONA)
        assert str(fine_richiesta) in str(errore.value)

    def test_inizio_negativo_solleva_errore(self):
        from cryptocustode.core.entities import aggiungi_span_manuale
        f, doc = self._fascicolo_con_doc()
        with pytest.raises(ValueError) as errore:
            aggiungi_span_manuale(f, doc, -1, 5, Category.PERSONA)
        assert "-1" in str(errore.value)

    def test_documento_non_del_fascicolo_solleva_errore(self):
        from cryptocustode.core.entities import aggiungi_span_manuale
        f = fascicolo_vuoto("f1")  # nessun documento caricato
        estraneo = documento("estraneo", "Testo di un documento mai caricato.")
        with pytest.raises(ValueError) as errore:
            aggiungi_span_manuale(f, estraneo, 0, 5, Category.PERSONA)
        assert "estraneo" in str(errore.value)

    def test_sovrapposizione_con_span_esistente_solleva_errore(self):
        from cryptocustode.core.entities import aggiungi_span_manuale
        f, doc = self._fascicolo_con_doc("CF RSSMRA85M01H501Q per il cliente.")
        analizza_documento(f, doc, usa_ner=False)
        cf = next(s for s in f.spans if s.category is Category.CF)
        with pytest.raises(ValueError) as errore:
            aggiungi_span_manuale(f, doc, cf.start, cf.end, Category.PERSONA)
        assert cf.span_id in str(errore.value)

    def test_range_non_valido_non_brucia_segnaposto_ne_crea_span(self):
        """Un rifiuto non deve lasciare tracce: niente entità, niente span,
        niente indice bruciato sul contatore (spec §5)."""
        from cryptocustode.core.entities import aggiungi_span_manuale
        f, doc = self._fascicolo_con_doc()
        with pytest.raises(ValueError):
            aggiungi_span_manuale(f, doc, 10, 5, Category.PERSONA)
        assert f.counters[Category.PERSONA] == 0
        assert f.entities == {}
        assert f.spans == []

    def test_percorso_felice_crea_entita_e_segnaposto(self):
        from cryptocustode.core.entities import aggiungi_span_manuale
        f, doc = self._fascicolo_con_doc(
            "Contratto con Giulia Neri, libera professionista."
        )
        inizio = doc.text.index("Giulia Neri")
        fine = inizio + len("Giulia Neri")
        span = aggiungi_span_manuale(f, doc, inizio, fine, Category.PERSONA)
        assert span in f.spans
        assert span.doc_id == doc.doc_id
        assert span.category is Category.PERSONA
        entita = f.entities[span.entity_id]
        assert entita.category is Category.PERSONA
        assert entita.canonical_value == "Giulia Neri"
        assert entita.placeholder == "[PERSONA_1]"


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

    def test_omonimia_registra_gli_span_delle_occorrenze(self):
        """`occurrence_span_ids` è il campo che la coda di revisione userà per
        mostrare all'utente *dove* compare l'omonimia: deve contenere
        esattamente gli span dell'entità ambigua, non una lista vuota."""
        from cryptocustode.core.entities import risolvi_ambiguita_omonimia
        f = self._fascicolo_con_omonimo()
        risolvi_ambiguita_omonimia(f)
        bloccanti = [a for a in f.ambiguities if a.blocca_approvazione]
        entity_id = bloccanti[0].candidate_entity_ids[0]
        attesi = [s.span_id for s in f.spans if s.entity_id == entity_id]
        assert len(attesi) == 2
        assert bloccanti[0].occurrence_span_ids == attesi


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
        f.documents.append(doc)
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

    def test_suggerimento_registra_gli_span_delle_occorrenze(self):
        """Come per l'omonimia: la coda di revisione ha bisogno di sapere dove
        compaiono le due varianti, non solo che sono candidate alla fusione."""
        from cryptocustode.core.entities import suggerisci_fusioni
        f = self._fascicolo_con("M. Rossi", "Mario Rossi")
        suggerisci_fusioni(f)
        suggerimento = f.ambiguities[0]
        attesi = [
            s.span_id for s in f.spans
            if s.entity_id in suggerimento.candidate_entity_ids
        ]
        assert len(attesi) == 2
        assert sorted(suggerimento.occurrence_span_ids) == sorted(attesi)

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


class TestIlCodiceFiscaleNonLegaLePersone:
    """Emendamento della spec §7 deciso nella issue #12.

    Il codice fiscale viene mascherato come entità a sé, ma non viene mai
    legato a una persona: nessuna regola dice quale CF appartiene a quale
    nome, e sbagliare quel legame fonderebbe due persone diverse. Il rischio
    accettato è la *mancata* fusione, mai la fusione errata (spec §2,
    decisione 3).
    """

    def test_il_modello_non_porta_un_legame_persona_codice_fiscale(self):
        """La spec non promette più il legame, quindi il tipo non deve
        offrirne il posto: un campo che nessuno popola è una promessa che il
        prossimo lettore crederà mantenuta."""
        assert "cf" not in {campo.name for campo in fields(Entity)}

    def test_due_omonimi_con_cf_diversi_restano_un_solo_segnaposto(self):
        """Fissa il limite accettato, non un comportamento desiderabile.

        Padre e figlio con lo stesso nome e due CF diversi nello stesso
        documento condividono `[PERSONA_1]`: al ripristino uno riceverebbe il
        nome dell'altro. È il prezzo dichiarato nella §16, e nessuna coda
        avvisa l'utente. Se qualcuno implementerà la legatura CF-persona
        questo test fallirà, ed è il suo scopo: obbligarlo a emendare la §7
        invece di cambiare il comportamento di straforo.
        """
        from cryptocustode.core.entities import (
            risolvi_ambiguita_omonimia,
            suggerisci_fusioni,
        )
        testo = (
            "Comparsi Marco Rossi, C.F. RSSMRC50A01H501Q, "
            "e suo figlio Marco Rossi, C.F. RSSMRC80A01H501W."
        )
        doc = documento("d1", testo)
        f = fascicolo_vuoto("f1")
        f.documents.append(doc)
        analizza_documento(f, doc, usa_ner=False)
        for inizio in (testo.index("Marco Rossi"), testo.rindex("Marco Rossi")):
            _registra_manuale(f, doc, inizio, inizio + len("Marco Rossi"))
        suggerisci_fusioni(f)
        risolvi_ambiguita_omonimia(f)

        codici = [e for e in f.entities.values() if e.category is Category.CF]
        persone = [e for e in f.entities.values() if e.category is Category.PERSONA]
        assert sorted(e.placeholder for e in codici) == ["[CF_1]", "[CF_2]"]
        assert [e.placeholder for e in persone] == ["[PERSONA_1]"]
        assert len([s for s in f.spans if s.category is Category.PERSONA]) == 2
        assert f.ambiguities == []


def _registra_manuale(fascicolo, documento, inizio, fine):
    """Aggiunge uno span PERSONA come se l'utente lo avesse selezionato a mano."""
    from cryptocustode.core.entities import aggiungi_span_manuale
    if documento not in fascicolo.documents:
        fascicolo.documents.append(documento)
    aggiungi_span_manuale(fascicolo, documento, inizio, fine, Category.PERSONA)
