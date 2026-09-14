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

from cryptocustode.api.app import crea_app
from tests.pagine import pagine

INDIRIZZO_DI_PROVA = "http://127.0.0.1:8765"

ROTTA_DEL_PASSO = {
    "carica": "/api/fascicolo/documenti",
    "salva": "/api/fascicolo/esportazione",
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
def con_passi() -> list[tuple[str, str]]:
    """Le pagine che dichiarano una barra dei passi, col loro sorgente.

    Dal 2026-09-14 le pagine sono tre e una sola ha i passi: `nascondi.html`.
    Il test non la nomina lo stesso — le cerca — perché una barra aggiunta
    domani a un'altra pagina deve entrare in questi controlli da sé, e un nome
    scritto qui la lascerebbe fuori senza far diventare rosso niente.
    """
    trovate = [
        (percorso.name, percorso.read_text(encoding="utf-8"))
        for percorso in pagine()
        if '<nav class="passi"' in percorso.read_text(encoding="utf-8")
    ]
    assert trovate, "nessuna pagina dichiara dei passi: il test va riscritto"
    return trovate


def chip(pagina: str) -> list[tuple[str, bool]]:
    """Il nome di ogni chip e se è acceso, letti dalla `nav` dei passi."""
    nav = re.search(r'<nav class="passi".*?</nav>', pagina, flags=re.S)
    assert nav is not None, "la nav dei passi non c'è più: il test va riscritto"

    trovati = []
    # `class="passo"` senza altre classi è un chip valido: la barra a due passi
    # marca solo quello corrente, e pretendere una seconda classe farebbe
    # sparire dal controllo proprio il passo non ancora raggiunto.
    for span in re.finditer(
        r'<span class="passo([^"]*)"(.*?)>(.*?)</span>', nav.group(0), flags=re.S
    ):
        classi, _, contenuto = span.groups()
        # Il nome è il testo fuori dall'SVG, senza il numero d'ordine: «1.
        # Carica» è lo stesso passo di «Carica», e il numero serve all'utente,
        # non alla tabella delle rotte.
        senza_svg = re.sub(r"<svg.*?</svg>", "", contenuto, flags=re.S)
        nome = " ".join(senza_svg.split()).lower()
        nome = re.sub(r"^\d+\.\s*", "", nome)
        trovati.append((nome, "inattivo" not in classi))
    return trovati


def test_ogni_chip_acceso_ha_la_sua_rotta(con_passi, percorsi):
    """Il difetto della #42, preso alla radice."""
    for nome_pagina, pagina in con_passi:
      accesi = [nome for nome, acceso in chip(pagina) if acceso]
      assert accesi, f"{nome_pagina}: nessun chip acceso, il test va riscritto"

      for nome in accesi:
        assert nome in ROTTA_DEL_PASSO, (
            f"{nome_pagina}: il chip {nome!r} è acceso ma non dichiara quale "
            "rotta lo rende vero: aggiungilo a ROTTA_DEL_PASSO, o spegnilo"
        )
        rotta = ROTTA_DEL_PASSO[nome]
        assert rotta in percorsi, (
            f"{nome_pagina}: il chip {nome!r} è acceso ma {rotta} non esiste: "
            "la pagina promette un passo che l'applicazione non ha"
        )


def test_ogni_chip_spento_e_dichiarato_tale_anche_ai_lettori_di_schermo(con_passi):
    """Un chip grigio al solo colore è acceso per chi non lo vede."""
    for nome_pagina, pagina in con_passi:
        for span in re.finditer(r'<span class="passo([^"]*)"([^>]*)>', pagina):
            classi, attributi = span.groups()
            if "inattivo" in classi:
                assert 'aria-disabled="true"' in attributi, (
                    f"{nome_pagina}: un passo {classi!r} è spento solo visivamente"
                )


def test_la_didascalia_non_smentisce_i_chip(con_passi):
    """L'altro verso, quello della #51: il vault funzionava e la pagina diceva
    che non c'era. Qui la didascalia non può nominare come spento un passo che
    i chip mostrano acceso.

    Dal 2026-09-14 una pagina può non avere didascalia, e `nascondi.html` non
    ce l'ha: la didascalia serviva a spiegare perché cinque chip su sei fossero
    grigi, e con due chip entrambi raggiungibili non resta niente da scusare.
    Il controllo non si indebolisce — una pagina **senza** didascalia non può
    avere chip spenti, altrimenti l'utente vedrebbe del grigio senza che nulla
    gli dica perché.
    """
    for nome_pagina, pagina in con_passi:
        spenti = [nome for nome, acceso in chip(pagina) if not acceso]
        accesi = [nome for nome, acceso in chip(pagina) if acceso]

        didascalia = re.search(r'<p class="didascalia">(.*?)</p>', pagina, flags=re.S)
        if didascalia is None:
            assert not spenti, (
                f"{nome_pagina} non ha didascalia ma ha passi spenti: {spenti}. "
                "Spiegali, o accendili."
            )
            continue

        testo = " ".join(didascalia.group(1).split()).lower()
        # La frase che elenca ciò che non funziona è quella che contiene
        # «spent-» («restano spenti», «resta spento»). Si guarda l'intero
        # periodo e non solo ciò che precede la parola, perché l'elenco può
        # stare da entrambi i lati.
        periodi = [p for p in re.split(r"[.;]", testo) if "spent" in p]

        if not periodi:
            # Saltare qui era un buco: una didascalia che non nomina nessuno
            # spento passava il controllo **anche** con dei chip grigi in
            # pagina, cioè proprio nel caso in cui l'utente non ha modo di
            # sapere perché quel passo non risponde.
            assert not spenti, (
                f"{nome_pagina}: la didascalia non dice che nulla è spento, ma "
                f"questi passi lo sono: {spenti}. Nominali, o accendili."
            )
            continue

        for periodo in periodi:
            for nome in accesi:
                assert nome not in periodo, (
                    f"{nome_pagina}: la didascalia dice spento il passo "
                    f"{nome!r}, che invece è acceso: «{periodo.strip()}»"
                )


def test_i_passi_spenti_non_hanno_un_comando_in_pagina(con_passi):
    """La promessa che la didascalia fa: ciò che è spento non ha un bottone.

    Un bottone per un passo che non ha rotta darebbe un 404 in faccia
    all'utente, che è peggio di un chip grigio — il grigio almeno si spiega.
    """
    for nome_pagina, pagina in con_passi:
        spenti = [nome for nome, acceso in chip(pagina) if not acceso]
        minuscola = pagina.lower()

        for nome in spenti:
            bottoni = re.findall(r"<button[^>]*>(.*?)</button>", minuscola, flags=re.S)
            for testo in bottoni:
                parole = " ".join(re.sub(r"<[^>]+>", "", testo).split())
                assert nome not in parole, (
                    f"{nome_pagina}: il passo {nome!r} è spento ma la pagina ha "
                    f"un bottone che lo promette: {parole!r}"
                )
