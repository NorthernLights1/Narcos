# Status

Dear Temesgen,

Working state of `build` as of 2026-08-03 (late). The entire outstanding
queue you greenlit — the seven decided improvements, R53 and R49 — is
**built, tested and committed** (`f2ae659`, `099b84f`, `e997e30`).
Local `build` is four commits ahead of `origin/build`; nothing is pushed.

## Nothing is blocked on you

Both open questions you answered today are honoured: R53 became a
**storeroom picking list** (D107), and R49 was built to the agreed scope
(D108, full `ItemForm`, receiving only).

## The server is up

`http://127.0.0.1:8000` answers (302 → login, correct when signed out).
**Hard-refresh the browser** — app.js changed (`?v=20260803a`), and the new
receiving dialog misbehaves on cached assets.

## What was implemented — Round 17 (2026-08-03)

| Ref | Req | Change |
|-----|-----|--------|
| D102 | R48a/R48b/R51 | Items read **generic-first everywhere**: `CODE — Generic (Brand)` in every dropdown and refusal message; Generic name column on the items list (headers now use verbose names); attachment prints `Generic (Brand), Strength, Dosage` |
| D103 | R50 | Generic printout: **Prepared By** (`created_by`) + ruled signature line, `break-inside: avoid`; no stamp box, no Received By |
| D104 | R52 | `due_date` labelled **"Payment due date"** (state-only migration `docs.0009`, applied) |
| D105 | R54 | Draft lines show **"Net (preview)"** — `qty × price − discount`, display-only |
| D106 | R56 | Reference form runs through `fields_hidden_by_settings()` — machine-total box now hides there too |
| D107 | R53 | **Picking list** print for sales/proformas/consignment issues, drafts included: item, batch, shelf/bin, qty, tick boxes, "Picked by" line — **no prices, no number** |
| D108 | R49 | **+ New item** on the Receiving lines card: full `ItemForm` in a dialog (D67 auto-code, D81 price rules, D33 margins, audited); the created item is injected into every picker and selected on an empty row |

Tests: 7 new test files (~25 new tests) covering every item above. The
comment guard you requested caught one multi-line template comment I wrote
in `form.html` — converted to `{% comment %}`; the guard works.

Docs updated: `02-decisions.md` Round 17 (D102–D108), `03-open-risks.md`
(R48–R54 and R56 flipped to RESOLVED), `ops/MANUAL-TESTING.md` dated note
with a verification walk-through for the receiving dialog.

## What is left

### Next build queue — R57–R60 (your round-4 feedback, recorded, NOT built)

| Ref | Request | Note |
|-----|---------|------|
| R57 | Item picking wider on wide screens | Page capped at 72rem, item column at 14rem — CSS change + rebuild |
| R58 | Printouts carry dosage form, strength, base unit, pack description | *Open:* which layouts — all three assumed |
| R59 | Items VAT-exempt by default | One default flip + migration. *Open:* flat, or DRUG-only? |
| R60 | Base unit as a combobox | Today a datalist nobody discovers; wanted a visible dropdown that still takes typed units |

Say "build R57–R60" (and answer the two *Open* points) when ready.

### Yours
- **Hard-refresh and try the receiving dialog**: new receiving → *+ New
  item* → save with name + price only → it must get an auto code and land
  selected on an empty line. Also print a draft sale — the Picking list
  button is next to Edit.
- Push when satisfied — say "sync".
- Company phone still blank in Settings; negative-balance position still on
  the default "Allowed".

### Client-side / ops (unchanged)
- UPS + backup drive purchase · R43 parallel run · R40 accountant confirms
  the 3% base and 20,000/10,000 thresholds · R39 legal form → withholding
  switches · cut a `v*` tag to ship.

### Watch (deliberately not queued)
R46 per-customer price lists · R8b master-data merge · R9 broader returns ·
R55 (editable posted documents) recurring.

## Environment

- Migrations on the dev DB: through `core.0006` and `docs.0009`.
- Server restarted after the changes; asset cache-buster `?v=20260803a`.
- `master` stays behind by decision (2026-08-02); the GHCR pipeline fires on
  `v*` tags only.

## Recommended next steps

1. Hard-refresh, then walk the D102–D108 items with the MANUAL-TESTING note.
2. Say "sync" to push the round.
3. Cut a `v*` tag when the client should receive this build.
