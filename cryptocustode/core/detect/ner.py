"""Riconoscimento statistico delle entità con spaCy: priorità P4 (spec §6).

Il modello è generalista: non offre garanzie di completezza. Serve ad assistere
la revisione umana, non a sostituirla.
"""

import re
from functools import lru_cache

import spacy
from spacy.language import Language

from cryptocustode.core.models import Category, Source, Span

MAPPA_LABEL: dict[str, Category] = {
    "PER": Category.PERSONA,
    "ORG": Category.AZIENDA,
    "LOC": Category.INDIRIZZO,
}

# Vocabolario di scarto per la validazione P4 della spec §6 ("scarto stopword e
# token di una sola lettera").
#
# La regola è deliberatamente nella sua forma più conservativa: uno span viene
# scartato **solo se ogni** suo token è una stopword, un titolo o un carattere
# singolo. Un nome vero ha sempre almeno un token che non è nessuna delle tre
# cose, quindi la regola non può far cadere una persona reale — e l'asimmetria
# è il punto, perché scartare uno span del NER è la direzione che fa fuggire i
# dati. Per la stessa ragione nell'elenco non entra nessuna parola che possa
# essere un cognome o un nome italiano ("Rosa", "Patti", "Costa", "Piazza"): i
# falsi positivi di quel tipo restano coperti dal limite noto §16.1.
#
# I termini sono a livello di *token*, dopo casefold e rimozione della
# punteggiatura: "Sig.ra" si spezza in "sig" e "ra", "Dott.ssa" in "dott" e
# "ssa". Per questo l'elenco non coincide con `_TITOLI` di `entities.py`, che
# invece serve a togliere il titolo dal *prefisso* di una stringa intera.
_STOPWORD_NER = frozenset({
    # titoli della normalizzazione (spec §7) e loro frammenti
    "sig", "sigra", "ra", "signor", "signora", "signori", "dott", "ssa",
    "dottore", "dottoressa", "avv", "avvocato", "ing", "ingegner", "arch",
    "geom", "rag", "prof", "on", "spett", "spettle", "egr",
    # etichette dei recapiti
    "tel", "telefono", "cell", "cellulare", "fax", "mobile", "email", "mail",
    "pec", "iban", "cf", "piva", "iva", "vat", "indirizzo", "recapito",
    # parole di struttura del documento
    "contratto", "contratti", "scrittura", "privata", "atto", "documento",
    "locazione", "locatore", "locatrice", "conduttore", "conduttrice",
    "venditore", "acquirente", "cliente", "fornitore", "committente",
    "appaltatore", "mandante", "mandatario", "intestatario", "beneficiario",
    "premesso", "premessa", "premesse", "oggetto", "articolo", "art", "comma",
    "allegato", "allegati", "allegata", "fattura", "ricevuta", "canone",
    "importo", "totale", "imponibile", "pratica", "protocollo", "riferimento",
    "codice", "fiscale", "partita", "residente", "residenza", "domicilio",
    "domiciliato", "domiciliata", "nato", "nata", "sede", "legale",
    "sottoscritto", "sottoscritta", "presente", "predetto", "predetta",
    "seguito", "firma", "firmato", "data", "luogo", "pagina", "pag",
    # articoli, preposizioni e congiunzioni
    "il", "lo", "la", "le", "gli", "un", "uno", "una", "di", "del", "dello",
    "della", "dei", "degli", "delle", "da", "dal", "dalla", "in", "con", "su",
    "sul", "sulla", "per", "tra", "fra", "al", "allo", "alla", "ai", "agli",
    "alle", "ed", "che", "non", "come", "quanto", "segue", "presso",
})

# I token si ricavano spezzando su tutto ciò che non è lettera, cifra o
# apostrofo: la punteggiatura dei titoli e delle sigle non deve entrare nel
# confronto con il vocabolario.
_SEPARATORE_TOKEN = re.compile(r"[^\w'À-ÿ]+")


@lru_cache(maxsize=2)
def carica_modello(nome: str = "it_core_news_lg") -> Language:
    """Carica il modello una volta sola per processo: sono circa 550 MB."""
    try:
        return spacy.load(nome)
    except OSError as errore:
        raise RuntimeError(
            f"modello spaCy '{nome}' non installato. "
            f"Eseguire: python -m spacy download {nome}"
        ) from errore


def solo_parole_di_struttura(valore: str) -> bool:
    """Vero se *ogni* token di `valore` è una stopword, un titolo o un
    carattere singolo: allora non è un nome, è un'etichetta del documento.

    Falso appena un token non lo è, anche uno solo: è la condizione che
    protegge i nomi veri ("Sig. Rossi" ha "rossi", che non è nell'elenco).
    """
    token = [t for t in _SEPARATORE_TOKEN.split(valore) if t]
    if not token:
        return True
    for grezzo in token:
        chiave = grezzo.casefold().strip("'")
        if len(chiave) <= 1:
            continue
        if chiave in _STOPWORD_NER:
            continue
        return False
    return True


def tronca_al_primo_a_capo(valore: str) -> str:
    """La parte di `valore` che precede il primo a capo, senza spazi in coda.

    Un a capo separa due campi del documento, non due parti dello stesso dato:
    l'a capo è il confine, e qui è dove lo span si ferma (issue #36).

    **Si tronca, non si scarta.** Sullo span vorace il troncamento dà la
    risposta giusta e basta — `'ALBERTO\\nMatricola 0012345 - Qualifica'`
    diventa `'ALBERTO'`, `'Orbassano\\nAssunto'` diventa `'Orbassano'` — perché
    il modello parte dall'entità vera e poi dilaga oltre il confine. Ma la
    ragione per cui si tronca vale anche quando il troncamento *non* dà la
    risposta giusta, ed è il caso che segue.

    **Cosa viene sacrificato: il nome legittimamente spezzato a capo
    dall'estrazione PDF.** Se il testo estratto contiene `'Alberto\\nFerrante'`
    e il modello lo riconosce come una persona sola, da qui esce `'Alberto'` e
    il cognome resta in chiaro. È una perdita reale e dichiarata, ed è la stessa
    famiglia del limite già noto per cui un codice fiscale spezzato a capo non
    viene rilevato. La si accetta perché le due direzioni non sono simmetriche:

    - troncare fa fuggire `'Ferrante'`;
    - scartare lo span farebbe fuggire `'Alberto Ferrante'`, cioè tutto.

    La fuga del troncamento è un sottoinsieme stretto della fuga dello scarto,
    quindi troncare domina su ogni testo. È la stessa asimmetria che governa
    `solo_parole_di_struttura` (commit `2c61c8f`): scartare uno span del NER è
    la direzione che fa fuggire i dati, e non la si prende senza necessità.
    Il sottoinsieme è stretto davvero: gli offset arrivano qui già ripuliti
    dallo spazio ai bordi, quindi la testa non è mai vuota e c'è sempre
    qualcosa che il troncamento maschera e lo scarto no.

    **Perché non si spezza in due span, tenendo anche la coda.** È la terza via
    che sembrerebbe dominare entrambe, e non funziona: la coda dopo l'a capo è
    proprio il campo *altrui* in cui il modello è dilagato, quindi promuoverla
    a span rimette in piedi il difetto invece di toglierlo. `'Matricola 0012345
    - Qualifica'` diventerebbe un `[PERSONA_n]` per conto suo, e
    `solo_parole_di_struttura` non lo ferma, perché "matricola" non è una
    parola di struttura. Sui due casi la stessa mossa ha esiti opposti, e
    distinguerli è esattamente ciò che il modello ha sbagliato. Troncare
    sceglie: della testa ci si fida, della coda no — ed è la scelta calibrata
    su come il modello sbaglia, cioè partendo dall'entità vera e dilagando in
    avanti.

    **Un troncamento che lascia un frammento corto non viene scartato.** Se
    l'estrazione spezza la parola invece della riga (`'Ferran\\nte'`), da qui
    esce `'Ferran'`: mezzo cognome mascherato e mezzo in chiaro. Non si
    introduce una soglia di lunghezza minima sotto la quale buttare il resto,
    per due ragioni. La prima è l'asimmetria di sopra, identica un livello più
    in basso: scartare il frammento fa fuggire *anche* la testa che il
    troncamento aveva mascherato, quindi la soglia peggiora il caso che vuole
    curare. La seconda è che non sarebbe verificabile — i cognomi italiani di
    due lettere esistono (Fo, Bo, Re), e una regola che li scarta è la
    "euristica sulla plausibilità del nome" che `2c61c8f` ha rifiutato per
    nome. L'unica soglia che resta è quella che il repo aveva già, il carattere
    singolo della validazione P4 (spec §6): `trova_per_ner` la applica *dopo*
    il troncamento invece che prima, così guarda ciò che diventa davvero uno
    span invece di ciò che il modello aveva proposto.

    All'obiezione che mezzo nome mascherato sia peggio di niente, perché dà
    falsa sicurezza, la risposta sta nella spec §16.7: la gamba statistica è
    dichiaratamente inaffidabile e assiste la revisione umana invece di
    sostituirla. Quello che resta in chiaro resta *visibile* a chi rivede, che
    può marcarlo a mano; quello che si scarta è in chiaro esattamente allo
    stesso modo, solo con un segnaposto in meno accanto. Nessuna delle due
    scelte è una garanzia, e fra le due si prende quella che maschera di più.

    Si taglia solo sull'a capo, che è un confine di campo. Non si taglia sulle
    corse di spazi (`'Alberto   Luogo'`, colonne di un PDF): uno spazio sta
    dentro i nomi veri, quindi lì il confine non è deterministico e la regola
    smetterebbe di essere verificabile.

    Il risultato è sempre un prefisso di `valore`, ed è l'invariante su cui
    poggia l'aritmetica degli offset in `trova_per_ner`: l'inizio non si muove
    e la nuova fine si ricava dalla lunghezza, senza ricercare niente nel
    testo.
    """
    testa, a_capo, _ = valore.partition("\n")
    if not a_capo:
        return valore
    return testa.rstrip()


def trova_per_ner(testo: str, doc_id: str) -> list[Span]:
    """Span ricavati dal NER, senza risoluzione delle sovrapposizioni."""
    documento = carica_modello()(testo)
    trovati: list[Span] = []
    for entita in documento.ents:
        categoria = MAPPA_LABEL.get(entita.label_)
        if categoria is None:
            continue
        # Gli offset di spaCy possono includere spazi ai bordi: li riduco, così
        # il testo mascherato non resta con spazi doppi.
        inizio = entita.start_char + (len(entita.text) - len(entita.text.lstrip()))
        fine = entita.end_char - (len(entita.text) - len(entita.text.rstrip()))
        # Issue #36: un a capo separa due campi, non due parti dello stesso
        # dato, e lo span si ferma lì. Il taglio viene prima delle due
        # validazioni che seguono perché le sposta entrambe: quello che va
        # pesato — un carattere solo, o sole parole di struttura — è il resto
        # che diventa segnaposto, non quello che il modello aveva proposto.
        valore = tronca_al_primo_a_capo(testo[inizio:fine])
        fine = inizio + len(valore)
        if len(valore) <= 1:
            continue
        # Validazione P4 della spec §6: uno span fatto solo di parole di
        # struttura non è un dato personale. Il filtro non protegge la privacy
        # — sovra-mascherare è la direzione sicura — ma brucia indici di
        # segnaposto che per progetto non vengono mai riciclati (spec §5),
        # degrada il testo che l'IA riceve e sommerge gli span veri che
        # l'utente deve rivedere.
        if solo_parole_di_struttura(valore):
            continue
        trovati.append(
            Span(
                span_id=f"{doc_id}:{inizio}-{fine}:{categoria.value}",
                doc_id=doc_id,
                start=inizio,
                end=fine,
                category=categoria,
                source=Source.NER,
                entity_id="",
            )
        )
    trovati.sort(key=lambda s: (s.start, -s.lunghezza))
    return trovati
