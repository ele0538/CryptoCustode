"""Documenti di verifica: testo mai visto dal motore, contro Gemini vero (spec §16).

La consegna originale chiedeva documenti di verifica **distinti** da quelli di
sviluppo, scritti a motore già finito, per provare che il motore trova dati
personali in un testo su cui non è mai stato messo a punto. Un file con questo
nome esisteva e provava il vecchio motore a regole + spaCy, che non esiste più
(commit `94ac206`): un doppio non può provare niente sulla qualità del
riconoscimento, perché risponde solo quello che il test gli ha detto. L'unico
modo di onorare la consegna con il motore attuale — `RilevatoreGemini` — è
chiamare il modello vero, ed è quello che fa questo file.

Per questo è l'unico punto della suite marcato `rete` (vedi `pyproject.toml`):
tocca la rete davvero, quindi resta fuori da `python -m pytest -q` e si esegue
solo con `pytest -m rete`. I quattro documenti qui sotto sono testo nuovo,
scritto apposta per questo file: non sono copie né varianti dei documenti di
sviluppo (`tests/test_matrice_consegna.py`), altrimenti misurerebbero solo
quanto il motore ricorda un caso già visto, non quanto generalizza.

Ogni nome, codice fiscale, IBAN, partita IVA, email e telefono qui dentro è
inventato: nessuno di questi valori appartiene a una persona o a un'azienda
reale, e le email usano domini riservati da RFC 2606 (`example.com`,
`example.org`, `example.net`) che nessuno può registrare — la stessa
convenzione già in uso nel resto della suite (commit `633a60f`).

Cosa si misura, e i suoi limiti onesti:

1. **Anti-fuga**: ogni valore pianificato che Gemini ha davvero nominato non
   deve sopravvivere nel testo mascherato. Qui, per la prima volta nella suite,
   con un rilevatore vero e non un doppio.
2. **Round-trip**: `ripristina(tagga(testo, tabella).mascherato,
   dizionario_di(tabella))` torna al testo originale.
3. **Richiamo**: quanti valori pianificati il modello ha nominato, con una
   soglia minima. Un valore che il modello non nomina resta in chiaro e nessun
   controllo automatico se ne accorge — è il limite noto 1 della spec §16, e
   questo è l'unico posto della suite in cui viene davvero misurato invece che
   solo dichiarato.

Cosa questo file non promette: l'output esatto del modello, la numerazione dei
tag o la categoria assegnata a un valore non sono asseriti, perché variano fra
esecuzioni anche a `temperature=0` — si asseriscono proprietà, non trascrizioni.
"""

import os
from dataclasses import dataclass

import pytest

from cryptocustode.ai.gemini import VARIABILE_CHIAVE, RilevatoreGemini
from cryptocustode.core.tagga import assegna_tag, conta_occorrenze, dizionario_di, tagga
from cryptocustode.core.unmask import ripristina

pytestmark = [
    pytest.mark.rete,
    pytest.mark.skipif(
        not os.environ.get(VARIABILE_CHIAVE),
        reason=(
            f"serve una chiave Gemini vera nella variabile d'ambiente "
            f"{VARIABILE_CHIAVE}: senza rete questo file non misura niente, e "
            "non deve né fallire né sollevare AIKeyMissing"
        ),
    ),
]


@dataclass(frozen=True)
class DocumentoDiVerifica:
    """Un documento mai visto dal motore, con la sua verità di terra.

    `soglia_richiamo` è il numero minimo di `valori_veri` che il modello deve
    nominare perché il test passi: non tutti, altrimenti un singolo mancato
    (il modo in cui il modello sbaglia più spesso, per normalizzazione — vedi
    `StatoTag.NON_TROVATO`) renderebbe il test fragile senza che sia successo
    nulla di grave.
    """

    nome: str
    testo: str
    valori_veri: tuple[str, ...]
    soglia_richiamo: int


# --- Documento 1: clausola di contratto di locazione -------------------------
#
# Diverso per struttura e contenuto da TESTO_RICCO di test_matrice_consegna.py:
# lì è il "canone firmato da"; qui è una clausola sul deposito cauzionale e sul
# garage, con due persone invece di una.
TESTO_CONTRATTO = (
    "Con la presente clausola integrativa, la locatrice Ottavia Marchetti, "
    "residente in Via dei Salici 9, concede in uso il garage annesso "
    "all'abitazione al conduttore Leonardo Bruni. Le parti convengono che ogni "
    "comunicazione relativa al presente contratto sia inviata all'indirizzo "
    "ottavia.marchetti@example.com oppure al recapito 348 220 9931. Il "
    "deposito cauzionale è versato sull'IBAN IT19K0306909606100000012345."
)
VALORI_VERI_CONTRATTO = (
    "Ottavia Marchetti",
    "Via dei Salici 9",
    "Leonardo Bruni",
    "ottavia.marchetti@example.com",
    "348 220 9931",
    "IT19K0306909606100000012345",
)

# --- Documento 2: disposizione di bonifico bancario ---------------------------
#
# Un ordinante e un beneficiario distinti dal locatore/conduttore di sopra, un
# codice fiscale invece di un IBAN come identificativo dell'ordinante, e una
# causale che non nomina nessuno.
TESTO_BONIFICO = (
    "Disposizione di bonifico SEPA: l'ordinante Rebecca Fantin, codice "
    "fiscale FNTRCC90A41L736Y, dispone il pagamento di 1.875,40 euro a favore "
    "del beneficiario Corrado Vitiello, titolare dell'IBAN "
    "IT52D0100003245000000891234. Causale: acconto ristrutturazione bagno. In "
    "caso di problemi contattare l'ordinante allo 0461 887654 o scrivere a "
    "rebecca.fantin@example.org."
)
VALORI_VERI_BONIFICO = (
    "Rebecca Fantin",
    "FNTRCC90A41L736Y",
    "Corrado Vitiello",
    "IT52D0100003245000000891234",
    "0461 887654",
    "rebecca.fantin@example.org",
)

# --- Documento 3: certificato anagrafico comunale -----------------------------
#
# Un registro comunale, non un contratto fra privati: un solo interessato, una
# data di nascita invece di un IBAN o una email, e un tono da atto pubblico.
TESTO_COMUNALE = (
    "Il Comune di Fossalta certifica che il sig. Emidio Castellani, nato a "
    "Fossalta il 03/11/1968, codice fiscale CSTMDE68S03D653P, risulta "
    "residente in Piazza della Vittoria 5. La presente certificazione è "
    "rilasciata su richiesta dell'interessato per gli usi consentiti dalla "
    "legge."
)
VALORI_VERI_COMUNALE = (
    "Emidio Castellani",
    "03/11/1968",
    "CSTMDE68S03D653P",
    "Piazza della Vittoria 5",
)

# --- Documento 4: fattura di un'impresa artigiana -----------------------------
#
# L'unico dei quattro con una partita IVA e una ragione sociale (AZIENDA),
# oltre a un cliente persona fisica: copre categorie che gli altri tre non
# toccano.
TESTO_FATTURA = (
    "Fattura elettronica emessa da Falegnameria Artigiana Bruttomesso S.n.c., "
    "partita IVA 04837156219, nei confronti della cliente Wanda Pellizzari, "
    "per lavori di manutenzione infissi eseguiti presso l'abitazione in "
    "Vicolo Corto 3. Totale dovuto: 430,00 euro, da saldare tramite bonifico "
    "sull'IBAN IT08F0501803400000000276543. Per chiarimenti: "
    "amministrazione@example.net, tel. 049 761 2288."
)
VALORI_VERI_FATTURA = (
    "Falegnameria Artigiana Bruttomesso S.n.c.",
    "04837156219",
    "Wanda Pellizzari",
    "Vicolo Corto 3",
    "IT08F0501803400000000276543",
    "amministrazione@example.net",
    "049 761 2288",
)

DOCUMENTI = (
    DocumentoDiVerifica(
        nome="clausola_di_locazione",
        testo=TESTO_CONTRATTO,
        valori_veri=VALORI_VERI_CONTRATTO,
        soglia_richiamo=3,  # metà di 6, arrotondata per difetto
    ),
    DocumentoDiVerifica(
        nome="disposizione_di_bonifico",
        testo=TESTO_BONIFICO,
        valori_veri=VALORI_VERI_BONIFICO,
        soglia_richiamo=3,  # metà di 6
    ),
    DocumentoDiVerifica(
        nome="certificato_anagrafico",
        testo=TESTO_COMUNALE,
        valori_veri=VALORI_VERI_COMUNALE,
        soglia_richiamo=2,  # metà di 4
    ),
    DocumentoDiVerifica(
        nome="fattura_artigiana",
        testo=TESTO_FATTURA,
        valori_veri=VALORI_VERI_FATTURA,
        soglia_richiamo=3,  # metà di 7, arrotondata per difetto
    ),
)
"""Le soglie sono metà dei valori pianificati, arrotondate per difetto: basse
abbastanza da non diventare rosse per un singolo mancato normale (spec §16,
limite noto 1 — la normalizzazione del modello), alte abbastanza perché una
regressione vera del prompt o del modello — la metà dei valori non più
riconosciuti — non passi inosservata. Non il 100%: la consegna stessa chiede
di non renderla fragile."""


def _rilevatore() -> RilevatoreGemini:
    """Il rilevatore di produzione, senza alcuna chiamata iniettata: la chiave
    viene letta da `VARIABILE_CHIAVE`, che `pytestmark` ha già verificato
    presente, quindi qui non serve ricontrollarla."""
    return RilevatoreGemini()


@pytest.mark.parametrize("caso", DOCUMENTI, ids=[caso.nome for caso in DOCUMENTI])
def test_il_motore_rileva_maschera_e_ripristina_un_documento_mai_visto(caso):
    """Le tre proprietà della consegna, su un rilevatore vero e un documento
    che il motore non ha mai incontrato prima d'ora."""
    rilevazioni = _rilevatore().rileva(caso.testo)
    valori_rilevati = {rilevazione.valore for rilevazione in rilevazioni}

    trovati = [valore for valore in caso.valori_veri if valore in valori_rilevati]
    mancanti = [valore for valore in caso.valori_veri if valore not in valori_rilevati]

    # Proprietà 3: il richiamo, riportato per intero nel messaggio anche se la
    # soglia è superata — è questo elenco, non il numero nudo, che dice a chi
    # legge un fallimento futuro *quale* dato il modello non ha più trovato.
    assert len(trovati) >= caso.soglia_richiamo, (
        f"{caso.nome}: Gemini ha nominato {len(trovati)}/{len(caso.valori_veri)} "
        f"valori pianificati (soglia minima {caso.soglia_richiamo}). "
        f"Trovati: {trovati!r}. Mancanti: {mancanti!r} — un valore mancante "
        "resta in chiaro nel documento esportato e nessun controllo "
        "automatico se ne accorgerebbe da solo (spec §16, limite noto 1): "
        "questo test è quel controllo."
    )

    # Stesso giro della route di produzione (test_matrice_consegna.analizza):
    # assegna_tag -> tagga per documento -> conta_occorrenze.
    tabella, _contatori = assegna_tag(rilevazioni, {}, {})
    mascheratura = tagga(caso.testo, tabella)
    tabella = conta_occorrenze(tabella, [mascheratura])

    # Proprietà 1: anti-fuga, applicata per la prima volta a un rilevatore
    # vero e non a un doppio. Solo sui valori che Gemini ha davvero nominato:
    # su un valore mancante l'assenza dal mascherato non proverebbe nulla,
    # sarebbe solo il limite noto 1 travestito da successo.
    for valore in trovati:
        assert valore not in mascheratura.mascherato, (
            f"{caso.nome}: {valore!r} è stato rilevato da Gemini ma sopravvive "
            "nel testo mascherato"
        )

    # Proprietà 2: il round-trip è un'identità. Il dizionario copre l'intera
    # tabella, tag NON_TROVATO compresi: i loro segnaposto non compaiono nel
    # mascherato (tagga() non li ha trovati alla lettera), quindi non hanno
    # voce in capitolo nel ripristino — l'identità vale per costruzione sui
    # tag APPLICATO, che sono gli unici a lasciare un segnaposto nel testo.
    dizionario = dizionario_di(tabella)
    assert ripristina(mascheratura.mascherato, dizionario) == caso.testo
