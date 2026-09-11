import itertools

from cryptocustode.core.detect.rules import trova_per_regole
from cryptocustode.core.entities import analizza_documento
from cryptocustode.core.mask import maschera_documento
from cryptocustode.core.models import (
    Category,
    Document,
    Source,
    Span,
    fascicolo_vuoto,
)
from cryptocustode.core.spans import risolvi, si_sovrappongono


def span(
    inizio: int, fine: int, categoria: Category, id_suffisso: str = "",
    doc_id: str = "d1",
) -> Span:
    return Span(
        span_id=f"s{inizio}-{fine}{id_suffisso}", doc_id=doc_id, start=inizio, end=fine,
        category=categoria, source=Source.RULE, entity_id="",
    )


def test_span_adiacenti_non_si_sovrappongono():
    assert si_sovrappongono(span(0, 5, Category.CF), span(5, 10, Category.EMAIL)) is False


def test_span_che_condividono_un_carattere_si_sovrappongono():
    assert si_sovrappongono(span(0, 6, Category.CF), span(5, 10, Category.EMAIL)) is True


def test_priorita_alta_vince_su_sovrapposizione():
    # il CF (P1) contiene cifre che la DATA (P3) potrebbe interpretare
    vincitori = risolvi([span(0, 16, Category.CF), span(6, 14, Category.DATA)])
    assert [s.category for s in vincitori] == [Category.CF]


def test_a_parita_di_priorita_vince_il_piu_lungo():
    # INDIRIZZO e AZIENDA sono entrambe P4
    vincitori = risolvi([span(0, 10, Category.INDIRIZZO), span(0, 25, Category.AZIENDA)])
    assert [s.category for s in vincitori] == [Category.AZIENDA]


def test_span_disgiunti_sopravvivono_tutti():
    dati = [span(0, 5, Category.CF), span(10, 20, Category.EMAIL), span(30, 35, Category.IBAN)]
    assert len(risolvi(dati)) == 3


def test_risultato_ordinato_per_offset():
    dati = [span(30, 35, Category.IBAN), span(0, 5, Category.CF), span(10, 20, Category.EMAIL)]
    assert [s.start for s in risolvi(dati)] == [0, 10, 30]


def test_invariante_nessuna_sovrapposizione_nel_risultato():
    dati = [
        span(0, 16, Category.CF), span(6, 14, Category.DATA), span(12, 30, Category.INDIRIZZO),
        span(28, 40, Category.EMAIL), span(35, 50, Category.AZIENDA), span(50, 60, Category.IBAN),
    ]
    risolti = risolvi(dati)
    for a, b in itertools.combinations(risolti, 2):
        assert not si_sovrappongono(a, b), f"{a.span_id} e {b.span_id} si sovrappongono"


def test_risoluzione_deterministica():
    dati = [span(0, 10, Category.INDIRIZZO, "a"), span(0, 10, Category.AZIENDA, "b")]
    assert [s.span_id for s in risolvi(dati)] == [s.span_id for s in risolvi(list(reversed(dati)))]


def test_a_parita_di_priorita_e_lunghezza_vince_quello_che_inizia_prima():
    # INDIRIZZO e AZIENDA sono entrambe P4, stessa lunghezza (10 caratteri),
    # diverso inizio: INDIRIZZO parte da 9, AZIENDA parte da 10.
    # Senza il termine span.start in _forza, l'ordinamento dei span_id ("s10-20" < "s9-19")
    # metterebbe AZIENDA prima, facendola vincere erroneamente.
    # Il test fallisce se start è negato o rimosso, provando che il tiebreaker
    # per inizio è effettivamente rispettato.
    vincitori = risolvi([span(9, 19, Category.INDIRIZZO), span(10, 20, Category.AZIENDA)])
    assert [s.category for s in vincitori] == [Category.INDIRIZZO]


def test_lista_vuota():
    assert risolvi([]) == []


def test_span_di_documenti_diversi_non_si_sovrappongono():
    # gli offset sono relativi al testo del proprio documento: confrontarli fra
    # documenti non significa niente
    a = span(0, 16, Category.CF, doc_id="d1")
    b = span(0, 16, Category.CF, doc_id="d2")
    assert si_sovrappongono(a, b) is False


def _mascherato(testo: str) -> str:
    """Il testo mascherato da capo a fondo, senza NER: regole, risoluzione
    delle sovrapposizioni, entità e sostituzione."""
    documento = Document(
        doc_id="d1", filename="contratto.txt", text=testo, page_offsets=[0],
        sha256="x",
    )
    fascicolo = fascicolo_vuoto("f1")
    fascicolo.documents.append(documento)
    analizza_documento(fascicolo, documento, usa_ner=False)
    return maschera_documento(fascicolo, documento)


def test_il_telefono_col_prefisso_internazionale_non_si_mangia_la_data():
    # Issue #14: il ramo `+39` della regex del telefono era vorace e senza
    # `\b` in coda, quindi lo span arrivava a "+39 340 123456 1" — la prima
    # cifra della data dentro il numero. Il conteggio restava plausibile, il
    # validatore accettava, e qui `risolvi` faceva il resto: TELEFONO è P2 e
    # DATA è P3, quindi lo span della data veniva scartato *intero* perché
    # sovrapposto. È il punto in cui la fuga diventa visibile.
    testo = "Tel. +39 340 123456 14/03/2024"
    risolti = risolvi(trova_per_regole(testo, "d1"))
    assert [(s.category, testo[s.start:s.end]) for s in risolti] == [
        (Category.TELEFONO, "+39 340 123456"),
        (Category.DATA, "14/03/2024"),
    ]


def test_la_data_dopo_un_telefono_finisce_mascherata():
    # la conseguenza dell'anti-fuga precedente, vista da fuori: prima della
    # correzione questo testo diventava "Tel. [TELEFONO_1]4/03/2024" e la data
    # restava in chiaro accanto a un numero storpiato
    assert _mascherato("Tel. +39 340 123456 14/03/2024") == "Tel. [TELEFONO_1] [DATA_1]"


def test_la_data_dopo_un_fisso_a_gruppi_corti_finisce_mascherata():
    # stesso controllo sul ramo dei fissi, la cui corsa è vorace: se il
    # ritaglio non riportasse la coda dentro il conteggio, qui sparirebbe il
    # numero invece della data
    assert _mascherato("Tel. 02 12 34 56 78 il 14/03/2024") == (
        "Tel. [TELEFONO_1] il [DATA_1]"
    )


def test_risolvi_non_scarta_span_di_documenti_diversi():
    # senza il termine sul doc_id, `risolvi(fascicolo.spans)` scarterebbe in
    # silenzio gli span di un documento perché "sovrapposti" a quelli di un
    # altro, e quel testo resterebbe in chiaro
    dati = [
        span(0, 16, Category.CF, "a", doc_id="d1"),
        span(0, 16, Category.CF, "b", doc_id="d2"),
        span(4, 12, Category.DATA, "c", doc_id="d2"),
    ]
    risolti = risolvi(dati)
    # i due CF sopravvivono, uno per documento; la DATA perde contro il CF del
    # *proprio* documento, che è l'unica sovrapposizione vera
    assert {(s.doc_id, s.category) for s in risolti} == {
        ("d1", Category.CF), ("d2", Category.CF),
    }
