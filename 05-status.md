# Status

Dear Temesgen,

Working state of `build` as of 2026-08-04. Two rounds landed back to back:
**Round 17** (the queue you greenlit — D102–D108) and **Round 18** (your
four field comments, built the same day you answered the open questions —
D109–D112). Everything is tested; Round 18's commits follow the suite run
now finishing. Nothing is pushed yet.

## Nothing is blocked on you

All your answers are honoured: R53 = storeroom picking list, R49 scope as
agreed, R57 container widened too, R58 on all layouts with grid separators,
R59 on drugs only, R60 combobox.

## The server is up

`http://127.0.0.1:8000` answers. **Hard-refresh** — both app.css and app.js
changed (`?v=20260804a`).

## What was implemented

### Round 17 (2026-08-03, commits `f2ae659`/`099b84f`/`276c610`)
| Ref | Req | Change |
|-----|-----|--------|
| D102 | R48a/b, R51 | Generic-first item naming everywhere; Generic column on items list; attachment reads `Generic (Brand), …` |
| D103 | R50 | Prepared By + signature line on the generic printout |
| D104 | R52 | "Payment due date" label (migration `docs.0009`) |
| D105 | R54 | Drafts show per-line "Net (preview)" |
| D106 | R56 | Reference form obeys the fiscal-machine switch |
| D107 | R53 | Picking-list print for the storeroom — no prices, drafts included |
| D108 | R49 | + New item dialog on Receiving, full ItemForm, audited |

### Round 18 (2026-08-04, committing now)
| Ref | Req | Change |
|-----|-----|--------|
| D109 | R57 | Entry pages use the full screen width; item picker column 14→22rem |
| D110 | R58 | `Item.full_description` (generic (brand), strength, dosage, unit, pack) on all three print layouts; full grid borders on generic + picking list |
| D111 | R59 | VAT exempt starts ticked and follows the category (DRUG on, others off) until touched; no migration, existing items untouched |
| D112 | R60 | Base unit is a dropdown of common units + "Other — type it below"; typed unit saved verbatim, custom units rejoin the list on edit |

Verified: 1920px screenshot of the receiving form (fills the width), and
~46 tests across the two rounds, full suite green.

## What is left

### Yours
- Hard-refresh and walk the 2026-08-04 note in `ops/MANUAL-TESTING.md`.
- Say "sync" to push — local `build` is several commits ahead of origin.
- Company phone still blank in Settings; negative-balance position still
  "Allowed".

### Client-side / ops (unchanged)
- UPS + backup drive · R43 parallel run · R40 accountant confirms the 3%
  base and 20,000/10,000 thresholds · R39 legal form → withholding
  switches · cut a `v*` tag to ship.

### Watch (deliberately not queued)
R46 per-customer price lists · R8b master-data merge · R9 broader returns ·
R55 recurring.

## Environment

- Migrations on the dev DB: through `core.0006` and `docs.0009`.
- Assets rebuilt (`build_css.sh`); cache-buster `?v=20260804a`.
- `master` stays behind by decision; the GHCR pipeline fires on `v*` tags.

## Recommended next steps

1. Hard-refresh, test both rounds.
2. "sync" to push.
3. Cut a `v*` tag when the client should receive this build.
