import dataclasses
import re

import pytest

from cryptocustode.core.mask import (
    hash_approvazione,
    maschera,
    maschera_documento,
    span_attivo,
)
from cryptocustode.core.models import (
    Category,
    Document,
    Entity,
    Source,
    Span,
    State,
    fascicolo_vuoto,
)

FORMATO_SEGNAPOSTO = re.compile(r"\[[A-Z]+_\d+\]")


def scenario():
    """Un fascicolo con un documento, due entità e due span."""
    testo = "Mario Rossi paga a Anna Bianchi la somma dovuta."
    doc = Document(doc_id="d1", filename="contratto.txt", text=testo,
                   page_offsets=[0], sha256="x")
    f = fascicolo_vuoto("f1")
    f.documents.append(doc)
    f.entities["e1"] = Entity(
        entity_id="e1", category=Category.PERSONA, placeholder="[PERSONA_1]",
        canonical_value="Mario Rossi", variants={"Mario Rossi"},
    )
    f.entities["e2"] = Entity(
        entity_id="e2", category=Category.PERSONA, placeholder="[PERSONA_2]",
        canonical_value="Anna Bianchi", variants={"Anna Bianchi"},
    )
    f.spans.append(Span(span_id="s1", doc_id="d1", start=0, end=11,
                        category=Category.PERSONA, source=Source.NER, entity_id="e1"))
    f.spans.append(Span(span_id="s2", doc_id="d1", start=19, end=31,
                        category=Category.PERSONA, source=Source.NER, entity_id="e2"))
    return f, doc


class TestMascheratura:
    def test_sostituisce_tutti_gli_span(self):
        f, doc = scenario()
        assert maschera_documento(f, doc) == (
            "[PERSONA_1] paga a [PERSONA_2] la somma dovuta."
        )

    def test_nessun_valore_originale_sopravvive(self):
        f, doc = scenario()
        mascherato = maschera_documento(f, doc)
        for entita in f.entities.values():
            for variante in entita.variants:
                assert variante not in mascherato

    def test_i_segnaposto_rispettano_il_formato(self):
        f, doc = scenario()
        for trovato in FORMATO_SEGNAPOSTO.finditer(maschera_documento(f, doc)):
            assert trovato.group(0).startswith("[PERSONA_")

    def test_span_disabilitato_non_viene_mascherato(self):
        f, doc = scenario()
        f.spans[0] = dataclasses.replace(f.spans[0], enabled=False)
        mascherato = maschera_documento(f, doc)
        assert "Mario Rossi" in mascherato
        assert "[PERSONA_2]" in mascherato

    def test_categoria_disattivata_non_viene_mascherata(self):
        f, doc = scenario()
        f.category_enabled[Category.PERSONA] = False
        assert maschera_documento(f, doc) == doc.text

    def test_span_attivo_richiede_entrambi_gli_interruttori(self):
        f, _ = scenario()
        span = f.spans[0]
        assert span_attivo(span, f) is True
        f.category_enabled[Category.PERSONA] = False
        assert span_attivo(span, f) is False

    def test_ordine_di_sostituzione_non_corrompe_gli_offset(self):
        # tre span consecutivi: se si sostituisse da sinistra, gli offset
        # successivi slitterebbero
        testo = "AAAA BBBB CCCC"
        doc = Document(doc_id="d1", filename="a.txt", text=testo,
                       page_offsets=[0], sha256="x")
        f = fascicolo_vuoto("f1")
        f.documents.append(doc)
        for indice, (inizio, fine) in enumerate([(0, 4), (5, 9), (10, 14)], start=1):
            f.entities[f"e{indice}"] = Entity(
                entity_id=f"e{indice}", category=Category.PRATICA,
                placeholder=f"[PRATICA_{indice}]",
                canonical_value=testo[inizio:fine], variants={testo[inizio:fine]},
            )
            f.spans.append(Span(span_id=f"s{indice}", doc_id="d1", start=inizio,
                                end=fine, category=Category.PRATICA,
                                source=Source.RULE, entity_id=f"e{indice}"))
        assert maschera_documento(f, doc) == "[PRATICA_1] [PRATICA_2] [PRATICA_3]"

    def test_testo_senza_span_resta_identico(self):
        doc = Document(doc_id="d1", filename="a.txt", text="Nulla da nascondere.",
                       page_offsets=[0], sha256="x")
        f = fascicolo_vuoto("f1")
        assert maschera(doc.text, [], {}) == doc.text

    def test_span_con_entita_assente_solleva_errore(self):
        # uno span che punta a un entity_id non presente nel fascicolo non va
        # ignorato in silenzio: il testo originale non deve mai sopravvivere
        # senza che qualcuno se ne accorga (finding 1)
        f, doc = scenario()
        f.spans.append(Span(span_id="s_fantasma", doc_id="d1", start=35, end=39,
                            category=Category.PERSONA, source=Source.NER,
                            entity_id="e_fantasma"))
        with pytest.raises(ValueError) as errore:
            maschera_documento(f, doc)
        assert "s_fantasma" in str(errore.value)
        assert "e_fantasma" in str(errore.value)


class TestHashDiApprovazione:
    def test_deterministico(self):
        f, _ = scenario()
        assert hash_approvazione(f) == hash_approvazione(f)

    def test_cambia_se_cambia_uno_span(self):
        f, _ = scenario()
        prima = hash_approvazione(f)
        f.spans.pop()
        assert hash_approvazione(f) != prima

    def test_cambia_se_cambia_un_toggle_di_categoria(self):
        f, _ = scenario()
        prima = hash_approvazione(f)
        f.category_enabled[Category.PERSONA] = False
        assert hash_approvazione(f) != prima

    def test_indipendente_dall_ordine_dei_documenti(self):
        f, doc = scenario()
        secondo = Document(doc_id="d2", filename="allegato.txt", text="Testo neutro.",
                           page_offsets=[0], sha256="y")
        f.documents.append(secondo)
        atteso = hash_approvazione(f)
        f.documents.reverse()
        assert hash_approvazione(f) == atteso

    def test_e_uno_sha256_esadecimale(self):
        f, _ = scenario()
        assert re.fullmatch(r"[0-9a-f]{64}", hash_approvazione(f))

    def test_non_dipende_dallo_stato_del_fascicolo(self):
        # l'hash misura il testo, non il ciclo di vita
        f, _ = scenario()
        prima = hash_approvazione(f)
        f.state = State.APPROVED
        assert hash_approvazione(f) == prima

    def test_indipendente_dall_ordine_a_parita_di_nome_file(self):
        # due documenti con lo stesso filename ma doc_id diverso: il nome
        # file da solo non è un ordine totale, serve il doc_id come
        # spareggio, altrimenti l'ordine di inserimento nel fascicolo
        # cambierebbe l'hash (finding 2)
        f, _ = scenario()
        duplicato_a = Document(doc_id="da", filename="scan.pdf", text="Contenuto A.",
                               page_offsets=[0], sha256="a")
        duplicato_b = Document(doc_id="db", filename="scan.pdf", text="Contenuto B.",
                               page_offsets=[0], sha256="b")
        f.documents.append(duplicato_a)
        f.documents.append(duplicato_b)
        atteso = hash_approvazione(f)
        f.documents[-2], f.documents[-1] = f.documents[-1], f.documents[-2]
        assert hash_approvazione(f) == atteso
