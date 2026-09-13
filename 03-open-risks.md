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

### R62 — Expiry correctable without voiding — `RESOLVED` (→ D121, 2026-08-08)
Declined on 2026-08-05, with the trap written down: a wrong expiry is
uncorrectable once its stock is partly sold, and the note said *"revisit only
if that bites in practice."* It bit on 2026-08-08 — batch EP241208S of
ITM-0032, typed 2026 for 2029, on an opening stock already sold from. Built as
[D121](02-decisions.md) to the shape that note specified: owner-only, a
mandatory reason, a two-step review naming every document that shares the
batch, and the change committed together with its audit row.

---

## From the pre-ship audit (2026-08-05)

### R63 — Fiscal receipt no ignored the fiscal-machine switch — `RESOLVED` (→ D115)
`fiscal_machine_present = False` hid the machine total but left the receipt
number on every entry form, on the printout, and (after R61) as a pencil on
posted documents. The number is printed *by* the machine, so it cannot
exist without one. Both halves of D18/D43 now follow the switch.

### R64 — A cash sale discounted to zero cannot post — `QUEUED` (2026-08-05)
Confirmed on the posting path. Discount a cash sale to 0.00 and the auto
payment (D3/D44) refuses it — *"Payment needs money lines or a withheld
amount"* — an error naming a document the user never created. Fails safely
inside the transaction; no data damage. Rare (giveaways booked as 100%
discount). *Temesgen, 2026-08-05: note it for next improvement, we'll
consider it then.* Likely shape: let a zero-total cash sale skip the auto
payment entirely, since there is no money to move.

### R65 — Pack-factor cost rounding — `NOT LIVE` (2026-08-05)
**Downgraded after checking the actual data.** Temesgen: *"I don't buy per
tablet, I buy per box — this is wholesale, so purchase is per pack."*
Confirmed in the working database: `unit_conversion_enabled` is already
**off**, every item's base unit is a whole item (`unit`, `pair`), and 36 of
38 document lines carry `factor = 1`. When the pack *is* the base unit the
division is exact and nothing is lost. The original finding assumed a
retail tablet-level breakdown that does not exist in this business.

Mechanism, kept for the record: [handlers.py:125](docs/handlers.py#L125)
divides what was paid by the number of base units and rounds to 2 dp, so
buying in a *larger* unit than the one sold loses the remainder. One dev
lot still shows it (400.00 paid, 399.00 booked) — a leftover from a
`factor = 100` test entry, not client data.

*Trigger to watch:* the day anyone buys an outer unit and sells the inner
one — a carton of 12 boxes, say — factor rises above 1 and the drift
returns. Fix then, not now: widen `CostLot.unit_cost` and
`DocumentLine.unit_cost_entered` from 2 dp to 4 dp.

### R66 — Remittance payable check runs outside the lock — `OPEN` (low)
`WhtRemittanceHandler.validate` reads the PAYABLE balance before
`NumberSequence.take` acquires the lock, and `build_effects` never
re-reads. `ExpenseHandler` re-checks under the lock for exactly this
reason. Two remittances posted in the same instant could take PAYABLE
negative — the corruption D99 guards against on the void path, unguarded
on the post path. Needs genuine concurrency on a one-till system, so
practically unreachable. Fix: move the balance check into
`build_effects`.

---

## New — joint whole-app audit, round 20 (2026-08-06)

The pre-ship audit above (R63–R66) examined **the 29-commit batch**. This round
examined **the whole application**, independently by Codex (GPT-5.6) and Claude,
with every finding traced in the code by both before it was written down.
R67–R78 correspond to the joint report's F1–F12.

**The headline:** ten of these twelve are present in `v1.0.0` — already in the
client's hands. Shipping the batch does not make them worse. **R70 is the
exception**: it is new, and it is the reason this batch must not be tagged as it
stands.

### R67 — Referenced customer returns are valued from current data — `RESOLVED` (→ D117)
A return matches its sale by item+batch only, then treats `matching[0]` as "the
original" ([handlers_sales.py:527-535](docs/handlers_sales.py#L527-L535)). Cost is
weighted across matching lines ([:596](docs/handlers_sales.py#L596)) while price
falls back to the first line ([:585](docs/handlers_sales.py#L585)) and only when
the submitted price is empty — so the prefilled *current* catalog price is
normally accepted. Tax is frozen at today's rate, not the sale's
`tax_rate_snapshot` ([models.py:101](docs/models.py#L101)). Negative
`line_discount` is unvalidated ([models.py:208](docs/models.py#L208)).
*Live now. In `v1.0.0`.* Fix needs a source-line reference on `DocumentLine`
(migration) and reconciliation of posted returns.

### R68 — Return credits never reduce the invoice's open balance — `RESOLVED` (→ D118)
`open_balance()` counts only `PaymentAllocation` rows
([handlers_payments.py:21-29](docs/handlers_payments.py#L21-L29)); a no-refund
return posts a party-ledger effect and no allocation
([handlers_sales.py:626](docs/handlers_sales.py#L626)). The customer's overall AR
drops but the returned invoice still reads fully open, so aging and payment
validation disagree with the ledger. *Live now. In `v1.0.0`.* Must land together
with R67 or the books stay contradictory.

### R69 — The documented backup/restore path cannot recover — `MITIGATED` (→ D120) — unverified until a drill on the Windows host
[DEPLOYMENT.md:53](ops/DEPLOYMENT.md#L53) puts `NARCOS_BACKUP_ROOT` in `.env`,
which Compose interpolates ([compose.yml:18](compose.yml#L18)) but PowerShell
never sees — so [docker-backup.ps1:12](ops/docker-backup.ps1#L12) throws at
[:15](ops/docker-backup.ps1#L15) on first run. Restore is worse: the header says
to bring up only `db` ([docker-restore.ps1:11](ops/docker-restore.ps1#L11)), yet
media restore runs `docker compose exec -T app`
([:40](ops/docker-restore.ps1#L40)) and treats failure as a warning
([:41](ops/docker-restore.ps1#L41)) before reporting success. *In `v1.0.0`.*
Settled only by a real drill on the Windows host, not by reading the scripts.

### R70 — Correction voids linked returns and receipts without recreating them — `RESOLVED` (→ D116)
**The one finding introduced by this batch.** `_duplicate_as_draft`
([views.py:549-589](docs/views.py#L549-L589)) copies the source document's own
fields, lines, charges and payments. Posting the correction voids the original,
and `void()` cascades into linked customer returns
([posting.py:345-358](docs/posting.py#L345-L358)) and separate settling receipts
([:361-371](docs/posting.py#L361-L371)) — which the replacement never recreates.
Correct a sale that had a return and a receipt and both disappear from the books.
Hiding the button is not enough: an existing correction draft still posts through
the generic endpoint. *Absent from `v1.0.0`* (migration `docs/0008`).

### R71 — Voids rewrite history instead of recording a current-period reversal — `MITIGATED` (→ D119) — interim guard, reports still not reversal-aware
`void()` writes reversal rows at the current time but flips the original to
VOIDED, and reports query only currently-posted documents — so a June sale voided
in August vanishes from June and appears nowhere in August. *In `v1.0.0`;
correction makes it more frequent.* **Not independently re-verified by Claude —
Codex's tracing only.**

### R72 — Supplier returns can reduce the wrong supplier's payable — `RESOLVED` (→ D120)
`validate()` checks the lot's item ([handlers.py:222](docs/handlers.py#L222)) but
never that the lot came from `doc.supplier`, then reduces that supplier's AP
([:260](docs/handlers.py#L260)). Supplier B's lot can pay down supplier A.
*Unconditional, ordinary UI path, no setting mitigates it. In `v1.0.0`.*

### R73 — Zero conversion factor allows money without stock — `RESOLVED` (→ D120)
Only receiving validates the factor ([handlers.py:77](docs/handlers.py#L77)).
`factor` is a `PositiveIntegerField` ([models.py:200](docs/models.py#L200)), so 0
is storable; sale/return revenue uses `qty_entered` while stock and COGS use
`qty_entered × factor`. Dormant through the normal UI while conversion is off
(the field is hidden, [forms.py:89](docs/forms.py#L89)) — reachable by a crafted
POST, and fresh installs default conversion on. *In `v1.0.0`.*

### R74 — Stock counts apply stale variances — `RESOLVED` (→ D120)
Movement after the snapshot is detected but only logged
([handlers.py:404-411](docs/handlers.py#L404-L411)); the variance is still
computed against the frozen `qty_base` ([:417](docs/handlers.py#L417)) and posted
against current stock ([:433-452](docs/handlers.py#L433-L452)), overwriting what
moved. The owner never sees the warning before approving. *Live whenever counting
happens while trading continues. In `v1.0.0`.*

### R75 — Reports omit document discounts and charges — `RESOLVED` (→ D120)
Revenue sums `line_net` ([reports/views.py:200](reports/views.py#L200)), which
carries line discounts but not `doc_discount` ([models.py:96](docs/models.py#L96))
or charges ([models.py:248](docs/models.py#L248)). Reported revenue differs from
invoice revenue by `charges − doc_discount`. Charges are available in the live UI
today. *In `v1.0.0`.*

### R76 — Manual opening stock multiplies cost by the factor — `RESOLVED` (→ D120)
Opening stock stores the entered-unit cost as the **base-unit** cost
([handlers_opening.py:63-71](docs/handlers_opening.py#L63-L71)) where receiving
correctly divides amount paid by base units
([handlers.py:120-125](docs/handlers.py#L120-L125)). 10 cartons of 12 at 120/carton
books 120 per tablet — a 12× overvaluation. Dormant while conversion is off; the
CSV importer forces factor 1. *In `v1.0.0`.*

### R77 — Consignment settlement discards the issue's document discount — `RESOLVED` (→ D120)
Settlement derives value from the issue's `line_net`, which excludes the issue's
`doc_discount`, and applies only its own (blank) discount. Dormant while discounts
are disabled; fresh installs default them on. *In `v1.0.0`.*

### R78 — Django is a security patch behind — `RESOLVED` (→ D120)
Pinned 6.0.6 ([requirements.txt:3](requirements.txt#L3)); 6.0.8 is the 2026-08-04
security release. No disclosed path was shown reachable here, so this is overdue
patching, not a demonstrated Narcos exploit. *In `v1.0.0`.*

### Not established by this audit
No production data was inspected, so **the number and value of affected rows is
unknown** — the defects are proven, the damage is not. The live settings
(conversion off, discounts off, one till) were taken from these project records,
not queried from the deployed database. The Windows scripts were traced but never
executed on the real host.

### Round 20 — what changed, and what is still open

All twelve are addressed in the working tree, and Codex then reviewed the diff
adversarially and returned thirteen objections. Six were acted on immediately
(below); the rest are recorded as R79-R83. 456 tests pass on PostgreSQL,
`manage.py check` is clean and `makemigrations --check` finds nothing pending.
Decisions are written up as [D116-D120](02-decisions.md).

Two are marked `MITIGATED` rather than `RESOLVED`, and the distinction is real:

- **R69** — the scripts are fixed as code and have **never been executed**.
  There is no Windows host here. It is settled by a restore drill on the
  client machine and by nothing else: run `ops\docker-restore.ps1 <stamp>`
  into the scratch database, confirm it refuses a non-empty target, and
  confirm the media step now fails loudly instead of printing "Restored".
- **R71** — the guard stops a closed month being rewritten; it does not make
  reports reversal-aware. A void inside an open month still vanishes from that
  month rather than showing as a dated reversal. The real fix is reporting
  work, deferred.

**Deferred by Temesgen's instruction, deliberately:** no reconciliation of
data already on the client machine. Ten of these twelve defects are in
`v1.0.0` and have been live, so rows written under the old behaviour may be
wrong — most plausibly opening-stock lot costs (R76), referenced return values
(R67), invoice open balances (R68) and any stock count posted while trading
continued (R74). The agreed sequence is: deploy the fixes first, then a script
that looks for each mistake in the live data and reports what it finds. Little
has been entered yet and several of these workflows the client has not used at
all, so the exposure is expected to be small — but it is unmeasured, not zero.

## Codex's review of the fixes — round 20b

Codex reviewed the diff on `gpt-5.6-sol`/`ultra` and returned **do-not-ship**
with thirteen objections. Two were regressions the fixes themselves had
introduced, and both are now fixed:

- **The receiving twin of the R70 bug.** Sparing a cash sale's auto payment
  but not a cash receiving's auto supplier payment meant correcting a paid
  receiving was refused for no reason. `AUTO_PAYMENT_OF` now covers both.
- **Opening consignment kept the undivided cost.** R76 divided the lot's cost
  down to base units but left the frozen `LotConsumption` beside it at the
  entered-unit cost, so the same goods carried two different costs.

Four more were accepted and fixed in the same pass: the correction check now
takes the original's row lock *before* looking for dependents; a referenced
return is refused when the sale carries the same item and batch at two
different prices (averaging them credits neither) or when either side carries
a document discount; `open_balance()` is clamped at zero; opening stock is
refused when the per-base cost would round away to nothing; and a supplier
return of unknown-origin stock is now genuinely owner-only, which the code
comment had claimed but nothing enforced.

The rest are real and are **not** fixed:

### R79 — Supplier returns do not reduce the receiving's open balance — `OPEN` (high)
The AP mirror of R68, and the same shape: receive 100 on credit, return 20
without a refund, and `open_balance(receiving)` still reads 100, so a 100
payment is accepted and leaves the supplier 20 in credit. Not introduced by
this batch — `open_balance` has only ever counted allocations. Needs supplier
returns attributed to the originating receiving through
`lot.source_line.document`.

### R80 — R68 is not propagated to lists, pickers and filters — `OPEN` (medium)
`open_balance()` now subtracts return credits, but the transaction list, the
receipt picker and the settlement helpers compute their own figures and still
show the uncredited total. One reusable annotation should serve all of them.

### R81 — The stock-count guard is sequential, not concurrent — `OPEN` (medium)
R74 refuses a count when movement is already recorded, but nothing holds a
lock across the check and the adjustment it authorises, so a movement landing
in between still applies the variance to figures that have changed. Needs a
stable per-item lock in every stock posting path. Narrow on a one-till system.

### R82 — `books_closed_through` is not a full transactional boundary — `OPEN` (medium)
It refuses voids and corrections inside a closed period but not the posting of
an explicitly dated opening document into one, and the settings row is not
locked while the boundary is read, so closing a month can race a void.

### R83 — The restore order still leaves a half-restored system running — `WATCH` (accepted for v1.1)
`docker-restore.ps1` now fails loudly on media, but only *after* the database
is restored and after `app` has started, auto-migrated and published its port
— so a failure leaves a partial application live, and re-running refuses the
now-non-empty database. Media and dump should be checked before the target
database is touched, and the extraction should use a one-shot container with
no ports. Still unverified on Windows either way. Temesgen accepted this
operational risk for v1.1 on 2026-08-07; revisit before the deployment model or
recovery requirements expand.

### R84 — Granular draft permissions — `WATCH` (accepted for v1.1)
The current draft boundary is intentionally accepted for this installation:
the only users are the owner and his trusted sister, so per-creator draft
permissions and finer owner/employee RBAC do not block v1.1. Revisit before
adding less-trusted staff or expanding beyond this trusted two-person setup.
At that point, make owner-only posting checks use the current posting actor and
restrict editing, deleting, or posting another user's drafts.

### Codex's standing objections to R67
Its recommended fix was a source-line foreign key on `DocumentLine`, and it
maintains that the pro-rata credit is not equivalent: split returns can drift
by a cent, and tax does not round-trip on a split. What ships refuses the
cases that are demonstrably wrong (mixed prices, document discounts) rather
than pricing them wrongly, and credits a homogeneous return exactly. The
foreign key remains the right answer and is not in this round.

## Disposition review — round 21 (2026-08-07)

Six findings, each verified against the working tree rather than taken from a
summary, and dispositioned with Temesgen the same day. **No code was changed:**
the decision was to write them up first and choose later. Every entry names the
line that proves it, so whoever picks one up starts from evidence.

Two are dormant *because of how this shop is configured*, not because the code
is right. They are recorded precisely so that registering for VAT or TOT later
does not quietly wake them.

The regime answer also settled a live setup question. This business runs **no
sales tax at all** — its only tax path is the 3% withholding a PLC customer
keeps back when paying. `withholding_rate` already defaults to `3`
(`core/models.py:70`), but `tax_regime` defaults to **VAT** (`core/models.py:61`)
and `withholding_on_sales` defaults to **False** (`core/models.py:68`). Those two
must be changed on the client machine or every invoice adds 15% VAT that does
not exist and no withholding is ever shown. That is configuration, not a
defect — see `ops/RELEASE-CHECKLIST.md` §1.

### R85 — Stock-defining fields stay editable after the item has stock — `OPEN` (high)
`base_unit`, `is_batch_tracked` and `has_expiry` are ordinary editable fields on
`ItemForm` (`catalog/forms.py:45-51`), and `clean()` checks only that expiry
implies batch tracking — never whether stock or documents already exist. The
stored quantity is a bare number in the base unit, so changing `base_unit` from
"tablet" to "carton" reinterprets 120 tablets as 120 cartons and converts
nothing. Turning `is_batch_tracked` off strands batched stock outright: a sale
then looks for `batch_id=None` lots (`docs/handlers_sales.py:67`) and finds
none, while the goods sit on the shelf. Fix: keep the three editable until the
item has a `CostLot`, a `StockBalance` or a posted line, and after that require
a controlled conversion or a new item. Name, price, shelf and reorder level
stay freely editable throughout — this is not a general edit lock.

### R86 — Nothing on the server checks that a batch belongs to its item — `OPEN` (medium)
The batch picker carries `data-item` so the browser can filter the list
(`docs/forms.py:58`), and that is the whole of the enforcement:
`DocumentLineForm.clean()` validates the selling price and nothing else
(`docs/forms.py:429-443`). A posted line can therefore pair Amoxicillin with
Paracetamol's batch — via a stale form, a replayed POST, or any client that
does not run the script. Fix: one check in `clean()` refusing a batch whose
`item_id` is not the line's. Small, and it closes the hole for every document
type at once.

### R87 — The item form saves before it validates the unit conversions — `OPEN` (medium)
`master_form` calls `form.save()` and only then validates `ItemUnitFormSet`
(`catalog/views.py:103-111`). An invalid conversion — a duplicate "carton", say
— re-renders the page with an error while the item's own changes are already
committed, and the `log_change` below is never reached. So the user is told the
save failed, the price changed anyway, and the audit trail has no record of it.
Nothing in that view is inside a transaction. Fix: validate form and formset
together, wrap both saves and the audit row in one `transaction.atomic()`, and
write nothing at all when either is invalid.

### R88 — Posted documents read today's master record, not the one they were printed from — `WATCH` (accepted for v1.1)
`Document` links to `Customer`/`Supplier` by foreign key (`docs/models.py:84-87`)
and keeps no copy of the name, TIN or item description, so a reprint always
renders current master data. Correct a customer's phone in August and March's
invoice reprints with the new number: the copy in the customer's file and the
copy in yours no longer agree, and nothing records that they ever diverged. The
fix is to freeze the identity fields onto the document at posting and print from
the frozen copy — a migration plus posting and template work, the largest of
these six. **Temesgen accepted the current behaviour on 2026-08-07:** master
records stay live and reprints follow them. Revisit if reprints of old
documents start being relied on as evidence, or if master corrections become
routine.

### R89 — `vat_exempt` suppresses TOT as well as VAT — `WATCH` (dormant by configuration)
`line.is_taxable = not line.item.vat_exempt` (`docs/handlers_sales.py:30`) is
blind to the regime, so under TOT an exempt item escapes turnover tax too —
which contradicts D30 in as many words: "The TOT and none regimes are
unaffected." **Dormant here:** this shop runs the *None* regime, where the rate
resolves to zero for every line anyway (`docs/handlers_sales.py:42-45`), so the
flag suppresses a tax that is already nothing. Under VAT the same line is
correct. It goes live only if the business registers for **TOT**, and the rule
is worth confirming with the accountant before it is fixed.

### R90 — Opening consignment does not freeze a tax rate — `WATCH` (dormant by configuration)
`OpeningConsignmentHandler` (`docs/handlers_opening.py:162-184`) never assigns
`tax_rate_snapshot`, so it keeps the model default of `0` (`docs/models.py:101`),
and a later settlement reads that frozen zero (`docs/handlers_sales.py:482`) and
charges no tax on goods that should carry it. Under VAT at 15%, settling two
items issued at 100 each would bill 200 instead of 230. **Dormant here:** under
the *None* regime zero is the right answer, and whether any opening consignment
will be entered at all is still unknown. Fix alongside R89 if the regime
changes.

### Still open from earlier rounds, unchanged
**R79** (supplier returns do not reduce the receiving's open balance) was
confirmed again in this pass and stands exactly as written above. The wording
that caused confusion is worth restating: the "unrefunded" case is the ordinary
**credit-note** one — you receive 1,000 on credit, return 200 of damaged goods
before paying, and the supplier reduces what you owe to 800 rather than handing
back cash. The supplier's overall balance reads 800 correctly; the receiving
itself still reads open for 1,000, so the payment screen accepts 1,000 and
leaves the supplier 200 in credit. It is a normal purchasing scenario, not an
exotic one, and the application supports both settlement styles explicitly.

## From building D121 (2026-08-08)

Codex reviewed the feature on `gpt-5.6-sol`/`ultra`, scoped to it alone, and
returned **do-not-ship** with eight objections. Six were acted on before this
was committed: the impact preview counted DISPOSED stock as on hand and
claimed consigned goods would "become sellable" (only the warehouse feeds a
sale); voided documents were left out of the list of what shares the batch; an
unchanged date wrote a pointless audit row; the save and its audit row were
separate commits with no row lock; the confirm step was not bound to the date
actually reviewed; and validation errors were returned as `400`, which htmx
does not render at all. Two remain:

### R91 — Expiry correction does not serialize against posting — `OPEN` (medium)
`batch_expiry_edit` locks the `Batch` row; `post()` does not. A sale can
validate a batch's expiry, have the date corrected underneath it, and still
commit — leaving a posted sale of what is now expired stock. The fix is a
stable per-batch lock taken by every posting path, which is a change to the
posting engine; deferred on the same reasoning as R81, and for the same
reason — this is a one-till business, so the window needs two people acting in
the same instant. **Until it is closed the operating rule is: correct an expiry
when nothing is being posted** — not mid-sale, not from a second tab with a
document open. Codex accepted the deferral only on that condition. Revisit if
a second till is ever added.

### R92 — htmx never renders a 4xx, so some form errors are invisible — `OPEN` (medium)
Vendored htmx 2.0.4 defaults `{code:"[45]..", swap:false}`, so any fragment
returned with a 4xx status is discarded and the user sees nothing happen at
all. D121 returns `200` for bound-form errors because of this. **The shipped
D114 inline field edit does not** — [views.py:373](docs/views.py#L373) returns
`400`, so a rejected `fiscal_receipt_no` or `machine_total` on a posted
document fails silently in the browser today. In `v1.1.0`. Found by Codex
while reviewing D121; left unfixed only because it is outside that feature and
this round was scoped to it. One line each way: return 200, or configure
`htmx.config.responseHandling`.

### R95 — Three schema changes, now decided by the client's real data — `ANSWERED` (was OPEN, medium)
Round 22 shipped every change that needed no migration. Three deliberately did
not ship, because each is a judgement call that data settles better than
argument, and a failing migration on the client's box is an **outage**, not a
defect: `docker-entrypoint.sh` runs under `set -e` and applies migrations
*before* handing off, with `restart: unless-stopped`, so a raise means a
restart loop with nothing on screen.

| Deferred | What the data decides |
|---|---|
| `catalog.Generic` + `Item.generic` | How many generics are really duplicates. On dev, mechanical folding merges **nothing** — the only true pair, `Acetemenophin` / `acetemenophine`, differs by a trailing letter, not by case. If that holds on real data, the migration's value is near zero and the merge tool is the whole feature. |
| `Customer.also_supplier` FK | How many businesses have both faces, and how many tax numbers are blank or ambiguous. D127 works by tax number today. |
| `Item.superseded_by` | Whether near-duplicate items agree on base unit, batch tracking, expiry and VAT status. If they disagree, a merge is unsafe (R85) and supersede is the only path. If they agree and no batch number collides, a guarded merge is legitimate. |

**Note on "impossible".** An earlier reading of this held that merging two
items could not be done because the stock ledger refuses `save()` and
`delete()`. That is wrong and was corrected by executing it: `QuerySet.update()`
bypasses both guards and moves the rows. The barriers are correctness, not
mechanism — base-unit divergence silently reinterpreting every historical
quantity (R85), batch-number collision under the (item, batch_no) constraint,
FIFO order and auto-margin pricing changing after the merge, and tracking or
tax flags disagreeing. Plus the architectural objection, which is separate and
weaker: the guards exist to say posted history is not rewritten.

**Answered 2026-09-09 against the real database.** Full evidence in
[06-client-data.md](06-client-data.md). Summary of what the data decided:

| Deferred change | Verdict |
|---|---|
| `catalog.Generic` + `Item.generic` | **Cleanup value near zero.** 201 items, 187 distinct generics, and lowercase+trim folds them to **187** — it merges nothing. Only 9 generics carry more than one brand. Build it for the picker, or not at all; the merge tool is the whole feature. |

**Corrected 2026-09-10 — the `Generic` verdict above is wrong, and it is the
row that deferred this work.** The case-folding measurement was accurate and
measured the wrong property. These names do not duplicate by capitalisation;
they duplicate by having the **size or dosage form typed into the generic**.
Stripping a trailing size/form token collapses 187 to 154 — **52 of the 187
strings are restatements of 19 real generics** (ng tube in five sizes,
endothracheal tube in four, paracetamol in four, catheter in five,
metronidazole in three, syringe in three, and thirteen more). About 28% of the
generic list is duplicated.

The same size is additionally being written into three different fields
depending on the operator: the generic name, the brand field (the four Vicryl
records, "Syringe 20cc"), the `strength` field (Fogatery 3FH/4FH/5FH), and
sometimes two at once — "endothracheal tube #3" also has `strength = "#3"`.

**Consequence:** "build it for the picker or not at all" no longer holds. The
cleanup is the stronger of the two arguments, and the `Generic` row is the only
place where a rename or a merge is safe, because a generic owns no stock, no
batches, no cost lots and no document lines. Superseded by **D132**, which
also records that the 19 groups need human review — 154 is a count of
candidates, not of correct generics.

Full evidence and the group list are in [06-client-data.md](06-client-data.md)
§3.
| `Customer.also_supplier` FK | **Justified, and seeding must use the name.** 13 businesses have both faces; **0** match by tax number and all 13 match by name. Only 3 of 70 customers have a tax number at all. 8 pairs carry live balances, the largest 411,480 owed one way against 182,050 the other. |
| `Item.superseded_by` + guarded merge | **Both earn their place.** Duplicates are real but rare (~5 records in 201). The guard passes on the ORS pair (all flags match, no batch collision) and correctly refuses the three Fogatery records, which disagree on VAT exemption and category. |

The original next step, kept for the method:

**Next step:** a copy of `narcos.dump` from the client's nightly backup,
restored into a throwaway `postgres:16` container. Send **only** that file —
`.env` sits beside it in the same folder and holds the database password and
the secret key.

### R96 — `sale_price_editable` on the client's box — `ANSWERED` (was OPEN, high) — verified against the real database
D126's whole sizing rests on this flag being **on**. It is on in dev, and its
default is **off**. If the client's machine has it off, every sale price comes
from the item master, the price spread the new reports exist to show cannot
arise from typing, and "different prices to different customers" becomes R46
(per-customer standing price lists) — a much larger change that partly reopens
D80. One settings read answers it. **Read it before estimating anything else.**

R46's own text is now stale either way: it justifies deferral by citing "D23
(maintained price, editable per sale)", and D80 removed that editability before
D89 handed it back behind this switch.

**Answered 2026-09-09 from `narcos.dump` (2026-09-08): the flag is ON.** Staff
type prices; `discounts_enabled` is off, so typed prices are the *only* source
of variation. 58 of the 70 items sold more than once went out at more than one
price, tracking the buyer. **D126 is a report and R46 is not needed to answer
the client's question.** One caveat for reading those reports: the audit log
shows the flag was turned on **2026-08-08**, so sales before that date carry
item-master prices and a spread straddling that date has two causes. Full
evidence in [06-client-data.md](06-client-data.md) §1 and §6.

### R97 — Retention counted crashed runs as backups and deleted the real ones — `FIXED` (was critical) — verified by execution

Found while rescuing the client machine on 2026-09-07, after roughly a month of
power cuts and no backups.

[docker-backup.ps1:36-37](ops/docker-backup.ps1#L36-L37) creates
`<BackupRoot>\<stamp>\` *before* the dump runs. Every later step throws on
failure, so a power cut or a wedged Docker leaves the folder behind holding
nothing restorable. Retention then listed **every** directory under the backup
root, sorted newest-first, and kept fourteen. Empty wreckage sorts exactly like
a real backup.

**The sequence, executed against the client's actual state** (one good backup
from the v1.1.0 update on 2026-08-07, thirty crashed runs after it, then one
successful run today):

| | Folders kept | `20260807-160000` |
|---|---|---|
| Before the fix | 15, of which 13 were empty | **deleted** |
| After the fix | 10, every complete backup among them | survives |

Thirteen of the fourteen keep slots went to empty folders, and the monthly rule
picked `20260831` — also empty — as August's survivor, so the only real backup
of the client's business was pruned while the script printed success and logged
a `BACKUP` audit event.

**Fixed:** a folder counts as a backup only if it holds a non-empty
`narcos.dump` **and** `media.tar.gz`. Retention chooses its keep set from those
alone. Incomplete folders are kept for seven days as evidence that runs are
failing, then pruned, and their count is warned about on every run.

**Answered 2026-09-08:** the schedule never existed. `Get-ScheduledTask` on
the client machine matched only five built-in Windows tasks; no Narcos task had
ever been registered. The 8 August backup was taken by `deploy.ps1` during the
v1.1.0 update, which is why it carries that date. Nothing was ever running, so
the retention trap described above never actually fired - it was a loaded gun,
not a fired one. See `ops/INCIDENT-2026-09-08.md`.

**Originally recorded as still open:** why the schedule stopped is not settled. The task may
never have fired at all — R69 records that these scripts had never been
executed on a Windows host, and the last backup is dated the same day v1.1.0
was tagged, which is what `deploy.ps1` takes on its own. Answer it from the task's
**Last Run Result** in Task Scheduler.

### R98 — Power cuts zero-fill Docker's config and the fix on screen deletes the database — `MITIGATED`

Seen on the client machine 2026-09-07, photographed. Docker Desktop refused to
start with:

```
loading/formatting daemon.json: parsing daemon config
C:\Users\hp\.docker\daemon.json: parsing JSON:
invalid character '\x00' looking for beginning of value
```

NTFS commits a file's new size before its contents reach the disk. A power cut
in between leaves the file readable but full of NUL bytes. Nothing was wrong
with the engine, the volumes, or the database — one settings file was zeroed.

**Why this is a risk and not just a fault:** the dialog Docker Desktop shows
offers exactly two buttons, *Quit* and **Reset to factory defaults**. Reset
deletes named volumes, and `pgdata` is a named volume. The remedy presented on
screen to a non-technical operator, during an outage, destroys the business.
With three power cuts a day this dialog will appear again.

**Mitigated by** [ops/fix-docker-config.ps1](ops/fix-docker-config.ps1), which
quarantines unreadable config (renames, never deletes) and lets Docker Desktop
rebuild defaults. This deployment needs no custom daemon settings, so defaults
are correct. Detection covers zero-length, NUL-filled and half-written JSON;
all four cases are tested, including a valid file being left untouched.

**Not fixed, and cannot be from here:** the underlying cause is the power. This
is R11's UPS, now purchased. Until it is installed, expect recurrence.

### R99 — The scheduled backup depended on a working directory nobody set — `FIXED`

Found on the client machine 2026-09-08, while setting up the schedule that had
never existed.

`docker-backup.ps1` read `.\.env` relative to whatever directory Task Scheduler
happened to hand it. The deployment guide covers this with a "Start in" field,
which is one unticked box away from a job that fails every day. A scheduled job
that fails is silent by nature, which is the entire reason this client went a
month with no backup and nobody noticed.

**Fixed:** the script now finds the deploy directory by walking up from its own
location until it finds `compose.yml`. Verified by running it from `/` with the
deploy folder elsewhere: it resolved the correct backup root and dumped
normally. `backup-now.ps1` and `copy-data-out.ps1` do the same.

**Related operational fact, not a defect:** `docker-backup.ps1` archives media
and writes an audit row through the **app** container, and by R69's deliberate
design it throws if either fails. So the scheduled backup cannot succeed while
the app container is down. On 2026-09-08 the client's app image was missing
from the Docker image store entirely, only `postgres:16` survived. Restore the
app before enabling the schedule, or every run leaves a partial folder. Use
`backup-now.ps1` in the meantime, which treats both steps as best effort and
still produces a verified dump.

### R100 — Task Scheduler reported success for backups that never happened — `FIXED`

Found on the client machine 2026-09-08, minutes after registering the schedule
that R99 fixed. `Start-ScheduledTask` was followed by `LastTaskResult = 0`, but
the directory listing in the same command printed nothing: no backup folder had
been created.

`powershell.exe -File` exits 0 even when the script hit a terminating error, so
the task's only health signal always said success. A scheduled job whose result
code cannot express failure is worse than no job at all - it manufactures
confidence. This is the same shape as R97 and R99: the backup system's failures
were all silent, and that is why a month went missing.

**Fixed:** `docker-backup.ps1` installs a `trap` that writes the failure to
`ops\backup.log` and exits 1, and logs `BACKUP OK` with the folder on success.
Task Scheduler now sees a real result code, and there is a dated line on disk
either way.

**Verified by execution** against a healthy database with a broken app
container, which is the client's current state: exit code 1, and
`BACKUP FAILED 2026-09-08 07:59 - Media archive failed.` in the log. Before the
fix the same run reported 0. The success path is straight-line and not yet run
end-to-end here for want of a working app image; it is proven the first time
the script is run by hand on the client after the app is restored.

### R101 — The unattended-recovery chain was never completed at install — `DECIDED` (→ D131)

Checked on the client machine 2026-09-08:
`AutoAdminLogon = 0`, `DefaultUserName = hp`.

[DEPLOYMENT.md section 2](ops/DEPLOYMENT.md) specifies a three-link boot chain
so the machine returns on its own after a power blip: Windows auto-login, then
Docker Desktop starting on sign-in, then `restart: unless-stopped` bringing the
containers back. Links two and three are in place - Docker Desktop is in the
`HKCU:\...\Run` key, and compose.yml carries the restart policy. Link one was
never done.

So the PC boots to a lock screen and stays there. Nothing starts until a person
signs in. At a site with three power cuts a day this is the difference between
a system that heals itself and one that needs someone present every time, and
it also means a missed 16:00 backup only catches up once somebody logs in.

**Fix:** enable auto sign-in through `netplwiz`, which stores the credential in
LSA secrets. Do **not** set `DefaultPassword` in the registry - that writes the
account password in plain text. On current Windows the netplwiz checkbox is
hidden until Windows Hello sign-in is turned off in Settings, Accounts,
Sign-in options.

**The trade being made:** auto-login means whoever switches the PC on is inside
the system. For a single-owner pharmacy on one machine behind a locked door
that is usually right, but it is the owner's decision to take knowingly, not a
default to slip past them.

**Also seen in the same Run key:** OneDrive and Microsoft Edge auto-launch.
Both compete for RAM on an 8 GB machine already capped to 3 GB for WSL2.
Removing them is free headroom.

**Resolved 2026-09-08 by D131, not by configuration.** The owner keeps
auto-login off deliberately: the security cost is permanent, and someone is on
site during the hours the power actually cuts. Links two and three stay in
place, so once a person signs in the stack returns on its own. The obligation
that replaces link one is the recovery card at the machine - a manual step that
nobody has been taught is not a decision, it is an outage waiting to happen.

### R102 — Withholding is switched off for the one tax that applies, and the sale-side box is inert — `OPEN` (high)
Two problems, one configuration and one code, found together on 2026-09-09 in
the client's real database ([06-client-data.md](06-client-data.md) §7).

**Configuration.** The client is a **sole proprietorship**. They never withhold
when purchasing, so `withholding_on_purchases = FALSE` is correct. Their
customers — hospitals and PLCs — withhold 3% when paying them, so
`withholding_on_sales` must be **on**. It is **off**, and the audit log shows
it has never been changed from its install default. This is the only tax that
touches the business, and nothing is being recorded.

**Money already affected.** Staff ticked the withholding checkbox on three
credit sales in their first three days:

| Invoice | Customer | Total | 3% never recorded | Settled |
|---|---|---|---|---|
| SI-000001 | Shalom primary hospital | 44,200.00 | 1,326.00 | fully open |
| SI-000002 | Shalom primary hospital | 49,446.00 | 1,483.38 | **in full** |
| SI-000003 | Alula Primary Hospital | 60,550.00 | 1,816.50 | **in full** |

4,625.88 in withholding credit, no certificates, and zero rows in
`money_withholdingledger`.

**Code defect.** The two halves of the feature disagree. The payment side
refuses out loud — `_PaymentBase.validate()` raises `PostingError`
("Withholding is disabled in settings (D51/D52)."). The sale side is silent:
`if settings.withholding_on_sales and doc.customer_will_withhold:` stores the
tick and ignores it. `fields_hidden_by_settings()` hides boxes for the fiscal
machine, discounts and pack conversion but **not** withholding, so this is the
only switched-off feature still showing a live control — an inert control,
which is exactly what D89's other three flags avoid.

**The failure mode that matters.** Ticking is silent at sale time; the refusal
arrives later at payment time. The invoice then will not balance and the
tempting move is to record a **full** payment to close it. SI-000002 and
SI-000003 being settled in full is consistent with that. If those hospitals did
withhold, cash is overstated by ~3,300 and the certificates are gone.

**Order of work:**
1. **Turn `withholding_on_sales` on** at the client. Settings change, not a release.
2. **Ask whether Shalom and Alula paid 100% or 97%.** Cannot be answered from data.
3. Hide `customer_will_withhold` when the feature is off — one line in
   `fields_hidden_by_settings()`, no migration. Third, because it is a
   consistency repair, not the thing protecting the money.

Also: only 1 of 70 customers carries `is_withholding_agent`, yet staff ticked
the box for a customer that is not flagged. The customer master is not being
maintained for this.

### R103 — D127's both-faces report is inert on the client's real data — `OPEN` (high)
D127 pairs a customer with their supplier record by normalised tax number, and
so does D79's statement counterpart. On the client's database that finds
**nothing**:

| Measure | Value |
|---|---|
| Customers | 70 (only **3** have a tax number) |
| Suppliers | 50 (only 7 have a tax number) |
| Businesses appearing as both | **13** |
| Matching by tax number | **0** |
| Matching by name | **13** |

Eight of the thirteen carry live balances, the largest being 411,480 owed one
way against 182,050 the other. The client's question — "who owes who" — is
about real money and the report shows an empty table.

**This is also the clearest evidence for why round 22's tests were not enough.**
Six tests pass against seven toy items with tax numbers invented to make the
matching work. The feature was correct against its fixtures and useless against
production.

**Fix:** match on normalised name as well as tax number, and prefer an explicit
`Customer.also_supplier` link seeded from name (R95). Name matching alone is
riskier in general — two unrelated businesses can share a name — so the
explicit link, human-confirmed, is the durable answer and the report is the
interim.

### R104 — Shipping a drug reference catalogue inside the application — `OPEN` (medium)
Asked 2026-09-09: "since this is a pharmaceutical program can we enter
everything — all generics and brands and strength known — into the db as part of
the application."

**It must not go into `catalog.Item`.** `Item` is a trading object: it carries a
code, a price, a pricing mode, batches, cost lots and stock, and it is the row
every picker on every sale and receiving screen searches. The client's whole
catalogue is **201 items**, of which **162 are drugs**. Loading even a modest
national list would put thousands of priceless, stockless, batchless rows in
front of a counter clerk who is looking for one of 201. Reorder reports,
zero-stock listings and the item picker all degrade the day it lands. This is
the round-22 failure mode (R103) inverted: not an inert feature, but a feature
that harms the screens that currently work.

**"Everything known" is not obtainable for this market.** RxNorm and the FDA NDC
directory are United States registries; the brands on this client's shelves are
Indian, Chinese, Gulf and Ethiopian — `zitromax`, `Gabalin`, `Moxipil`,
`Suxathon`. DrugBank is licence-restricted for commercial redistribution. EFDA
publishes registered-product lists, but as periodic documents rather than a
maintained machine-readable feed — **this needs verifying before anything is
scoped on it.** A partial list that presents itself as complete is worse than no
list, because staff will trust it and stop reading the carton.

**Strength and dosage form must keep coming off the physical carton.** This
business invoices hospitals. If a shipped reference says 200mg, the carton says
250mg, and `Item.full_description` prints our value onto the invoice, the system
has manufactured a wrong medicines document. Any reference may propose a generic
*name*; it may not fill strength.

**What the data says is actually wrong, and it is smaller than the question.**

| Field | Filled | Raw distinct | After lowercase + trim |
|---|---|---|---|
| `generic_name` | 201 / 201 | 187 | 187 |
| `dosage_form` | 200 / 201 | **19** | 18 |
| `strength` | 143 / 201 | — | — |
| `base_unit` | 201 / 201 | **16** | 16 |

Two hundred and one items produce only **19** dosage forms, and four of them are
junk: `Euipment` (×2), `suspenssion`, `.`, and one empty. `reagent` and
`reagents` are the same thing. `base_unit` has the same shape: `pcs`/`piece`,
`pk`/`pack`, `Bag`/`bag`. **A closed list of about twenty dosage forms removes
that entire class of defect and needs no drug database at all.**

The generic names are where a reference would help, and the errors are
misspellings rather than case: `Suxamethiom`, `Doxycyclline`, `Amoxacillin`,
`Antiheamoroid`, `Embolectomy Cathater`. Case folding merges nothing (R95), so
a typeahead is the only mechanism that prevents the 188th spelling of
amoxicillin. **The client's own 187 generics are already the best available
seed for that typeahead** — no new data, no licence, no staleness.

**Proposed order of work, smallest first:**

1. Close `dosage_form` to a choice list with an "other" escape, and fold the
   `base_unit` synonyms. Kills the four junk values and prevents recurrence.
2. Typeahead on `generic_name` seeded from existing `Item.generic_name` values.
   This is the picker half of R95, which the data already said was the only half
   worth building.
3. **Only after 1 and 2 are live**, consider vendoring a generic-names-only
   reference (WHO EML plus the Ethiopian NEML, on the order of several hundred
   rows) into a separate read-only table feeding the same typeahead. Never in
   `Item`, never auto-filling strength, and marked as a suggestion.

Correcting the existing misspelled generics is a data fix and therefore a
management command the owner runs, not a hand edit.

### R105 — The Inventory search ignores `generic_name`, so brand-named items look absent — `OPEN` (high)
Reported by the client on 2026-09-09 as "catheter is not in my database even
though I added it before". He is right about what he saw.

`stock/views.py:54` filters `code` and `name` only. `catalog.views.MASTER["items"]`
filters `code`, `name` **and** `generic_name`. Typing `catheter`:

| Screen | Finds |
|---|---|
| Inventory (`/inventory/`) | **3 of 10** |
| Master → Items (`/master/items/`) | 7 of 10 |

The four `Folly` catheters (ITM-0052/53/54/55) exist, appear in Master, appear
in the sale picker, and are invisible on the one screen that answers "how many
have I got". This trade reads by generic name — `Item.__str__` leads with it and
says so in a comment (R48) — so a stock screen that cannot search it is a
defect, not a preference. The gap hits every brand-named item: Fogatery, ETT,
NG tube, BOSO, Folly.

**Fix:** add `generic_name__icontains` to the filter. One line, no migration.
The document line picker is not affected — it is a Choices.js searchable select
(`docs/forms.py:330`) over the generic-first label.

**Related data defect, separate fix.** ITM-0065/66/67 spell the generic
`Embolectomy Cathater`, and ITM-0052's name is `Folly cathater`, so the correct
spelling misses them on **both** screens. Ships as a management command the
owner runs, never a hand edit. Correcting the spelling does **not** merge the
three Fogatery rows — they remain the case §4 of
[06-client-data.md](06-client-data.md) uses as the merge a guard must refuse.

### R106 — A voided sale is not an undone sale, and 544 units are counted as sellable because of it — `OPEN` (high)
Found 2026-09-09 while chasing the client's "we sold it and the number did not
go down" report. §9 of [06-client-data.md](06-client-data.md) checked that
voided documents' ledger rows net to exactly zero and treated that as proof of
correctness. **It proves the reversal is complete. It says nothing about whether
the goods came back.**

Staff void an invoice to correct a price or a quantity and re-issue it. When the
re-issue is smaller than the void — or never happens — the difference stays on
the books as sellable stock while the customer already has it. Nine voided sale
lines across the snapshot leave **544 units** in that state:

| Code | Item | Voided | Re-issued | Gap | On hand | Reason given |
|---|---|---|---|---|---|---|
| ITM-0096 | Epifenac (Diclofenac IV) | 1170 | 780 | **390** | **390** | ERROR |
| ITM-0046 | ETT #6 | 50 | 0 | **50** | **50** | ERROR |
| ITM-0001 | fluco-ssp | 40 | 0 | 40 | 0 | ERROR |
| ITM-0094 | Pethidine | 100 | 70 | 30 | 950 | ERROR |
| ITM-0002 | Gabalin | 20 | 0 | 20 | 50 | returned |
| ITM-0086 | Actirapid (insulin) | 10 | 0 | 10 | 150 | selling price adj |
| ITM-0169 | Omni | 2 | 0 | 2 | 0 | returned |
| ITM-0088 | URS-2MAC | 1 | 0 | 1 | 15 | ERROR |
| ITM-0010 | Promulet | 13 | 12 | 1 | 1026 | qty error |

Re-issue matched as same item, same customer, posted within 14 days.

For **ITM-0096 and ITM-0046 the phantom is the entire remaining balance** — the
screen's number is composed of nothing else. Epifenac is an injection, which
matches the client's words, and is the first thing to put to him: opening 1170,
a 1170 sale to Alula Primary Hospital voided, a 700 sale voided, a 780 sale
posted. Ask what that hospital actually received.

**Two of the nine give the reason "returned".** There are zero CUSTOMER_RETURN
documents in the database, so a return is being recorded by voiding the original
sale. That is numerically right for a full return, silently wrong for a partial
one, and either way it erases the fact that a sale happened. This and §9's
write-off gap are the same wound.

**Not an engine fault.** All 376 posted sale lines move stock by exactly
`−qty_base`; balance equals ledger across all 255 groups; zero draft sales;
`free_qty` is 0 on every posted line.

**Fix:** no new code. `StockCountHandler` already freezes a snapshot, measures
the variance and auto-posts an owner-only ADJUSTMENT, respecting append-only.
The screen has never been used. Count ITM-0096 and ITM-0046 first — 440 of the
544 units. Whether voiding should also warn that stock is being returned to the
shelf is a **separate design question** and needs the client's own account of
how he uses void before anything is built.
