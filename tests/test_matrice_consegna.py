"""I casi della matrice della consegna e il test anti-fuga generico (spec §13
del 2026-09-14, che aggiorna la §14 del 2026-09-10).

`analizza_documento` e la pipeline regole+NER non esistono più: il rilevatore
è sempre un doppio (`tests/doppi.RilevatoreFinto`, o un doppio locale per i
casi che devono fallire), come prescrive la spec §13 — «gli unici test che
chiamano Gemini davvero stanno dietro il marcatore `rete`».
"""

import pytest

from cryptocustode.core.errors import (
    AIResponseInvalid,
    ExportNotAllowed,
    ScannedDocumentRejected,
    UnknownPlaceholder,
)
from cryptocustode.core.ingest.loader import aggiungi_documento, costruisci_documento
from cryptocustode.core.models import (
    Category,
    Fascicolo,
    Rilevazione,
    State,
    StatoTag,
    fascicolo_vuoto,
)
from cryptocustode.core.tagga import assegna_tag, conta_occorrenze, dizionario_di, tagga
from cryptocustode.core.unmask import ripristina
from cryptocustode.state.session import (
    SessionStore,
    analisi_completata,
    approva,
    export_sanitized_text,
    registra_mutazione,
)
from tests.doppi import RilevatoreFinto, accendi
from tests.pdf_di_prova import pdf_di_prova

# Le parole di contesto sono scelte di proposito fra quelle *comuni nei documenti
# veri*: `Codice Fiscale` davanti a un numero di 11 cifre (il codice fiscale di
# una società ha la forma della P.IVA) e `Recapito telefonico:` sono forme che
# compaiono per davvero nei contratti, non solo quelle "fortunate".
TESTO_RICCO = (
    "Il contratto è firmato da Mario Rossi, codice fiscale RSSMRA85M01H501Q, "
    "per la ditta individuale con Codice Fiscale 12345678903 "
    "e IBAN IT60X0542811101000000123456. "
    "Recapito telefonico: 3401234567, mario.rossi@example.com."
)

# Ciò che un vero Gemini dovrebbe rilevare in TESTO_RICCO: qui è il doppio a
# dirlo, non un motore a regole. Le sei categorie coprono quelle che la
# matrice pianta apposta (spec §13).
RILEVAZIONI_RICCHE = [
    Rilevazione(valore="Mario Rossi", categoria=Category.PERSONA),
    Rilevazione(valore="RSSMRA85M01H501Q", categoria=Category.CF),
    Rilevazione(valore="12345678903", categoria=Category.PIVA),
    Rilevazione(valore="IT60X0542811101000000123456", categoria=Category.IBAN),
    Rilevazione(valore="3401234567", categoria=Category.TELEFONO),
    Rilevazione(valore="mario.rossi@example.com", categoria=Category.EMAIL),
]


class RilevatoreCheFallisce:
    """Il doppio del caso TC-08: il modello ha risposto fuori schema.

    `RilevatoreFinto` non solleva mai — risponde solo ciò che il test gli ha
    dato — quindi "il modello risponde male" non è nella sua responsabilità:
    serve un doppio a parte che imita `AIResponseInvalid` così come la
    solleverebbe il client vero (spec §6).
    """

    def rileva(self, testo: str) -> list[Rilevazione]:
        raise AIResponseInvalid("la risposta del modello non rispetta lo schema")


def analizza(fascicolo: Fascicolo, rilevatore) -> None:
    """Lo stesso giro della route `POST /analisi` (`routes_fascicolo.py`),
    ripetuto qui perché quella route vive fuori dai file che questo task può
    toccare: raccoglie tutte le rilevazioni prima di scrivere, così un
    rilevatore che solleva lascia il fascicolo esattamente com'era (spec §6).
    """
    rilevazioni: list[Rilevazione] = []
    for documento in fascicolo.documents:
        rilevazioni.extend(rilevatore.rileva(documento.text))
    tabella, contatori = assegna_tag(rilevazioni, fascicolo.tags, fascicolo.counters)
    mascherature = [tagga(d.text, tabella) for d in fascicolo.documents]
    fascicolo.tags = conta_occorrenze(tabella, mascherature)
    fascicolo.counters = contatori
    fascicolo.analizzati.update(d.doc_id for d in fascicolo.documents)


def fascicolo_con(testo: str, rilevatore, nome: str = "contratto.txt") -> Fascicolo:
    fascicolo = fascicolo_vuoto("f1")
    documento = costruisci_documento(nome, testo.encode("utf-8"))
    aggiungi_documento(fascicolo, documento)
    analizza(fascicolo, rilevatore)
    analisi_completata(fascicolo)
    return fascicolo


def store_con(fascicolo: Fascicolo) -> SessionStore:
    store = SessionStore()
    store.salva(fascicolo)
    return store


def test_anti_fuga_nessun_valore_del_dizionario_compare_nell_esportato():
    """Il test più importante della suite, e i suoi limiti onesti.

    Prova che ogni valore che il rilevatore ha davvero applicato è assente dal
    testo esportato, e che le categorie che questa fixture pianta
    deliberatamente (CF, IBAN, P. IVA, email, telefono, persona) risultano
    tutte applicate — non solo che la tabella, qualunque cosa contenga, non
    fuga. Il rilevatore è un doppio (spec §13): non può provare che Gemini
    *riconoscerebbe* questi valori in un testo mai visto, solo che, una volta
    rilevati, la mascheratura e l'esportazione non li lasciano trapelare. La
    misura del richiamo su un documento vero, con un client vero, è compito
    del test marcato `rete` promesso da una fase successiva, non di questo.

    Percorso coperto: `approva` -> `export_sanitized_text`, cioè il gate di
    stato e il controllo di integrità — ciò che la spec §13 chiede alla
    lettera, «non compare nel testo *esportato*».
    """
    fascicolo = fascicolo_con(TESTO_RICCO, RilevatoreFinto(sempre=RILEVAZIONI_RICCHE))
    # Un fascicolo nuovo non maschera niente (spec §2, emendamento alla
    # decisione 4). Questo test parla di cosa succede quando la mascheratura è
    # accesa: acceso tutto, così l'anti-fuga copre ogni categoria piantata e
    # non solo quelle che un default avrebbe scelto per noi.
    accendi(fascicolo)
    approva(fascicolo)
    esportato = export_sanitized_text("f1", store_con(fascicolo))
    testo_esportato = "\n".join(esportato.values())

    applicati = [tag for tag in fascicolo.tags.values() if tag.stato is StatoTag.APPLICATO]
    assert applicati, "il fascicolo deve avere almeno un tag applicato, altrimenti il test non prova nulla"

    categorie_rilevate = {tag.categoria for tag in applicati}
    categorie_pianificate = {
        Category.CF,
        Category.IBAN,
        Category.PIVA,
        Category.EMAIL,
        Category.TELEFONO,
        Category.PERSONA,
    }
    mancanti = categorie_pianificate - categorie_rilevate
    assert not mancanti, (
        "la fixture pianta queste categorie apposta per essere applicate; se "
        f"mancano ({mancanti}) il ciclo sottostante quantifica su meno di "
        "quanto promesso e il test non proverebbe più nulla per loro"
    )
    for tag in applicati:
        assert tag.valore not in testo_esportato


def test_TC_01_pdf_con_una_pagina_scansionata_su_cinque_viene_rifiutato():
    contenuto = pdf_di_prova(["testo", "testo", "testo", "testo", "immagine"])
    with pytest.raises(ScannedDocumentRejected, match=r"pagina 5\b"):
        costruisci_documento("scansione.pdf", contenuto)


def test_il_segnaposto_generato_si_ripristina_con_il_valore_canonico():
    # Chiude il cerchio generatore -> matcher -> dizionario: se un giorno il
    # formato del segnaposto cambiasse, questo test lo direbbe (il ripristino
    # solleverebbe MalformedPlaceholder o UnknownPlaceholder).
    fascicolo = fascicolo_con(TESTO_RICCO, RilevatoreFinto(sempre=RILEVAZIONI_RICCHE))
    tag = next(iter(fascicolo.tags.values()))
    frase = f"Confermo {tag.tag} per conoscenza."
    atteso = f"Confermo {tag.valore} per conoscenza."
    assert ripristina(frase, dizionario_di(fascicolo.tags)) == atteso


def test_TC_04_export_in_stato_draft_e_negato():
    fascicolo = fascicolo_vuoto("f1")
    assert fascicolo.state is State.DRAFT
    with pytest.raises(ExportNotAllowed):
        export_sanitized_text("f1", store_con(fascicolo))


def test_TC_05_un_segnaposto_sconosciuto_interrompe_il_ripristino():
    fascicolo = fascicolo_con(TESTO_RICCO, RilevatoreFinto(sempre=RILEVAZIONI_RICCHE))
    dizionario = dizionario_di(fascicolo.tags)
    with pytest.raises(UnknownPlaceholder, match=r"\[PERSONA_99\]"):
        ripristina("Rispondo a [PERSONA_99].", dizionario)


def test_TC_06_una_mutazione_dopo_l_approvazione_riporta_in_pending_e_nega_l_export():
    fascicolo = fascicolo_con(TESTO_RICCO, RilevatoreFinto(sempre=RILEVAZIONI_RICCHE))
    approva(fascicolo)
    assert fascicolo.state is State.APPROVED
    registra_mutazione(fascicolo)
    assert fascicolo.state is State.PENDING_REVIEW
    with pytest.raises(ExportNotAllowed):
        export_sanitized_text("f1", store_con(fascicolo))


def test_TC_07_un_valore_che_il_testo_non_contiene_resta_non_trovato():
    """Il modello ha nominato un valore normalizzato che nel documento non
    compare alla lettera: la riga resta in tabella come NON_TROVATO, il testo
    non cambia, e non si solleva nessun errore (spec §7)."""
    rilevatore = RilevatoreFinto(
        sempre=[Rilevazione(valore="Rossi Mario", categoria=Category.PERSONA)]
    )
    fascicolo = fascicolo_con(TESTO_RICCO, rilevatore)

    [tag] = list(fascicolo.tags.values())
    assert tag.stato is StatoTag.NON_TROVATO
    assert tag.occorrenze == 0

    documento = fascicolo.documents[0]
    assert tagga(documento.text, fascicolo.tags).mascherato == documento.text


def test_TC_08_una_risposta_fuori_schema_lascia_il_fascicolo_intatto():
    """Se il rilevatore solleva `AIResponseInvalid`, il fascicolo non deve
    cambiare affatto: niente tag scritti a metà, nessun contatore avanzato
    (spec §6)."""
    fascicolo = fascicolo_vuoto("f1")
    documento = costruisci_documento("contratto.txt", TESTO_RICCO.encode("utf-8"))
    aggiungi_documento(fascicolo, documento)

    with pytest.raises(AIResponseInvalid):
        analizza(fascicolo, RilevatoreCheFallisce())

    assert fascicolo.tags == {}
    assert fascicolo.counters == {categoria: 0 for categoria in Category}
    assert fascicolo.analizzati == set()
    assert fascicolo.state is State.DRAFT
