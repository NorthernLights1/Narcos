# Status

Dear Temesgen,

**The previous version of this file was wrong.** It said "436 / 436 green, the
batch is ready to tag." The tests were green, but the audit behind that
sentence had only covered the 29-commit batch — not the application. A
whole-app audit has now been done jointly with Codex, and it found twelve
defects, one of which the batch itself introduced.

All twelve are fixed in the working tree, and Codex has since attacked the
diff and found thirteen more things — six acted on, five recorded, two of them
regressions the fixes themselves introduced. **456 / 456 tests green**,
`manage.py check` clean, `makemigrations --check` clean, Django 6.0.8.
Nothing is committed yet.

## How this round was done

You asked the two of us to talk to each other instead of you carrying messages
between us. Codex ran read-only on `gpt-5.6-sol` at `ultra` effort, resuming
its own session so it kept full context; I drove it from a script and read its
reports directly. It audited, I verified every finding in the code myself, I
implemented, and then I handed it the diff to attack. It corrected itself under
challenge on one claim and sharpened two others.

I re-derived eleven of the twelve independently. **R71 I did not** — that one
rests on Codex's tracing, and the file says so.

## What was actually wrong

Twelve findings, recorded as R67–R78 in [03-open-risks.md](03-open-risks.md),
decided as [D116–D120](02-decisions.md).

**Ten of the twelve are in `v1.0.0` — already on the client's machine.**
Shipping this batch does not make them worse; it fixes them.

| # | What it did | Fix |
|---|-------------|-----|
| R70 | Correcting a sale that had a return or a receipt against it voided those too and never put them back — the customer was billed again for money they had paid | D116 |
| R67 | A credit note used today's catalogue price, not the price the invoice charged; tax at today's rate, not the sale's | D117 |
| R68 | A return never reduced the invoice it came from, so aging chased money no longer owed | D118 |
| R71 | Voiding a June sale in August erased it from June and put it in no month at all | D119 (interim) |
| R72 | A supplier return could pay down the wrong supplier's balance | D120 |
| R73 | Units-per-pack of 0 invoiced the customer and moved no stock | D120 |
| R74 | A stock count applied its variance to figures that had already changed | D120 |
| R75 | Reports left out delivery charges and document discounts, so they disagreed with the invoices | D120 |
| R76 | Opening stock booked a carton price as a tablet price — twelve times over | D120 |
| R77 | Settling a discounted consignment issue billed the undiscounted price | D120 |
| R78 | Django one security release behind | D120 |
| R69 | The documented backup could not run and the restore reported success without your attachments | D120 |

**R70 is the one this batch introduced.** It is the reason the old "ready to
tag" was not merely optimistic but unsafe.

## What is fixed but not proven

**R69 — the backup and restore scripts have never been executed.** There is no
Windows host here, so I have fixed them as code and that is all I can honestly
claim. The backup now reads `NARCOS_BACKUP_ROOT` from the same `.env` Compose
reads (before, PowerShell never saw it and the first scheduled run threw before
touching the database). The restore now starts the container the media step
needs and fails loudly instead of printing "Restored" with no attachments.

This is settled by a drill on the client machine and by nothing else.

**R71 — the guard is interim.** There is now a *Books closed through* date in
Settings, empty by default. Once you set it, documents dated on or before it
cannot be voided or corrected. It stops a closed month being rewritten. It does
**not** make reports show a void as a dated reversal — that is real reporting
work, deferred.

## Deliberately not done — your instruction

No reconciliation of data already on the client machine. Ten of these twelve
have been live, so rows written under the old behaviour may be wrong: most
plausibly opening-stock lot costs, referenced return values, invoice open
balances, and any stock count posted while trading continued.

Your call was to fix and deploy first, then write a script that checks the live
data for each mistake and reports what it finds. That script is **not written
yet** — it is the next piece of work after this ships. Little has been entered
and several of these workflows the client has not touched, so the exposure is
expected to be small. Expected, not measured.

## Where the numbers stand

- `build` is **33 commits ahead of `v1.0.0`** — the old file said 29.
- Nothing from this round is committed. `git status` shows 22 modified files
  and one new migration (`core.0008`, the closed-through date). Say the word
  and I will commit it.
- The client image is built by the `v*` tag, so a tag is what ships this.

## Recommended next steps

1. Read D116 and D119 — those two change how the app behaves for you, not just
   internally. A correction can now be refused, and the closed-through date is
   a new lever you own.
2. Hard-refresh and walk `ops/MANUAL-TESTING.md`.
3. **Run the restore drill on the Windows host.** R69 stays unproven until you
   do, and it is the one finding whose failure mode is losing everything.
4. Commit, then tag.
5. Then the data-checking script.

## Still yours, unchanged

Company phone still blank in Settings · negative-balance policy still
"Allowed" · UPS + backup drive · R43 parallel run · R40 accountant confirms the
3% base and the 20,000/10,000 thresholds · R39 legal form → withholding
switches.

**Watch, deliberately not queued:** R46 per-customer price lists · R8b
master-data merge · R9 broader returns · R55 recurring · R64 zero-total sale ·
R65 pack rounding · R66 remittance timing.
