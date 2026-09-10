"""Documento di verifica, distinto da quelli di sviluppo (spec §14).

La spec programma questo test proprio adesso: «documenti di verifica distinti
da quelli di sviluppo, come chiede la consegna: due set separati, il secondo
scritto dopo il completamento del motore».

Perché serve, e perché non basta il test anti-fuga generico che sta in
`test_mask.py`: quello mascherà gli span che gli vengono *dati*, su uno
scenario costruito a mano, quindi per costruzione non può accorgersi di un
valore che il motore non ha riconosciuto. Un documento realistico letto da
capo a fondo dalla catena vera — `trova_per_regole` + `trova_per_ner` →
`risolvi` → `analizza_documento` → `maschera_documento` — misura invece le due
cose che contano insieme:

- **anti-fuga**: nessuno dei valori attesi sopravvive nel testo mascherato;
- **richiamo**: ognuno di quei valori ha davvero prodotto uno span.

La seconda direzione è quella che mancava. Senza di essa un motore che non
riconosce niente supererebbe il test anti-fuga a pieni voti.

Tutti i dati del documento sono inventati: nomi, codici fiscali, IBAN, partita
IVA, recapiti, indirizzi e ragione sociale non appartengono a nessuno. I
checksum (CIN del codice fiscale, cifra di controllo della P.IVA, MOD-97
dell'IBAN) sono però corretti, altrimenti le regole di priorità P1 li
scarterebbero e il documento non eserciterebbe le categorie che deve.
"""
import re

import pytest

from cryptocustode.core.entities import analizza_documento
from cryptocustode.core.mask import maschera_documento
from cryptocustode.core.models import Category, Document, fascicolo_vuoto

pytestmark = pytest.mark.lento

CONTRATTO = """SCRITTURA PRIVATA DI LOCAZIONE

Con la presente scrittura privata, redatta in data 14/03/2024 in Orbassano,

il locatore Alberto Ferrante, nato il 12/05/1974, codice fiscale
FRRLBR74E12C627I, residente in Via delle Betulle 12/A, 10043 Orbassano,
tel. 011 123 45 67, indirizzo di posta elettronica alberto.ferrante@posta-esempio.it,

e la conduttrice Marta Lorusso, codice fiscale LRSMRT86P55L219A,
domiciliata in Via all'Aeroporto 3, 10121 Torino, cell. 340 1234 567,
posta elettronica marta.lorusso@posta-esempio.it,

con l'intermediazione di Cooperativa alle Ginestre S.r.l., partita IVA
03456789019, con sede in Corso della Repubblica 118, 10098 Rivoli,

convengono quanto segue.

Articolo 1. Oggetto. Il locatore concede in locazione l'unità immobiliare
sita in Via sul Mare 8, 17021 Alassio, censita al foglio 24 particella 318
sub 7.

Articolo 2. Canone. Il canone mensile è pari a 800,00 € da versare entro il
quinto giorno di ogni mese sul conto IT95X0300203280000400123456 intestato
al locatore. Il deposito cauzionale ammonta a 1.600,00 EUR.

Articolo 3. Riferimenti. La pratica 2024/LOC-318 è depositata presso lo
sportello competente in data 20 marzo 2024.
"""

# I valori che *devono* essere mascherati, elencati a mano e non ricavati dal
# motore: se li ricavassimo dagli span il test non potrebbe accorgersi di una
# mancanza. Coprono tutte e dodici le categorie della spec §5.
VALORI_ATTESI = (
    # PERSONA
    "Alberto Ferrante",
    "Marta Lorusso",
    # AZIENDA
    "Cooperativa alle Ginestre S.r.l",
    # INDIRIZZO
    "Via delle Betulle 12/A",
    "Via all'Aeroporto 3",
    "Corso della Repubblica 118",
    "Via sul Mare 8",
    # EMAIL
    "alberto.ferrante@posta-esempio.it",
    "marta.lorusso@posta-esempio.it",
    # TELEFONO
    "011 123 45 67",
    "340 1234 567",
    # CF
    "FRRLBR74E12C627I",
    "LRSMRT86P55L219A",
    # PIVA
    "03456789019",
    # IBAN
    "IT95X0300203280000400123456",
    # DATA
    "14/03/2024",
    "12/05/1974",
    "20 marzo 2024",
    # IMPORTO, nelle due forme: simbolo dopo le cifre (la più comune in un
    # contratto italiano) e sigla alfabetica
    "800,00 €",
    "1.600,00 EUR",
    # PRATICA
    "2024/LOC-318",
    # CATASTO
    "foglio 24 particella 318",
)

# Spec §11, passo 3: la regex permissiva che intercetta i quasi-segnaposto.
# Applicata al *nostro* output, dice se la mascheratura ha prodotto qualcosa
# che il ripristino rifiuterebbe.
QUASI_SEGNAPOSTO = re.compile(r"\[[A-Za-z]+[_\-\s]?\d*\]?")
SEGNAPOSTO = re.compile(r"\[[A-Z]+_\d+\]")


@pytest.fixture(scope="module")
def analisi():
    """Il giro completo sul documento di verifica, una volta per modulo."""
    documento = Document(
        doc_id="v1", filename="contratto-di-verifica.txt", text=CONTRATTO,
        page_offsets=[0], sha256="verifica",
    )
    fascicolo = fascicolo_vuoto("fascicolo-di-verifica")
    fascicolo.documents.append(documento)
    analizza_documento(fascicolo, documento)
    return fascicolo, documento, maschera_documento(fascicolo, documento)


@pytest.mark.parametrize("valore", VALORI_ATTESI)
def test_nessun_valore_atteso_sopravvive_nel_testo_mascherato(analisi, valore):
    """Anti-fuga: se un solo valore arriva in chiaro all'IA esterna, lo
    strumento ha mancato il suo unico compito."""
    _, _, mascherato = analisi
    assert valore not in mascherato


@pytest.mark.parametrize("valore", VALORI_ATTESI)
def test_ogni_valore_atteso_ha_prodotto_uno_span(analisi, valore):
    """Richiamo: la direzione che il test anti-fuga da solo non può misurare.
    Uno span deve coprire il valore — può essere più largo (il CAP e il comune
    dentro l'indirizzo, la parola chiave dentro CATASTO e PRATICA), non più
    corto."""
    fascicolo, documento, _ = analisi
    coperto = [
        s for s in fascicolo.spans if valore in documento.text[s.start:s.end]
    ]
    assert coperto, f"nessuno span copre {valore!r}"


def test_tutte_le_dodici_categorie_producono_almeno_uno_span(analisi):
    fascicolo, _, _ = analisi
    trovate = {s.category for s in fascicolo.spans}
    mancanti = sorted(c.value for c in Category if c not in trovate)
    assert mancanti == [], f"categorie senza alcuno span: {mancanti}"


def test_nessun_valore_del_dizionario_sopravvive(analisi):
    """Anti-fuga sul dizionario, versione *catena di mascheratura*.

    La spec §14 chiede questa asserzione generica sul testo **esportato**, e
    quella la porta `test_matrice_consegna.py`. Questa qui è la sua gemella
    sull'altro percorso: non è un duplicato, e togliere una delle due
    lascerebbe scoperto un percorso intero.

    - Qui: `analizza_documento` -> `maschera_documento`, chiamate a mano sul
      documento di verifica realistico, senza gate in mezzo. Questo modulo,
      tramite `VALORI_ATTESI`, misura in più il *richiamo* su tutte e dodici
      le categorie in prosa vera — la direzione che l'altro test non può
      misurare, perché quantifica solo sulle entità che il motore ha già
      trovato.
    - Là: `approva` -> `export_sanitized_text`, cioè il gate di stato e il
      controllo di integrità. Qui la mascheratura è invocata direttamente,
      quindi il gate non è sotto osservazione.

    Le due direzioni sono state falsificate una per una, non solo affermate:

    - se `export_sanitized_text` restituisce `documento.text` invece del testo
      mascherato, l'anti-fuga della matrice fallisce e questo modulo passa
      per intero;
    - se il motore perde una categoria che la matrice non pianta (provato
      spegnendo la regex CATASTO), questo modulo fallisce su tre test e la
      matrice passa per intero.

    Ecco perché convivono: ognuna copre una fuga che l'altra non vede.
    """
    fascicolo, _, mascherato = analisi
    for entita in fascicolo.entities.values():
        for variante in entita.variants:
            assert variante not in mascherato, (
                f"la variante {variante!r} di {entita.placeholder} è in chiaro"
            )


def test_gli_span_risolti_non_si_sovrappongono(analisi):
    """Contratto di `risolvi`, verificato sulla pipeline vera: è la condizione
    che rende il documento mascherabile senza corruzione."""
    fascicolo, _, _ = analisi
    ordinati = sorted(fascicolo.spans, key=lambda s: s.start)
    for precedente, successivo in zip(ordinati, ordinati[1:]):
        assert precedente.end <= successivo.start


def test_il_testo_mascherato_non_contiene_segnaposto_alterati(analisi):
    """Ogni quasi-segnaposto trovato nell'output deve essere un segnaposto
    ben formato: un troncamento come "[PERSONA_1]ONA_2]" bloccherebbe il
    ripristino (spec §11) invece di limitarsi a essere brutto."""
    _, _, mascherato = analisi
    for trovato in QUASI_SEGNAPOSTO.finditer(mascherato):
        assert SEGNAPOSTO.fullmatch(trovato.group(0)), (
            f"segnaposto alterato nel testo mascherato: {trovato.group(0)!r}"
        )
