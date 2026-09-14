"""I chip in cima alla pagina devono dire la verità (issue #42, issue #51).

Questa è la guardia che mancava, e la si scrive dopo averne pagato il costo
due volte in versi opposti:

- la **#42**: un chip acceso per un passo che non funzionava;
- la **#51**: il vault funzionante mentre il chip restava grigio, con le sue
  issue chiuse su GitLab. Chi leggeva il tracker e chi apriva il programma
  vedevano due prodotti diversi, e nessuno dei due sbagliava a leggere.

Il difetto comune non è l'HTML: è che lo stato dichiarato dalla pagina e lo
stato reale dell'applicazione erano due scritture indipendenti, e niente le
teneva insieme. Qui vengono confrontate.

Il verso controllato è quello che fa danno: **un chip acceso deve avere la sua
rotta**. Il verso opposto — una rotta che esiste e un chip spento — non si può
controllare allo stesso modo senza inventare i nomi delle rotte che ancora non
esistono, e un test costruito su nomi immaginari passerebbe anche il giorno in
cui l'esportazione arriva sotto un altro percorso. Resta coperto dalla seconda
verifica: la didascalia non può dire spento ciò che i chip dicono acceso.
"""

import re

import pytest
from fastapi.testclient import TestClient

from cryptocustode.api.app import UI, crea_app

INDIRIZZO_DI_PROVA = "http://127.0.0.1:8765"

ROTTA_DEL_PASSO = {
    "carica": "/api/fascicolo/documenti",
    "revisione": "/api/fascicolo/analisi",
    "approvazione": "/api/fascicolo/approvazione",
    "esportazione": "/api/fascicolo/esportazione",
    "ripristino": "/api/fascicolo/ripristino",
    "vault": "/api/vault/salva",
}
"""La rotta che rende vero ogni passo acceso.

Solo i passi accesi stanno qui. Quando approvazione, esportazione o ripristino
arriveranno, chi accende il chip aggiunge la riga — e se se ne dimentica, il
test qui sotto glielo dice, perché un chip acceso senza voce in questa tabella
è rosso.
"""


@pytest.fixture(scope="module")
def percorsi() -> set[str]:
    """I percorsi che l'applicazione serve davvero, chiesti allo schema OpenAPI
    e non elencati a mano: una rotta rinominata deve far fallire questo test,
    non passare inosservata."""
    with TestClient(crea_app(), base_url=INDIRIZZO_DI_PROVA) as client:
        return set(client.get("/openapi.json").json()["paths"])


@pytest.fixture(scope="module")
def pagina() -> str:
    return (UI / "index.html").read_text(encoding="utf-8")


def chip(pagina: str) -> list[tuple[str, bool]]:
    """Il nome di ogni chip e se è acceso, letti dalla `nav` dei passi."""
    nav = re.search(r'<nav class="passi".*?</nav>', pagina, flags=re.S)
    assert nav is not None, "la nav dei passi non c'è più: il test va riscritto"

    trovati = []
    for span in re.finditer(
        r'<span class="passo ([^"]+)"(.*?)>(.*?)</span>', nav.group(0), flags=re.S
    ):
        classi, _, contenuto = span.groups()
        # Il nome è il testo fuori dall'SVG: l'ultima riga non vuota.
        senza_svg = re.sub(r"<svg.*?</svg>", "", contenuto, flags=re.S)
        nome = " ".join(senza_svg.split()).lower()
        trovati.append((nome, "inattivo" not in classi))
    return trovati


def test_ogni_chip_acceso_ha_la_sua_rotta(pagina, percorsi):
    """Il difetto della #42, preso alla radice."""
    accesi = [nome for nome, acceso in chip(pagina) if acceso]
    assert accesi, "nessun chip acceso: la nav è cambiata e il test va riscritto"

    for nome in accesi:
        assert nome in ROTTA_DEL_PASSO, (
            f"il chip {nome!r} è acceso ma non dichiara quale rotta lo rende "
            "vero: aggiungilo a ROTTA_DEL_PASSO, o spegnilo"
        )
        rotta = ROTTA_DEL_PASSO[nome]
        assert rotta in percorsi, (
            f"il chip {nome!r} è acceso ma {rotta} non esiste: la pagina "
            "promette un passo che l'applicazione non ha"
        )


def test_ogni_chip_spento_e_dichiarato_tale_anche_ai_lettori_di_schermo(pagina):
    """Un chip grigio al solo colore è acceso per chi non lo vede."""
    for span in re.finditer(
        r'<span class="passo ([^"]+)"([^>]*)>', pagina
    ):
        classi, attributi = span.groups()
        if "inattivo" in classi:
            assert 'aria-disabled="true"' in attributi, (
                f"un passo {classi!r} è spento solo visivamente"
            )


def test_la_didascalia_non_smentisce_i_chip(pagina):
    """L'altro verso, quello della #51: il vault funzionava e la pagina diceva
    che non c'era. Qui la didascalia non può nominare come spento un passo che
    i chip mostrano acceso."""
    didascalia = re.search(r'<p class="didascalia">(.*?)</p>', pagina, flags=re.S)
    assert didascalia is not None, "la didascalia non c'è più"

    testo = " ".join(didascalia.group(1).split()).lower()
    # La frase che elenca ciò che non funziona è quella che contiene «spent-»
    # («restano spenti», «resta spento»). Si guarda l'intero periodo e non solo
    # ciò che precede la parola, perché l'elenco può stare da entrambi i lati:
    # «restano spenti approvazione ed esportazione» è italiano quanto il
    # contrario.
    periodi = [p for p in re.split(r"[.;]", testo) if "spent" in p]
    accesi = [nome for nome, acceso in chip(pagina) if acceso]
    spenti = [nome for nome, acceso in chip(pagina) if not acceso]

    if not periodi:
        # Saltare qui era un buco: una didascalia che non nomina nessuno
        # spento passava il controllo **anche** con dei chip grigi in pagina,
        # cioè proprio nel caso in cui l'utente non ha modo di sapere perché
        # quel passo non risponde. È il difetto della #42 preso dall'altro
        # verso: lì la pagina prometteva meno di quello che faceva, qui
        # prometterebbe di più.
        assert not spenti, (
            "la didascalia non dice che nulla è spento, ma questi passi lo "
            f"sono: {spenti}. Nominali, o accendili."
        )
        pytest.skip("nessun passo spento da dichiarare: la didascalia è muta a ragione")

    for periodo in periodi:
        for nome in accesi:
            assert nome not in periodo, (
                f"la didascalia dice spento il passo {nome!r}, che invece è "
                f"acceso: «{periodo.strip()}»"
            )


def test_i_passi_spenti_non_hanno_un_comando_in_pagina(pagina):
    """La promessa che la didascalia fa: ciò che è spento non ha un bottone.

    Un bottone per un passo che non ha rotta darebbe un 404 in faccia
    all'utente, che è peggio di un chip grigio — il grigio almeno si spiega.
    """
    spenti = [nome for nome, acceso in chip(pagina) if not acceso]
    minuscola = pagina.lower()

    for nome in spenti:
        bottoni = re.findall(r"<button[^>]*>(.*?)</button>", minuscola, flags=re.S)
        for testo in bottoni:
            parole = " ".join(re.sub(r"<[^>]+>", "", testo).split())
            assert nome not in parole, (
                f"il passo {nome!r} è spento ma la pagina ha un bottone che lo "
                f"promette: {parole!r}"
            )
