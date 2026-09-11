import hashlib

import pytest

from cryptocustode.core.detect import ner as modulo_ner
from cryptocustode.core.detect.ner import (
    MAPPA_LABEL,
    carica_modello,
    solo_parole_di_struttura,
    tronca_al_primo_a_capo,
    trova_per_ner,
)
from cryptocustode.core.entities import analizza_documento
from cryptocustode.core.models import Category, Document, Source, fascicolo_vuoto
from cryptocustode.state.session import (
    SessionStore,
    analisi_completata,
    approva,
    export_sanitized_text,
)

# Il marcatore vale per tutto il file: anche i test che non chiamano il modello
# pagano l'import di spaCy, che questo modulo fa all'import.
pytestmark = pytest.mark.lento


def valori(testo: str, categoria: Category) -> list[str]:
    return [testo[s.start:s.end] for s in trova_per_ner(testo, "d1") if s.category is categoria]


def test_il_modello_si_carica_una_volta_sola():
    assert carica_modello() is carica_modello()


def test_riconosce_una_persona():
    testo = "Il presente contratto è sottoscritto da Mario Rossi in data odierna."
    assert any("Rossi" in v for v in valori(testo, Category.PERSONA))


def test_riconosce_una_azienda():
    testo = "La società Alfa Costruzioni S.r.l. si impegna a consegnare l'opera."
    assert any("Alfa" in v for v in valori(testo, Category.AZIENDA))


def test_le_label_mappate_coprono_le_tre_categorie_previste():
    assert set(MAPPA_LABEL.values()) == {
        Category.PERSONA, Category.AZIENDA, Category.INDIRIZZO,
    }


def test_gli_span_sono_marcati_come_ner():
    testo = "Contratto firmato da Mario Rossi."
    for span in trova_per_ner(testo, "d1"):
        assert span.source is Source.NER
        assert span.entity_id == ""
        assert testo[span.start:span.end].strip() == testo[span.start:span.end]


def test_scarta_token_di_una_sola_lettera():
    for span in trova_per_ner("La lettera A firmata da B.", "d1"):
        assert span.lunghezza > 1


def test_offset_coerenti_con_il_testo():
    testo = "Il signor Mario Rossi abita a Torino."
    for span in trova_per_ner(testo, "d1"):
        assert 0 <= span.start < span.end <= len(testo)


class TestScartoDelleStopword:
    """Validazione P4 della spec §6 ("scarto stopword e token di una sola
    lettera"), nella forma conservativa: si scarta solo se *ogni* token è una
    stopword, un titolo o un carattere singolo."""

    @pytest.mark.parametrize(
        "valore",
        ["CONTRATTO", "Locatore", "Conduttore", "Tel", "Sig", "Sig.", "Dott.ssa",
         "di seguito", "A B"],
    )
    def test_scarta_gli_span_di_sole_parole_di_struttura(self, valore):
        assert solo_parole_di_struttura(valore) is True

    @pytest.mark.parametrize(
        "valore",
        ["Alberto Ferrante", "Ferrante", "Sig. Rossi", "Mario Rossi",
         "Alfa Costruzioni S.r.l.", "Via Roma"],
    )
    def test_non_scarta_gli_span_con_almeno_un_token_pieno(self, valore):
        assert solo_parole_di_struttura(valore) is False

    @pytest.mark.parametrize("valore", ["Rosa", "Patti", "Costa", "Piazza"])
    def test_i_nomi_che_sono_anche_parole_comuni_non_vengono_scartati(self, valore):
        """Il vocabolario non contiene nessuna parola che possa essere un nome
        o un cognome italiano: quei falsi positivi restano coperti dal limite
        noto §16.1, perché scartarli è la direzione che fa fuggire i dati."""
        assert solo_parole_di_struttura(valore) is False

    def test_le_parole_di_struttura_non_diventano_span(self):
        testo = (
            "CONTRATTO DI LOCAZIONE\n\n"
            "Tra il Sig. Alberto Ferrante, di seguito il Locatore, e la "
            "Sig.ra Marta Lorusso,\ndi seguito il Conduttore.\n"
            "Tel. 011 1234567\n"
        )
        trovati = [testo[s.start:s.end] for s in trova_per_ner(testo, "d1")]
        assert "CONTRATTO" not in trovati
        assert "Locatore" not in trovati
        assert "Conduttore" not in trovati
        assert "Tel" not in trovati
        assert "Sig" not in trovati
        assert any("Ferrante" in v for v in trovati), (
            "il filtro non deve far cadere il nome vero"
        )


BUSTA_PAGA = """AZIENDA ESEMPIO S.R.L.
Prospetto paga - marzo 2024

Dipendente: FERRANTE ALBERTO
Matricola 0012345 - Qualifica: impiegato 5 livello
Residenza: Via delle Betulle 12/A lotto 3, 10043 Orbassano
Assunto con decorrenza 1 marzo 2024.

Cognome e nome: LORUSSO MARTA
QUALIFICA: quadro
Residente in Frazione Tetti Neirotti 8, 10098 Rivoli
Luogo di nascita: Torino
"""


def _esporta_mascherato(testo: str) -> str:
    """Il testo mascherato che esce dal gate vero (spec §8).

    Passa dalla catena completa — `analizza_documento` -> `analisi_completata`
    -> `approva` -> `export_sanitized_text` — e non da `maschera_documento`
    diretto: il difetto della #36 si vede sul prodotto, cioè sul testo che
    l'IA riceve, e non sugli span.
    """
    fascicolo = fascicolo_vuoto("f36")
    documento = Document(
        doc_id="d36", filename="busta.pdf", text=testo, page_offsets=[0],
        sha256=hashlib.sha256(testo.encode()).hexdigest(),
    )
    fascicolo.documents.append(documento)
    analizza_documento(fascicolo, documento)
    analisi_completata(fascicolo)
    approva(fascicolo)
    store = SessionStore()
    store.salva(fascicolo)
    return export_sanitized_text("f36", store)["busta.pdf"]


class TestSpanCheAttraversanoLAcapo:
    """Issue #36: lo span del NER attraversa l'a capo e si porta dentro
    l'etichetta del campo successivo, così due campi interi della busta paga
    spariscono dentro un segnaposto e due righe si fondono."""

    def test_nessuno_span_del_ner_contiene_un_a_capo(self):
        attraversano = [
            BUSTA_PAGA[s.start:s.end]
            for s in trova_per_ner(BUSTA_PAGA, "d36")
            if "\n" in BUSTA_PAGA[s.start:s.end]
        ]
        assert attraversano == [], f"span che attraversano l'a capo: {attraversano}"

    def test_il_testo_mascherato_non_fonde_due_righe(self):
        mascherato = _esporta_mascherato(BUSTA_PAGA)
        assert mascherato.count("\n") == BUSTA_PAGA.count("\n"), (
            f"il numero di righe deve restare quello dell'originale:\n{mascherato}"
        )

    def test_i_campi_inghiottiti_sopravvivono_nel_testo_mascherato(self):
        """Matricola e qualifica non devono sparire dentro un `[PERSONA_n]`."""
        mascherato = _esporta_mascherato(BUSTA_PAGA)
        for atteso in ("Matricola 0012345", "Qualifica", "Assunto con decorrenza",
                       "Luogo di nascita"):
            assert atteso in mascherato, (
                f"{atteso!r} è stato inghiottito da un segnaposto:\n{mascherato}"
            )

    def test_il_nome_prima_dell_a_capo_resta_mascherato(self):
        """Troncare non deve far fuggire quello che il NER aveva preso: è la
        ragione per cui si tronca invece di scartare."""
        mascherato = _esporta_mascherato(BUSTA_PAGA)
        for segreto in ("ALBERTO", "Orbassano", "Rivoli"):
            assert segreto not in mascherato, (
                f"{segreto!r} è rimasto in chiaro:\n{mascherato}"
            )

    @pytest.mark.parametrize(
        ("valore", "atteso"),
        [
            ("ALBERTO\nMatricola 0012345 - Qualifica", "ALBERTO"),
            ("Orbassano\nAssunto", "Orbassano"),
            ("Rivoli\nLuogo", "Rivoli"),
            ("0012345\nQUALIFICA", "0012345"),
            # il taglio porta via anche gli spazi rimasti in coda
            ("Torino   \nVia Roma", "Torino"),
            ("Marta\r\nLorusso", "Marta"),
            # senza a capo il valore non viene toccato
            ("Mario Rossi", "Mario Rossi"),
            ("Via delle Betulle 12/A", "Via delle Betulle 12/A"),
        ],
    )
    def test_il_taglio_tiene_la_parte_prima_del_primo_a_capo(self, valore, atteso):
        assert tronca_al_primo_a_capo(valore) == atteso

    def test_il_resto_del_taglio_fatto_di_sola_struttura_viene_scartato(self):
        """Composizione con `2c61c8f`: il troncamento viene *prima* dello
        scarto delle parole di struttura, così un resto come 'Residente in'
        non diventa un segnaposto."""
        resto = tronca_al_primo_a_capo("Residente in\nFrazione Tetti Neirotti 8")
        assert resto == "Residente in"
        assert solo_parole_di_struttura(resto) is True

    def test_il_taglio_non_spezza_mai_una_parola(self):
        """Si taglia su un a capo, che è per costruzione un confine di token:
        il resto non è mai mezzo nome tranne quando l'estrazione stessa aveva
        già spezzato la parola."""
        for valore in ("ALBERTO\nMatricola", "Orbassano\nAssunto"):
            resto = tronca_al_primo_a_capo(valore)
            assert valore.startswith(resto)
            assert resto == resto.strip()

    @pytest.mark.parametrize(
        "valore",
        [
            "ALBERTO\nMatricola 0012345 - Qualifica", "Orbassano\nAssunto",
            "Torino   \nVia Roma", "Marta\r\nLorusso", "A\nRossi",
            "Fo\nMotivazione", "Mario Rossi", "\n".join(("Uno", "Due", "Tre")),
        ],
    )
    def test_il_resto_e_sempre_un_prefisso_del_valore(self, valore):
        """L'invariante su cui poggia l'aritmetica degli offset: `trova_per_ner`
        tiene fermo l'inizio e ricava la nuova fine dalla lunghezza del resto.
        Se il resto non fosse un prefisso, l'offset punterebbe a un altro pezzo
        di testo e lo span maschererebbe la cosa sbagliata."""
        assert valore.startswith(tronca_al_primo_a_capo(valore))


class _EntitaFinta:
    """Il minimo che `trova_per_ner` legge da un'entità di spaCy."""

    def __init__(self, valore: str, inizio: int, label: str) -> None:
        self.text = valore
        self.start_char = inizio
        self.end_char = inizio + len(valore)
        self.label_ = label


class _DocumentoFinto:
    def __init__(self, entita: list[_EntitaFinta]) -> None:
        self.ents = entita


def _span_da_entita(monkeypatch, testo: str, *etichettate: tuple[str, str]):
    """Fa girare il post-processing vero di `trova_per_ner` su entità decise qui.

    Il modello sceglie da sé dove mettere i confini, quindi non è il posto da
    cui pinnare il post-processing: una testa di un solo carattere non si
    ottiene chiedendola a spaCy, e un caso che oggi il modello produce può
    sparire al prossimo aggiornamento del modello. Qui viene sostituito solo
    il punto d'ingresso del modello, `carica_modello`: offset, taglio e le due
    validazioni restano quelli veri.
    """
    entita = [
        _EntitaFinta(valore, testo.index(valore), label)
        for valore, label in etichettate
    ]
    monkeypatch.setattr(
        modulo_ner, "carica_modello", lambda *_: lambda _t: _DocumentoFinto(entita)
    )
    return trova_per_ner(testo, "d1")


class TestIlTaglioDentroTrovaPerNer:
    """Il taglio cablato nel percorso del NER: gli offset lo seguono, e le due
    validazioni della spec §6 guardano il resto invece della proposta del
    modello."""

    def test_lo_span_si_ferma_sull_a_capo_e_gli_offset_lo_seguono(self, monkeypatch):
        testo = "Dipendente: FERRANTE ALBERTO\nMatricola 0012345 - Qualifica: quadro\n"
        (span,) = _span_da_entita(
            monkeypatch, testo, ("ALBERTO\nMatricola 0012345 - Qualifica", "PER")
        )
        assert testo[span.start:span.end] == "ALBERTO"

    def test_un_resto_di_sola_struttura_non_brucia_un_segnaposto(self, monkeypatch):
        """L'ordine, non solo il taglio: `solo_parole_di_struttura` (2c61c8f)
        sul valore intero direbbe di no, perché 'Frazione' non è una parola di
        struttura. È rosso se qualcuno valida prima di tagliare."""
        testo = "Residente in\nFrazione Tetti Neirotti 8, 10098 Rivoli\n"
        assert _span_da_entita(monkeypatch, testo, ("Residente in\nFrazione", "LOC")) == []

    def test_una_testa_di_un_solo_carattere_non_diventa_uno_span(self, monkeypatch):
        """L'unica soglia di lunghezza è quella che il repo aveva già, il
        carattere singolo della validazione P4: dopo il taglio la si applica al
        resto, che è ciò che diventa davvero uno span."""
        testo = "Firmato A\nRossi ha controfirmato.\n"
        assert _span_da_entita(monkeypatch, testo, ("A\nRossi", "PER")) == []

    def test_una_testa_di_due_lettere_resta_uno_span(self, monkeypatch):
        """Decisione dichiarata sul frammento corto: non si scarta, e non si
        introduce nessuna soglia oltre il carattere singolo. I cognomi italiani
        di due lettere esistono, e una soglia più alta li butterebbe — è la
        stessa euristica sulla plausibilità del nome che `2c61c8f` ha rifiutato
        per nome. Questo test è rosso se qualcuno la introduce."""
        testo = "Il premio a Dario Fo\nMotivazione: teatro civile.\n"
        (span,) = _span_da_entita(monkeypatch, testo, ("Fo\nMotivazione", "PER"))
        assert testo[span.start:span.end] == "Fo"
