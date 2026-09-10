import pytest

from cryptocustode.core.errors import MalformedPlaceholder, UnknownPlaceholder
from cryptocustode.core.models import Category, Entity
from cryptocustode.core.unmask import ripristina


def dizionario():
    return {
        "e1": Entity(
            entity_id="e1",
            category=Category.PERSONA,
            placeholder="[PERSONA_1]",
            canonical_value="Mario Rossi",
        ),
        "e2": Entity(
            entity_id="e2",
            category=Category.PERSONA,
            placeholder="[PERSONA_10]",
            canonical_value="Luisa Bianchi",
        ),
        "e3": Entity(
            entity_id="e3",
            category=Category.IBAN,
            placeholder="[IBAN_1]",
            canonical_value="IT60X0542811101000000123456",
        ),
    }


def test_un_segnaposto_viene_sostituito():
    assert ripristina("Il contratto è di [PERSONA_1].", dizionario()) == (
        "Il contratto è di Mario Rossi."
    )


def test_piu_segnaposto_di_categorie_diverse():
    testo = "[PERSONA_1] versa su [IBAN_1]."
    assert ripristina(testo, dizionario()) == (
        "Mario Rossi versa su IT60X0542811101000000123456."
    )


def test_lo_stesso_segnaposto_ripetuto_viene_sostituito_ovunque():
    testo = "[PERSONA_1] e ancora [PERSONA_1]"
    assert ripristina(testo, dizionario()) == "Mario Rossi e ancora Mario Rossi"


def test_indice_a_due_cifre_non_lascia_uno_zero_orfano():
    # Il caso che impone l'ordinamento per lunghezza decrescente: sostituendo
    # prima [PERSONA_1] resterebbe "Mario Rossi0".
    assert ripristina("[PERSONA_10] firma.", dizionario()) == "Luisa Bianchi firma."


def test_testo_senza_segnaposto_torna_identico():
    assert ripristina("Nessun segnaposto qui.", dizionario()) == (
        "Nessun segnaposto qui."
    )


def test_segnaposto_sconosciuto_interrompe_il_ripristino():
    # TC-05: [PERSONA_99] non è nel dizionario del fascicolo attivo.
    with pytest.raises(UnknownPlaceholder, match=r"\[PERSONA_99\]"):
        ripristina("Il contratto è di [PERSONA_99].", dizionario())


def test_tipo_inesistente_ma_ben_formato_e_uno_sconosciuto():
    # [PERSON_1] supera la regex severa: è ben formato, e il fatto che PERSON
    # non esista è una questione di dizionario (scostamento 3 in testa al piano).
    with pytest.raises(UnknownPlaceholder, match=r"\[PERSON_1\]"):
        ripristina("Firmato da [PERSON_1].", dizionario())


def test_segnaposto_senza_chiusura_e_malformato():
    with pytest.raises(MalformedPlaceholder, match=r"\[PERSONA_1"):
        ripristina("Firmato da [PERSONA_1 oggi.", dizionario())


def test_segnaposto_in_minuscolo_e_malformato():
    with pytest.raises(MalformedPlaceholder, match=r"\[persona_1\]"):
        ripristina("Firmato da [persona_1].", dizionario())


def test_il_messaggio_cita_i_frammenti_letteralmente():
    with pytest.raises(MalformedPlaceholder) as errore:
        ripristina("[persona_1] e [PERSONA_2", dizionario())
    messaggio = str(errore.value)
    assert "[persona_1]" in messaggio
    assert "[PERSONA_2" in messaggio


def test_nessun_ripristino_parziale_con_un_segnaposto_sconosciuto():
    # Un solo segnaposto ignoto basta a fermare tutto: gli altri, validi,
    # non vengono sostituiti.
    with pytest.raises(UnknownPlaceholder):
        ripristina("[PERSONA_1] e [PERSONA_99]", dizionario())


def test_nessun_ripristino_parziale_con_un_frammento_malformato():
    with pytest.raises(MalformedPlaceholder):
        ripristina("[PERSONA_1] e [persona_2]", dizionario())


def test_le_alterazioni_hanno_la_precedenza_sugli_sconosciuti():
    # Quando ci sono entrambi si segnala prima la forma: è l'errore che
    # l'utente può correggere leggendo il proprio testo.
    with pytest.raises(MalformedPlaceholder):
        ripristina("[persona_1] e [PERSONA_99]", dizionario())


def test_una_parentesi_quadra_innocente_blocca_comunque_il_ripristino():
    # Falso positivo noto e voluto: la regex permissiva della spec §11 rende
    # opzionali separatore e cifre, quindi "[Nota]" le somiglia abbastanza.
    # Fermarsi è il verso giusto in cui sbagliare — l'alternativa è procedere
    # su un testo in cui un segnaposto storpiato è passato inosservato.
    with pytest.raises(MalformedPlaceholder, match=r"\[Nota\]"):
        ripristina("[PERSONA_1] firma. [Nota] a margine.", dizionario())
