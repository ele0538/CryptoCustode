import itertools

from cryptocustode.core.models import Category, Source, Span
from cryptocustode.core.spans import risolvi, si_sovrappongono


def span(inizio: int, fine: int, categoria: Category, id_suffisso: str = "") -> Span:
    return Span(
        span_id=f"s{inizio}-{fine}{id_suffisso}", doc_id="d1", start=inizio, end=fine,
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


def test_lista_vuota():
    assert risolvi([]) == []
