import hashlib

import pytest

from cryptocustode.core.errors import (
    DuplicateFilename,
    EmptyDocument,
    FascicoloFull,
    InvalidEncoding,
)
from cryptocustode.core.ingest.loader import (
    aggiungi_documento,
    costruisci_documento,
    segnaposto_preesistenti,
)
from cryptocustode.core.models import Fascicolo, fascicolo_vuoto
from tests.pdf_di_prova import pdf_di_prova


def documento(indice: int):
    return costruisci_documento(f"doc{indice}.txt", b"Testo di prova.")


@pytest.fixture
def fascicolo_pieno():
    # Fascicolo al tetto, per i test in cui riempire è il preambolo e la tesi
    # è il rifiuto dell'undicesimo. Il documento in eccesso resta nel test: è la
    # mossa sotto esame, non il setup.
    # Il tetto non è cablato, così la fixture segue MAX_DOCUMENTI se cambia. E
    # se `aggiungi_documento` smettesse di accettare i primi dieci, la fixture
    # andrebbe in errore invece di nascondere il rifiuto che dovrebbe preparare.
    fascicolo = fascicolo_vuoto("f1")
    for indice in range(Fascicolo.MAX_DOCUMENTI):
        aggiungi_documento(fascicolo, documento(indice))
    return fascicolo


def test_txt_viene_riconosciuto_dall_estensione():
    doc = costruisci_documento("contratto.txt", "Torino".encode("utf-8"))
    assert doc.text == "Torino"
    assert doc.filename == "contratto.txt"


def test_pdf_viene_riconosciuto_dall_estensione():
    doc = costruisci_documento("contratto.pdf", pdf_di_prova(["testo"]))
    assert "Contratto di locazione" in doc.text


def test_l_estensione_e_insensibile_alle_maiuscole():
    doc = costruisci_documento("CONTRATTO.TXT", b"Torino")
    assert doc.text == "Torino"


def test_l_estensione_pdf_maiuscola_viene_riconosciuta():
    # A differenza del caso .TXT sopra, questo può passare solo se il
    # confronto sull'estensione è insensibile alle maiuscole: senza `.lower()`
    # ".PDF" non farebbe match con ".pdf" e il file cadrebbe nel ramo TXT,
    # dove tentare di decodificare byte PDF come UTF-8 fallisce.
    doc = costruisci_documento("CONTRATTO.PDF", pdf_di_prova(["testo"]))
    assert "Contratto di locazione" in doc.text


def test_estensione_sconosciuta_viene_trattata_come_txt():
    # Un file senza estensione nota è tentato come testo: se non è UTF-8
    # l'errore arriva dal caricatore TXT, che è il comportamento voluto.
    with pytest.raises(InvalidEncoding):
        costruisci_documento("appunti", "perch\xe8".encode("latin-1"))


def test_sha256_del_txt_e_dei_byte_originali():
    # Per un TXT valido decode+encode UTF-8 è un'identità: i byte originali e
    # il testo riestratto, una volta ricodificato, tornano identici. Questo
    # test dimostra quindi solo che l'assert vale sul percorso TXT: non basta
    # a distinguere un digest sui byte originali da uno sul testo estratto —
    # per quello vedi il caso PDF sotto, dove i due divergono davvero.
    contenuto = "Torino".encode("utf-8")
    doc = costruisci_documento("a.txt", contenuto)
    assert doc.sha256 == hashlib.sha256(contenuto).hexdigest()


def test_sha256_del_pdf_e_dei_byte_originali_non_del_testo_estratto():
    # Sul PDF i byte del file e il testo estratto, ricodificato in UTF-8, sono
    # provabilmente diversi: solo qui il test può distinguere un digest sui
    # byte originali da uno (erroneamente) sul testo estratto.
    contenuto = pdf_di_prova(["testo"])
    doc = costruisci_documento("a.pdf", contenuto)
    assert doc.text.encode("utf-8") != contenuto
    assert doc.sha256 == hashlib.sha256(contenuto).hexdigest()


def test_i_doc_id_sono_distinti():
    primo = costruisci_documento("a.txt", b"uno")
    secondo = costruisci_documento("b.txt", b"due")
    assert primo.doc_id != secondo.doc_id


def test_il_txt_ha_un_solo_offset_di_pagina():
    doc = costruisci_documento("a.txt", b"Torino")
    assert doc.page_offsets == [0]


def test_dieci_documenti_entrano():
    # Non usa la fixture `fascicolo_pieno` di proposito: qui il ciclo è la tesi
    # e non il preambolo. La claim è proprio che dieci `aggiungi_documento` di
    # fila riescono, e spostarla nel setup la renderebbe invisibile a chi legge.
    fascicolo = fascicolo_vuoto("f1")
    for indice in range(Fascicolo.MAX_DOCUMENTI):
        aggiungi_documento(fascicolo, documento(indice))
    assert len(fascicolo.documents) == 10


def test_l_undicesimo_documento_viene_rifiutato(fascicolo_pieno):
    with pytest.raises(FascicoloFull, match="10"):
        aggiungi_documento(fascicolo_pieno, documento(99))


def test_il_rifiuto_non_lascia_il_fascicolo_alterato(fascicolo_pieno):
    with pytest.raises(FascicoloFull):
        aggiungi_documento(fascicolo_pieno, documento(99))
    assert len(fascicolo_pieno.documents) == 10


def test_un_secondo_file_con_lo_stesso_nome_viene_rifiutato():
    # Issue #19: il payload dell'export è indicizzato per nome file (spec §8),
    # quindi due omonimi presi da cartelle diverse collasserebbero in una sola
    # chiave e l'utente riceverebbe un documento in meno senza alcun errore.
    # Il nome finisce nel messaggio: è l'unico modo per sapere quale rinominare.
    fascicolo = fascicolo_vuoto("f1")
    aggiungi_documento(fascicolo, costruisci_documento("contratto.txt", b"Primo"))
    with pytest.raises(DuplicateFilename, match="contratto.txt"):
        aggiungi_documento(fascicolo, costruisci_documento("contratto.txt", b"Secondo"))


def test_il_rifiuto_dell_omonimo_lascia_intatto_il_primo():
    # Il controllo precede la mutazione, come per FascicoloFull: il documento
    # già caricato resta quello di prima, non viene sovrascritto dal secondo.
    fascicolo = fascicolo_vuoto("f1")
    aggiungi_documento(fascicolo, costruisci_documento("contratto.txt", b"Primo"))
    with pytest.raises(DuplicateFilename):
        aggiungi_documento(fascicolo, costruisci_documento("contratto.txt", b"Secondo"))
    assert [doc.filename for doc in fascicolo.documents] == ["contratto.txt"]
    assert fascicolo.documents[0].text == "Primo"


def test_nessun_segnaposto_preesistente_in_un_testo_normale():
    assert segnaposto_preesistenti("Il conduttore firma il contratto.") == []


def test_segnaposto_preesistente_viene_segnalato_con_la_posizione():
    testo = "Il conduttore [PERSONA_1] firma."
    assert segnaposto_preesistenti(testo) == [(14, "[PERSONA_1]")]


def test_piu_segnaposto_preesistenti_in_ordine():
    testo = "[IBAN_2] e poi [PERSONA_10]"
    assert segnaposto_preesistenti(testo) == [(0, "[IBAN_2]"), (15, "[PERSONA_10]")]


def test_un_quasi_segnaposto_non_viene_segnalato():
    # La forma canonica è [MAIUSCOLE_CIFRE]: queste non lo sono.
    assert segnaposto_preesistenti("[persona_1] e [PERSONA] e [1_PERSONA]") == []


def test_un_documento_senza_testo_non_entra_nel_fascicolo():
    """Un PDF di sole pagine bianche — nessun testo e nessuna immagine — passava
    l'esame delle scansioni una pagina per volta: «pagina bianca senza immagini,
    non contiene nulla da proteggere, passa». Nessuno guardava il documento
    intero, e il risultato entrava nel fascicolo con zero caratteri.

    Non è un caso di scuola. Quel documento costava un'analisi a Gemini, usciva
    come file mascherato vuoto, e falliva al ripristino con «il file è vuoto»:
    l'utente lo scopriva in fondo a un giro intero, invece che nell'unico
    momento in cui il rifiuto è ancora gratis.
    """
    with pytest.raises(EmptyDocument):
        costruisci_documento("scansione.pdf", pdf_di_prova(["bianca"]))


def test_una_pagina_bianca_accanto_a_una_con_testo_resta_ammessa():
    """Il contrappeso del test qui sopra, e il motivo per cui la regola sta sul
    documento e non sulla pagina: un documento con una pagina bianca in mezzo ha
    comunque testo da proteggere, e continua a entrare. È la decisione già presa
    da `test_pagina_bianca_senza_immagini_e_accettata`, che questa regola non
    deve revocare di straforo.
    """
    doc = costruisci_documento("misto.pdf", pdf_di_prova(["testo", "bianca"]))

    assert "Contratto di locazione" in doc.text


def test_un_txt_di_soli_spazi_non_entra_nel_fascicolo():
    """Stessa regola, altro formato. Il buco era identico: `carica_txt` decodifica
    e restituisce, e una stringa di soli spazi è UTF-8 validissimo. La regola sta
    nella facciata proprio per valere su entrambi i formati senza essere scritta
    due volte.
    """
    with pytest.raises(EmptyDocument):
        costruisci_documento("vuoto.txt", "   \n\n\t".encode("utf-8"))
