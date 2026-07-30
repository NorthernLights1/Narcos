# Status

Dear Temesgen,

Working state of `build` as of 2026-07-29.

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

All of the above is on GitHub. `build` and `origin/build` both at `3f88f65`.
`master` still sits at `caaf991` (D83) — it is the last client-validated
baseline, and D84–D93 have not been merged into it yet.

## Environment

- Dev server up on `:8000`, `--noreload`.
- Migrations applied to dev DB: `core.0005` (settings flags), `docs.0008` (`corrects`, `correction_reason`).
- Full suite green.
- Asset cache-buster at `?v=20260728a` — **browsers need a hard refresh** for D88/D93 to behave.
- Company phone is still blank in Settings; fill it or D91 prints nothing.

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

**Blocked on your decision:**
- R48b — Do item pickers switch to generic-first? Changes `Item.__str__`, affects every dropdown.
- R49 — Minimum fields in the inline "new item" modal. Must reuse `ItemForm` or D81/D67 get bypassed.
- R53 — Is draft printing a picking list or a customer quote? Decides watermarked-reuse vs. purpose-built layout.

## Recommended next steps

1. **Decide on the `check_voidable` guards.** Highest value is `SaleHandler`
   refusing when a posted allocation targets the invoice, message pointing at
   the payment to unallocate first. Follows the existing `_PaymentBase` /
   `AdjustmentHandler` pattern. Open sub-question: owner override, or hard
   block? *(In plain terms: should voiding an already-paid invoice be
   blocked?)*
2. **Batch the five ready items** — one round, roughly a session.
3. **Answer R48b / R49 / R53** so the remainder unblocks; R49 will reuse the
   D93 dialog machinery.
4. **Merge `build` → `master`** once the client validates this round, as with
   the previous one. Nothing deploys on merge — the GHCR pipeline fires on
   `v*` tags only.
