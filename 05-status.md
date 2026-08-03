# Status

Dear Temesgen,

Working state of `build` as of 2026-08-03. Local `build` is at `a679aa7`,
one commit ahead of `origin/build` — **not pushed yet**. This file is the only
uncommitted change.

## One thing is blocked on you

**Can a cash or bank account go negative?** Probed today: it already can, two
ways. Posting an expense of 4000 against an empty drawer succeeds and leaves
cash at **−4000.00** — `_write_money` (`docs/posting.py:133`) writes ledger
rows with no balance check at all. Voiding an opening-cash document after the
money was spent does the same. Stock has a DB CHECK constraint that makes this
impossible; money has nothing.

I did **not** fix it, because the fix depends on your answer and the wrong
choice blocks legitimate work:

- **If cash may never go negative:** the guard belongs at posting time, and
  staff will be stopped from recording a payment before the opening balance is
  entered or the drawer is counted.
- **If it may go negative:** nothing to build; a negative balance is a signal
  to go and count, and the Finance page should show it in red.

Related but separate: the same hole in the *withholding* bucket **was** fixed
today (D99), because the codebase already declared that bucket must never go
negative — the remittance form has refused to over-remit since D52. Money has
no such existing rule, so fixing it would be inventing policy.

Everything else from 2026-07-30 is answered and built.

## What was implemented

### Round 14 (2026-08-02)
| Ref | Change |
|-----|--------|
| D92 | Void deferred to posting time; correcting is reversible |
| D93 | Confirm dialogs on Correct / Post-correction / Void |
| D94 | One payment settles exactly one invoice |
| D95 | Voiding a document reverses the payment that settled it |

### Round 15 (2026-08-02)
| Ref | Change |
|-----|--------|
| D96 | Voiding a sale reverses its customer return (was corrupting **stock**, not just money) |
| D97 | A settled consignment issue refuses the void in words that explain it |
| D98 | Void and post-correction dialogs are over-explained and type-gated |

Measured on the original bug: sale 200 → owes 200; payment 200 → owes 0;
void → **owes −200**. After D95: **0**. The return case (D96) was worse — the
warehouse gained two packs that never existed. After D96: balance 0, warehouse
unchanged.

### Round 16 (2026-08-03, commit `a679aa7`)
| Ref | Change |
|-----|--------|
| D99 | A payment cannot be voided once its withholding was remitted |
| D100 | Refusals name the medicine and the documents, not row ids |
| — | Two tests that were failing at `499cfbf` now pass |

Earlier rounds D84–D91 remain as previously reported, all pushed.

## What is left

### Bug fixes — the void sweep is finished

All three shapes flagged this morning were probed. Results:

1. **Withholding ↔ remittance — real, fixed (D99).** Measured: pay a 1000
   receiving as 970 cash + 30 withheld, remit the 30, then void the payment →
   **PAYABLE −30.00**, money already gone to the tax office. Now refused, in
   both the direct and the cascade path, naming the remittance to void first.
2. **Opening documents — clean.** Voiding an opening AR settled by a receipt
   lands the customer at 0.00 and returns the cash (the D95 cascade does it).
   Voiding opening stock after a sale is correctly refused by the D4 rule.
   No change needed.
3. **Wording — fixed (D100).** The shortfall message said "item 10 lot 12 in
   WAREHOUSE"; it now reads *"AMOX — Amoxicillin, batch B-1 in Warehouse
   (have 15, need 20)"*, and because it comes from the engine, every stock
   refusal in the app improved. The receiving message now names the documents
   that took the goods instead of advising a supplier return when a supplier
   return is what took them.

**Found while probing, not fixed:** money accounts can go negative — see the
question at the top of this file.

**Also found:** `499cfbf` shipped with two failing tests. D98 changed the
dialog titles and the D93 assertions were never updated, so the "full suite
green" line in the 2026-07-30 status was wrong. Fixed in `a679aa7`; the suite
is genuinely green now.

### Feature improvements — decided, ready to build

| Ref | Change | Where |
|-----|--------|-------|
| R48b | Generic name first in every item dropdown | `Item.__str__`, `catalog/models.py:100` |
| R48a | Generic name column on the items list | items list template |
| R51 | Generic before brand on the Cash Sales Attachment | `templates/docs/print_sales_attachment.html` |
| R50 | Prepared By (`created_by`) + signature line, `break-inside: avoid` | `templates/docs/print.html` — has no signature markup at all |
| R52 | `due_date` label → "Payment Due Date" | `docs/models.py:81`, no `verbose_name` today |
| R54 | Per-line net on saved drafts, display-only, labelled preview | `line_net` is frozen at posting |

**Second phone number — likely nothing to build.** `CompanySettings.phone` is
already a single free-text field labelled "Phone numbers", 100 characters,
printed verbatim on both layouts (`core/models.py:53`). Two numbers can be
typed into it today. Only worth a schema change if you want them as separate,
separately-labelled fields.

### New features

- **R49 — add an item without leaving Receiving.** A modal on the line row that
  runs the full `ItemForm` and drops the new item into the picker. The largest
  remaining item; reuses the D93 dialog machinery. Must not be a simplified
  parallel form, or D81 and the D67 auto-code rules get bypassed.
- `WATCH`, deliberately not queued: R46 per-customer price lists, R8b master
  data merge, R9 broader returns, R55 (editable posted documents) recurring.

### Ops — code side is done

R10 (password recovery), R11 (`TIME_ZONE = "Africa/Addis_Ababa"`,
`narcos/settings.py:117`), R44 (update procedure) and R45 (localhost DB
binding, static IP, secrets) are all built into `ops/RUNBOOK.md` and settings.
What remains is not code:

- UPS + backup drive — the client's purchase, before go-live.
- R43 — 2–4 week parallel run against the old process.
- R40 — accountant confirms the 3% base and the 20,000 / 10,000 thresholds.
- R39 — ask the client's legal form, then set the two withholding switches.

## Environment

- Migrations on the dev DB: `core.0005` (settings flags), `docs.0008`
  (`corrects`, `correction_reason`).
- Full suite green.
- Asset cache-buster — **hard refresh** the browser or D88/D93/D98 misbehave.
- Company phone is still blank in Settings; fill it or D91 prints nothing.

`master` stays behind by decision (2026-08-02) — nothing deploys from it, the
GHCR pipeline fires on `v*` tags only. Not to be raised again.

## Recommended next steps

1. **Answer the negative-money question** at the top — one sentence unblocks it.
2. **Build the six-item improvement batch** (R48a/R48b/R50/R51/R52/R54) in one
   sitting — they are small, all decided, and R48b/R51 must land together so
   the wording agrees everywhere.
3. **Then R49** on its own.
4. **Cut a `v*` tag** when the client is meant to receive this build. That, not
   a branch merge, is what ships an image to their machine.

Say "commit and sync" when you want `a679aa7` on GitHub.
