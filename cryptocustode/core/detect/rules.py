"""Applica pattern e validatori al testo e produce span da regole deterministiche,
di qualunque priorità.

Gli span nascono con `entity_id` vuoto: l'assegnazione delle entità è compito
di `core/entities.py`.
"""
from __future__ import annotations

import re
from datetime import date

from cryptocustode.core.detect import validators
from cryptocustode.core.detect.patterns import (
    FINESTRA_CONTESTO,
    MESI,
    PAROLE_CONTESTO,
    PATTERN,
)
from cryptocustode.core.models import Category, Source, Span

_NOMI_MESI = {nome: numero for numero, nome in enumerate(MESI.split("|"), start=1)}

# Compilate una sola volta per categoria: un'alternanza delle parole chiave,
# ciascuna delimitata da confini di parola non standard (`\b` non si comporta
# bene dopo un punto finale come in "p.i."), così "particella" non attiva
# "cell" (spec §6, §16 limite 3).
_REGEX_CONTESTO: dict[Category, re.Pattern[str]] = {
    categoria: re.compile(
        "|".join(rf"(?<!\w){re.escape(parola)}(?!\w)" for parola in parole)
    )
    for categoria, parole in PAROLE_CONTESTO.items()
}

# Prefissi che certificano da soli il requisito di contesto: fanno parte del
# match stesso, quindi non possono comparire nella finestra che lo precede
# (spec §6: si applica solo a una sequenza nuda o senza prefisso internazionale).
_PREFISSI_AUTOSUFFICIENTI: dict[Category, tuple[str, ...]] = {
    Category.PIVA: ("IT",),
    Category.TELEFONO: ("+39",),
}

# `0039` non è inequivocabile come `+39`: coincide con le prime quattro cifre di
# un numero qualunque. Vale come prefisso internazionale solo se lo seguono le
# 9-10 cifre di un numero nazionale; "00391234567" sono undici cifre nude, che
# senza parola chiave vicina la spec §6 vuole scartare.
_PREFISSO_0039 = re.compile(r"\A0039\D*(?:\d\D*){9,10}\Z")


def _ha_contesto(testo: str, inizio: int, valore: str, categoria: Category) -> bool:
    prefissi = _PREFISSI_AUTOSUFFICIENTI.get(categoria, ())
    if valore.startswith(prefissi):
        return True
    if categoria is Category.TELEFONO and _PREFISSO_0039.match(valore):
        return True
    pattern = _REGEX_CONTESTO.get(categoria)
    if pattern is None:
        return True
    finestra = testo[max(0, inizio - FINESTRA_CONTESTO):inizio].lower()
    return pattern.search(finestra) is not None


def _data_esiste(valore: str) -> bool:
    ripulito = valore.strip().lower()
    numerica = re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", ripulito)
    if numerica:
        giorno, mese, anno = (int(g) for g in numerica.groups())
    else:
        iso = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", ripulito)
        if iso:
            anno, mese, giorno = (int(g) for g in iso.groups())
        else:
            testuale = re.fullmatch(r"(\d{1,2})\s+([a-zà-ÿ]+)\s+(\d{4})", ripulito)
            if not testuale:
                return False
            giorno = int(testuale.group(1))
            mese = _NOMI_MESI.get(testuale.group(2), 0)
            anno = int(testuale.group(3))
    try:
        date(anno, mese, giorno)
    except ValueError:
        return False
    return True


def _telefono_plausibile(valore: str) -> bool:
    """Spec §6: lunghezza complessiva 9-11 cifre.

    Il prefisso internazionale non entra nel conteggio: `+39 340 1234567` è lo
    stesso numero di `340 1234567`, e contare anche il `39` respingerebbe come
    troppo lungo qualunque cellulare con prefisso.
    """
    nazionale = re.sub(r"\A(?:\+39|0039)", "", valore.strip())
    return 9 <= len(re.sub(r"\D", "", nazionale)) <= 11


_VALIDATORI = {
    Category.CF: validators.cf_valido,
    Category.PIVA: validators.piva_valida,
    Category.IBAN: validators.iban_valido,
    Category.TELEFONO: _telefono_plausibile,
    Category.DATA: _data_esiste,
}

# Pavimento del ritaglio, **per categoria**: sotto questa lunghezza il
# candidato non può più superare il validatore, quindi continuare ad
# accorciarlo è lavoro buttato e il ritaglio si arrende.
#
# Era un numero solo, 15, cioè la lunghezza minima di un IBAN (due lettere di
# paese, due cifre di controllo, undici caratteri di corpo — spec §6),
# applicato a ogni categoria. Nessun candidato telefonico arriva a 15
# caratteri, quindi per il telefono il ritaglio era morto in partenza: una coda
# vorace troppo lunga veniva scartata invece di essere riportata dentro il
# conteggio, e il numero spariva del tutto (issue #14). Ogni pavimento
# discende ora dal validatore della *propria* categoria, quindi abbassarne uno
# non allenta gli altri.
#
# CF, PIVA e DATA sono qui per completezza e non cambiano comportamento: le
# loro regex non contengono spazi (CF, PIVA) oppure non ammettono alcun
# troncamento valido (togliere l'ultimo gruppo a "14 marzo 2024" non produce
# mai una data), quindi per loro il ritaglio finisce comunque senza candidati.
_LUNGHEZZA_MINIMA_RITAGLIO: dict[Category, int] = {
    # Sedici caratteri, lunghezza fissa del codice fiscale.
    Category.CF: 16,
    # Undici cifre; con il prefisso `IT` sono tredici, ma il pavimento è un
    # minimo e deve valere per la forma più corta.
    Category.PIVA: 11,
    Category.IBAN: 15,
    # Nove cifre senza separatori: è la forma più corta che
    # `_telefono_plausibile` possa accettare.
    Category.TELEFONO: 9,
    # "1/1/2024", la forma numerica più corta che `_data_esiste` accetta.
    Category.DATA: 8,
}


# Caratteri su cui il ritaglio può tagliare, oltre agli spazi di qualunque
# forma (compreso l'a capo che l'estrazione da PDF infila dentro i numeri).
#
# Tagliare ai soli spazi non basta. La coda vorace non si attacca sempre
# attraverso uno spazio: se al numero seguono altre cifre separate da "/" o
# "-" ("011 1234567/14"), l'ultimo spazio del candidato cade *prima* del
# numero, il ritaglio scende di colpo al solo prefisso e il numero viene
# scartato del tutto — la stessa fuga totale che la correzione deve chiudere.
#
# Sono i separatori che le regex ammettono *dentro* un valore, quindi tagliare
# qui non inventa confini: al più si prova un candidato in più, e l'ultima
# parola resta al validatore. Per l'IBAN l'insieme è inerte, perché
# la sua regex ammette solo spazi fra i gruppi; per la data i candidati più
# corti non sono mai date valide, quindi il ritaglio finisce come prima senza
# candidati.
_SEPARATORI_DI_RITAGLIO = ".-/"


def _ultimo_taglio(candidato: str) -> int:
    """L'indice dell'ultimo separatore del candidato, oppure -1 se non ce ne
    sono: è il punto in cui il ritaglio prova ad accorciarlo."""
    return max(
        (
            indice
            for indice, carattere in enumerate(candidato)
            if carattere.isspace() or carattere in _SEPARATORI_DI_RITAGLIO
        ),
        default=-1,
    )


def _accettato(categoria: Category, valore: str) -> str | None:
    """Il candidato più lungo che supera il validatore della categoria, oppure
    `None` se nessuno lo supera.

    Un match può inglobare testo che non appartiene al valore. Quando il
    validatore lo boccia, riprovo con candidati via via più corti, tagliati
    all'ultimo separatore, e mi fermo al primo che passa: è il validatore a
    disambiguare dove finisce il valore.

    I consumatori sono due. L'IBAN, la cui regex tollera gli spazi interni e la
    cui coda vorace arriva a mangiare la parola maiuscola successiva
    ("IT60... PRESSO"), e il telefono, la cui corsa vorace può inglobare le
    cifre di ciò che segue il numero ("011 1234567 14" davanti a una data).
    CF e PIVA hanno lunghezza fissa e nessuno spazio interno: per loro il primo
    taglio non esiste nemmeno.
    """
    validatore = _VALIDATORI.get(categoria)
    if validatore is None:
        return valore
    # Il valore di ripiego è 0, cioè "nessuna scorciatoia": una categoria con
    # validatore ma senza pavimento dichiarato ritaglia fino a esaurire gli
    # spazi. È più lento, non più permissivo — resta il validatore a decidere
    # — e non lascia passare in silenzio una categoria dimenticata.
    pavimento = _LUNGHEZZA_MINIMA_RITAGLIO.get(categoria, 0)
    candidato = valore
    while True:
        if validatore(candidato):
            return candidato
        taglio = _ultimo_taglio(candidato)
        if taglio < 0 or len(candidato) < pavimento:
            return None
        candidato = candidato[:taglio]


def trova_per_regole(testo: str, doc_id: str) -> list[Span]:
    """Tutti gli span ricavabili da regex e checksum, senza risoluzione delle
    sovrapposizioni: quella è responsabilità di `core/spans.py`."""
    trovati: list[Span] = []
    for categoria, pattern in PATTERN.items():
        for corrispondenza in pattern.finditer(testo):
            # PRATICA cattura l'identificativo nel gruppo 1: lo span copre
            # l'intera espressione, parola chiave inclusa, così l'utente vede
            # il contesto che ha giustificato il riconoscimento.
            valore = corrispondenza.group(0)
            if categoria is Category.PRATICA and not any(
                c.isdigit() for c in corrispondenza.group(1)
            ):
                continue
            accettato = _accettato(categoria, valore)
            if accettato is None:
                continue
            if not _ha_contesto(testo, corrispondenza.start(), accettato, categoria):
                continue
            # `fine` si ricava dal candidato accettato, non dal match: se la coda
            # è stata ritagliata, `testo[inizio:fine]` deve essere esattamente il
            # valore riconosciuto.
            inizio = corrispondenza.start()
            fine = inizio + len(accettato)
            trovati.append(
                Span(
                    span_id=f"{doc_id}:{inizio}-{fine}:{categoria.value}",
                    doc_id=doc_id,
                    start=inizio,
                    end=fine,
                    category=categoria,
                    source=Source.RULE,
                    entity_id="",
                )
            )
    trovati.sort(key=lambda s: (s.start, -s.lunghezza))
    return trovati
