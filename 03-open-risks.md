# Open Risks & Blind Spots

Status: `OPEN` (needs a decision), `TO BUILD` (decided, not built yet), `WATCH`
(future, don't block it), `RESOLVED` (in [02-decisions.md](02-decisions.md)),
`DROPPED`/`DEFERRED` (out of v1).

**As of 2026-07-28 (client field testing):** the build is in the client's
hands and real use has reopened a short list of questions — see
[round 3 below](#new--client-field-testing-round-3-2026-07-28) (R47–R55).
Rounds 1 and 2 of that feedback are already built and logged as D84–D91.

**As of 2026-07-03 (after round 7):** every design question is closed. Tax
settled (D50–D54) · stack locked (D55: Django + **PostgreSQL 16** + HTMX/Alpine +
Tailwind — D66 confirms PostgreSQL after D65 amendment) · owner's closing answers
landed as D56–D63, including **D62 (unit conversion kept — D58 reversed)** and
**D63 (input VAT confirmed not modeled — R34 closed)**. Ops/build items:
`TO BUILD` (R10, R11 — UPS/backup-drive purchase is the client's to make, R44, R45).
`WATCH` (R9, R8b, R40, R46).
**Go-live checklist:** R39 legal form per client → set withholding switches ·
R43 parallel run · printer confirmed owned ✓ · UPS + backup drive to be bought
by client before go-live. **The buildable spec exists:**
[04-build-spec.md](04-build-spec.md) (from D1–D66, incl. the R25 revival fixed
by D64). R38's "carry units into the buildable spec" is done (spec §3.2/D62).
**Next step: build phase P0.1 (Postgres setup) → P1–P10.**

---

## Resolved — round 1

R1→D18 (fiscal machine) · R2→D19 (fiscal year) · R3→D24 (withholding — *removed
by D45, then reinstated at 3% by D51/D52*) · R4→D20 (discounts) · R5→D21 (bonus
goods) · R6→D22 (no expiry) · R7→D25 (credit limit) · R8→D26 (dup prevention) ·
R12→D27 (count freeze) · R13→D23 (pricing).

## Resolved — round 2

R14→D30 (VAT-exempt — *deferred by D45, then reinstated by D50*) · R15→D31
(VAT-exclusive) ·
R16→D32 (VAT-on-total rounding) · R17→D33 (hide cost/profit) · R18→D34 (low-stock
alert) · R19b→D35 (cash close — ***not built in v1, D49***) · R20→D36 (CSV) ·
R24→D37 (sales extra charges).

## Resolved — round 3

- **R25 — discount allocation on mixed VAT/exempt** → moot per **D45** — *but
  D50 (round 4) un-mooted it by bringing exempt items back. Re-resolved by
  **D64** (round 6): invoice-level discounts allocate pro-rata across line nets
  before the taxable/exempt bases are computed.*
- **R26 — customer-side withholding** → **D45** (removed) — *then reinstated at
  3% by D51 in round 4.*
- **R27 — opening consignment / expired / unfit** → **D39**.
- **R28 — manufacturer batch vs cost lot** → **D40**.
- **R29 — returns (customer + supplier)** → **D41** (minimal workflow in v1).
- **R30 — employee receiving vs hidden cost** → **D42**.
- **R31 — clock trust + audit** → **D47** (keeps system-time dating; no backdating).
- **R32 — fiscal-machine reconciliation** → **D43**.
- **R33 — payment edge cases** → **D44** (partial yes; advances/overpay/write-off
  deferred).
- **R34 — purchase input VAT** → ~~TABLED~~ **RESOLVED by D63 (round 6)**:
  owner confirmed purchases are VAT-exempt medical goods, so input VAT is not
  modeled; stock cost = entered goods cost. If a taxable purchase ever occurs
  (equipment), the entered cost is what was paid; reclaim is the accountant's.
- **R35 — expired/near-expiry sale rule** → **D46** (block expired, warn near).
- **R36 — backup retention / encryption / restore owner** → **D48**.
- **R37 — immutable audit coverage** → **D47**.
- **R38 — units of measure / pack conversion** → not a gap; the model exists in
  the original spec. **Action: carry it into the buildable spec** so it isn't lost.
  *(Round 5: D58 briefly removed unit conversion; **round 6: D62 reversed that
  same day — the conversion model is kept**, base unit + fixed-factor alternate
  units, so the original action stands.)*

---

## Deferred / dropped from v1

- ~~**VAT-exempt items (R14/D30)** → DEFERRED by D45~~ → **REINSTATED in v1 by
  D50** (round 4 — client + law confirmed medicines are exempt).
- ~~**Withholding tax (R3/R26/D24)** → REMOVED by D45~~ → **REINSTATED in v1 by
  D51/D52** (round 4 — at 3%, optional both directions).
- **Depreciation/write-off display (D16)** → DEFERRED by D49 (basic asset
  recording + consumable expensing stays). *(confirmed)*
- **Print-template editor (D17)** → DEFERRED by D49 (selectable built-ins in v1).
- **Daily cash close (D35)** → NOT BUILT in v1 (D49).
- **Period locking (R21)** → DROPPED by D38 (system-time dating).
- **R22 free samples**, **R23 customer statements**, **advances / overpayments /
  write-offs** → out of v1. (**R34** is *tabled*, not dropped — see above.)

---

## Open / new — round 4 (2026-07-02)

### R39 — Is the client's own business a withholding agent? — `RESOLVED` (→ D54)
Ethiopian law makes **"bodies"** (PLCs, share companies, government, NGOs) and
*specified large sole proprietors* withhold 3% when **they pay** suppliers.
**D54** made this a non-question for the design: legal form is never modeled or
assumed — withholding behavior comes entirely from the D51/D52 settings, so the
same build serves a PLC or a sole proprietorship. What remains is a **go-live
checklist item per client**: ask their legal form (and whether the tax office
designated them a withholding agent), then set the two switches.

### R40 — Withholding fine print — `WATCH`
Confirm with the accountant before go-live (all are help-text/config issues,
not structural): (a) the 3% base is the **VAT-exclusive** amount — assumed in
D51/D52; (b) current thresholds — ETB **20,000** goods / **10,000** services
per transaction (Proclamation 1395/2025); (c) whether any government customers
also withhold **VAT itself** under the new VAT law — if so, that's a separate
mechanism we have deliberately **not** modeled; the fiscal machine / accountant
handles it (same boundary as D18).

---

## New — round 5 (2026-07-02, pre-build pitfall review)

### R41 — UI language — `RESOLVED` (→ D56)
Owner: **English only for now**, with Tigrigna and Amharic as possible later
additions. D56 locks the cheap-now/expensive-later part: every string wrapped
for translation from day one, so later languages are translation files, not
code. Verify print layouts render Ethiopic fonts once during the build.

### R42 — Go-live data entry vs import tooling — `RESOLVED` (→ D57)
Owner agreed: **owner-only CSV import** for items, customers, suppliers,
opening stock (batch + expiry) and opening invoices ships in v1. Reused for
every future client (D54).

### R43 — Parallel run at go-live — `RESOLVED` (policy agreed 2026-07-02)
Owner agreed: run the old process (paper/Excel) alongside Narcos for
**2–4 weeks**, reconciling cash + stock daily. Lives on the go-live checklist —
costs discipline, not code.

### R44 — Updating a live system — `TO BUILD` (ops runbook; owner agreed)
After go-live, every code update and schema migration hits real money data on
one PC. Rule: **restore the latest backup to a scratch copy and run the
migration there first**, then apply to live. Pin dependency versions. Document
the update procedure next to the backup/restore runbook (D13/D48).

### R45 — LAN security basics — `TO BUILD` (ops; owner agreed)
Deployment note from the owner: **v1 likely starts on a single PC** — LAN is a
future expansion. The rules below cost nothing now and matter from day one
anyway (especially the first):
- **Database bound to localhost only** — browsers talk to the app, never the
  DB. Otherwise D33 (employees can't see cost/margin) is defeated by anyone
  with the DB password.
- **Static IP / hostname for the server PC** — do this when the LAN arrives so
  client browsers don't break when DHCP reshuffles addresses.
- Strong unique DB password + app secret key; keep them out of source control.
  HTTPS optional on a closed LAN (self-signed if wanted); revisit before any
  internet exposure.

---

## Watch (future, don't block it now)

### R9 — Free-form / broader returns — `WATCH`
D41 brings the **minimal** customer + supplier returns into v1. Broader cases
(complex partial-credit, return-to-different-batch nuances) stay out; don't block
them.

### R8b — Master-data merge tool — `WATCH`
Deferred from D26. Build only if duplicates become a real problem; must respect
the never-erase rule.

### R46 — Per-customer standing price lists — `WATCH`
Owner asked if this can wait: **yes**. A customer×item price table + a default
lookup at sale entry is purely **additive** — it touches no posted documents,
costing, or history. D23 (maintained price, editable per sale) + D20 discounts
cover today. Build if/when the client asks.

---

## To build (decided ops items, not design questions)

### R10 — Owner password recovery — `TO BUILD`
On-prem, no email reset. Document an admin recovery procedure (superuser/CLI
reset) so the owner can't be locked out.

### R11 — Timezone & power — `TO BUILD`
Set the server clock to **Africa/Addis_Ababa** (and audit clock changes — D47).
Budget for a **small UPS** so power cuts don't lose half-typed forms.

---

## Build-ready decision set (all decided)

[02-decisions.md](02-decisions.md): D1–D66. Round 3 added D39 opening
consignment · D40 batch + cost lots · D41 minimal returns · D42 receiving sees
cost · D43 fiscal reconciliation · D44 partial payments · D45 VAT simplified
(*largely undone by round 4*) · D46 expiry sale rule · D47 audit + clock · D48
backup retention · D49 v1 scope trims. Round 4 added D50 VAT-exempt reinstated ·
D51 withholding on sales (3%) · D52 withholding on purchases (3%, off by
default) · D53 withholding never touches revenue/profit · D54 legal form is
configuration, not code. Round 5 added D55 stack (Django + PostgreSQL + HTMX) ·
D56 English-only, translation-ready · D57 go-live CSV import · D58 one unit per
item (*superseded by D62*) · D59 near-expiry default 6 months · D60 consignment
term + reminders (2w/1w before 3 months) · D61 FEFO batch suggestion. Round 6
added D62 unit-conversion model kept · D63 input VAT confirmed not modeled.
Round 7 (2026-07-03) added D65 SQLite amendment (test scope) and D66 PostgreSQL
final (test-what-you-ship principle, multi-client product, postings must be
multi-user correct).

---

## New — client field testing, round 3 (2026-07-28)

Eight comments came back from the client after real use. Three of them are
still design questions; the rest are decided and waiting to be built.
All implemented: R47 shipped earlier (D89); the rest landed 2026-08-03 as D102–D108.

### R47 — Selling price editable on sales — `RESOLVED` (→ D89)
Already shipped: **Settings → "Sale price editable at the time of sale"**,
off by default because it reverses D80 (the CN-000002 lesson). Nothing to
build — the owner just ticks the box. Discounts remain the safer route.

### R48 — Items read by brand, not generic name — `RESOLVED` (→ D102)
`Item.name` holds the brand; `generic_name` is a separate field. Two
changes hide in one request:
- **Items list gains a Generic name column** — decided, `TO BUILD`. (It is
  already *searchable*, just not shown.)
- **Item pickers on document lines** — `OPEN`. `Item.__str__` is
  `"CODE — brand"` and drives **every dropdown in the app**, so switching
  to generic-first changes how every line on every form reads. Needs the
  owner's call before building.

### R49 — Create an item without leaving Receiving — `RESOLVED` (→ D108)
Staff must abandon a half-typed receiving to add an unknown item. Wanted:
a modal on the line row that creates the item and drops it into the
picker. **Must reuse `ItemForm`**, not a parallel simplified form, or D81
(every item needs a usable price) and the auto-code rules (D67) get
bypassed and half-formed items accumulate. `OPEN`: minimum fields in the
modal — proposed generic name, brand name, base unit, price.

### R50 — Prepared By + signature on the printout — `RESOLVED` (→ D103)
The **generic** layout (`print.html`, labelled "Attachment / not a fiscal
receipt", and the COMPACT default) has no signature markup at all; only
the Cash Sales Attachment layout does. Decided with the owner
(2026-07-28): print **Prepared By: <full name>** from the document's
**`created_by`** (matches the Cash Sales Attachment; "prepared" = who
entered it), with a ruled signature line beneath, at the bottom of the
page under the D85 totals. **No stamp box** (client to confirm later) and
**no Received By** for now. Block needs `break-inside: avoid` so a
multi-page print cannot split the name from its line.

### R51 — Generic name before brand on the attachment — `RESOLVED` (→ D102)
The Cash Sales Attachment prints `Brand (Generic), Strength, Dosage`; the
client reads generic-first. Flip to `Generic (Brand), …`. Do it together
with R48 so the wording agrees everywhere.

### R52 — "Due Date" → "Payment Due Date" — `RESOLVED` (→ D104)
`Document.due_date` carries no `verbose_name`, so Django auto-labels it
"Due date". The same field doubles as the supplier's credit terms on
receivings (feeds AP overdue) — "Payment due date" reads correctly for
both, so one label change covers it.

### R53 — Print a draft — `RESOLVED` (→ D107, picking list)
`document_print` accepts posted documents only; a draft 404s. Buildable,
but a draft **has no document number** (assigned at posting under gapless
rules, D8) and is not yet a record of anything — printed plain, someone
will hand it to a customer. Would need a loud **DRAFT** watermark (the D18
watermark machinery already exists) and no number where the number goes.
`OPEN`: is this a **picking list** for the storeroom or a **quote** for the
customer? A picking list wants its own layout, not a watermarked invoice.

### R54 — Price/net on a saved draft — `RESOLVED` (→ D105)
A saved draft already shows an **Expected totals** card (D67–D69), but the
per-line **Net** column reads 0.00 because `line_net` is frozen at posting
(※) and defaults to zero. Compute per-line net on the fly for drafts,
**display only**, clearly labelled as a preview — those figures can still
move at posting (tax allocation, master-price re-derivation under D80).

### R55 — Editable posted documents — `RESOLVED` (→ D90)
The client asked for a flag letting the owner edit anything on a posted
document. Refused as designed, and answered with D90 instead. The reason
in one line: **a posted document is the cause of ledger rows, not a record
of them** — editing it changes the paper and leaves the stock, money,
party and withholding ledgers (and the FIFO cost lots later sales already
consumed) saying something else, which no report would ever reconcile. The
guards in `Document.save()`, `PaymentLine.save()` and the lot-consumption
freeze are the warning, not the safety. Making editing safe means
reversing and re-applying every ledger row under the same locks and
balance checks — which is void + repost, i.e. exactly what **"Correct this
document" (D90)** now does in one click. A narrow set of ledger-free
fields is already editable and audited (`fiscal_receipt_no`,
`machine_total`, `withholding_certificate_no`); `notes` and `due_date`
could be added at low risk if the client asks. `WATCH` that request
recurring.

### R56 — Reference form ignored the fiscal-machine flag — `RESOLVED` (→ D106)
Found 2026-08-03: `DocumentReferenceForm` hardcoded its three fields, so
turning off *Fiscal machine present* (D89) left the machine-total box on the
posted-document Reference form. Now filtered through the same
`fields_hidden_by_settings()` as the entry forms.

---

## New — client field testing, round 4 (2026-08-04)

Four comments from Temesgen after using the round-17 build. Recorded first
per his instruction; **all built 2026-08-04 as D109–D112** once he answered
the open questions.

### R57 — Item picking too narrow on wide screens — `RESOLVED` (→ D109)
The page body is capped (`.page { max-width: 72rem }`) and the line-table
item picker at `.table-input .choices { min-width: 14rem }` — on a wide
monitor most of the screen is empty margin while long generic-first names
truncate. Widen the document form page and give the Item column the freed
space. Needs `scripts/build_css.sh` + cache-buster bump.

### R58 — Printouts should carry the full item description — `RESOLVED` (→ D110, all layouts + grid)
Wanted on printing: **dosage form, strength, base unit, pack description**.
Today: the Cash Sales Attachment prints strength + dosage but not pack
description (unit of measure column shows the line's unit label); the
generic layout and the picking list print only `CODE — Generic (Brand)`.
*Open:* which layouts — assume all three unless he narrows it.

### R59 — Items VAT-exempt by default — `RESOLVED` (→ D111, drugs only)
`Item.vat_exempt` defaults False; medicines are VAT-exempt by law (the help
text already says so) and this trade is a pharmaceutical wholesaler, so
staff must tick the box on nearly every item. Flip the default to True
(migration; existing items untouched). *Open:* flat default, or per
category (DRUG exempt, EQUIPMENT/SUPPLY not)?

### R60 — Base unit should be a combobox — `RESOLVED` (→ D112)
The base-unit box is a text input with a `datalist` of common units — the
suggestions only appear once you click/type, so nobody finds them. Wanted:
a visible dropdown (common units) that still allows a typed custom unit.
Applies to Master → Items and the R49 dialog alike.

---

## New — round 5 (2026-08-05)

### R61 — Edit posted fields where they are, not on a page — `RESOLVED` (→ D114)
"Instead of a dedicated reference field I want to place small edit next to
the fields that can be edited." Scope settled in conversation: a pencil on
every low-risk editable field, which added `notes` and `due_date` to the
three §7.12 reference fields.

### R62 — Expiry correctable without voiding — `DECLINED` (2026-08-05)
Offered as a setting; Temesgen declined it for now. The analysis is kept in
the D114 entry of [02-decisions.md](02-decisions.md) — including the trap
that a wrong expiry can currently be uncorrectable once its stock is partly
sold. Revisit only if that bites in practice.
