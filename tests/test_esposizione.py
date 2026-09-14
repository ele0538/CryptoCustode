"""Quanti dati usciranno in chiaro, contati prima di esportarli (issue #53).

Un fascicolo nuovo non maschera niente: si accende cio' che serve
(`33521f7`). È una decisione di prodotto presa apposta, e resta. Il suo bordo
tagliente era teorico finché non esisteva un comando di esportazione in pagina;
da `77f7a16` caricare, approvare ed esportare senza toccare un interruttore
consegna il documento in chiaro in tre clic.

Questo modulo non impedisce niente — l'utente ha il diritto di esportare un
documento che non contiene nulla da nascondere. Conta, perché la pagina possa
dirlo **prima** del clic invece di lasciarlo scoprire dopo.

Il conteggio è di occorrenze e non di tag: «tre dati in chiaro» e «un dato
ripetuto tre volte» sono la stessa quantità di testo che esce, e all'utente
interessa quanto esce, non quante righe ha la tabella.
"""

import pytest

from cryptocustode.core.esposizione import esposizione
from cryptocustode.core.models import Category, StatoTag, Tag, fascicolo_vuoto


def tag(segnaposto: str, categoria: Category, occorrenze: int, stato=StatoTag.APPLICATO):
    return Tag(
        tag=segnaposto,
        categoria=categoria,
        valore=segnaposto.strip("[]").lower(),
        occorrenze=occorrenze,
        stato=stato,
    )


def fascicolo_con(*tags: Tag, accese: tuple[Category, ...] = ()):
    """Un fascicolo con `accese` accese ed esattamente le altre spente.

    Le categorie vengono spente esplicitamente invece di affidarsi allo stato
    iniziale di `fascicolo_vuoto`: questi test provano il calcolo
    dell'esposizione, non quale sia il default, e legarli al default li faceva
    diventare rossi il giorno che il default e' cambiato — dicendo "il calcolo
    e' rotto" quando il calcolo non era stato toccato.
    """
    fascicolo = fascicolo_vuoto("f1")
    for t in tags:
        fascicolo.tags[t.tag] = t
    for categoria in Category:
        fascicolo.category_enabled[categoria] = categoria in accese
    return fascicolo


MARIO = tag("[PERSONA_1]", Category.PERSONA, 2)
IMPORTO = tag("[IMPORTO_1]", Category.IMPORTO, 3)
CF = tag("[CF_1]", Category.CF, 1)


def test_un_fascicolo_vuoto_non_espone_niente():
    """Nessun tag, nessuna esposizione: la pagina non deve allarmare chi non ha
    ancora analizzato."""
    esito = esposizione(fascicolo_vuoto("f1"))

    assert esito["in_chiaro"] == 0
    assert esito["mascherati"] == 0
    assert esito["categorie"] == []


def test_senza_interruttori_esce_tutto_in_chiaro():
    """Il caso della issue: analizzato e non toccato."""
    esito = esposizione(fascicolo_con(MARIO, IMPORTO, CF))

    assert esito["in_chiaro"] == 6
    assert esito["mascherati"] == 0


def test_con_tutte_accese_non_esce_niente_in_chiaro():
    esito = esposizione(
        fascicolo_con(MARIO, IMPORTO, CF, accese=(Category.PERSONA, Category.IMPORTO, Category.CF))
    )

    assert esito["in_chiaro"] == 0
    assert esito["mascherati"] == 6
    assert esito["categorie"] == []


def test_il_caso_intermedio_e_quello_che_conta():
    """Due categorie su tre accese: l'utente crede di aver finito, e l'importo
    esce. È il caso che la conferma sul «niente acceso» non vede."""
    esito = esposizione(
        fascicolo_con(MARIO, IMPORTO, CF, accese=(Category.PERSONA, Category.CF))
    )

    assert esito["in_chiaro"] == 3
    assert esito["mascherati"] == 3
    assert esito["categorie"] == [{"categoria": "IMPORTO", "quanti": 3}]


def test_le_categorie_in_chiaro_sono_ordinate_dalla_piu_esposta():
    """Chi legge una riga sola deve leggere per prima la categoria che espone
    di più, non quella che viene prima nell'enum."""
    esito = esposizione(fascicolo_con(MARIO, IMPORTO, CF))

    assert esito["categorie"] == [
        {"categoria": "IMPORTO", "quanti": 3},
        {"categoria": "PERSONA", "quanti": 2},
        {"categoria": "CF", "quanti": 1},
    ]


def test_a_parita_di_occorrenze_l_ordine_e_stabile():
    """Due categorie con lo stesso conteggio non devono scambiarsi di posto fra
    un ridisegno e l'altro: l'ordine alfabetico le fissa."""
    esito = esposizione(fascicolo_con(tag("[DATA_1]", Category.DATA, 2), MARIO))

    assert [voce["categoria"] for voce in esito["categorie"]] == ["DATA", "PERSONA"]


def test_un_tag_spento_a_mano_conta_come_in_chiaro():
    """`tabella_attiva` legge due interruttori in `and`: la categoria accesa non
    basta se l'utente ha spento quel singolo tag (spec §5)."""
    spento = tag("[PERSONA_2]", Category.PERSONA, 4, stato=StatoTag.DISATTIVATO)

    esito = esposizione(fascicolo_con(MARIO, spento, accese=(Category.PERSONA,)))

    assert esito["in_chiaro"] == 4
    assert esito["mascherati"] == 2
    assert esito["categorie"] == [{"categoria": "PERSONA", "quanti": 4}]


def test_un_tag_non_trovato_non_conta_come_esposizione():
    """`NON_TROVATO` significa che il modello ha nominato un valore che nel
    testo non compare: non c'è niente da mascherare e niente che esca. Contarlo
    gonfierebbe l'allarme con dati che non sono nel documento."""
    assente = tag("[PERSONA_9]", Category.PERSONA, 0, stato=StatoTag.NON_TROVATO)

    esito = esposizione(fascicolo_con(assente))

    assert esito["in_chiaro"] == 0
    assert esito["categorie"] == []


def test_l_esposizione_non_muta_il_fascicolo():
    fascicolo = fascicolo_con(MARIO, IMPORTO)
    prima = (dict(fascicolo.tags), dict(fascicolo.category_enabled))

    esposizione(fascicolo)

    assert (fascicolo.tags, fascicolo.category_enabled) == prima
