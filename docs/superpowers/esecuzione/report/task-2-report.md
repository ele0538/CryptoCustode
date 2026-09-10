# Task 2 Report: Modello dati

## Implementazione completata

Ho implementato il modello dati di CryptoCustode con i seguenti componenti:

- **Enum**: `Category` (12 valori), `Source`, `State`, `AmbiguityKind`
- **Dataclass**: `Document` (frozen), `Span` (frozen), `Entity`, `Ambiguity`, `Fascicolo`
- **Costante**: `PRIORITA` dict[Category, int]
- **Funzione**: `fascicolo_vuoto(fascicolo_id: str) -> Fascicolo`
- **Proprietà**: Span.priorita, Span.lunghezza, Ambiguity.blocca_approvazione

## TDD - Evidenza

### RED (Step 2)
```
.venv\Scripts\python -m pytest tests/test_models.py -v
```
**Output**: `ModuleNotFoundError: No module named 'cryptocustode.core.models'`
**Stato**: FAIL atteso - il modulo non esiste ancora.

### GREEN (Step 4)
```
.venv\Scripts\python -m pytest tests/test_models.py tests/test_architettura.py -v
```
**Output**:
```
tests\test_models.py ........                            [ 44%]
tests\test_architettura.py ..........                    [100%]

============================= 18 passed in 0.05s ==============================
```
**Stato**: PASS - tutti i 18 test passano.

## File modificati

- **Creato**: `cryptocustode/core/models.py` (210 linee)
- **Creato**: `tests/test_models.py` (72 linee)

## Commit

```
71d921d feat: tipi di dominio con priorita e fascicolo vuoto
```

## Auto-revisione

| Aspetto | Risultato |
|---------|-----------|
| **Completezza** | Tutti i tipi e la funzione dichiarati nel brief ✓ |
| **Nomi** | Corrispondono esattamente al brief ✓ |
| **Priorità** | CF=1, IBAN=1, PIVA=1, EMAIL=2, DATA=3, PERSONA=4 ✓ |
| **Frozen** | Document e Span sono immutabili ✓ |
| **MAX_DOCUMENTI** | Senza annotazione di tipo come richiesto ✓ |
| **Import** | Solo stdlib (dataclasses, enum, __future__) ✓ |
| **Vincoli arch** | models.py in core/, nessun import vietato ✓ |
| **Test** | 8/8 su test_models.py + 10/10 su test_architettura.py ✓ |

## Problemi o preoccupazioni

Nessuno. Il codice è fedele al brief, tutti i test passano, nessuna violazione di vincoli architetturali.
