"""Le istruzioni e lo schema con cui si interroga Gemini (spec §6).

Sta in `ai/` e non in `core/` perché è la forma di una richiesta a un
fornitore, non una regola del dominio: `core/` non deve sapere che esista un
prompt. Le categorie però vengono da `core/models.py`, perché una seconda
lista scritta a mano divergerebbe al primo cambiamento.
"""

from cryptocustode.core.models import Category

MODELLO = "gemini-3.8-flash"
"""Il Flash di punta, stabile, con structured output vincolato da JSON Schema."""

CATEGORIE = [categoria.value for categoria in Category]

SCHEMA_RILEVAZIONI: dict = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "valore": {"type": "string"},
            "categoria": {"type": "string", "enum": CATEGORIE},
        },
        "required": ["valore", "categoria"],
        "propertyOrdering": ["valore", "categoria"],
    },
}


def istruzioni() -> str:
    """Il testo di sistema, con il vincolo di letteralità in primo piano.

    Il vincolo non è una preferenza di stile: `tagga()` cerca ogni valore alla
    lettera nel documento, quindi un valore normalizzato non viene trovato e il
    dato resta in chiaro nel file esportato. La motivazione sta nel prompt e
    non solo qui, perché un modello che capisce *perché* una regola esiste la
    rispetta più spesso di uno che la legge come un capriccio.
    """
    elenco = "\n".join(f"- {categoria}" for categoria in CATEGORIE)
    return (
        "Sei un revisore che individua i dati personali in documenti italiani.\n"
        "Elenca ogni dato personale presente nel testo che ti viene dato.\n\n"
        "REGOLA PIÙ IMPORTANTE: ogni `valore` che restituisci deve essere una "
        "sottostringa letterale del documento, copiata carattere per carattere "
        "esattamente come vi compare. Non normalizzare, non correggere, non "
        "riordinare, non aggiungere né togliere titoli, non cambiare "
        "maiuscole, spaziatura o punteggiatura.\n"
        "Il motivo: chi riceve la tua risposta cerca quella stringa nel "
        "documento per sostituirla. Se la stringa non combacia, il dato "
        "personale resta visibile.\n\n"
        "Esempio: se il documento scrive `ROSSI Mario`, rispondi `ROSSI Mario` "
        "e non `Mario Rossi`.\n\n"
        "Se lo stesso dato compare più volte **nella stessa forma**, elencalo "
        "una volta sola.\n\n"
        "ATTENZIONE, LO STESSO DATO SCRITTO IN DUE MODI VA ELENCATO DUE "
        "VOLTE. I documenti italiani ripetono spesso lo stesso dato in una "
        "seconda forma, e mascherarne una sola non nasconde niente: chi "
        "legge ricostruisce il dato dall'altra. Ogni forma è una stringa "
        "diversa, quindi va restituita come voce a sé.\n"
        "I casi che ricorrono:\n"
        "- importi in cifre e in lettere: `€ 14.400,00` **e** "
        "`quattordicimilaquattrocento/00` sono due voci IMPORTO, non una;\n"
        "- date in cifre e per esteso: `14/05/1980` **e** "
        "`quattordici maggio millenovecentottanta` sono due voci DATA;\n"
        "- qualunque numero ripetuto in lettere fra parentesi.\n"
        "Copia anche queste alla lettera, con le parentesi e la "
        "punteggiatura come stanno nel documento se ne fanno parte.\n"
        "Se non trovi nessun dato personale, restituisci una lista vuota.\n\n"
        f"Categorie ammesse:\n{elenco}\n"
    )
