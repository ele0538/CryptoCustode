# Task 3 Report: Validatori deterministici

## Implementazione completata

Ho implementato esattamente il codice fornito nel brief:
- `cryptocustode/core/detect/validators.py`: modulo autonomo con 4 funzioni pubbliche
- `tests/test_validators.py`: 22 test parametrizzati e combinati

## Ciclo TDD eseguito

### RED (Step 2)
```
ModuleNotFoundError: No module named 'cryptocustode.core.detect.validators'
```
Atteso e verificato.

### GREEN (Step 4)
```
tests/test_validators.py ......................                          [100%]
22 passed in 0.05s
```

### Full suite
```
tests/test_architettura.py ..........                                    [ 25%]
tests/test_models.py ........                                            [ 45%]
tests/test_validators.py ......................                          [100%]
40 passed in 0.07s
```
Nessuna regressione.

## Verifica tabelle ufficiali

Ho verificato manualmente il test `test_cin_calcolato_a_mano`:
- Input: `RSSMRA85M01H501`
- Posizioni dispari (1-based): R(8), S(12), R(8), 8(19), M(18), 1(0), 5(13), 1(0) = **78**
- Posizioni pari: S(18), M(12), A(0), 5(5), 0(0), H(7), 0(0) = **42**
- Totale: 78 + 42 = 120
- 120 mod 26 = 16 → chr(65+16) = chr(81) = **'Q'** ✓

Le tabelle `_DISPARI` e `_PARI` sono corrette.

## File modificati

- `cryptocustode/core/detect/validators.py` (149 linee, nuovo)
- `tests/test_validators.py` (70 linee, nuovo)

## Commit

```
cfc31ae feat: validatori di codice fiscale, partita IVA e IBAN
```

## Auto-revisione

| Aspetto | Status |
|---------|--------|
| **Completezza** | ✓ 4 funzioni pubbliche implementate |
| **Qualità** | ✓ Tabelle trascritte fedelmente char-by-char |
| **Disciplina** | ✓ Solo stdlib (`re`), nessun helper extra |
| **Test** | ✓ 22/22 passano, 40 totali, 0 regressioni |
| **Naming** | ✓ Italiano, conforme brief |

## Note

- Nessun file modificato al di fuori dello scope
- Nessuna dipendenza aggiunta
- Output pytest pulito, nessun warning
- Test case hardcoded (omocodia, spazi IBAN, ecc.) tutti coperti
