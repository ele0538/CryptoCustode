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

Su questo repo lavorano più sessioni Claude insieme, ciascuna con le proprie
worktree e i propri agenti. Due segnali che sembrano coordinamento non lo sono:

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
La #22 tocca la stessa regex `INDIRIZZO` in `core/detect/patterns.py` e la stessa classe
di test in `tests/test_rules.py` che `cryptocustode-9c` teneva in esclusiva per la #14 —
viva, e partita da dieci minuti. Il conflitto è stato evitato solo perché le due sessioni
si sono parlate.

**Come ci si parla.** `ListAgents` elenca le sessioni peer come `cryptocustode-NN`;
`SendMessage` con quel nome recapita, e la risposta arriva in un minuto o due. Sono
strumenti della sessione, non comandi `glab`: su GitLab non resta traccia, quindi quello
che viene concordato va poi scritto in una nota sulla issue.

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
File tenuti in esclusiva: core/detect/patterns.py (Category.INDIRIZZO, righe 156-203),
tests/test_rules.py (nuove classi in coda)."
```

È esattamente questo che ha tenuto le altre sessioni alla larga dalla #14 e dalla #15:
non l'assegnatario, ma l'elenco dei file. Scrivi la nota **prima** di far partire un
agente, e aggiornala se l'ambito cambia: una nota che elenca file che non stai più
toccando blocca gli altri per niente.

### Se scopri che qualcuno è già partito

Non far mollare nessuno per anzianità di assegnazione: **dividi l'ambito**. Quando bc e
9c si sono parlate hanno spartito lo stesso file per righe — `Category.TELEFONO` righe
88-95 a una, `Category.INDIRIZZO` righe 156-203 all'altra — e hanno concordato dove
ciascuna avrebbe appeso le nuove classi di test. Nessuna delle due ha buttato via il
proprio lavoro. Dopo l'accordo, entrambe le sessioni aggiornano la nota della propria
issue, così la divisione sopravvive a chi l'ha concordata.

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
