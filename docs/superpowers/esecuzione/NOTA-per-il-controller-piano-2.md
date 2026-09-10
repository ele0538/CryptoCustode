# Cambio di contratto nel piano 1 che riguarda il piano 2

Dal controller che ha eseguito i Task 1-4 e la revisione finale del ramo
`feat/motore-riconoscimento`. Scritto dopo il fix wave della revisione finale.

## `analizza_documento` adesso solleva un'eccezione

L'item I4 della revisione finale ha chiuso un difetto che distruggeva il testo in silenzio:
`analizza_documento` non era idempotente, e una seconda analisi dello stesso documento
produceva span duplicati che `maschera` poi applicava senza difesa, troncando il documento.
Misurato prima della correzione:

```
1a analisi: 2 span -> 'Bonifico su [IBAN_1] il [DATA_1].'
2a analisi: 4 span -> 'Bonifico su [IBAN_1]'          <-- il resto del documento sparito
```

Due cambiamenti, entrambi fail-closed come il Ruling F che avevi gia' accettato su `mask.py`:

1. **`analizza_documento` rifiuta un documento che ha gia' span nel fascicolo.** Il rifiuto e'
   per documento, non per fascicolo: analizzare il secondo documento di un fascicolo resta
   legittimo.
2. **`maschera` solleva un'eccezione se due degli span che riceve si sovrappongono**, invece di
   produrre un segnaposto malformato tipo `[PERSONA_1]ONA_2]` che il ripristino della §11
   rifiuterebbe come `MalformedPlaceholder`.

Se `analisi_completata` nel piano 2 puo' essere invocata due volte sullo stesso documento —
per esempio su una ri-analisi dopo una mutazione — serve una delle due: passare da uno stato
che azzera gli span del documento prima di rianalizzarlo, oppure intercettare l'eccezione.
Meglio saperlo adesso che scoprirlo nei test.

## Un paio di cose che ti servono per il piano 2

- **Risolvere una `SAME_NAME_NO_CF` come "separa" richiede uno SPLIT di entita', non un merge.**
  `_entita_per_valore` fonde fra documenti *prima* di accodare l'ambiguita', quindi
  `candidate_entity_ids` porta un solo id. Separare vuol dire riassegnare span e bruciare un
  indice nuovo, non unire due entita'. La revisione finale l'ha segnalato come forma da sapere
  prima di progettare, non come difetto.
- **La regola del CF della spec §7 non e' implementata** e `Entity.cf` non viene mai assegnato:
  la spec rende il CF decisivo senza mai dire come un CF si lega a una persona. Adesso e'
  documentato in codice con `# LIMITE NOTO`. Serve un emendamento alla spec prima che il piano 3
  progetti la UI di disambiguazione. Conseguenza aperta: due omonimi nello stesso documento
  condividono `[PERSONA_1]`.
- **L'invariante 2 della spec §4 ora e' sorvegliata da un test** (`test_architettura.py`):
  `core/mask.py` non puo' importare filesystem, orologio o random. Il gate di integrita'
  dell'export del piano 2 poggia su quell'invariante, e adesso e' garantita e non solo intesa.
- **La suite e' a 279 test.** `addopts` NON esclude i `lento`: e' una decisione (Ruling 19), non
  una dimenticanza. L'intermittenza vista durante l'esecuzione parallela veniva da quattro
  processi che tenevano 550 MB ciascuno; `carica_modello` e' gia' `@lru_cache`. Evita di lanciare
  la suite da piu' worktree contemporaneamente.
