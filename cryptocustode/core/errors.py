"""Gli errori di dominio della spec §13.

I nomi restano in inglese come i tipi di dominio; i messaggi che li accompagnano
sono in italiano perché arrivano all'utente.
"""


class CryptoCustodeError(Exception):
    """Base di tutti gli errori di dominio, così un chiamante può catturarli
    tutti insieme senza elencarli."""


class InvalidEncoding(CryptoCustodeError):
    """TXT che non è UTF-8 valido."""


class ScannedDocumentRejected(CryptoCustodeError):
    """PDF con almeno una pagina che è una scansione."""


class EmptyDocument(CryptoCustodeError):
    """Documento la cui estrazione non ha reso un solo carattere di testo.

    Non e' lo stesso di `ScannedDocumentRejected`, e per questo ha un nome suo:
    una scansione ha del contenuto che l'app non sa leggere, un documento vuoto
    non ne ha affatto. Il verdetto sulle scansioni si da' una pagina per volta,
    e la riga «pagina bianca senza immagini: passa» e' giusta — una pagina
    bianca in mezzo a un contratto non deve bloccare il contratto. Ma nessuno
    guardava il documento finito, e un PDF di sole pagine bianche entrava nel
    fascicolo con zero caratteri: costava un'analisi, usciva come file
    mascherato vuoto, e falliva al ripristino con «il file e' vuoto». Questo
    errore sposta quella scoperta all'unico momento in cui e' ancora gratis.
    """


class FascicoloFull(CryptoCustodeError):
    """Undicesimo documento in un fascicolo."""


class DuplicateFilename(CryptoCustodeError):
    """Secondo documento con un nome file già presente nel fascicolo.

    Non è un capriccio: il payload dell'export è indicizzato per nome file
    (spec §8), quindi due omonimi collasserebbero in una sola chiave e l'utente
    riceverebbe un documento in meno senza alcun errore (issue #19). Il rifiuto
    all'ingresso è ciò che rende quel payload onesto.
    """


class FascicoloNotFound(CryptoCustodeError):
    """Fascicolo chiesto allo store con un id che non vi corrisponde.

    Esiste perché lo store non lasci uscire il `KeyError` del dizionario che lo
    indicizza: quel KeyError non è un `CryptoCustodeError`, esce dal primo dei
    tre controlli della §8 e attraversa il gate dell'export senza che nessuno
    lo riconosca; il layer HTTP lo tradurrebbe in un 500 al posto del 404 della
    §13 (issue #16).
    """


class ExportNotAllowed(CryptoCustodeError):
    """Esportazione richiesta con il fascicolo in uno stato diverso da APPROVED."""


class IntegrityError(CryptoCustodeError):
    """Il testo mascherato è cambiato dopo l'approvazione."""


class UnknownPlaceholder(CryptoCustodeError):
    """Segnaposto ben formato ma estraneo al dizionario del fascicolo."""


class MalformedPlaceholder(CryptoCustodeError):
    """Frammento che somiglia a un segnaposto senza esserlo."""


class VaultUnreadable(CryptoCustodeError):
    """Password errata o file danneggiato: i due casi non si distinguono."""


class VaultVersionNotSupported(VaultUnreadable):
    """Vault scritto da una versione più recente dell'applicazione.

    Sottoclasse e non fratello di `VaultUnreadable`: un vault che non si sa
    leggere *è* illeggibile, quindi chi cattura il genitore continua a
    funzionare, e chi vuole distinguere il caso può prenderlo per nome.

    È l'unico fallimento del vault con un messaggio proprio, e non contraddice
    la regola della §13 sul messaggio indistinguibile: il numero di versione
    vive dentro il payload cifrato, quindi per arrivare a leggerlo servono già
    la password giusta e il file integro. Dirlo a quel punto non rivela nulla a
    chi è ancora fuori (issue #17).
    """


class UploadTooLarge(CryptoCustodeError):
    """Caricamento più grande del tetto, rifiutato prima di leggerlo.

    È l'unico errore della §13 che nasce fuori dal core, e non per comodità:
    quando la route riceve il suo `UploadFile` i byte del file sono già stati
    scritti nella cartella temporanea, perché starlette controlla
    `max_part_size` solo per le parti che non sono file. Un rifiuto emesso lì
    arriverebbe a danno già fatto, quindi il controllo precede il parser e vive
    nel layer HTTP — ma l'errore resta di dominio, così passa dal gate della
    §13 come tutti gli altri e l'utente riceve un messaggio in italiano invece
    di un 500.
    """


class AIKeyMissing(CryptoCustodeError):
    """Chiave di Gemini assente, o piano non attestato come a pagamento.

    È un 503 e non un 500: non è un difetto del server, è una dipendenza non
    configurata, cioè un servizio indisponibile per una ragione che l'utente
    può rimuovere. Il messaggio deve dire come.

    L'attestazione del piano a pagamento è la decisione D8 della spec del
    2026-09-14: sul piano gratuito i termini di Gemini vietano l'invio di dati
    personali, e questa applicazione non manda altro.
    """


class AIUnavailable(CryptoCustodeError):
    """Gemini irraggiungibile, in timeout, o in errore di trasporto.

    Chi la solleva deve aver lasciato il fascicolo esattamente com'era: niente
    analisi parziale, niente tag a metà (spec §6).
    """


class AIResponseInvalid(CryptoCustodeError):
    """Risposta che lo schema non accetta, o categoria fuori dall'enum.

    È un 502 e non un 503 perché la reazione dell'utente è diversa: sul 503
    riprova, sul 502 riprova e, se si ripete, c'è qualcosa da segnalare.
    """


class VaultNotFound(CryptoCustodeError):
    """Nessun vault corrisponde al file che l'utente sta importando.

    Dichiarato qui in fase 1 benché lo sollevi solo la fase 3: la tabella degli
    errori è un contratto dell'applicazione, e il test di esaustività la
    pretende completa. Il repo lo fa già per le righe 409 dell'esportazione.
    """
