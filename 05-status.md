# Status

Dear Temesgen,

Working state of `build` as of 2026-08-03. `build` and `origin/build` are both
at `499cfbf`; the working tree is clean and this file is the only change.

## Nothing is blocked on you

All questions from 2026-07-30 are answered and the two that needed building are
built. The open sub-decision from that day — *what happens when one receipt
settles several invoices* — was closed by making it impossible (D94).

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

Earlier rounds D84–D91 remain as previously reported, all pushed.

## What is left

### Bug fixes — no open reproduction, but unprobed surface

D95/D96/D97 closed every void pair that was actually probed. Three shapes have
**not** been checked:

1. **Sale ↔ WHT remittance.** `WhtRemittanceHandler` has no `check_voidable`,
   and `WHT_REMITTANCE` is not in the `related_document` cascade
   (`docs/posting.py:264-277`). Voiding a sale whose withholding was already
   remitted reverses the sale's `WithholdingLedger` rows and leaves the
   remittance standing. Structurally identical to the D95 bug.
2. **Opening documents.** Voiding an opening stock / opening AR after later
   transactions consumed it. No handler override; the default is *allow*.
3. **Wording, D97 class.** Voiding a receiving after a supplier return is
   correctly blocked, but the message reads "goods were already sold or moved"
   (`docs/handlers.py:178-191`). Right answer, wrong words.

Method for all three is the one that worked twice: build the scenario in a
rolled-back transaction and read the balances.

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

1. **Build the six-item improvement batch** (R48a/R48b/R50/R51/R52/R54) in one
   sitting — they are small, all decided, and R48b/R51 must land together so
   the wording agrees everywhere.
2. **Probe the three remaining void shapes**, WHT remittance first — it is the
   one with real money behind it.
3. **Then R49** on its own.
4. **Cut a `v*` tag** when the client is meant to receive this build. That, not
   a branch merge, is what ships an image to their machine.
