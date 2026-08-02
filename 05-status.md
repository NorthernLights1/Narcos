# Status

Dear Temesgen,

Working state of `build` as of 2026-07-30. Everything committed is pushed;
this file is the only uncommitted change.

## Nothing is blocked on you

All four open questions were answered 2026-07-30:

| Question | Answer | State |
|---|---|---|
| Multi-invoice receipt | Never allow it — one invoice, one receipt | **built (D94)** |
| Medicine dropdowns (R48b) | Generic name first, brand second | queued |
| "Add new item" pop-up (R49) | The full item form, all fields | queued |
| Draft printing (R53) | Dropped | closed |

The money bug is **fixed and pushed** (D94/D95). Measured before: sale 200 →
owes 200; payment 200 → owes 0; void → **owes −200**. After: **0**.

## Queued — next batch, no decisions outstanding

1. Generic name before brand: item dropdowns (R48b), Cash Sales Attachment
   line text (R51), Generic name column on the Items list (R48a).
2. **Second phone number** in Settings, printing alongside the first.
3. Prepared By (`created_by` full name) + signature line on the generic
   printout (R50).
4. `due_date` label → "Payment Due Date" (R52).
5. Per-line price/net on saved drafts, display-only (R54).
6. Add-item pop-up carrying the whole item form (R49) — largest; reuses the
   D93 dialog machinery.

## Shipped

| Ref | Change | Remote |
|-----|--------|--------|
| D84 | `free_qty` off receiving form + detail table | pushed |
| D85 | Printout totals moved below the lines | pushed |
| D86 | Cleared payment amount no longer blocks save | pushed |
| D87 | Payment lines default to one row | pushed |
| D88 | Row delete is a ✕ button, not a checkbox | pushed |
| D89 | 4 settings flags: fiscal machine, discounts, factor, editable sale price | pushed |
| D90 | "Correct this document" (void + prefilled draft) | pushed |
| D91 | Company phone on all print layouts | pushed |
| R47–R55 | Round-3 client feedback logged in `03-open-risks.md` | pushed |
| D92 | Void deferred to posting time; correcting is now reversible | pushed |
| D93 | Confirm dialogs on Correct / Post-correction / Void | pushed |

All of the above is on GitHub. `build` and `origin/build` both at `262b230`.

`master` is behind and **staying** that way by decision (2026-08-02). Nothing
deploys from it — the GHCR pipeline fires on `v*` tags only — so merging would
plant a rollback marker that a single-developer, single-branch repo has no use
for. The checkpoint that matters is the version tag, cut when the client is
meant to receive a new build. Not to be raised again.

## Environment

- Dev server up on `:8000`, `--noreload`.
- Migrations applied to dev DB: `core.0005` (settings flags), `docs.0008` (`corrects`, `correction_reason`).
- Full suite green.
- Asset cache-buster at `?v=20260728a` — **browsers need a hard refresh** for D88/D93 to behave.
- Company phone is still blank in Settings; fill it or D91 prints nothing.

## Decided 2026-07-30 — voiding a paid invoice

Temesgen: **do not block it.** Show a large warning, require an explicit
confirmation (not a single tap), and **reverse the money** as part of the void.

Investigation result: `void()` already cascades — `posting.py:264-271` voids any
posted `CUSTOMER_PAYMENT` / `SUPPLIER_PAYMENT` / `ADJUSTMENT` whose
`related_document` points at the document being voided. That covers
system-generated payments (cash sale → auto receipt, stock count → auto
adjustment).

The gap is payments linked by **`PaymentAllocation`** rather than by
`related_document` — a receipt the user entered and applied to the invoice.
Those are not cascaded, which is why the customer is left at −200.00 with a
dangling allocation. The fix extends the existing cascade to allocation-linked
payments; the machinery and the pattern already exist.

**Open sub-decision:** one receipt may settle several invoices. Cascading it
un-settles the others too. Plan is to proceed anyway and name every affected
invoice in the warning rather than refuse. Awaiting confirmation.

## Defect found, not fixed

`check_voidable` is overridden on **3 of ~15 handlers** (receiving, auto-adjustment, auto-payment). Default is *allow*.

Probed and confirmed: voiding a fully-allocated credit sale is permitted and leaves the customer at **−200.00** (credit balance) with the `PaymentAllocation` still pointing at the voided invoice. Pre-existing, not introduced by D92 — but D92 routes a common workflow (correcting an already-paid sale) straight through it. Same dangling-reference shape exists for consignment issue↔settlement and sale↔customer return.

Stock is protected by the no-negative CHECK constraint; money and party balances have no equivalent backstop.

## Backlog — R47–R55

**Specified, ready to build:**
- R50 — Prepared By (`created_by` full name) + signature line on the generic printout
- R51 — Generic name before brand on the Cash Sales Attachment
- R52 — `due_date` label → "Payment Due Date"
- R48a — Generic name column on the items list
- R54 — Per-line price/net on saved drafts (display-only, labelled preview)

**All answered 2026-07-30.** R48b → generic first, brand second. R49 → the
full item form. R53 → dropped. The multi-invoice receipt question → never
allowed, built as D94.

## Recommended next steps

1. **Build the queued batch** (items 1–5 above) — one sitting.
2. **Then the add-item pop-up** (R49) on its own.
3. **Probe the remaining void shapes.** D95 fixed invoice↔payment. Consignment
   issue↔settlement and sale↔customer return have the same separate-document
   structure and have *not* been checked for equivalent dangling references.
   Same method: build it in a rolled-back transaction and read the balances.
4. **Cut a `v*` tag** when the client is meant to receive a new build — that,
   not a branch merge, is what ships an image to their machine.
