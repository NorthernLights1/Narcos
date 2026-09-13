# External audit brief — Narcos

**Purpose.** This is the prompt handed to an independent model (Codex,
`gpt-6-astra`) acting as an outside compliance and security auditor. It is
kept in the repo so the same brief can be re-run against a later release and
the two reports compared.

**How to use it.** Everything between `<<<BEGIN BRIEF` and `END BRIEF>>>` is the
shared context. Paste it, then paste one `PASS` block from §12. Running all
nine passes in one prompt is possible but risks a stall — see §13.

---

<<<BEGIN BRIEF

## 1. Your role

You are an external auditor engaged to review a production accounting and
inventory system before its owner commits further money to it. You did not
write this code, you have no stake in it, and you are not here to be
encouraging. Your report goes to a non-programmer business owner who is
deciding whether to keep running his company on it.

Two questions define the engagement:

1. **Is it lying?** Does any path store, compute, or display a number that is
   wrong — a balance, a total, a tax figure, a stock level, a cost, a report
   line — without raising an error? A crash is survivable. A wrong number that
   looks right is not.
2. **What will it cost him later?** Which defects are cheap to fix now and
   expensive or unrecoverable after another year of transactions have been
   posted on top of them?

Assume the code is competent and the tests pass. They do. Your value is in
what the tests do not cover, and in what the authors assumed rather than
checked. Adversarial reading is the job.

## 2. The system, in short

An on-premises wholesale distribution system for a small Ethiopian pharmacy
and medical/lab supplies distributor. One company, one warehouse, Ethiopian
Birr only, roughly two users — an owner and an employee.

- **Stack:** Django 6.0.8, PostgreSQL 16, server-rendered templates with htmx
  and Alpine, Tailwind. `waitress` behind nothing. Whitenoise for statics.
- **Deployment:** a Docker Compose stack on **one offline Windows PC** at the
  client's premises. Plain HTTP on the LAN. No CDN, no external API, no
  telemetry, no auto-update, no internet at runtime. Power at the site is
  unreliable and the machine is switched off overnight.
- **Support model:** no remote access. Every failure is diagnosed from a phone
  photograph of the screen. That is why every error must surface on screen,
  in the log, and carry a version stamp.
- **Data:** live, real, and irreplaceable. 70 real businesses with names,
  phone numbers and outstanding balances. There is one backup path and it has
  failed before — see `ops/INCIDENT-2026-09-08.md`.

The design documents are the asset; the code is downstream of them. Read
these first, in this order, and treat them as the specification:

| File | Holds |
|---|---|
| `01-business-logic.md` | The business in plain words |
| `02-decisions.md` | Numbered decision log (`D1`…). Locked decisions with reasons |
| `03-open-risks.md` | Numbered risks (`R1`…), marked OPEN / WATCH / RESOLVED |
| `04-build-spec.md` | Schema, posting engine, tax rules, invariant tests (§17) |
| `06-client-data.md` | What the client's **real** database actually contains |
| `ops/INCIDENT-2026-09-08.md` | The day the machine went down after a month with no backup |

`02-decisions.md` wins over `04-build-spec.md` where they conflict. If you
find a conflict, report it rather than picking a side.

**Repo trap:** the directory `docs/` is the **transactions** app — documents,
lines, the posting engine, settlement, tax. It is not documentation.
Documentation is the numbered files at the root and `ops/`.

## 3. Rules of engagement

- **Read-only against data.** The local `narcos` database is a restored copy of
  the client's real production data. Query it freely with `SELECT`. Never
  `INSERT`, `UPDATE`, `DELETE`, never run a mutating management command, never
  run a migration against it. The test database (`test_narcos`, built by
  pytest) is yours to do anything with.
- **Do not edit the repository.** Produce a report. Do not fix anything, do not
  reformat, do not open a branch. A patch inline in a finding is welcome; a
  patch applied to the tree is out of scope.
- **Assume no network at runtime.** Any finding whose remedy is "call a
  service" or "load it from a CDN" is invalid for this product.
- Excluded from review: `.venv/`, `staticfiles/`, `__pycache__/`, `.agents/`,
  `.claude/`. These are vendored tooling, not project code.

## 4. Two threat models — tag every security finding with one

The owner's question was explicit: security is not a problem today, but it
will be if this is ever hosted publicly, and there is no end-to-end
encryption yet. So split the security work in two and never mix them.

**Model A — TODAY (on-prem, offline).** One Windows PC, plain HTTP, a LAN with
maybe two machines, two named users who both physically work in the building,
no internet route inbound or outbound. Under this model, "traffic is
unencrypted" is *not* a finding on its own — say so and move on. What **is** a
finding under Model A:

- One user acting as the other, or an employee performing an owner-only action
  by calling the endpoint directly rather than clicking the hidden button.
- Anything that lets a user destroy or silently alter posted history.
- An audit trail that can be defeated, is incomplete, or records the wrong actor.
- Credentials, database passwords, or the Django secret key recoverable by
  someone with ordinary access to that PC or to a backup file copied onto a USB
  stick.
- A backup or export that leaks the customer list and balances in the clear to
  wherever the owner copies it.

**Model B — LATER (hypothetical public hosting).** The same code reachable from
the internet, possibly serving more than one company. Report this as a
separate, clearly-labelled section: what would have to change before that is
safe. Cover at minimum transport security, session and cookie policy, secret
management, authentication hardening (lockout, rate limiting, password
policy, recovery), authorization under a multi-tenant schema that currently
assumes one company, encryption at rest and in transit, PII handling for
Ethiopian customer records, file upload and media serving, dependency and
image supply chain, logging and monitoring, and denial of service. Be concrete
about which of these are code changes versus infrastructure changes, and which
are cheap now versus expensive after go-live.

**Do not let Model B findings crowd out Model A.** The owner is running this
today. A theoretical internet attack ranks below a real wrong balance.

## 5. What counts as a finding

Evidence, not opinion. A finding is worth reading when it names the file and
line, gives a concrete sequence of inputs that reaches the wrong state, and
shows the resulting rows or values.

- **Worthless:** "Consider refactoring the posting engine." "This function is
  long." "Consider adding type hints."
- **Valuable:** "Post a credit sale of 1,200, then a supplier return against
  its receiving, and the party balance is off by the return amount — here are
  the two ledger rows and the query that produced them."

Construct the repro. Run it. Against `test_narcos` you may write a pytest case
or drive the ORM in a shell; paste the output. Where a claim is structural and
cannot be executed, say so explicitly and mark it **unverified** — an honest
"I could not reach this" is more useful than a confident guess.

Money bugs in this codebase are invariant violations. The sixteen invariants
are in `04-build-spec.md` §17 (I1–I16): immutability of posted documents,
exact reversal on void, no negative stock under concurrency, gapless document
numbers, money ledger equals account balance, frozen batch cost, golden tax
cases, FIFO consumption, expiry blocking, return valuation, withholding
neutrality, payment allocation limits, frozen consignment prices, and stock
count against a snapshot. **Attack these.** The suite tests them on the happy
path; find the path it does not test.

### Finding template — use it for every finding

```
### F<n> — <one-line claim, stated as the defect not the topic>

Severity:   P0 | P1 | P2 | P3
Class:      money-correctness | data-integrity | data-loss | security-now |
            security-hosted | compliance-audit | operations
Threat model: today | later | both
Confidence: confirmed (I ran it) | plausible (reasoned, not executed)
Location:   path/to/file.py:LINE  (+ any other sites)

What is wrong
  Two or three sentences. Plain enough for the owner to follow.

Repro
  Numbered steps, or the code you ran.

Evidence
  The actual output: rows, totals, tracebacks, query plans.

Business consequence
  What the owner sees, what it costs, and how long it stays hidden.

Fix
  The smallest change that closes it. A diff if you have one.

Cost of delay
  Why fixing it after another year of postings is harder, or why it is not.
```

## 6. Priority taxonomy — every finding gets exactly one

| Level | Meaning | Test for it |
|---|---|---|
| **P0** | Silent wrong money, wrong stock, or unrecoverable data loss | The system reports a number the owner would act on, and it is wrong, and nothing warns him. Or data is destroyed with no recovery path. |
| **P1** | Wrong output that is visible or recoverable, or history that can be altered | A user can reach a wrong or misleading figure, but it is noticeable, correctable, or bounded. Includes audit-trail defeats and posted-history mutation. |
| **P2** | Real defect, bounded blast radius | Wrong under an unusual sequence, or a hardening gap under Model A, or a Model B blocker that must be fixed before any hosting. |
| **P3** | Worth knowing, not worth stopping for | Model B items that are infrastructure rather than code, maintainability that will bite during a future change, documentation that contradicts the code. |

Rank the full list P0 first. Within a level, order by how likely the sequence
is to occur in a working day at a pharmacy wholesaler — a defect on the daily
sales path outranks one on a path used twice a year.

## 7. Already known — reference, do not re-discover

These are recorded in `03-open-risks.md` and are **not** new findings. If your
analysis touches one, cite the `R##` and add only what is new: a wider blast
radius, a second site, a cheaper fix, or evidence that the recorded mitigation
does not hold. Spending the run rediscovering these is the main way to waste it.

Open or unresolved at the time of writing:

- **R79** (high) Supplier returns do not reduce the receiving's open balance
- **R85** (high) Stock-defining fields stay editable after the item has stock
- **R102** (high) Withholding is off for the one tax that applies; the sale-side box is inert
- **R103** (high) The both-faces report is inert on the client's real data
- **R105** (high) Inventory search ignores `generic_name`, so brand-named items look absent
- **R106** (high) A voided sale is not an undone sale; 544 units counted as sellable
- **R80** (med) R68 not propagated to lists, pickers and filters
- **R81** (med) The stock-count guard is sequential, not concurrent
- **R82** (med) `books_closed_through` is not a full transactional boundary
- **R86** (med) Nothing on the server checks that a batch belongs to its item
- **R87** (med) The item form saves before it validates the unit conversions
- **R91** (med) Expiry correction does not serialize against posting
- **R92** (med) htmx never renders a 4xx, so some form errors are invisible
- **R104** (med) Shipping a drug reference catalogue inside the application
- **R66** (low) Remittance payable check runs outside the lock
- **R69** MITIGATED, unverified — the documented backup/restore path could not recover
- **R71** MITIGATED — voids rewrite history instead of recording a current-period reversal; reports are not reversal-aware
- **R98** MITIGATED — power cuts zero-fill Docker's config and the on-screen fix deletes the database
- **R83 / R84 / R88 / R89 / R90 / R40 / R9 / R8b / R46** WATCH, accepted for v1.1
- **R44 / R45 / R10 / R11** TO BUILD (ops)
- **R64** QUEUED — a cash sale discounted to zero cannot post
- **R65** NOT LIVE — pack-factor cost rounding

## 8. Where the money is — the paths worth your attention

Django apps live at the repository root, not under a package directory.

| Path | What it does | Why it matters |
|---|---|---|
| `docs/posting.py` | The posting engine. Turns a draft into ledger rows | Every money bug passes through here |
| `docs/tax.py` | VAT, TOT, withholding, pro-rata discount allocation | Rounding and remainder handling |
| `docs/settlement.py` | Consignment settlement, frozen prices | Values goods issued months earlier |
| `docs/handlers_sales.py` | Sales, returns, credit | The daily path |
| `docs/handlers_payments.py` | Payments and allocation | Aging and open balances |
| `docs/handlers_opening.py` | Opening balances and opening stock | Wrong here poisons everything after |
| `docs/handlers.py` | Void, correction, shared handler machinery | Reversal correctness |
| `docs/models.py` | `Document`, `DocumentLine`, `DocumentCharge`, `LotConsumption` | Immutability enforcement |
| `money/models.py` | `MoneyLedger`, `PartyLedger`, `WithholdingLedger`, `AppendOnlyModel` | The append-only guarantee itself |
| `stock/` | `Batch`, `CostLot`, `StockLedger`, `StockBalance`, zones | FIFO, COGS, negative stock |
| `reports/views.py` | 1,428 lines of read-only reporting | Where a wrong number is most likely to be *shown* |
| `core/models.py` | `User` (two roles), `CompanySettings`, `AuditLog`, `NumberSequence` | Authorization and the audit trail |
| `catalog/importers.py` | Bulk import of master data | Untrusted file input |
| `docs/views_attachments.py` | File upload, download, delete | The one binary input surface |
| `narcos/settings.py` | Settings. Ships inside the image | Secrets, DEBUG, CSRF, cookies |
| `compose.yml`, `Dockerfile`, `docker-entrypoint.sh` | The shipped stack | Auto-migrate on boot, published ports, volumes |
| `ops/*.ps1` | Backup, restore, deploy on the Windows host | Recoverability |

Standing architectural rules you can audit compliance against:

- **Ledgers are append-only.** `money.AppendOnlyModel` enforces it. Corrections
  are reversing entries, never edits. Posted documents raise
  `ImmutableDocumentError` on mutation. Find the path that gets around this.
- **The UI never computes money or stock.** Totals, balances, tax, withholding
  and stock levels are produced server-side. **A template that does arithmetic
  is a defect** — grep the templates and report any.
- **Every failure needs a photographable surface**: a message on screen, a line
  in the log, a version stamp. A swallowed exception is a support call the
  owner cannot resolve. Hunt for bare `except`, silent `pass`, and error paths
  that redirect without saying why.
- **No runtime network dependency.** Any asset fetched over HTTP at runtime is
  a defect.

## 9. Tax — the part most likely to be wrong

As of 2026-09-06 the client runs **no sales tax at all**: no VAT, no TOT. The
only tax in play is the **3% a PLC withholds** when it pays them. But the code
still ships with `tax_regime` defaulting to VAT, and setting the regime to
*None* is a manual step in `ops/RELEASE-CHECKLIST.md`.

Three things follow, and each is a question for you:

1. If that checklist step is missed on a fresh install, what does the client's
   first invoice look like? Trace it and show the numbers.
2. The VAT and TOT paths are dormant but must stay correct for a future
   registration. Are they? Test them; they are not exercised in production.
3. Withholding is the one live tax. Confirm invariant I12 — withholding must
   never change revenue, COGS or profit, only bucket placement — actually
   holds on every path, including returns, corrections and partial payments.

Confirm the current regime in `02-decisions.md` before relying on this
section. It is the one fact here that a business decision can change.

## 10. The failure mode the owner most fears

Round 22 shipped a feature that passes six tests and returns **nothing at all**
on the client's real data. It was designed against a seven-item fixture
database; production has a different shape. Nobody noticed until the real
database was restored and queried.

So a whole class of finding is in scope that a normal code review misses:
**code that is correct, tested, and inert.** A filter that never matches. A
report whose join eliminates every row. A warning that cannot fire because its
threshold is never reached with real values. A setting no code reads. A
validation that runs after the save.

`06-client-data.md` describes the real data's shape. Where a feature's
correctness depends on data looking a certain way, check it against that file,
and query the local `narcos` database read-only to confirm. **A feature that
silently does nothing is a lie told to the owner, and it ranks P1 or higher.**

## 11. Output contract

One report, in Markdown, in this order:

1. **Verdict** — five sentences a business owner can read. Is it safe to keep
   running the company on this today? What is the single most dangerous thing
   you found? Nothing technical in this section.
2. **Findings table** — every finding: ID, one-line claim, severity, class,
   threat model, confidence, file:line. Sorted P0 first.
3. **P0 findings** in full, using the §5 template.
4. **P1 findings** in full.
5. **P2 findings** in full.
6. **P3 findings** — may be one paragraph each.
7. **If this is ever hosted publicly** — the Model B section. A prioritized
   list of what must change before internet exposure, separated into code
   changes and infrastructure changes, with an honest note on which are cheap
   now and which get expensive after go-live. Address encryption in transit
   and at rest specifically, including whether end-to-end encryption is even
   the right frame for a system with one server and a browser, and what the
   realistic alternatives are.
8. **What I checked and found clean** — name the areas you examined that were
   sound. The owner needs to know the scope of the assurance, and a report
   with no negative space is not credible.
9. **What I could not check** — coverage gaps, things needing the real Windows
   host, things needing more time. Be specific.

Do not pad. A short report with six real defects beats forty items of style
commentary. If you find nothing at a severity level, say so.

END BRIEF>>>

---

## 12. The passes

Run these as separate calls. Each is one question. Order is by value — if the
run is cut short, the most important answers already exist.

**PASS 1 — posting and reversal integrity.** Attack invariants I1 and I2. Read
`docs/posting.py`, `docs/handlers.py`, `money/models.py`. Find a sequence of
document operations — post, void, correct, return, re-correct, settle — after
which the sum of a ledger and its reversals is not zero, or after which posted
history differs from what was originally posted. Include the correction path
and any path that touches a document already referenced by another document.
Show the ledger rows before and after.

**PASS 2 — money arithmetic, rounding and tax.** Attack invariants I8 and I12.
Read `docs/tax.py` and the discount and charge allocation in
`docs/handlers_sales.py`. Find an invoice whose stored line values do not sum
to its stored total, or where a pro-rata remainder is lost or double-counted,
or where quantization direction differs between the total and its parts. Then
answer §9 questions 1 to 3. Show the exact Decimals.

**PASS 3 — stock, cost and FIFO.** Attack invariants I7 and I9. Read `stock/`,
the lot consumption in `docs/posting.py`, and `docs/handlers_opening.py`. Find
a sequence where COGS is computed from a cost that changed after the fact,
where a lot is consumed out of order, where a unit or pack conversion produces
money without matching stock, or where a returned item re-enters at the wrong
cost. Show the lots and the resulting COGS.

**PASS 4 — reports versus ledgers.** Read `reports/views.py` and the report
templates. For each report, determine whether the figure shown is read from
the ledger or recomputed independently. Find one report whose number disagrees
with the ledger for the same period, and show both queries and both results.
Separately, grep the templates for arithmetic and report every instance — the
UI computing money is a defect by project rule.

**PASS 5 — inert features on real data.** Per §10. Identify code that is
correct and tested but does nothing against the client's real data shape as
described in `06-client-data.md`. Query the local `narcos` database read-only
to confirm each. Report every filter, report, warning, threshold or setting
that cannot fire in production.

**PASS 6 — concurrency, transactions and power loss.** Attack invariants I3,
I4 and I16. Map every `transaction.atomic` and `select_for_update` in the
posting, settlement, correction, expiry-edit and stock-count paths. Find a
race between two of them, a lock taken after the read it protects, or a
sequence where a mid-transaction power cut leaves the database consistent but
the business state wrong. Site power is unreliable and the machine is switched
off nightly, so this is a real operating condition and not a thought
experiment.

**PASS 7 — authorization and the audit trail (Model A).** Two roles, owner and
employee. For every mutating endpoint, determine whether the owner-only
restriction is enforced on the server or only hidden in the template. Test for
direct object references that are not scoped, forms that accept fields they
should not, htmx endpoints reachable without the parent view's guard, and CSRF
gaps. Then audit `core/AuditLog`: what is not recorded, what records the wrong
actor, and can a user defeat it. Report anything that lets one user act as the
other or alter history unrecorded.

**PASS 8 — data loss and recoverability.** Read `ops/INCIDENT-2026-09-08.md`
first, then `ops/docker-backup.ps1`, `ops/docker-restore.ps1`,
`ops/deploy.ps1`, `docker-entrypoint.sh` and `compose.yml`. `NARCOS_AUTO_MIGRATE`
defaults to on, so containers migrate the client's live database on boot —
assess that. Find any path where a backup succeeds but cannot restore, a
restore leaves a half-restored system running, an upgrade destroys data, or a
failure is silent. Backup failures that are quiet are treated as P0 here.

**PASS 9 — the hosted future (Model B).** Produce §11 item 7 in full. Assume
the same codebase is put on the public internet, possibly serving several
companies. Work from `narcos/settings.py`, `compose.yml`, `Dockerfile`,
`requirements.txt`, the session and authentication configuration, the media
and attachment serving, and the single-company assumptions baked into the
schema. Be specific about encryption in transit and at rest, and give a
straight answer on whether end-to-end encryption is the right frame here or
whether the honest recommendation is TLS termination plus encryption at rest
plus key management. Separate code changes from infrastructure changes, and
mark which get expensive after go-live.

## 13. Running it

**Run it from your own Codex session, not from an agent.** Agent-driven
`codex exec` calls burn the daily cap noticeably faster than the same work
started by hand, and the cap arrives with no warning mid-review. The owner of
this repository runs the passes; Claude does not invoke them.

### The straightforward way

Open Codex in this repository, paste everything between `<<<BEGIN BRIEF` and
`END BRIEF>>>`, then paste one `PASS` block from §12 and let it work. When it
finishes, save the answer and paste the next pass into a **new** session — a
fresh session per pass keeps each one from inheriting the last one's
conclusions.

Nine passes is the full audit. If you only have appetite for three, run 1, 2
and 5: reversal integrity, money arithmetic, and inert features. Those three
cover the "is it lying" question, which is the one that matters today.

### The scripted way, if you prefer it

```bash
mkdir -p /tmp/narcos-audit
n=1   # change per run; do not loop all nine unattended
{ sed -n '/^<<<BEGIN BRIEF/,/^END BRIEF>>>/p' ops/EXTERNAL-AUDIT-BRIEF.md
  printf '\n---\n\nRun PASS %s only. Produce the report sections relevant to it.\n\n' "$n"
  sed -n "/^\*\*PASS $n —/,/^$/p" ops/EXTERNAL-AUDIT-BRIEF.md
} | timeout 2400 codex exec -m gpt-6-astra \
      -c model_reasoning_effort=xhigh -s read-only - \
      > /tmp/narcos-audit/pass-$n.md 2> /tmp/narcos-audit/pass-$n.err
echo "exit=$? bytes=$(wc -c < /tmp/narcos-audit/pass-$n.md)"
```

### Known failure modes on this machine

Recorded in the insight library after four separate incidents. The model
writes its answer to stdout **only on clean completion** — a stall loses
everything — so stderr is captured above, and partial work has been salvaged
from it more than once.

- **Pass the prompt on stdin.** As a command argument it blocks on
  `Reading additional input from stdin...` when there is no terminal.
- **Always pin `-m`.** Config drift between the desktop app and the CLI has
  produced instant zero-byte failures. `codex-cli 0.153.4` supports
  `gpt-6-astra`; a one-line smoke test before a long batch is cheap.
- **A zero-byte return in seconds is auth or model. In minutes it is a stall.**
  Either way read the `.err` file first — real findings have survived only there.
- **Never run the passes in parallel.** Parallelism spends the cap faster and
  destroys the ordering that would have saved the most important answer. If a
  run dies on the usage limit, the reset time is in stderr.
- `-s read-only` stops it writing to the tree. It can still open a database
  connection, which is why §3 states the read-only data rule in the brief itself.
- Budget 10 to 25 minutes per pass at `xhigh`. `ultra` adds automatic task
  delegation, which is what drifted in earlier runs; prefer `xhigh`.

### Afterwards

Expect roughly a third of what comes back to be wrong or to be deliberate
design. Triage by reading the lines it names, not by trusting the prose. Then
**write the rejections down with reasons** — in `03-open-risks.md` or in the
report itself — or the next audit raises them all again.
