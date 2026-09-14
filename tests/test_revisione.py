"""Revisione: testo evidenziato e toggle per tag (issue #4, riscritta per la
corsia IA della spec del 2026-09-14).

Questi test difendono due cose che si verificano su **superfici diverse**, e
tenerle distinte è il punto della slice:

1. quello che il fascicolo diventa — stato `PENDING_REVIEW`, tabella dei tag
   popolata, interruttori che cambiano davvero cosa verrà mascherato — si
   verifica **guardando il fascicolo nello store**, non credendo alla
   risposta HTTP sulla parola;
2. quello che l'utente vede — il testo segmentato, le evidenziazioni per
   categoria, gli interruttori che si accendono — si verifica **eseguendo il
   vero `cryptocustode/ui/app.js`** tramite `tests/ui_harness.mjs`.

La ragione della seconda è misurata, non temuta: nella issue #3 tre rotture da
un solo token nella UI (il nome del campo multipart, l'id di un elemento, una
lettera nella rotta) hanno lasciato la suite completamente verde mentre
l'utente vedeva 422, 404 e una pagina morta. «La risposta contiene X» non è una
verifica di «la pagina mostra X».

Quello che l'harness **non** prova, e non va spacciato per coperto: il
rendering, il CSS applicato, e che il browser esegua davvero la pagina.

Il rilevatore non è più il NER interno: è iniettato (`client_con_rilevatore`),
ed è un `RilevatoreFinto` a rispondere. Senza quel doppio ogni test che
analizza farebbe partire il client Gemini vero — l'invariante 5 della spec §4.
"""

import inspect
import json
import re
import shutil
import subprocess
from contextlib import ExitStack
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from cryptocustode.api.app import UI, crea_app
from cryptocustode.api.routes_fascicolo import ID_FASCICOLO_ATTIVO, crea_router
from cryptocustode.core.models import Category, Rilevazione, State, StatoTag
from cryptocustode.state.session import SessionStore
from tests.doppi import RilevatoreCheFallisceSuAlcuniTesti, RilevatoreFinto

INDIRIZZO_DI_PROVA = "http://127.0.0.1:8765"
"""L'app accetta solo il loopback nell'intestazione `Host` (`HOST_CONSENTITI`),
quindi il `base_url` di default del TestClient prenderebbe un 400 su ogni
richiesta. Il valore di prova sta qui e non fra gli host di produzione."""

ROTTA_DOCUMENTI = "/api/fascicolo/documenti"
ROTTA_ANALISI = "/api/fascicolo/analisi"
ROTTA_CATEGORIA = "/api/fascicolo/categoria"
ROTTA_TAG = "/api/fascicolo/tag"

HARNESS = Path(__file__).parent / "ui_harness.mjs"

UNO = "Il sig. Mario Rossi paga 1.200,00 euro."
DUE = "Anche Mario Rossi firma, IBAN IT60X0542811101000000123456."


@pytest.fixture
def store() -> SessionStore:
    """Lo store passato come seme all'app, per guardarci dentro dopo."""
    return SessionStore()


@pytest.fixture
def client(store):
    with TestClient(crea_app(store=store), base_url=INDIRIZZO_DI_PROVA) as client:
        yield client


@pytest.fixture
def client_con_rilevatore(store):
    """Un `TestClient` e il `RilevatoreFinto` che l'app userà.

    Il rilevatore arriva per parametro come già fa lo store: costruirlo dentro
    `crea_app` significherebbe che ogni test fa partire il client Gemini vero,
    cioè che la suite tocca la rete (spec §4, invariante 5).

    Restituisce una funzione e non una coppia già fatta perché ogni test ha
    bisogno di un doppio programmato diversamente: una fixture che decidesse
    lei le rilevazioni costringerebbe i test ad accettare le sue.

    Ogni `TestClient` costruito da `costruisci` entra nel proprio context
    manager tramite l'`ExitStack` della fixture, non lo restituisce grezzo:
    senza `__enter__` starlette non programma mai `self.lifespan`, quindi
    `ciclo_di_vita` (e con lui `al_pronto`) non partirebbe per nessun test che
    usa questa fixture — oggi innocuo solo perché `ciclo_di_vita` non fa altro,
    ma silenzioso e fragile per la prossima inizializzazione che vi si
    appoggerà. Lo stack si chiude allo smontaggio della fixture, chiudendo con
    sé anche il client — la stessa pulizia che la fixture `client` ottiene dal
    suo `with`.

    `rilevatore`, se passato, scavalca `RilevatoreFinto`: serve ai test che
    devono provare un fallimento a metà giro (spec §6), per cui `RilevatoreFinto`
    non basta — non solleva mai, risponde solo quello che gli si è detto.
    """
    with ExitStack() as stack:
        def costruisci(rilevatore=None, **kwargs):
            finto = rilevatore if rilevatore is not None else RilevatoreFinto(**kwargs)
            app = crea_app(store=store, rilevatore=finto)
            client = stack.enter_context(TestClient(app, base_url=INDIRIZZO_DI_PROVA))
            return client, finto

        yield costruisci


def carica(client: TestClient, nome: str, testo: str):
    return client.post(
        ROTTA_DOCUMENTI, files={"file": (nome, testo.encode("utf-8"), "text/plain")}
    )


def _file(nome: str, testo: str):
    return {"file": (nome, testo.encode("utf-8"), "text/plain")}


def fascicolo_di(store: SessionStore):
    return store.prendi(ID_FASCICOLO_ATTIVO)


# --- L'analisi usa il rilevatore iniettato -----------------------------------


def test_l_analisi_usa_il_rilevatore_iniettato(client_con_rilevatore):
    client, finto = client_con_rilevatore(
        sempre=[Rilevazione(valore="Mario Rossi", categoria=Category.PERSONA)]
    )
    client.post(ROTTA_DOCUMENTI, files=_file("a.txt", "Mario Rossi paga."))
    revisione = client.post(ROTTA_ANALISI).json()

    segmenti = revisione["documenti"][0]["segmenti"]
    assert [s["testo"] for s in segmenti] == ["Mario Rossi", " paga."]
    assert segmenti[0]["tag"] == "[PERSONA_1]"
    assert segmenti[0]["mascherato"] is False, "nessuna categoria parte accesa"

    # Il rilevatore ha fatto il suo lavoro anche con la categoria spenta: il
    # dato è stato trovato e ha il suo segnaposto, solo non verrà sostituito
    # finché l'utente non accende l'interruttore. È la distinzione fra
    # *riconoscere* e *mascherare*, e il default nuovo la rende osservabile.
    acceso = client.post(ROTTA_CATEGORIA, json={"categoria": "PERSONA", "attiva": True})
    assert acceso.json()["documenti"][0]["segmenti"][0]["mascherato"] is True


def test_un_documento_gia_analizzato_non_ripaga_una_chiamata(client_con_rilevatore):
    """Ogni chiamata costa e manda il documento in rete: rianalizzare ciò che
    si è già analizzato è una spesa e un'esposizione senza contropartita."""
    client, finto = client_con_rilevatore(sempre=[])
    client.post(ROTTA_DOCUMENTI, files=_file("a.txt", "Mario Rossi paga."))
    client.post(ROTTA_ANALISI)
    client.post(ROTTA_ANALISI)

    assert finto.chiamate == ["Mario Rossi paga."]


def test_un_documento_aggiunto_dopo_l_analisi_viene_comunque_rilevato(client_con_rilevatore):
    """Criterio 5: chi aggiunge un documento dopo una prima analisi ripreme lo
    stesso bottone, e il documento nuovo deve passare dal rilevatore — solo
    quello già analizzato viene saltato, non l'intera seconda chiamata."""
    client, finto = client_con_rilevatore(sempre=[])
    client.post(ROTTA_DOCUMENTI, files=_file("a.txt", "Mario Rossi paga."))
    client.post(ROTTA_ANALISI)

    client.post(ROTTA_DOCUMENTI, files=_file("b.txt", "Anche Luigi firma."))
    seconda = client.post(ROTTA_ANALISI)

    assert seconda.status_code == 200, seconda.text
    assert finto.chiamate == ["Mario Rossi paga.", "Anche Luigi firma."]


def test_dopo_l_analisi_lo_stato_e_pending_review(client_con_rilevatore, store):
    """Criterio 4, verificato **nel fascicolo** e non nella risposta HTTP: un
    payload che dicesse `"stato": "PENDING_REVIEW"` senza che il fascicolo
    fosse davvero passato di stato non basterebbe (spec §7, TC-03 adattato
    alla corsia IA: l'omonimia fra documenti non è più intercettata, spec §16
    limite noto 2)."""
    client, finto = client_con_rilevatore(
        sempre=[Rilevazione(valore="Mario Rossi", categoria=Category.PERSONA)]
    )
    client.post(ROTTA_DOCUMENTI, files=_file("uno.txt", UNO))

    risposta = client.post(ROTTA_ANALISI)

    assert risposta.status_code == 200, risposta.text
    assert fascicolo_di(store).state is State.PENDING_REVIEW


def test_l_analisi_di_un_fascicolo_vuoto_e_rifiutata_invece_di_promuoverlo(client, store):
    """Senza documenti non c'è niente da analizzare, e promuovere comunque il
    fascicolo a `PENDING_REVIEW` lo renderebbe approvabile: un fascicolo vuoto
    approvato esporta zero documenti senza che nulla lo segnali. Usa il
    `client` semplice: senza documenti la route non arriva mai a interrogare
    il rilevatore, quindi il default (`RilevatoreGemini` senza chiave) non
    viene mai chiamato.
    """
    risposta = client.post(ROTTA_ANALISI)

    assert risposta.status_code == 422
    assert "documento" in risposta.json()["errore"]
    assert fascicolo_di(store).state is State.DRAFT


def test_un_rilevatore_che_fallisce_a_meta_giro_lascia_il_fascicolo_intatto(
    client_con_rilevatore, store
):
    """Spec §6, verificato sulla rotta vera — `tests/test_matrice_consegna.py`
    e `tests/test_documenti_di_verifica.py` verificano la stessa promessa, ma
    contro una copia della sequenza della rotta, non contro la rotta stessa.

    Il fallimento arriva apposta sul **secondo** documento, non sul primo: un
    doppio che sollevasse già alla prima chiamata passerebbe anche se la rotta
    scrivesse il fascicolo dopo ogni documento invece che a fine giro, che è
    esattamente il difetto che questo test deve poter vedere.
    """
    doppio = RilevatoreCheFallisceSuAlcuniTesti(
        {UNO: [Rilevazione(valore="Mario Rossi", categoria=Category.PERSONA)]}
    )
    client, _ = client_con_rilevatore(rilevatore=doppio)
    carica(client, "uno.txt", UNO)
    carica(client, "due.txt", DUE)

    risposta = client.post(ROTTA_ANALISI)

    assert risposta.status_code == 502, risposta.text
    fascicolo = fascicolo_di(store)
    assert fascicolo.tags == {}
    assert all(contatore == 0 for contatore in fascicolo.counters.values())
    assert fascicolo.analizzati == set()
    assert fascicolo.state is State.DRAFT


def test_riaccendere_un_tag_non_trovato_non_lo_marca_applicato(
    client_con_rilevatore, store
):
    """Un tag `NON_TROVATO` — il modello ha nominato un valore che nel testo
    non compare alla lettera, quindi zero occorrenze — non deve diventare
    `APPLICATO` solo perché l'utente lo riaccende: sarebbe una riga che
    dichiara una sostituzione mai avvenuta, e nella direzione insicura, quella
    che fa credere mascherato un dato rimasto in chiaro. Irraggiungibile dalla
    UI di oggi, che disegna solo i tag con almeno una regione — ma la tabella
    della fase 2 mostra anche `NON_TROVATO`, e da lì lo diventa.
    """
    client, finto = client_con_rilevatore(
        sempre=[Rilevazione(valore="Nome Assente", categoria=Category.PERSONA)]
    )
    carica(client, "uno.txt", UNO)
    client.post(ROTTA_ANALISI)
    assert fascicolo_di(store).tags["[PERSONA_1]"].stato is StatoTag.NON_TROVATO

    client.post(ROTTA_TAG, json={"tag": "[PERSONA_1]", "attivo": False})
    risposta = client.post(ROTTA_TAG, json={"tag": "[PERSONA_1]", "attivo": True})

    assert risposta.status_code == 200, risposta.text
    tag = fascicolo_di(store).tags["[PERSONA_1]"]
    assert tag.occorrenze == 0
    assert tag.stato is StatoTag.NON_TROVATO


# --- Criterio 1, metà server: i segmenti coprono il testo originale ---------


def test_i_segmenti_serviti_ricompongono_esattamente_il_testo_originale(
    client_con_rilevatore, store
):
    """Criterio 1, metà server. Il testo evidenziato si costruisce spezzando il
    testo **originale** sulle regioni che la mascheratura rivendica: se la
    giunzione perdesse o duplicasse un carattere, l'utente reviserebbe un
    testo che non è quello che verrà mascherato.

    La decisione 2 della spec §2 dice che il testo estratto è immutabile:
    questo test è ciò che la rende osservabile.
    """
    client, finto = client_con_rilevatore(
        sempre=[
            Rilevazione(valore="Mario Rossi", categoria=Category.PERSONA),
            Rilevazione(valore="1.200,00 euro", categoria=Category.IMPORTO),
        ]
    )
    carica(client, "uno.txt", UNO)

    esito = client.post(ROTTA_ANALISI).json()

    [documento] = esito["documenti"]
    assert "".join(s["testo"] for s in documento["segmenti"]) == UNO
    evidenziati = [s for s in documento["segmenti"] if s["categoria"] is not None]
    categorie = {s["categoria"] for s in evidenziati}
    assert categorie == {"PERSONA", "IMPORTO"}, categorie
    assert all(s["tag"] for s in evidenziati)
    # Il default dell'emendamento alla decisione 4 arriva fino al payload che
    # la pagina disegna: nessuna categoria parte accesa, quindi ogni segmento
    # è evidenziato — l'utente vede cosa è stato trovato — ma nessuno è ancora
    # mascherato. Asserito per categoria e non con un `any()`, così il giorno
    # in cui una categoria tornasse accesa il test dice quale.
    acceso = {s["categoria"]: s["mascherato"] for s in evidenziati}
    assert acceso == {"PERSONA": False, "IMPORTO": False}, acceso


# --- Criterio 2, metà server: gli interruttori cambiano il fascicolo -------


def test_il_toggle_di_categoria_spegne_il_mascheramento_di_quella_categoria(
    client_con_rilevatore, store
):
    """Criterio 2, metà server, verificato sul fascicolo: `category_enabled` è
    metà della condizione che `mask.tabella_attiva` legge, quindi è lì che si
    vede se il toggle cambia davvero cosa verrà mascherato. Una risposta HTTP
    che dicesse «spento» senza mutare il fascicolo esporterebbe comunque il
    dato.
    """
    client, finto = client_con_rilevatore(
        sempre=[
            Rilevazione(valore="Mario Rossi", categoria=Category.PERSONA),
            Rilevazione(valore="1.200,00 euro", categoria=Category.IMPORTO),
        ]
    )
    carica(client, "uno.txt", UNO)
    client.post(ROTTA_ANALISI)
    # `IMPORTO` parte spento (spec §2, emendamento alla decisione 4): lo
    # accendiamo prima, così l'asserzione più sotto prova davvero che il
    # toggle tocca solo la categoria richiesta. Su una categoria già al suo
    # valore predefinito non proverebbe nulla.
    client.post(ROTTA_CATEGORIA, json={"categoria": "IMPORTO", "attiva": True})

    risposta = client.post(ROTTA_CATEGORIA, json={"categoria": "PERSONA", "attiva": False})

    assert risposta.status_code == 200, risposta.text
    fascicolo = fascicolo_di(store)
    assert fascicolo.category_enabled[Category.PERSONA] is False
    assert fascicolo.category_enabled[Category.IMPORTO] is True, "spento solo il richiesto"
    [documento] = risposta.json()["documenti"]
    persona = [s for s in documento["segmenti"] if s["categoria"] == "PERSONA"]
    assert persona and not any(s["mascherato"] for s in persona)


def test_lo_spegnimento_di_un_tag_non_tocca_gli_altri_tag_della_stessa_categoria(
    client_con_rilevatore, store
):
    """Criterio 2, metà server. Nel mondo dei tag la granularità è il *valore*,
    non la singola occorrenza: spegnere `[PERSONA_1]` deve spegnere tutte le
    occorrenze di quel valore, ma non deve toccare un altro tag della stessa
    categoria — altrimenti sarebbe il toggle di categoria con un altro nome.
    """
    client, finto = client_con_rilevatore(
        sempre=[
            Rilevazione(valore="Mario Rossi", categoria=Category.PERSONA),
            Rilevazione(valore="Luigi Bianchi", categoria=Category.PERSONA),
        ]
    )
    carica(client, "uno.txt", "Mario Rossi e Luigi Bianchi firmano.")
    client.post(ROTTA_ANALISI)
    # La categoria va accesa: spegnere un singolo tag dentro una categoria già
    # spenta non distinguerebbe i due interruttori, che è tutto ciò che questo
    # test esiste per distinguere.
    client.post(ROTTA_CATEGORIA, json={"categoria": "PERSONA", "attiva": True})

    risposta = client.post(ROTTA_TAG, json={"tag": "[PERSONA_1]", "attivo": False})

    assert risposta.status_code == 200, risposta.text
    fascicolo = fascicolo_di(store)
    assert fascicolo.tags["[PERSONA_1]"].stato.value == "DISATTIVATO"
    assert fascicolo.tags["[PERSONA_2]"].stato.value != "DISATTIVATO"
    assert fascicolo.category_enabled[Category.PERSONA] is True, "la categoria resta accesa"
    [documento] = risposta.json()["documenti"]
    spento = [s for s in documento["segmenti"] if s["tag"] == "[PERSONA_1]"]
    acceso = [s for s in documento["segmenti"] if s["tag"] == "[PERSONA_2]"]
    assert spento and not any(s["mascherato"] for s in spento)
    assert acceso and all(s["mascherato"] for s in acceso)


def test_un_tag_inesistente_e_un_404(client_con_rilevatore):
    client, finto = client_con_rilevatore(sempre=[])
    client.post(ROTTA_DOCUMENTI, files=_file("a.txt", "niente."))
    client.post(ROTTA_ANALISI)

    risposta = client.post(
        ROTTA_TAG, json={"tag": "[PERSONA_99]", "attivo": False}
    )

    assert risposta.status_code == 404
    assert "PERSONA_99" in risposta.json()["errore"]


def test_la_revisione_non_parla_piu_di_ambiguita(client_con_rilevatore):
    client, finto = client_con_rilevatore(sempre=[])
    client.post(ROTTA_DOCUMENTI, files=_file("a.txt", "niente."))

    assert "ambiguita" not in client.post(ROTTA_ANALISI).json()


# --- La UI eseguita per davvero ---------------------------------------------

senza_node = pytest.mark.skipif(
    shutil.which("node") is None, reason="node non installato: la UI non viene eseguita"
)


def esito_della_ui(scenario: str) -> dict:
    """Esegue il vero `cryptocustode/ui/app.js` e restituisce quello che
    l'utente avrebbe visto: i segmenti disegnati con le loro classi, gli
    interruttori con la loro posizione, la riga di stato, e quali richieste
    sono davvero partite.

    L'harness carica il file di produzione — non una copia — dentro un DOM
    finto con una `fetch` programmata. Non prova il rendering, né il CSS
    applicato, né che il browser esegua la pagina: quello resta un controllo
    umano. Prova la logica, che è la metà che nessun test toccava.
    """
    esecuzione = subprocess.run(
        ["node", str(HARNESS), scenario], capture_output=True, text=True, encoding="utf-8"
    )

    assert esecuzione.returncode == 0, esecuzione.stderr
    return json.loads(esecuzione.stdout)


def risolvi_token(valore: str, css: str) -> str:
    """Il valore di una dichiarazione CSS, seguendo un eventuale `var(--x)`.

    I colori delle evidenziazioni passano da token, così il restyle della UI ha
    un solo posto in cui ritoccarli invece di dodici valori sparsi nelle
    regole. Ma il confronto fra categorie deve restare sui colori veri: due
    token distinti con lo stesso valore darebbero due evidenziazioni
    indistinguibili, e un confronto sui nomi dei token le chiamerebbe diverse.
    """
    riferimento = re.fullmatch(r"var\(\s*(--[\w-]+)\s*\)", valore)
    if riferimento is None:
        return valore
    dichiarato = re.search(rf"{re.escape(riferimento.group(1))}:\s*([^;]+);", css)
    assert dichiarato is not None, f"il token {riferimento.group(1)} non è dichiarato"
    return risolvi_token(dichiarato.group(1).strip(), css)


def campi_delle_rotte() -> list[tuple[str, set[str], set[str]]]:
    """Per ogni rotta del fascicolo: il percorso, i nomi dei suoi parametri e i
    campi del modello che ne descrive il corpo.

    `eval_str=True` non è un dettaglio: senza di quello, con annotazioni
    lasciate come stringhe da qualche import che tornasse a introdurre
    `from __future__ import annotations`, nessun `issubclass` scatterebbe e
    ogni test che cerca i campi del corpo passerebbe su un insieme vuoto —
    verde senza aver guardato niente.
    """
    router = crea_router(SessionStore(), RilevatoreFinto())
    rotte = []
    for rotta in router.routes:
        parametri = inspect.signature(rotta.endpoint, eval_str=True).parameters
        campi: set[str] = set()
        for parametro in parametri.values():
            annotazione = parametro.annotation
            if isinstance(annotazione, type) and issubclass(annotazione, BaseModel):
                campi.update(annotazione.model_fields)
        rotte.append((rotta.path, set(parametri), campi))
    return rotte


def segmenti_di(esito: dict) -> list[dict]:
    return [segmento for documento in esito["documenti"] for segmento in documento["segmenti"]]


def evidenze_di(esito: dict) -> list[dict]:
    return [segmento for segmento in segmenti_di(esito) if segmento["tag"] is not None]


@senza_node
def test_l_analisi_evidenzia_il_testo_originale_distinguendo_le_categorie():
    """Criterio 1, verificato sulla pagina. Due cose insieme, perché separate
    si spuntano entrambe con la pagina rotta:

    - il testo che l'utente legge è quello originale, senza un carattere perso
      o duplicato nella giuntura fra i segmenti;
    - le occorrenze di categorie diverse portano classi diverse, cioè sono
      *distinguibili* e non solo evidenziate tutte allo stesso modo.

    Il testo atteso arriva dall'harness perché su questa superficie «originale»
    significa «tutto quello che il server ha servito, nell'ordine in cui l'ha
    servito»: che i segmenti del server ricompongano il documento vero è
    dimostrato altrove, da
    `test_i_segmenti_serviti_ricompongono_esattamente_il_testo_originale`.
    """
    esito = esito_della_ui("revisione-analisi")

    reso = "".join(segmento["testo"] for segmento in segmenti_di(esito))
    assert reso == esito["testo_atteso"], "la pagina non mostra il testo che ha ricevuto"
    evidenze = evidenze_di(esito)
    assert len(evidenze) == 2, "le due occorrenze riconosciute devono essere evidenziate"
    assert {e["categoria"] for e in evidenze} == {"PERSONA", "IMPORTO"}
    classi = {e["classe"] for e in evidenze}
    assert len(classi) == 2, f"le due categorie sono dipinte con la stessa classe: {classi}"
    assert all(e["elemento"] == "mark" for e in evidenze), (
        "l'evidenziazione deve essere marcata anche per chi non vede i colori"
    )
    assert all(e["mascherato"] == "1" for e in evidenze), "spec §2 decisione 4"


@senza_node
def test_ogni_classe_di_evidenziazione_ha_un_colore_suo_nel_foglio_di_stile():
    """La metà del criterio 1 che l'harness non può provare: che le classi
    diverse siano anche *visibilmente* diverse. L'harness vede i nomi delle
    classi e si ferma lì; questo test chiude l'anello sul CSS vero, e fallisce
    sia se una classe non ha alcuna regola — evidenziazione invisibile — sia se
    due categorie condividono lo stesso colore.

    Il confronto è sui valori **risolti**, non sui nomi delle variabili: due
    categorie che puntassero a token diversi con lo stesso valore sarebbero
    indistinguibili a schermo, e un confronto sui nomi non se ne accorgerebbe.

    Non prova che il browser dipinga: quello resta un controllo umano.
    """
    esito = esito_della_ui("revisione-analisi")
    css = (UI / "style.css").read_text(encoding="utf-8")

    classi = {
        classe
        for evidenza in evidenze_di(esito)
        for classe in evidenza["classe"].split()
        if classe.startswith("cat-")
    }
    assert len(classi) >= 2, f"attese almeno due classi di categoria, trovate {classi}"
    colori = {}
    for classe in classi:
        regola = re.search(rf"\.{re.escape(classe)}\b[^{{]*\{{([^}}]*)\}}", css)
        assert regola is not None, f"la classe {classe} non ha nessuna regola nel CSS"
        colore = re.search(r"background(?:-color)?:\s*([^;]+)", regola.group(1))
        assert colore is not None, f"la classe {classe} non dichiara alcun colore di fondo"
        colori[classe] = risolvi_token(colore.group(1).strip(), css)
    assert len(set(colori.values())) == len(colori), f"colori ripetuti: {colori}"


def test_ogni_categoria_del_dominio_ha_una_regola_nel_foglio_di_stile():
    """L'harness prova solo le categorie che lo scenario contiene. Una
    categoria del dominio senza regola resterebbe senza evidenziazione nella
    pagina vera — un dato personale riconosciuto e invisibile all'utente, che
    non saprebbe di doverlo rivedere.
    """
    css = (UI / "style.css").read_text(encoding="utf-8")

    mancanti = [c.value for c in Category if f".cat-{c.value}" not in css]

    assert mancanti == [], f"categorie senza colore di evidenziazione: {mancanti}"


@senza_node
def test_spegnere_la_categoria_dalla_pagina_spegne_le_sue_occorrenze_nella_pagina():
    """Criterio 2, metà UI. L'interruttore viene cercato **fra gli elementi che
    la pagina ha disegnato**: se non portasse il nome della categoria, o se la
    pagina non disegnasse affatto gli interruttori, l'harness non troverebbe il
    bersaglio e questo test fallirebbe prima di ogni asserzione.

    Poi verifica le due metà che possono rompersi separatamente: la richiesta
    che parte (nome della rotta e forma del corpo, che è la rottura da un solo
    token della #3) e il ridisegno che ne segue.
    """
    esito = esito_della_ui("revisione-categoria-spenta")

    inviati = [t for t in esito["tentativi"] if t["url"].endswith("/categoria")]
    assert len(inviati) == 1, f"richieste partite: {[t['url'] for t in esito['tentativi']]}"
    assert json.loads(inviati[0]["corpo"]) == {"categoria": "PERSONA", "attiva": False}
    persona = [e for e in evidenze_di(esito) if e["categoria"] == "PERSONA"]
    assert persona and all(e["mascherato"] == "0" for e in persona)
    assert all("spenta" in e["classe"].split() for e in persona)
    importo = [e for e in evidenze_di(esito) if e["categoria"] == "IMPORTO"]
    assert importo and all("spenta" not in e["classe"].split() for e in importo), (
        "spegnere una categoria non deve spegnere le altre"
    )
    assert {i["categoria"]: i["acceso"] for i in esito["interruttori"]} == {
        "PERSONA": False,
        "IMPORTO": True,
    }


@senza_node
def test_cliccare_una_singola_occorrenza_ne_chiede_lo_spegnimento():
    """Criterio 2, metà UI, sul singolo tag. Il bersaglio del click è
    l'elemento vero disegnato dalla pagina, trovato per il suo `data-tag`: un
    rendering che non lo portasse non sarebbe cliccabile per nessuno, e qui
    fallisce.

    `attivo: false` è dedotto dallo stato disegnato, non da un contatore nel
    JavaScript: cliccare su un'occorrenza accesa la spegne, e questo è il solo
    posto in cui quel verso si vede.
    """
    esito = esito_della_ui("revisione-tag-spento")

    inviati = [t for t in esito["tentativi"] if t["url"].endswith("/tag")]
    assert len(inviati) == 1, f"richieste partite: {[t['url'] for t in esito['tentativi']]}"
    corpo = json.loads(inviati[0]["corpo"])
    assert corpo["attivo"] is False
    assert corpo["tag"] == "[IMPORTO_1]", corpo["tag"]
    [importo] = [e for e in evidenze_di(esito) if e["categoria"] == "IMPORTO"]
    assert importo["mascherato"] == "0"
    [persona] = [e for e in evidenze_di(esito) if e["categoria"] == "PERSONA"]
    assert persona["mascherato"] == "1", "spegnere un'occorrenza non tocca le altre"


@senza_node
def test_il_corpo_dei_toggle_ha_i_nomi_che_le_rotte_aspettano():
    """La rottura da un solo token della #3, applicata a questa slice: un campo
    rinominato nel JavaScript farebbe rispondere 422 di validazione a ogni
    toggle, e la pagina direbbe soltanto «richiesta non valida».

    I nomi attesi sono chiesti ai modelli delle rotte, non riscritti a mano.
    """
    attesi = {
        rotta: campi for rotta, _, campi in campi_delle_rotte() if campi
    }

    for scenario, rotta in (
        ("revisione-categoria-spenta", "/api/fascicolo/categoria"),
        ("revisione-tag-spento", "/api/fascicolo/tag"),
    ):
        esito = esito_della_ui(scenario)
        [inviato] = [t for t in esito["tentativi"] if t["url"] == rotta]
        assert set(json.loads(inviato["corpo"])) == attesi[rotta], (
            f"{rotta}: lo script manda {sorted(json.loads(inviato['corpo']))}, "
            f"la rotta aspetta {sorted(attesi[rotta])}"
        )


@senza_node
def test_un_analisi_rifiutata_arriva_in_pagina_col_suo_messaggio():
    """Il rifiuto del fascicolo vuoto deve arrivare allo schermo. Senza,
    l'utente preme «Analizza», non succede niente visibile, e l'unica traccia
    resta in una console che non guarda: lo stesso silenzio che la #3 esisteva
    per impedire.
    """
    esito = esito_della_ui("revisione-analisi-rifiutata")

    assert "nessun documento da analizzare" in esito["stato"]
    assert "undefined" not in esito["stato"]


@senza_node
def test_la_pagina_dice_lo_stato_del_fascicolo():
    """Criterio 4, metà UI. Lo stato è verificato nel fascicolo da
    `test_dopo_l_analisi_lo_stato_e_pending_review`; qui si verifica l'altra
    metà, cioè che l'utente lo venga a sapere invece di doverlo dedurre dal
    fatto che la pagina è cambiata.
    """
    esito = esito_della_ui("revisione-analisi")

    assert "PENDING_REVIEW" in esito["stato"]
    assert "undefined" not in esito["stato"]


@senza_node
def test_gli_identificativi_cercati_dallo_script_esistono_nella_pagina():
    """Il secondo dei tre guasti della #3: un `getElementById` con un nome che
    la pagina non ha restituisce `null`, e la prima riga che ci scrive sopra fa
    morire tutto lo script — compreso il caricamento, che con la revisione non
    c'entra niente. Il test della #3 copriva gli id di allora; questo copre
    tutti quelli che lo script cerca oggi.
    """
    script = (UI / "app.js").read_text(encoding="utf-8")
    pagina = (UI / "index.html").read_text(encoding="utf-8")

    cercati = set(re.findall(r'getElementById\("([^"]+)"\)', script))

    assert len(cercati) > 4, "attesi anche gli elementi della revisione"
    mancanti = sorted(nome for nome in cercati if f'id="{nome}"' not in pagina)
    assert mancanti == [], f"lo script cerca elementi che la pagina non ha: {mancanti}"


@senza_node
def test_lo_script_della_ui_e_sintatticamente_valido():
    """Un errore di sintassi in `app.js` non fa fallire nulla nel resto della
    suite: la pagina viene servita, il browser scarta lo script e la UI è morta
    senza un solo test rosso. `node --check` non lo esegue, lo compila.
    """
    esito = subprocess.run(
        ["node", "--check", str(UI / "app.js")], capture_output=True, text=True
    )

    assert esito.returncode == 0, esito.stderr


def percorsi_di(valore, prefisso: str = "") -> set[str]:
    """I percorsi di chiave di una struttura JSON, con le liste appiattite.

    `{"a": [{"b": 1}]}` diventa `{".a[].b"}`: confronta la forma e non i
    valori, che fra il payload vero e quello dello scenario sono per forza
    diversi.
    """
    if isinstance(valore, dict):
        return {p for k, v in valore.items() for p in percorsi_di(v, f"{prefisso}.{k}")}
    if isinstance(valore, list):
        return {p for v in valore for p in percorsi_di(v, f"{prefisso}[]")} or {
            f"{prefisso}[]"
        }
    return {prefisso}


@senza_node
def test_il_payload_dello_scenario_ha_la_forma_di_quello_che_la_rotta_serve(
    client_con_rilevatore,
):
    """Il buco che resta aperto sotto tutti i test dell'harness: gli scenari
    sono scritti a mano, quindi possono descrivere un payload che il server non
    manda più. Da quel momento la UI verrebbe esercitata contro una forma
    immaginaria e resterebbe verde mentre la pagina vera muore su un campo
    assente — la stessa classe di difetto della #3, spostata dal codice ai
    dati di prova.

    Il confronto è sulla forma e non sui valori: un campo aggiunto o rinominato
    da una parte sola fa fallire qui, e il rimedio è aggiornare lo scenario.
    """
    client, finto = client_con_rilevatore(
        sempre=[Rilevazione(valore="Mario Rossi", categoria=Category.PERSONA)]
    )
    carica(client, "uno.txt", UNO)
    vero = client.post(ROTTA_ANALISI).json()

    # Lo scenario col fascicolo in chiaro, non l'altro: la rotta qui sopra
    # risponde su un fascicolo appena analizzato, che non maschera niente
    # (`33521f7`), e il confronto di forma vuole due payload dello stesso
    # stato. `revisione-analisi` descrive il default precedente e resta a
    # provare il disegno dello span mascherato.
    finto_payload = esito_della_ui("revisione-analisi-in-chiaro")["payload_servito"]

    assert percorsi_di(finto_payload) == percorsi_di(vero)


# --- Criterio 3: il testo non è modificabile in nessun punto -----------------


def test_la_pagina_non_offre_nessun_campo_in_cui_modificare_il_testo():
    """Criterio 3, e la decisione 2 della spec §2: il testo estratto è
    immutabile, l'utente agisce solo sui tag. Un campo modificabile
    permetterebbe di reintrodurre dati reali *dopo* il riconoscimento — cioè
    dati che nessun tag copre e che uscirebbero in chiaro dall'export — e di
    spostare i caratteri sotto le regioni già trovate.

    Verificato sul sorgente della pagina e non sull'harness: il DOM finto non
    ha attributi, quindi non può distinguere un contenitore modificabile da uno
    che non lo è. Questo è il controllo che quella lacuna lascia scoperto.
    """
    pagina = (UI / "index.html").read_text(encoding="utf-8").lower()

    assert "contenteditable" not in pagina
    assert "<textarea" not in pagina

    # Due sezioni della pagina hanno per forza dei campi da scrivere: la
    # configurazione (modello, prezzi, chiave, passphrase) e il vault (le due
    # password). Ammettere quei tipi **in blocco** svuoterebbe la guardia:
    # passerebbe anche un campo di testo aggiunto un domani accanto al
    # documento, che è esattamente la cosa che qui si vuole rendere
    # impossibile.
    #
    # Quindi non si allarga l'elenco dei tipi, si guarda **dove** stanno. Ogni
    # zona che può scrivere va dichiarata qui per id, una riga per zona: fuori
    # da quelle, gli unici campi ammessi restano quelli di prima. Il criterio
    # regge quando le zone crescono, e continua a far rosso se un campo
    # scrivibile compare dove si legge il testo.
    ZONE_CHE_SCRIVONO = {
        'id="pannello-config"': {"text", "number", "password", "checkbox"},
        'id="card-vault"': {"file", "password"},
    }

    fuori = pagina
    for marcatore, ammessi in ZONE_CHE_SCRIVONO.items():
        inizio = fuori.index(marcatore)
        fine = fuori.index("</section>", inizio)
        dentro = fuori[inizio:fine]
        fuori = fuori[:inizio] + fuori[fine:]

        # Dentro la zona: nessun campo che possa contenere il testo di un
        # documento. `textarea` è già escluso sopra per tutta la pagina.
        tipi_zona = set(re.findall(r'<input\b[^>]*?\btype="([^"]+)"', dentro, flags=re.S))
        assert tipi_zona <= ammessi, (
            f"la zona {marcatore} ha campi inattesi: {sorted(tipi_zona)}"
        )

    tipi = set(re.findall(r'<input\b[^>]*?\btype="([^"]+)"', fuori, flags=re.S))
    assert tipi <= {"file"}, (
        "fuori dalle zone che scrivono la pagina ha campi di immissione "
        f"inattesi: {sorted(tipi)}"
    )


def test_lo_script_non_costruisce_nessun_elemento_modificabile():
    """L'altra metà del criterio 3: la pagina statica può essere pulita e lo
    script crearsi un campo per conto suo, visto che tutta la revisione è
    disegnata da `app.js`. Gli unici `input` che lo script costruisce sono le
    caselle di spunta degli interruttori.
    """
    # Tutti gli script della pagina, non più il solo `app.js`: dalla issue #51
    # ce n'è più di uno, e un file nuovo che nessuno controlla è esattamente il
    # modo in cui questo criterio smetterebbe di valere senza che si veda.
    nomi = sorted(percorso.name for percorso in UI.glob("*.js"))
    assert nomi, "attesi degli script nella cartella della UI"

    for nome in nomi:
        script = (UI / nome).read_text(encoding="utf-8")

        assert "contentEditable" not in script, nome
        assert "designMode" not in script, nome
        creati = set(re.findall(r'createElement\(\s*"([a-zA-Z]+)"', script))
        assert creati, f"atteso che {nome} costruisca qualche elemento"
        assert "textarea" not in creati, nome
        # `button` sta accanto a `checkbox` e non allarga la guardia: un
        # `<button type="button">` non riceve testo, e il criterio è sempre
        # quello — nessun elemento costruito dallo script deve poter accettare
        # caratteri dall'utente. Un `text`, un `search` o un `email` qui sono
        # rossi, ed è l'unica cosa che questa riga deve saper distinguere.
        tipi = set(re.findall(r'\.type\s*=\s*"([^"]+)"', script))
        assert tipi <= {"checkbox", "button"}, (
            f"{nome} crea campi di immissione: {sorted(tipi)}"
        )


def test_nessuna_rotta_del_fascicolo_accetta_un_testo_da_sostituire():
    """La terza metà del criterio 3, che è quella che conta davvero: una UI non
    modificabile è una promessa che il server deve poter mantenere anche contro
    una richiesta costruita a mano. Finché nessuna rotta accetta del testo, il
    testo del fascicolo può cambiare solo caricando un documento.

    I campi sono chiesti alle firme e ai modelli delle rotte, non elencati a
    mano: una rotta nuova con un campo `testo` fa fallire qui.
    """
    vietati = {"testo", "text", "contenuto", "documento_testo"}

    campi = set()
    for _, parametri, campi_del_corpo in campi_delle_rotte():
        campi |= parametri | campi_del_corpo

    assert campi, "attese rotte con parametri: la riflessione non ha trovato niente"
    assert "attiva" in campi, (
        "i campi del corpo non sono stati letti: senza di quelli il test "
        "passerebbe su un insieme vuoto"
    )
    assert campi & vietati == set(), f"una rotta accetta del testo: {sorted(campi & vietati)}"
