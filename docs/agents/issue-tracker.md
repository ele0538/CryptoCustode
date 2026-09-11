# Issue tracker: GitLab

Issues and specs for this repo live as GitLab issues. Use the [`glab`](https://gitlab.com/gitlab-org/cli) CLI for all operations.

## Prerequisiti

`glab` 1.117.0 è installato e autenticato su `gitlab.trecuori.org` come
`emanuele.quagliotto` (credenziali nel keyring di Windows).

**Percorso del binario:** `C:\Users\emanuele.quagliotto\AppData\Local\Programs\glab\glab.exe`

È nel PATH dell'utente, ma le shell degli agenti possono avere una copia stale
dell'ambiente e non trovarlo. In quel caso, invece di rinunciare, usa il percorso
assoluto o prependi la cartella al PATH:

```
export PATH="/c/Users/emanuele.quagliotto/AppData/Local/Programs/glab:$PATH"
```

**Scope del token.** Serve un token con scope `api` (più `write_repository` per le
operazioni git). Un token *fine-grained* senza il permesso `Project: Read` fa fallire
ogni chiamata di progetto con `403 insufficient_granular_scope`, anche quando
`glab auth status` riporta il login come riuscito — quindi lo status verde non è prova
che le API funzionino. Verifica con `glab repo view`.

Forma della consegna — **decisa** (issue #13, 2026-09-10): tutto su GitLab, niente
su GitHub. `origin` resta `gitlab.trecuori.org/welfare/ai_service/CryptoCustode` e
codice e issue vivono nello stesso posto: nessun secondo remote, nessun mirror,
nessuna pubblicazione selettiva. Il progetto GitLab è **privato**. Verificato il
2026-09-10: su GitHub non esiste alcun repo CryptoCustode, quindi non c'era nulla da
spostare. Se emerge un vincolo esterno che impone davvero GitHub, si riapre #13
invece di aggiungere un remote di nascosto.

Conseguenza da non perdere: finché il repo resta privato, nome ed email degli autori
nei commit non sono esposti e non serve riscrivere la cronologia. Prima di qualunque
futura pubblicazione — repo pubblico o push su un remote esterno — vanno decise due
cose **prima** del primo push: se riscrivere gli autori dei commit, e una verifica di
riservatezza sull'intera cronologia git (a oggi fatta solo a campione sui file di
test: solo dati inventati, CF e IBAN sintetici).

## Conventions

- **Create an issue**: `glab issue create --title "..." --description "..."`. Use a heredoc for multi-line descriptions. Pass `--description -` to open an editor.
- **Read an issue**: `glab issue view <number> --comments`. Use `-F json` for machine-readable output.
- **List issues**: `glab issue list -F json` with appropriate `--label` filters.
- **Comment on an issue**: `glab issue note <number> --message "..."`. GitLab calls comments "notes".
- **Apply / remove labels**: `glab issue update <number> --label "..."` / `--unlabel "..."`. Multiple labels can be comma-separated or by repeating the flag.
- **Close**: `glab issue close <number>`. `glab issue close` does not accept a closing comment, so post the explanation first with `glab issue note <number> --message "..."`, then close.
- **Merge requests**: GitLab calls PRs "merge requests". Use `glab mr create`, `glab mr view`, `glab mr note`, etc., the same shape as `gh pr ...` with `mr` in place of `pr` and `note`/`--message` in place of `comment`/`--body`.

Infer the repo from `git remote -v`; `glab` does this automatically when run inside a clone.

## Sessioni Claude in parallelo

Su questo repo lavorano più sessioni Claude insieme, ciascuna coi propri agenti. Alcune
stanno in una worktree propria, altre scrivono direttamente nel **working tree
principale**, che è condiviso: la prima cosa da sapere è in quale dei due casi ti trovi,
e lo dicono `git rev-parse --show-toplevel` e `git worktree list`. Due segnali che
sembrano coordinamento non lo sono:

- **L'assegnatario GitLab non è un lock.** Tutte le sessioni agiscono come lo stesso
  utente (`emanuele.quagliotto`), quindi `glab issue update <n> --assignee @me` dice
  che la issue è presa, non *da quale sessione*. Due sessioni che la rivendicano si
  sovrascrivono a vicenda e nessuna delle due se ne accorge.
- **"Zero commit dietro" non prova che un agente sia morto.** Il lavoro di un agente
  vive dentro la sua worktree finché non viene committato: nelle prime ore un agente
  vivissimo è indistinguibile da uno morto. Un'assegnazione vecchia di ore senza
  commit è lo stato normale del lavoro in corso, non un'eredità da raccogliere.

Il caso reale, 2026-09-11. La sessione `cryptocustode-bc` ha letto la #14 assegnata da
17 ore senza commit, ha concluso "agente morto" e ha messo un proprio agente sulla #22.
La #22 tocca la stessa regex `INDIRIZZO` in `cryptocustode/core/detect/patterns.py` e la
stessa classe di test in `tests/test_rules.py` che `cryptocustode-9c` teneva in esclusiva
per la #14 — viva, e partita da dieci minuti. Il conflitto è stato evitato solo perché
le due sessioni si sono parlate.

**Come ci si parla.** `ListAgents` elenca le sessioni peer come `cryptocustode-NN`;
`SendMessage` con quel nome recapita, e la risposta arriva in un minuto o due. Sono
strumenti della sessione, non comandi `glab`: su GitLab non resta traccia, quindi quello
che viene concordato va poi scritto in una nota sulla issue.

### Nel working tree principale si è in tanti

Chi non lavora in una worktree propria scrive negli stessi file di chi sta scrivendo
adesso, e l'area di staging è una sola per tutti. Da lì è venuto il danno peggiore
finora, il 2026-09-10: mentre `cryptocustode-06` modificava `cryptocustode/core/vault.py`
nel tree condiviso, un'altra sessione ha fatto un `git add` a tappeto e ha committato.
Quelle modifiche sono finite dentro `d21d53e`, il cui messaggio parla delle correzioni
alla spec per la #21 e non le nomina nemmeno: `git show --stat d21d53e` mostra `vault.py`
accanto al file della spec, e chi cerca da dove salti fuori `VAULT_VERSION = 2` non lo
trova dove dovrebbe. Il contenuto era giusto e la suite verde, quindi nessuno se n'è
accorto subito — è un difetto della cronologia, non del codice, ed è per questo che dura.
Lo stesso rischio al contrario si è presentato lo stesso giorno: un `git add` del file
della spec ha raccolto il lavoro in corso di un'altra sessione sulla #19, e il patch è
stato filtrato hunk per hunk prima di committare.

- **`git add` sempre coi percorsi espliciti.** Mai `git add -A`, mai `git add .`, mai
  `git add <cartella>`: ingoi il lavoro in volo di un'altra sessione e lo seppellisci
  sotto un messaggio che parla d'altro.
- **Prima di committare leggi `git diff --cached --stat`** e controlla che contenga solo
  i file che hai toccato tu. Se un file condiviso — la spec, un file di test — contiene
  sia il tuo lavoro sia quello di un altro, filtra per hunk invece di committare tutto.
- **Un test rosso può non essere tuo**, e nemmeno un conteggio di test che cresce da
  solo: i file cambiano sotto di te a metà task. Prima di diagnosticare un fallimento,
  guarda con `git status` se il file rosso è fra quelli che hai toccato.
- **Niente operazioni distruttive sul repo mentre altre sessioni sono attive**: rimuovere
  worktree, `reset --hard`, riscrivere la storia. Vale anche per riparare un commit che
  ha inghiottito roba altrui — riscrivere la storia di un ramo su cui qualcuno sta
  lavorando fa più danni di quanti ne ripari. Si annota e si va avanti: è quello che ha
  fatto `71b2a37`, che dice in coda al messaggio cosa era finito per errore in `d21d53e`.

### Le intenzioni si chiedono, i fatti si verificano

Il punto più importante di questa sezione. Fra sessioni asincrone lo stato che hai
dell'altra è **sempre** vecchio di qualche minuto: va bene per sapere cosa una sessione
*intende* fare, non per sapere cosa *ha* fatto. Chiedi pure con `SendMessage` chi sta
facendo cosa, ma prima di agire su un fatto — se un ramo è fuso, se un file è cambiato,
se una issue è chiusa — guardalo nel repo: `git log`, `git status`, `git worktree list`.
Non fidarti del racconto, nemmeno del tuo di dieci minuti fa: possiede una issue chi ha
un agente in volo **verificato adesso**, non chi ce l'aveva secondo un messaggio di dieci
minuti fa.

Misurato il 2026-09-11: ogni deduzione tratta da un messaggio di un'altra sessione è
risultata sbagliata, ogni verifica fatta nel repo è risultata giusta al primo colpo.

**L'esempio lavorato è questo documento.** La catena, lo stesso giorno:

1. `9c` racconta in un messaggio che la collisione #14/#22 si risolve dividendo
   `patterns.py` per righe.
2. Mezz'ora dopo quella frase viene passata come fatto acquisito all'agente che sta
   scrivendo questa sezione, senza tornare a verificarla.
3. Nel frattempo `bc` e `9c` avevano già scartato quella soluzione e rinviato la #22 con
   `Blocked by: #14`.
4. La sezione stava per uscire insegnando ai lettori futuri a spartire un modulo fra due
   sessioni: esattamente la cosa che la convenzione esiste per impedire.
5. L'errore è stato intercettato solo perché `9c` leggeva il diff mentre veniva scritto,
   invece di aspettare il risultato.

La morale è scomoda: l'errore l'ha commesso chi stava scrivendo la regola, violando la
regola, su un fatto vecchio di trenta minuti. Non è negligenza, è il modo normale in cui
il racconto di un'altra sessione invecchia senza avvisare — un fatto non annuncia di
essere scaduto. E la pratica che l'ha fermato vale per conto suo: leggere il diff di
un'altra sessione mentre si scrive, invece di aspettarne il risultato.

### Prima di prendere una issue

1. `glab issue view <n> --comments` e leggi **le note**, non solo assegnatario e label:
   la rivendicazione vera sta lì.
2. Guarda le issue vicine per *file*, non per numero. Due issue che toccano lo stesso
   file sono la stessa issue dal punto di vista dei conflitti, anche se i numeri sono
   lontani: la #14 e la #22 non si somigliano affatto a leggerne i titoli.
3. Se una nota nomina una sessione, chiedile con `SendMessage` se è ancora sopra, invece
   di dedurlo dai commit.

### Come rivendicarla

`glab issue update <n> --assignee @me` va fatto comunque — serve alla frontier query del
wayfinder — ma da solo non dice niente a nessuno. La rivendicazione che funziona è una
nota:

```
glab issue note <n> --message "Presa da cryptocustode-9c, <data e ora>.
File tenuti in esclusiva: cryptocustode/core/detect/patterns.py (voce
Category.INDIRIZZO del dizionario PATTERN), tests/test_rules.py (nuove classi in coda)."
```

È esattamente questo che ha tenuto le altre sessioni alla larga dalla #14 e dalla #15:
non l'assegnatario, ma l'elenco dei file. Scrivi la nota **prima** di far partire un
agente, e aggiornala se l'ambito cambia: una nota che elenca file che non stai più
toccando blocca gli altri per niente.

Nomina le entità — la voce del dizionario, la classe, la funzione — invece dei numeri di
riga: i numeri invecchiano al primo commit che allunga il file (la #15 ne ha aggiunte 18
a `patterns.py` in un giorno), e chi legge la nota deve poter ritrovare il pezzo anche
dopo.

**Una rivendicazione condizionata non è possesso.** "La prendo se il mio utente me lo
conferma" non è una rivendicazione: o tieni la issue, o è libera. Lo stato intermedio,
lasciato implicito, ferma il lavoro degli altri senza che nessuno stia davvero lavorando.
Quindi la nota di esclusiva si scrive quando la conferma c'è; se l'hai scritta e la
conferma non arriva, scrivi una nota che libera la issue invece di lasciarla appesa.

### Se scopri che qualcuno è già partito

Non far mollare nessuno per anzianità di assegnazione, ma non dividere un modulo fra due
sessioni: **un modulo, una sessione.** Spartire lo stesso file per righe o per simboli
regge solo finché i due ticket restano disgiunti per caso — è una proprietà dei
ticket di oggi, non del modulo, e al primo lavoro che tocca qualcosa in mezzo la
collisione torna e va rinegoziata da capo. "Un modulo, una sessione" è invece una
proprietà del modulo e non si rinegozia a ogni ticket.

Nel caso #14/#22 la divisione per righe è stata proposta e poi scartata, per una ragione
tecnica prima che di etichetta: la #14 trasforma `_LUNGHEZZA_MINIMA_RITAGLIO` in
`rules.py` da valore unico tarato sull'IBAN a pavimento *per categoria*, e quel pavimento
sembrava governare il ritaglio di tutte le categorie, INDIRIZZO compresa. Un agente che
avesse fissato in parallelo i confini dello span dell'indirizzo li avrebbe fissati contro
il pavimento vecchio: non un rischio di merge, ma lavoro che nasce già da rifare.

**Epilogo, perché la lezione non poggi su un fatto falso: l'interazione non esisteva.**
Verificata al merge della #14, il ritaglio si applica **solo** alle categorie che hanno un
validatore (`rules.py`, `_accettato` ritorna il valore intatto quando il validatore manca),
e l'insieme dei validatori — CF, DATA, IBAN, PIVA, TELEFONO — coincide con quello dei
pavimenti dichiarati: il ripiego `.get(categoria, 0)` non è raggiungibile e INDIRIZZO non
entra mai nel ciclo. Il suo comportamento è identico a prima e la #22 non avrebbe dovuto
rifare niente.

Questo **non** riabilita la divisione per righe, la rafforza al contrario: al momento della
decisione l'accoppiamento era plausibile e nessuno dei due poteva escluderlo senza fondere
prima. Rinviare è costato qualche ora di attesa su un ticket non urgente; parallelizzare
avrebbe potuto costare il lavoro di un agente intero. **Si rinvia sull'accoppiamento
sospetto e si verifica all'integrazione** — ed è lì che il sospetto va sciolto per
iscritto, come qui, invece di restare nella memoria di chi c'era.

La regola non è calata dall'alto, è il residuo di un disaccordo, e conviene saperlo:
la divisione per righe l'aveva proposta `9c` — e per quei due ticket sarebbe stata
corretta; a smontarla è stato `bc`, con l'argomento dei ticket-contro-modulo che è poi
diventato la regola; il motivo tecnico che ha chiuso la questione, il pavimento
condiviso, l'ha portato di nuovo `9c`. Nessuna delle due aveva ragione dall'inizio ed
entrambe hanno cambiato idea: una regola raggiunta così regge meglio di una dichiarata.

Esito reale: la #22 è stata **rinviata**, non spartita. Porta `Blocked by: #14`, nessuna
delle due sessioni ha un agente sopra, e non parte niente prima che la #14 sia fusa.
Quando due ticket condividono un modulo, la domanda "di chi è" spesso non va risolta: va
rinviata. Il blocco si scrive sulla issue — la riga `Blocked by: #<n>` in cima alla
descrizione, o il quick action `/blocked_by` dove i link nativi ci sono — così sopravvive
alla sessione che l'ha concordato.

Se la sessione nominata non risponde, prendi un'altra issue che non condivida file: il
costo di aspettare è un ticket rimandato, il costo di sbagliare sono due rami che
riscrivono le stesse righe.

## Merge requests as a triage surface

**MRs as a request surface: no.** _(Set to `yes` if this repo treats external merge requests as feature requests; `/triage` reads this flag.)_

When set to `yes`, MRs run through the same labels and states as issues, using the `glab mr` equivalents:

- **Read an MR**: `glab mr view <number> --comments` and `glab mr diff <number>` for the diff.
- **List external MRs for triage**: `glab mr list -F json`, then keep only MRs whose author is not a project member/owner (a contributor's MR, not a maintainer's in-flight work).
- **Comment / label / close**: `glab mr note`, `glab mr update --label`/`--unlabel`, `glab mr close`.

Unlike GitHub, GitLab numbers issues and MRs separately, so `#42` is unambiguous once you know which surface the maintainer means.

## When a skill says "publish to the issue tracker"

Create a GitLab issue.

## When a skill says "fetch the relevant ticket"

Run `glab issue view <number> --comments`.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets.

- **Map**: a single issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body. `glab issue create --label wayfinder:map`. (On GitLab tiers with native epics, an epic may hold the map instead; a labelled issue works everywhere.)
- **Child ticket**: an issue carrying `Part of #<map>` at the top of its description and labels `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). Once claimed, the ticket is assigned to the driving dev.
- **Blocking**: GitLab's **native blocking link**, the canonical, UI-visible representation. Add it with the `/blocked_by #<n>` quick action, posted as a note (`glab issue note <child> --message "/blocked_by #<blocker>"`). Native blocking links are a Premium/Ultimate feature; on the free tier (or where unavailable) fall back to a `Blocked by: #<n>, #<n>` line at the top of the description. A ticket is unblocked when every blocker is closed.
- **Frontier query**: `glab issue list -F json` scoped to the map's children, drop any with an open blocker: a native `blocked_by` link to an open issue (`glab api projects/:id/issues/:iid/links`), or an open issue in the `Blocked by` line, or an assignee; first in map order wins.
- **Claim**: `glab issue update <n> --assignee @me`, the session's first write.
- **Resolve**: `glab issue note <n> --message "<answer>"`, then `glab issue close <n>`, then append a context pointer (gist + link) to the map's Decisions-so-far.
