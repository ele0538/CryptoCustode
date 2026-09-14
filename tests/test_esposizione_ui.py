"""La pagina dice, prima del clic, quanto uscira' in chiaro (issue #53).

Due difetti distinti, e conviene tenerli separati perche' solo il secondo si
vedeva a occhio:

1. **il colore di categoria non si applicava mai** agli span della revisione.
   `mark.evidenza { background: transparent }` vale (0,1,1) e batteva
   `.cat-PERSONA`, che vale (0,1,0), qualunque fosse l'ordine nel foglio. Le
   pastiglie della legenda si coloravano — li' non c'era regola concorrente —
   il testo no. Quindi «verra' mascherato» si vedeva come testo normale, e chi
   guardava non aveva modo di distinguerlo da «resta in chiaro»;
2. **il barrato diceva il contrario di quel che succede.** Una parola barrata
   si legge «tolta», ed era il segno del dato che *resta*.

Il primo si verifica sul foglio di stile, perche' e' un fatto di cascata e non
di disegno; il secondo e il riquadro dell'esposizione si verificano eseguendo
il vero `app.js` con l'harness.

Quello che qui **non** si prova, e non va spacciato per coperto: che il browser
dipinga davvero. Resta un controllo umano.
"""

import re

from cryptocustode.api.app import UI
from tests.test_revisione import esito_della_ui, senza_node

CSS = (UI / "style.css").read_text(encoding="utf-8")

SENZA_COMMENTI = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
"""Il foglio senza commenti.

Serve al calcolo della specificita': i commenti di questo progetto sono lunghi e
stanno subito sopra la regola che spiegano, quindi finirebbero dentro il
selettore e ne falserebbero il conteggio — un `.cat-` citato in un commento
verrebbe contato come una classe del selettore sotto."""


def specificita(selettore: str) -> tuple[int, int, int]:
    """(id, classi, elementi) del selettore, che e' quanto basta qui.

    Niente pseudo-classi ne' combinatori: i selettori di questo foglio sono
    semplici, e un calcolatore completo sarebbe piu' codice da sbagliare che
    regole da controllare.
    """
    identificativi = len(re.findall(r"#[\w-]+", selettore))
    classi = len(re.findall(r"\.[\w-]+", selettore))
    elementi = len(re.findall(r"(?:^|[\s>+~])([a-z]+)", selettore))
    return (identificativi, classi, elementi)


def regole_che_danno_il_fondo() -> dict[str, str]:
    """I selettori che dichiarano un `background` nel foglio, col loro valore."""
    trovate = {}
    for selettore, corpo in re.findall(r"([^{}]+)\{([^}]*)\}", SENZA_COMMENTI):
        fondo = re.search(r"(?:^|;)\s*background\s*:\s*([^;]+)", corpo)
        if fondo is not None:
            trovate[selettore.strip()] = fondo.group(1).strip()
    return trovate


class TestIlColoreDiCategoriaVince:
    def test_la_neutralizzazione_del_mark_non_batte_le_categorie(self):
        """Il difetto 1, preso dove viveva: nella cascata.

        Se qualcuno rimettesse la neutralizzazione su `mark.evidenza`, il fondo
        di categoria tornerebbe a non applicarsi mai e nessun test del disegno
        se ne accorgerebbe — l'harness non ha un motore CSS.
        """
        regole = regole_che_danno_il_fondo()
        neutralizzanti = {
            selettore: valore
            for selettore, valore in regole.items()
            if "mark" in selettore
            and "spenta" not in selettore
            and valore in {"transparent", "none"}
        }
        assert neutralizzanti, "nessuna regola neutralizza il giallo di `mark`"

        categoria = next(s for s in regole if s.strip().startswith(".cat-"))
        for selettore in neutralizzanti:
            assert specificita(selettore) < specificita(categoria), (
                f"{selettore!r} batte {categoria!r}: il fondo di categoria non "
                "si applichera' mai agli span della revisione"
            )

    def test_ogni_categoria_ha_il_suo_fondo(self):
        """Una categoria senza regola verrebbe disegnata senza evidenziazione:
        un dato personale invisibile a chi deve rivederlo."""
        from cryptocustode.core.models import Category

        regole = regole_che_danno_il_fondo()
        for categoria in Category:
            assert f".cat-{categoria.value}" in regole, (
                f"la categoria {categoria.value} non ha un colore"
            )


class TestInChiaroNonSiLeggeComeRimosso:
    def test_lo_span_in_chiaro_non_e_barrato(self):
        """Il difetto 2. Il barrato e' il segno di cio' che viene tolto, ed e'
        esattamente l'opposto di quello che succede a un dato lasciato in
        chiaro."""
        spenta = re.search(r"mark\.evidenza\.spenta\s*\{([^}]*)\}", SENZA_COMMENTI)
        assert spenta is not None, "la regola dello span in chiaro non c'e' piu'"

        assert "line-through" not in spenta.group(1), (
            "lo span che resta in chiaro e' barrato: si legge «rimosso», che e' "
            "il contrario di quello che fa"
        )

    def test_lo_span_in_chiaro_ha_un_segno_che_non_e_solo_colore(self):
        """Chi non distingue i colori, o stampa in bianco e nero, deve vedere
        comunque che quello span e' diverso."""
        spenta = re.search(r"mark\.evidenza\.spenta\s*\{([^}]*)\}", SENZA_COMMENTI)
        corpo = spenta.group(1)

        assert "dashed" in corpo or "wavy" in corpo, (
            "lo stato «in chiaro» e' affidato al solo colore"
        )


@senza_node
class TestIlRiquadroDellEsposizione:
    def test_con_tutto_in_chiaro_il_riquadro_allarma_e_conta(self):
        esito = esito_della_ui("revisione-analisi-in-chiaro")

        assert "espone" in esito["esposizione"]["classe"]
        testo = esito["esposizione"]["testo"]
        assert "2 dati" in testo, testo
        assert "in chiaro" in testo, testo

    def test_il_riquadro_nomina_le_categorie_esposte(self):
        """«2 dati usciranno in chiaro» non dice quali interruttori accendere."""
        testo = esito_della_ui("revisione-analisi-in-chiaro")["esposizione"]["testo"]

        assert "PERSONA" in testo, testo
        assert "IMPORTO" in testo, testo

    def test_con_tutto_mascherato_il_riquadro_non_allarma(self):
        """Un riquadro che grida sempre si smette di leggerlo, e il giorno che
        grida per davvero non lo guarda piu' nessuno."""
        esito = esito_della_ui("revisione-analisi")

        assert "espone" not in esito["esposizione"]["classe"]
        assert "in chiaro" not in esito["esposizione"]["testo"]


def test_la_legenda_usa_le_classi_vere_degli_span():
    """La legenda dei due stati non deve essere una copia dello stile: se un
    domani cambia il modo di disegnare «in chiaro», deve cambiare con lui invece
    di restare a descrivere un aspetto che la pagina non ha piu'."""
    # La legenda vive dove vive il testo evidenziato: dal 2026-09-14 è la
    # pagina «Nascondi», dentro il dettaglio che si apre con «Mostrami dove».
    pagina = (UI / "nascondi.html").read_text(encoding="utf-8")
    legenda = re.search(r'<p class="legenda-stati">(.*?)</p>', pagina, flags=re.S)
    assert legenda is not None, "la legenda dei due stati non c'e'"

    corpo = legenda.group(1)
    assert 'class="evidenza cat-' in corpo, "la legenda non usa le classi vere"
    assert "spenta" in corpo, "la legenda non mostra lo stato «in chiaro»"
    assert "in chiaro" in corpo.lower(), "la legenda non nomina lo stato in parole"


def test_i_file_serviti_alla_pagina_sono_testo_pulito():
    """Nessun carattere di controllo nei file che il browser riceve.

    Non e' teoria: scrivendo il glifo dello span in chiaro come sequenza di
    escape CSS da uno script, in `style.css` e' finito un **byte NUL**. Il file
    restava servibile, il browser lo digeriva, e git lo classificava come
    binario — cioe' da quel momento nessun diff sarebbe stato leggibile. I test
    di allora guardavano la presenza di «dashed» e «wavy» e non si sono accorti
    di niente.

    Tab e a capo sono legittimi; tutto il resto sotto lo spazio non lo e'.
    """
    for percorso in sorted(UI.iterdir()):
        if percorso.suffix not in {".css", ".js", ".html"}:
            continue
        grezzo = percorso.read_bytes()

        assert b"\x00" not in grezzo, f"{percorso.name} contiene un byte NUL"
        testo = grezzo.decode("utf-8")  # un errore qui e' gia' il fallimento
        sospetti = {
            carattere
            for carattere in testo
            if carattere < " " and carattere not in "\t\n\r"
        }
        assert not sospetti, (
            f"{percorso.name} contiene caratteri di controllo: "
            f"{sorted(hex(ord(c)) for c in sospetti)}"
        )
