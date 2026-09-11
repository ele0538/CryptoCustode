"""Revisione: testo evidenziato e toggle per categoria (issue #4).

Questi test difendono due cose che si verificano su **superfici diverse**, e
tenerle distinte è il punto della slice:

1. quello che il fascicolo diventa — stato `PENDING_REVIEW`, code delle
   ambiguità popolate, interruttori che cambiano davvero cosa verrà mascherato
   — si verifica **guardando il fascicolo nello store**, non credendo alla
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
"""

import inspect
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from cryptocustode.api.app import UI, crea_app
from cryptocustode.api.routes_fascicolo import ID_FASCICOLO_ATTIVO, crea_router
from cryptocustode.core.models import AmbiguityKind, Category, Source, Span, State
from cryptocustode.state.session import SessionStore

INDIRIZZO_DI_PROVA = "http://127.0.0.1:8765"
"""L'app accetta solo il loopback nell'intestazione `Host` (`HOST_CONSENTITI`),
quindi il `base_url` di default del TestClient prenderebbe un 400 su ogni
richiesta. Il valore di prova sta qui e non fra gli host di produzione."""

ROTTA_DOCUMENTI = "/api/fascicolo/documenti"
ROTTA_ANALISI = "/api/fascicolo/analisi"
ROTTA_CATEGORIA = "/api/fascicolo/categoria"
ROTTA_SPAN = "/api/fascicolo/span"

HARNESS = Path(__file__).parent / "ui_harness.mjs"

UNO = "Il sig. Mario Rossi paga 1.200,00 euro."
DUE = "Anche Mario Rossi firma, IBAN IT60X0542811101000000123456."


@pytest.fixture
def ner_finto(monkeypatch):
    """Sostituisce il NER con una ricerca letterale dei nomi che gli si danno.

    Il modello vero pesa 550 MB e caricarlo qui renderebbe questi test lenti e
    dipendenti da un download; ma senza NER non esiste nessuna categoria con
    varianti, e l'omonimia della spec §7 — l'unica ambiguità che popola la coda
    bloccante — non potrebbe nascere. Il doppio produce span `PERSONA` veri, che
    attraversano poi la pipeline vera: `risolvi`, l'assegnazione delle entità,
    i segnaposto.
    """
    nomi: list[str] = []

    def trova_per_ner(testo: str, doc_id: str) -> list[Span]:
        trovati = []
        for nome in nomi:
            for trovato in re.finditer(re.escape(nome), testo):
                inizio, fine = trovato.start(), trovato.end()
                trovati.append(
                    Span(
                        span_id=f"{doc_id}:{inizio}-{fine}:{Category.PERSONA.value}",
                        doc_id=doc_id, start=inizio, end=fine,
                        category=Category.PERSONA, source=Source.NER, entity_id="",
                    )
                )
        return trovati

    monkeypatch.setattr("cryptocustode.core.entities.trova_per_ner", trova_per_ner)
    return nomi


@pytest.fixture
def store() -> SessionStore:
    """Lo store passato come seme all'app, per guardarci dentro dopo."""
    return SessionStore()


@pytest.fixture
def client(store):
    with TestClient(crea_app(store=store), base_url=INDIRIZZO_DI_PROVA) as client:
        yield client


def carica(client: TestClient, nome: str, testo: str):
    return client.post(
        ROTTA_DOCUMENTI, files={"file": (nome, testo.encode("utf-8"), "text/plain")}
    )


def fascicolo_di(store: SessionStore):
    return store.prendi(ID_FASCICOLO_ATTIVO)


# --- Criterio 4: dopo l'analisi lo stato e la coda ---------------------------


def test_dopo_l_analisi_lo_stato_e_pending_review_e_la_coda_e_popolata(
    client, store, ner_finto
):
    """Criterio 4, verificato **nel fascicolo** e non nella risposta HTTP: un
    payload che dicesse `"stato": "PENDING_REVIEW"` senza che nessuno abbia
    chiamato `analisi_completata` lascerebbe le code vuote, e l'approvazione
    non troverebbe mai niente da bloccare (spec §7, TC-03).

    Due documenti con lo stesso nome e nessun CF sono il caso che apre
    l'omonimia: con un documento solo la coda resterebbe legittimamente vuota,
    e il test non distinguerebbe l'analisi fatta da quella saltata.
    """
    ner_finto.append("Mario Rossi")
    carica(client, "uno.txt", UNO)
    carica(client, "due.txt", DUE)

    risposta = client.post(ROTTA_ANALISI)

    assert risposta.status_code == 200, risposta.text
    fascicolo = fascicolo_di(store)
    assert fascicolo.state is State.PENDING_REVIEW
    omonimie = [
        a for a in fascicolo.ambiguities if a.kind is AmbiguityKind.SAME_NAME_NO_CF
    ]
    assert omonimie, "la coda delle ambiguità è vuota: `analisi_completata` non è passata"
    assert any(a.blocca_approvazione for a in fascicolo.ambiguities)


def test_l_analisi_di_un_fascicolo_vuoto_e_rifiutata_invece_di_promuoverlo(client, store):
    """Senza documenti non c'è niente da analizzare, e promuovere comunque il
    fascicolo a `PENDING_REVIEW` lo renderebbe approvabile: un fascicolo vuoto
    approvato esporta zero documenti senza che nulla lo segnali.
    """
    risposta = client.post(ROTTA_ANALISI)

    assert risposta.status_code == 422
    assert "documento" in risposta.json()["errore"]
    assert fascicolo_di(store).state is State.DRAFT


# --- Criterio 5: un documento in più fa rieseguire l'analisi -----------------


def test_un_documento_aggiunto_dopo_l_analisi_ne_fa_rieseguire_una(client, store, ner_finto):
    """Criterio 5. `analisi_completata` è l'unico punto che popola le code:
    saltarla dopo il secondo caricamento lascerebbe la coda com'era, cioè
    senza l'omonimia che il secondo documento ha appena creato — stantia, e
    silenziosamente.

    Il secondo passaggio non deve nemmeno rianalizzare il primo documento:
    `analizza_documento` lo rifiuta di proposito, perché una seconda copia di
    ogni span farebbe applicare a `maschera` due sostituzioni sovrapposte allo
    stesso intervallo, troncando il testo dal primo segnaposto in poi.
    """
    ner_finto.append("Mario Rossi")
    carica(client, "uno.txt", UNO)
    assert client.post(ROTTA_ANALISI).status_code == 200
    fascicolo = fascicolo_di(store)
    assert not [a for a in fascicolo.ambiguities if a.kind is AmbiguityKind.SAME_NAME_NO_CF]
    span_del_primo = [s.span_id for s in fascicolo.spans]

    carica(client, "due.txt", DUE)
    seconda = client.post(ROTTA_ANALISI)

    assert seconda.status_code == 200, seconda.text
    fascicolo = fascicolo_di(store)
    assert [
        a for a in fascicolo.ambiguities if a.kind is AmbiguityKind.SAME_NAME_NO_CF
    ], "la coda è rimasta com'era: la seconda analisi non ha ripopolato niente"
    rimasti = [s.span_id for s in fascicolo.spans if s.span_id in span_del_primo]
    assert sorted(rimasti) == sorted(span_del_primo)
    assert len(rimasti) == len(set(rimasti)), "gli span del primo documento sono duplicati"


# --- Criterio 1, metà server: i segmenti coprono il testo originale ----------


def test_i_segmenti_serviti_ricompongono_esattamente_il_testo_originale(
    client, store, ner_finto
):
    """Criterio 1, metà server. Il testo evidenziato si costruisce spezzando il
    testo **originale** sugli offset degli span: se la giunzione perdesse o
    duplicasse un carattere, l'utente reviserebbe un testo che non è quello che
    verrà mascherato, e gli offset su cui clicca non sarebbero più gli stessi.

    La decisione 2 della spec §2 dice che il testo estratto è immutabile:
    questo test è ciò che la rende osservabile.
    """
    ner_finto.append("Mario Rossi")
    carica(client, "uno.txt", UNO)

    esito = client.post(ROTTA_ANALISI).json()

    [documento] = esito["documenti"]
    assert "".join(s["testo"] for s in documento["segmenti"]) == UNO
    evidenziati = [s for s in documento["segmenti"] if s["categoria"] is not None]
    categorie = {s["categoria"] for s in evidenziati}
    assert categorie == {"PERSONA", "IMPORTO"}, categorie
    assert all(s["span_id"] for s in evidenziati)
    assert all(s["mascherato"] for s in evidenziati), "spec §2 decisione 4: tutto acceso"


# --- Criterio 2, metà server: gli interruttori cambiano il fascicolo ---------


def test_il_toggle_di_categoria_spegne_il_mascheramento_di_quella_categoria(
    client, store, ner_finto
):
    """Criterio 2, metà server, verificato sul fascicolo: `category_enabled` è
    metà della condizione che `mask.span_attivo` legge, quindi è lì che si vede
    se il toggle cambia davvero cosa verrà mascherato. Una risposta HTTP che
    dicesse «spento» senza mutare il fascicolo esporterebbe comunque il dato.
    """
    ner_finto.append("Mario Rossi")
    carica(client, "uno.txt", UNO)
    client.post(ROTTA_ANALISI)

    risposta = client.post(ROTTA_CATEGORIA, json={"categoria": "PERSONA", "attiva": False})

    assert risposta.status_code == 200, risposta.text
    fascicolo = fascicolo_di(store)
    assert fascicolo.category_enabled[Category.PERSONA] is False
    assert fascicolo.category_enabled[Category.IMPORTO] is True, "spento solo il richiesto"
    [documento] = risposta.json()["documenti"]
    persona = [s for s in documento["segmenti"] if s["categoria"] == "PERSONA"]
    assert persona and not any(s["mascherato"] for s in persona)


def test_il_toggle_di_un_singolo_span_non_tocca_gli_altri_della_categoria(
    client, store, ner_finto
):
    """Criterio 2, metà server. Il controllo sul singolo span è l'altra metà
    della decisione 4 della spec §2: spegnere un'occorrenza non deve spegnere
    le altre della stessa categoria, altrimenti sarebbe il toggle di categoria
    con un altro nome.
    """
    ner_finto.append("Mario Rossi")
    carica(client, "uno.txt", UNO)
    esito = client.post(ROTTA_ANALISI).json()
    [documento] = esito["documenti"]
    [persona] = [s for s in documento["segmenti"] if s["categoria"] == "PERSONA"]

    risposta = client.post(ROTTA_SPAN, json={"span_id": persona["span_id"], "attivo": False})

    assert risposta.status_code == 200, risposta.text
    fascicolo = fascicolo_di(store)
    spento = [s for s in fascicolo.spans if s.span_id == persona["span_id"]]
    assert spento and spento[0].enabled is False
    altri = [s for s in fascicolo.spans if s.span_id != persona["span_id"]]
    assert altri and all(s.enabled for s in altri)
    assert fascicolo.category_enabled[Category.PERSONA] is True, "la categoria resta accesa"


def test_uno_span_che_non_esiste_e_un_404_con_una_spiegazione(client, store, ner_finto):
    """Un id inventato non deve passare in silenzio: senza il controllo la
    route non muterebbe niente e risponderebbe 200, e la pagina mostrerebbe
    acceso uno span che l'utente crede di aver spento."""
    ner_finto.append("Mario Rossi")
    carica(client, "uno.txt", UNO)
    client.post(ROTTA_ANALISI)

    risposta = client.post(ROTTA_SPAN, json={"span_id": "inventato", "attivo": False})

    assert risposta.status_code == 404
    assert "inventato" in risposta.json()["errore"]


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

    `eval_str=True` non è un dettaglio: `routes_fascicolo.py` ha
    `from __future__ import annotations`, quindi senza di quello le annotazioni
    restano stringhe, nessun `issubclass` scatta, e ogni test che cerca i campi
    del corpo passerebbe su un insieme vuoto — verde senza aver guardato
    niente. È il difetto che questo stesso test ha intercettato su di sé.
    """
    router = crea_router(SessionStore())
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
    return [segmento for segmento in segmenti_di(esito) if segmento["span_id"] is not None]


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
    assert all(e["tag"] == "mark" for e in evidenze), (
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
    """Criterio 2, metà UI, sul singolo span. Il bersaglio del click è
    l'elemento vero disegnato dalla pagina, trovato per il suo `data-span-id`:
    un rendering che non lo portasse non sarebbe cliccabile per nessuno, e qui
    fallisce.

    `attivo: false` è dedotto dallo stato disegnato, non da un contatore nel
    JavaScript: cliccare su un'occorrenza accesa la spegne, e questo è il solo
    posto in cui quel verso si vede.
    """
    esito = esito_della_ui("revisione-span-spento")

    inviati = [t for t in esito["tentativi"] if t["url"].endswith("/span")]
    assert len(inviati) == 1, f"richieste partite: {[t['url'] for t in esito['tentativi']]}"
    corpo = json.loads(inviati[0]["corpo"])
    assert corpo["attivo"] is False
    assert corpo["span_id"].endswith(":IMPORTO"), corpo["span_id"]
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
        ("revisione-span-spento", "/api/fascicolo/span"),
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
def test_la_pagina_dice_lo_stato_e_quante_ambiguita_sono_in_coda():
    """Criterio 4, metà UI. Lo stato e la coda sono verificati nel fascicolo da
    `test_dopo_l_analisi_lo_stato_e_pending_review_e_la_coda_e_popolata`; qui
    si verifica l'altra metà, cioè che l'utente lo venga a sapere invece di
    doverlo dedurre dal fatto che la pagina è cambiata.
    """
    esito = esito_della_ui("revisione-analisi")

    assert "PENDING_REVIEW" in esito["stato"]
    assert "1" in esito["stato"], "il numero di ambiguità in coda deve comparire"
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
    client, store, ner_finto
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
    ner_finto.append("Mario Rossi")
    carica(client, "uno.txt", UNO)
    vero = client.post(ROTTA_ANALISI).json()

    finto = esito_della_ui("revisione-analisi")["payload_servito"]

    assert percorsi_di(finto) == percorsi_di(vero)


# --- Criterio 3: il testo non è modificabile in nessun punto -----------------


def test_la_pagina_non_offre_nessun_campo_in_cui_modificare_il_testo():
    """Criterio 3, e la decisione 2 della spec §2: il testo estratto è
    immutabile, l'utente agisce solo sugli span. Un campo modificabile
    permetterebbe di reintrodurre dati reali *dopo* il riconoscimento — cioè
    dati che nessuno span copre e che uscirebbero in chiaro dall'export — e di
    spostare i caratteri sotto gli offset degli span già trovati.

    Verificato sul sorgente della pagina e non sull'harness: il DOM finto non
    ha attributi, quindi non può distinguere un contenitore modificabile da uno
    che non lo è. Questo è il controllo che quella lacuna lascia scoperto.
    """
    pagina = (UI / "index.html").read_text(encoding="utf-8").lower()

    assert "contenteditable" not in pagina
    assert "<textarea" not in pagina
    tipi = set(re.findall(r'<input\b[^>]*?\btype="([^"]+)"', pagina, flags=re.S))
    assert tipi <= {"file"}, f"la pagina ha campi di immissione inattesi: {sorted(tipi)}"


def test_lo_script_non_costruisce_nessun_elemento_modificabile():
    """L'altra metà del criterio 3: la pagina statica può essere pulita e lo
    script crearsi un campo per conto suo, visto che tutta la revisione è
    disegnata da `app.js`. Gli unici `input` che lo script costruisce sono le
    caselle di spunta degli interruttori.
    """
    script = (UI / "app.js").read_text(encoding="utf-8")

    assert "contentEditable" not in script
    assert "designMode" not in script
    creati = set(re.findall(r'createElement\(\s*"([a-zA-Z]+)"', script))
    assert creati, "atteso che lo script costruisca gli elementi della revisione"
    assert "textarea" not in creati
    tipi = set(re.findall(r'\.type\s*=\s*"([^"]+)"', script))
    assert tipi <= {"checkbox"}, f"lo script crea campi di immissione: {sorted(tipi)}"


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
