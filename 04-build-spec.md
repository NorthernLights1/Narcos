# Buildable Spec (v1)

Derived from [02-decisions.md](02-decisions.md) **D1–D65**. This is the
document an implementing model builds from, module by module, in the order of
§16. **If anything here conflicts with the decision log, the decision log wins
— stop and flag the conflict instead of guessing.** Decision references (D…)
are deliberate: read the referenced decision before implementing that part.

Rules for the implementer:

- Build **one phase at a time** (§16). Do not start a phase before the
  previous phase's acceptance tests pass.
- **Never invent a business rule.** If a case is not covered here or in the
  decision log, stop and ask.
- Every user-facing string is wrapped for translation from the first line of
  code (D56): `gettext` / `{% trans %}`. English only ships in v1.
- Money is `Decimal`, 2 dp, ROUND_HALF_UP — never float. Quantities are
  **integers in base units** (packs are never split, D62; alternate-unit entry
  must convert to a whole base number or be rejected).
- All timestamps stored UTC; server timezone Africa/Addis_Ababa (R11).

---

## 1. Stack & project skeleton (D55)

| Layer | Choice |
|---|---|
| Language / framework | Python 3.12+, Django 6.x (needs ≥5.1) |
| Database | **PostgreSQL 16** — D66. Runs as a Windows native service, auto-start, localhost-only (D45/R45). Connection: `postgresql://narcos:$NARCOS_DB_PW@localhost:5432/narcos` (env var for password). |
| Frontend | Django templates + HTMX (partial updates) + Alpine.js (in-form math) + Tailwind CSS (standalone CLI build — **no Node project**) |
| Static files | WhiteNoise |
| App server | Waitress, run as a Windows service (NSSM or winsw) |
| Tests | pytest + pytest-django, factory-boy; coverage target 80%, invariants in §17 are mandatory |
| Printing | HTML print views + browser print (A4), selectable built-in layouts (D17/D49) |

Single Django project `narcos`, apps: `core` (settings, users, audit,
sequences), `catalog` (items, parties), `stock` (batches, lots, balances),
`docs` (documents, posting engine), `money` (accounts, ledgers, payments),
`reports`. Keep files under 800 lines; split by feature.

Dependencies: pin exact versions (R44). No Redis, no Celery, no background
workers — scheduled jobs (backup) run via Windows Task Scheduler; in-app
"alerts" are computed on dashboard load, not pushed.

**Database rules (D66, binding):** no raw SQL anywhere; unique constraints
only via Django expression-based `UniqueConstraint`; the posting engine calls
`select_for_update()` for real row locks on PostgreSQL (D14); ledger-reconciliation
totals sum in Python `Decimal`, never SQL `SUM` alone; invariants I3/I4 must
pass on PostgreSQL. These rules were written to enable portability (D65), but
D66 makes them the primary build standard.

---

## 2. Glossary

- **Document** — the only thing that changes ledgers. Draft → Posted →
  (maybe) Voided. Posted documents are immutable (D28, exceptions §7.12).
- **Ledger** — append-only rows created by posting. Four ledgers: stock,
  money, party (AR/AP), withholding.
- **Batch** — manufacturer production run: item + batch_no + expiry (D40).
- **Cost lot** — one receipt's quantity at one frozen cost, under a batch
  (or directly under a non-batch item) (D1, D40).
- **Zone** — where stock physically is: `WAREHOUSE`, `CONSIGNED` (+customer),
  `EXPIRED`, `UNFIT`, `DISPOSED`.
- **Base unit** — the unit stock is counted in (D62). Alternate units have
  fixed integer-safe factors.

---

## 3. Data model

Types: `pk` = bigint identity; `money` = numeric(14,2); `qty` = integer
(base units); `str` = varchar; `ts` = timestamptz. `※` = snapshot frozen at
posting, never recomputed.

### 3.1 core

**company_settings** (singleton row, owner-editable, every change audited)
- name, address, tin: str
- tax_regime: enum VAT | TOT | NONE (D7)
- vat_rate: numeric(5,2) default 15.00 · tot_rate default 2.00
- prices_tax_exclusive: bool default true (D31)
- withholding_on_sales: bool default false (D51)
- withholding_on_purchases: bool default false (D52)
- withholding_rate: numeric(5,2) default 3.00 (D51; rate is config, law changed once already)
- near_expiry_months: int default 6 (D59)
- consignment_term_months: int default 3 (D60)
- default_credit_limit: money nullable · default_credit_action: enum WARN|BLOCK (D25)
- fiscal_year_start: Ethiopian month, default Hamle (D19)
- date_display: enum GREGORIAN | ETHIOPIAN | BOTH (D19)

**users** — Django auth. `role`: OWNER | EMPLOYEE (D33/D42). Owner creates
employees. Password recovery = documented `manage.py reset_owner_password`
command, local console only (R10).

**audit_log** (append-only, D47)
- actor FK, action: str, entity: str, entity_id, before/after: jsonb, at: ts
- Log: posting, voiding, settings changes, master-data create/edit,
  role/user changes, owner overrides (with reason), reference-field edits
  (§7.12), CSV imports, backups/restores, **clock anomalies** (if a posting's
  `now()` < the latest existing posting timestamp, log `CLOCK_ANOMALY`).

**number_sequences** — doc_type: str pk, next_no: int. Row locked
`SELECT … FOR UPDATE` during posting (D8, D14). Numbers are **per doc type**,
gapless, assigned **only at posting**, format `SI-000123` (prefix per type,
§7 table). Drafts show internal id only.

### 3.2 catalog

**items** (D29)
- code: str unique · name: str · category: enum DRUG | REAGENT | SUPPLY | EQUIPMENT
- is_batch_tracked: bool (default: DRUG/REAGENT true) · has_expiry: bool (D22)
- vat_exempt: bool default false (D30/D50 — owner sets; help text: "medicines are VAT-exempt by law")
- base_unit: str label (D62), e.g. "pack of 10"
- generic_name, dosage_form, strength, pack_description: str nullable (drug-only, optional)
- maintained_price: money (D23) · pricing_mode: enum MANUAL | AUTO · auto_margin_pct
- min_margin_pct nullable (low-margin alert line, owner-only display)
- reorder_level: qty nullable (D34) · shelf_bin: str nullable · is_active: bool

**item_units** (D62) — item FK, unit_label: str, factor_to_base: int > 1,
unique (item, unit_label). Base unit itself is implicit factor 1.

**customers** — code unique, name, tin, phone, address,
credit_limit: money nullable (null → company default), credit_action nullable
(null → default) (D25), is_withholding_agent: bool default false (D51), is_active.

**suppliers** — code unique, name, tin, phone, address, is_active.

**accounts** — name, type: CASH | BANK, is_active. (D9/D10/D11)

**expense_categories** — name, is_active.

**fixed_assets** (D16/D49) — name, cost, purchase_date, useful_life_years,
notes. Recording only; **no depreciation display in v1**. Consumables the
business uses are just expenses (§7.10).

Master-data forms do **search-as-you-type against existing records** and
enforce unique codes (D26). No merge tool in v1 (R8b).

### 3.3 stock

**batches** (D40) — item FK, batch_no: str, expiry_date: date nullable
(required iff item.has_expiry), unique (item, batch_no). Items with
is_batch_tracked=false get **no batch row** — their stock rows carry batch=NULL (D29).

**cost_lots** (D1/D40) — item FK, batch FK nullable, source_line FK
(receiving/opening/adjustment/return line), received_at: ts,
qty_received: qty, unit_cost: money ※ (frozen forever). Never overwritten;
same batch received again at a new price = **new lot** (D1).

**stock_ledger** (append-only) — document_line FK, item FK, batch FK null,
lot FK, zone, consignment_customer FK null, qty_delta: qty (+ in, − out), at: ts.

**stock_balances** (derived cache, maintained in the same transaction as the
ledger rows; the ledger is the source of truth) — item, batch null, lot,
zone, consignment_customer null → qty. `CHECK (qty >= 0)` enforces
no-negative-stock at lot+zone granularity (D4). Uniqueness: Django
expression-based `UniqueConstraint` over `(item, Coalesce(batch, 0), lot,
zone, Coalesce(customer, 0))` — works across PostgreSQL and (if ever needed) SQLite.
Posting locks the touched balance rows via `select_for_update()` for real row locks (D14/D66).

Lot remaining sellable qty = its balance in WAREHOUSE. FIFO = oldest
`received_at` lot with WAREHOUSE balance, within the chosen batch (D40).
Batch suggestion at sale = earliest expiry first (FEFO), staff may override (D61).

### 3.4 docs

**documents**
- doc_type: enum (§7 table) · doc_no: str nullable until posted (D8)
- status: DRAFT | POSTED | VOIDED
- document_date: ts — **system time at posting** (D38); user never picks it.
  Opening documents (owner-only) may carry historical dates (D38 exc. 1).
- customer FK null · supplier FK null (per type)
- sale_kind: CASH | CREDIT (sales only) · due_date: date (credit sales, user-set — D38 exc. 3)
- supplier_invoice_date: date null (reference only, D38 exc. 2)
- Totals ※ (D32): subtotal, doc_discount, taxable_base, exempt_base,
  tax_total, grand_total — all money. tax_total is **authoritative**; nothing
  ever recomputes tax another way.
- withholding_expected: money ※ (D51, display only)
- fiscal_receipt_no: str null, machine_total: money null (D18/D43, §7.12)
- created_by/at, posted_by/at, voided_by/at, void_reason: str
- notes: str

**document_lines**
- document FK · item FK · batch FK null · unit_label ※ · factor ※ · qty_entered
- qty_base: qty ※ · unit_price: money ※ · line_discount: money ※
- line_net: money ※ = qty_entered × unit_price − line_discount
- is_taxable: bool ※ (snapshot of NOT item.vat_exempt at posting — D30/D50;
  consignment settlement copies it from the **consignment note**, not the item — D6)
- cogs_total: money ※ (sales/settlements; owner-visible only — D33)
- For settlements: qty_sold / qty_returned / qty_expired_unfit split (D6)

**lot_consumptions** — line FK, lot FK, qty, unit_cost ※. Written whenever a
line consumes stock; drives COGS, void restoration, and return re-entry.

**document_charges** (D37, sales/proforma only) — document FK, label, amount:
money, is_taxable: bool. Adds to totals and the D32 bases; no stock, no COGS.

### 3.5 money

**money_ledger** (append-only, D10/D11) — account FK, amount_delta: money,
document FK, at: ts. Balance = SUM. Opening cash is a seeded ledger row (D11).

**party_ledger** (append-only) — party_type CUSTOMER|SUPPLIER, party_id,
amount_delta: money (AR: + owed to us; AP: + we owe), document FK, at.

**payment_lines** (on payment documents, D10) — document FK, account FK,
method: CASH|BANK_TRANSFER|CHEQUE, amount: money.

**payment_allocations** (D3/D44) — payment doc FK, target document FK
(invoice/opening invoice/return), amount: money. Partial allowed; sum of
allocations = payment total (money lines + withheld_amount).

**withholding_ledger** (append-only, D51/D52) — direction RECEIVABLE|PAYABLE,
amount_delta: money, document FK, certificate_no: str null, at.

Payment documents also carry: withheld_amount: money default 0,
withholding_certificate_no: str null (§7.12 editable-after).

---

## 4. The posting engine (build once, reuse everywhere)

One code path posts every document type; per-type logic plugs in.

**Post(document)** — single DB transaction:
1. Validate the draft (per-type rules §7; system boundaries validated hard).
2. `select_for_update()` the number_sequences row for the doc type; then lock
   (or create) every stock_balances row the document touches, in a stable
   order (item id, lot id) to avoid deadlocks (D14). These take real row
   locks on PostgreSQL (D66).
3. Re-check business rules under lock — especially **no negative stock** (D4)
   and expired-sale block (D46).
4. Freeze snapshots ※: prices, discounts, is_taxable, unit factors, computed
   totals (§5), COGS lot consumptions (FIFO), withholding_expected (§6).
5. Assign doc_no = next_no++, set document_date = now() (D38).
6. Write ledger rows (stock/money/party/withholding as the type dictates §7)
   and update balances.
7. status = POSTED; audit_log row. Commit.

**Void(document)** — owner only (D28):
1. Blocked outright for receivings any of whose lots have been consumed or
   moved (D5). For everything else: build the exact reverse ledger deltas and
   run them through the same balance checks (D4) — if reversal would push any
   balance negative, block (owner may override with reason; override audited).
2. Write reversal ledger rows attached to the original document, set status =
   VOIDED with reason, audit. **No edits, ever** — corrections are void +
   re-enter, or an owner adjustment when void is blocked (D28).

Drafts are freely editable and deletable; they touch nothing (D28).

**Employees cannot void or override anything** (roles, D33). Owner overrides
always require a typed reason and are audited (D47).

---

## 5. Tax computation (D32 + D50 + D64) — the only algorithm allowed

Inputs: posted lines (line_net ※, is_taxable ※), charges (amount,
is_taxable), doc_discount, regime + rate from settings (snapshot the rate ※).

```
subtotal      = Σ line_net + Σ charge.amount
# pro-rata doc discount (D64): allocate by value over lines+charges,
# 2 dp per part, last part absorbs the rounding remainder
for each part p: p.alloc = round2(doc_discount × p.value / subtotal)   # last: remainder
taxable_base  = Σ (p.value − p.alloc) over taxable parts
exempt_base   = Σ (p.value − p.alloc) over exempt parts
if regime == VAT:  tax_total = round2(taxable_base × vat_rate/100)     # once, at doc level
if regime == TOT:  tax_total = round2(taxable_base × tot_rate/100)     # exempt flag still honored
if regime == NONE: tax_total = 0
grand_total   = taxable_base + exempt_base + tax_total
```

Prices are entered tax-exclusive (D31). Per-line tax is **never** stored or
summed — if a print layout shows a per-line split it is display-only math
(D32). Every screen/report reads the stored ※ totals.

Consignment settlement runs this algorithm over the **frozen consignment-note
values** (price, is_taxable, rate ※ from issue time), not current ones (D6).

---

## 6. Withholding (D51 / D52 / D53)

Never touches revenue, COGS, or profit (D53). Base = the **VAT-exclusive**
amount = grand_total − tax_total (R40a).

**Sales side (D51)** — visible only when settings.withholding_on_sales:
- Sale form shows checkbox "customer will withhold", pre-ticked from
  customer.is_withholding_agent. Posting stores
  `withholding_expected = round2(rate × (grand_total − tax_total))` — purely
  informational; receivable is the full grand_total.
- On a customer payment: user may enter withheld_amount (prefill: rate ×
  VAT-exclusive share of the amount being settled; editable). Effect:
  - money_ledger + per payment_lines (the 97%)
  - withholding_ledger RECEIVABLE +withheld_amount (certificate_no optional)
  - party_ledger CUSTOMER −(cash + withheld) — invoice settles in full
- Report: certificates per fiscal year (D19) → the accountant's year-end
  income-tax credit.

**Purchase side (D52)** — visible only when settings.withholding_on_purchases:
- Mirror on supplier payments: withheld_amount → withholding_ledger PAYABLE +,
  party_ledger SUPPLIER −(cash + withheld), certificate printed for supplier.
- **WHT remittance** document (§7.9): pays the tax office from an account:
  money_ledger −, withholding_ledger PAYABLE −.
- Report: withheld / remitted / still owed.

Legal thresholds (ETB 20,000 goods / 10,000 services) are help text only —
the human decides (D51/R40).

---

## 7. Document types

| doc_type | prefix | party | stock | money | party ledger | tax |
|---|---|---|---|---|---|---|
| RECEIVING | GRN | supplier | + WAREHOUSE (new lots) | − if paid now | AP + if credit | none (D63) |
| SALE | SI | customer | − WAREHOUSE | + if cash | AR + if credit | §5 |
| PROFORMA | PF | customer | none | none | none | §5 (display) |
| CONSIGNMENT_ISSUE | CN | customer | WAREHOUSE → CONSIGNED | none | none (exposure only, D25) | frozen ※ |
| CONSIGNMENT_SETTLEMENT | CS | customer | CONSIGNED → out/WAREHOUSE/EXPIRED/UNFIT | + if cash | AR + if credit | §5 on frozen values |
| CUSTOMER_RETURN | CR | customer | + chosen zone | − if refunded | AR − if credited | negative, §5 on returned lines |
| SUPPLIER_RETURN | SR | supplier | − WAREHOUSE | + if refunded | AP − | none |
| CUSTOMER_PAYMENT | RC | customer | none | + | AR − | none (D15) |
| SUPPLIER_PAYMENT | PV | supplier | none | − | AP − | none |
| WHT_REMITTANCE | WR | — | none | − | none | none |
| TRANSFER | TR | — | none | −from / +to (D9) | none | none |
| EXPENSE | EX | — | none | − | none | none |
| ZONE_MOVE | ZM | — | zone → zone | none | none | none |
| ADJUSTMENT | ADJ | — | ± | none | none | none |
| STOCK_COUNT | SC | — | via ADJ | none | none | none |
| OPENING_* | OP | varies | varies (D2/D39) | opening cash row | opening AR/AP | none |

### 7.1 Receiving (GRN)
Lines: item, batch_no + expiry (required iff batch-tracked/has_expiry — D22/D29),
unit + qty, unit_cost, **free/bonus qty** (D21). Creates batch rows (get-or-create
by item+batch_no; if expiry differs from an existing batch row → error, ask) and
one **cost lot per line**: `unit_cost = amount_paid ÷ (paid + free qty)` (D21).
Cost entry is allowed for employees (D42). Payment: cash now (auto-post a
linked SUPPLIER_PAYMENT) or credit (AP +). Void per D5.

### 7.2 Sale (SI)
Flagship screen (Alpine math). Lines: item search → batch pick (FEFO
suggested, D61; expired blocked, near-expiry warned with days left, D46/D59) →
unit + qty → price (default per D23, editable) → line discount (D20).
Doc discount, charges (D37), checkbox withholding (§6). CASH: payment lines
required, auto-post linked RC on posting. CREDIT: due_date required; credit
check (§8). COGS via FIFO lot consumption ※. Employees never see cogs/margin
(D33). fiscal_receipt_no/machine_total fillable later (D43, §7.12).

### 7.3 Proforma (PF)
Same shape, no ledger effect, printable, "convert to sale" copies lines into
a new draft SALE re-validated at posting.

### 7.4 Consignment issue (CN)
Lines like a sale but **no revenue/AR/tax due**: price, discount and
is_taxable are computed and **frozen on the note** ※ (D6). Stock moves
WAREHOUSE → CONSIGNED(customer) carrying its lots. Adds locked-price value to
customer exposure (D25). Term = settings default, editable per doc (D60).

### 7.5 Consignment settlement (CS)
Loads the outstanding consignment('s remaining quantities). Per line, split
qty into **sold / returned-good / expired-unfit** (Σ splits ≤ outstanding; the
rest stays out on consignment — partial settlements allowed, remainder keeps
the original term). Effects, all at frozen note values:
- sold → stock out of CONSIGNED (those lots), COGS ※ from those lots, revenue
  + tax now (§5 on frozen values), cash or AR (D6)
- returned-good → CONSIGNED → WAREHOUSE (same lots)
- expired/unfit → CONSIGNED → EXPIRED or UNFIT (same lots; the **only** path
  by which consigned goods reach the expired pile — D6; the loss report values
  it at lot cost)

### 7.6 Customer return (CR) (D41)
References an original sale (optional but encouraged). Lines: item/batch/qty,
destination zone (WAREHOUSE if resellable, else EXPIRED/UNFIT). Re-entry
creates a **new cost lot at the returned line's original COGS unit cost**
(from lot_consumptions when the sale is referenced; else owner enters cost).
Money: refund now (money −) **or** credit AR (party −). Tax: negative
tax_total computed by §5 over the returned lines (internal reversal);
fiscal-machine credit reference stored (D41/D18).

### 7.7 Supplier return (SR) (D41)
Stock out of WAREHOUSE (no-negative check), AP − or refund recorded (money +).
Consumes the specific lots being returned (picker).

### 7.8 Payments (RC / PV) (D3/D10/D44)
Payment lines (split cash+bank OK), allocations to specific open documents
(partial OK; advances/overpay/write-off are **out of scope** — total
allocations must equal payment total exactly, D44). Withholding per §6.
Certificate print (D24 mechanics).

### 7.9 WHT remittance (WR) — §6. Expense (EX): category, account, payee
text, amount → money −; consumable purchases for own use are expenses (D16).
Transfer (TR): from-account, to-account, amount → two money rows (D9).

### 7.10 Zone move (ZM)
WAREHOUSE → EXPIRED/UNFIT (employee OK), anything → DISPOSED (owner only).
Only for stock **in our warehouse zones** — consigned stock must come back via
settlement first (D6). Carries lots; loss valued at lot cost.

### 7.11 Adjustment (ADJ) & stock count (SC) (D12/D27/D28)
ADJ: owner-only, reason mandatory, lines ±qty per item/batch/zone. Negative:
consumes lots FIFO. Positive: creates a lot (owner enters unit cost; default =
item's latest cost). SC: start → **freeze snapshot** of expected qty per
(item,batch) in WAREHOUSE (D27); enter counted (re-typable until posted);
warn if any movement happened during the count; post → generates + posts an
ADJ for the differences (owner approves).

### 7.12 Reference-only fields editable after posting
`fiscal_receipt_no`, `machine_total` (D43), `withholding_certificate_no`.
They never touch ledgers; every edit is audited (D47). If machine_total ≠
grand_total → row appears in the reconciliation review list (D43); the
machine's figure is the legal one (D18).

### 7.13 Opening documents (owner-only, go-live) (D2/D39)
OPENING_STOCK (batches + lots at entered cost → WAREHOUSE), OPENING_AR /
OPENING_AP (one per old unpaid invoice: party, original date, amount, due
date — historical dates allowed; **no stock, excluded from sales/purchase
reports**), OPENING_CASH (money row per account), OPENING_CONSIGNMENT (lots
→ CONSIGNED(customer) at locked prices), OPENING_EXPIRED/UNFIT.

---

## 8. Credit limit, alerts, dashboard

**Credit exposure** (D25) = AR balance + Σ locked-price value of stock
currently in CONSIGNED(customer). Checked when posting SALE (credit) and
CONSIGNMENT_ISSUE: over limit → WARN (proceed, flagged) or BLOCK (owner
override with reason), per customer setting, falling back to company default.
Cash sales never count.

**Dashboard** (computed on load): low stock (≤ reorder_level, D34) ·
near-expiry & expired in stock (D46/D59) · consignments due in ≤14 days, ≤7
days, and overdue (D60) · low-margin items (owner only, D23) · fiscal-machine
mismatches (D43) · AR overdue summary. No email/SMS — dashboard only (D60).

---

## 9. Screens

Login · Dashboard (§8) · Settings (owner) · Users (owner) · Audit log (owner)
· Items (list/form + units) · Customers · Suppliers · Accounts · Expense
categories · Fixed assets · CSV imports (owner, §14) · Documents list (filter
by type/status/party/date) + one form per document type (§7; SALE is the
flagship) · Consignments outstanding (with terms + reminder states) ·
Payments (with allocation UI) · Reports hub (§10) · Print views (§13).

Employee visibility rule (D33/D42): employees see receiving cost entry, but
never margin, profit, valuation, item cost history, or cogs on sales.

---

## 10. Reports (all: date-range in fiscal-year presets (D19), CSV export (D36))

Stock on hand (item/batch/expiry/zone) · Stock movement (ledger) · Expiry
(expired + near per D59) · Low stock · **Valuation at lot cost (owner)** ·
Sales by period/customer/item · **Profit: Σ(line revenue − cogs) − expenses
(owner, D33)** · Losses (expired/unfit/disposed at lot cost) · AR aging &
AP aging (per-invoice, from allocations — D2/D3) · Consignment outstanding &
aging · VAT summary (output tax per period; internal cross-check — D18) ·
Withholding certificates received per FY (D51) · Withholding
withheld/remitted/owed (D52) · Expenses by category · Cash/bank book (D11).

---

## 11. Permissions

| Action | Employee | Owner |
|---|---|---|
| Enter/post sales, receivings, payments, returns, zone-moves (to expired/unfit), stock counts | ✔ | ✔ |
| See purchase cost on receiving entry (D42) | ✔ | ✔ |
| See margin/profit/valuation/cost history (D33) | ✖ | ✔ |
| Void, override (negative stock, credit block) — with reason (D28) | ✖ | ✔ |
| Adjustments, disposal, opening docs, CSV import | ✖ | ✔ |
| Settings, users, audit log, backups/restore (D48) | ✖ | ✔ |

---

## 12. Ethiopian calendar (D19)

Store Gregorian everywhere. Display per settings (Gregorian / Ethiopian /
both). Implement one conversion module `core/ethiopian_calendar.py`
(fixed arithmetic: Ethiopian new year = Gregorian Sep 11, or Sep 12 when the
following Gregorian year is a leap year; 12×30-day months + Pagume of 5/6
days) with exhaustive unit tests against known date pairs. Fiscal year =
Ethiopian year starting at settings.fiscal_year_start (default Hamle 1 ≈ Jul 8).
Report presets ("this fiscal year", "last fiscal year") derive from it.

---

## 13. Printing (D17/D18/D49)

Per document type: ≥2 built-in HTML/CSS A4 layouts, selectable in settings
(template editor is **not** v1). Documents printed from this app are
internal/commercial — the legal VAT receipt comes from the client's fiscal
machine (D18); layouts must carry the label "Attachment / not a fiscal
receipt" and show fiscal_receipt_no when present. Withholding certificate
print for supplier payments (D52). Test layouts once with Ethiopic-script
names (D56).

---

## 14. CSV imports (owner-only, D57)

Importers: items (+units), customers, suppliers, opening stock
(item_code, batch_no, expiry, qty, unit_cost), opening AR, opening AP.
Two-phase: **validate the whole file and show a row-by-row error report; post
nothing unless the file is clean.** Successful import creates the
corresponding opening documents (§7.13) and is audited.

---

## 15. Non-functional

- **Backups (D13/D48):** nightly Task Scheduler job: `pg_dump` (custom
  format, online-safe) + zip of media folder → local disk + external
  drive/cloud copy (may be encrypted). Retention: last 14 daily. Restore =
  `pg_restore` into a fresh database — owner-only, documented runbook,
  **tested before go-live**.
- **Updates (R44):** runbook — restore latest backup to a scratch DB, run
  migrations there, then apply to live. Versions pinned.
- **Security (R45):** PostgreSQL bound to **localhost only** — browsers talk
  to the app, never the DB. Strong unique DB password + Django `SECRET_KEY`
  in an env file outside source control; static IP/hostname when the LAN
  arrives; HTTPS optional on closed LAN.
- **Concurrency (D14):** everything in §4; plus the app must run correctly
  with a single PC (v1 reality) and multiple browsers alike.
- **i18n (D56):** wrap everything from day one; `LANGUAGES = [en]` in v1.
- **Clock (D47/R11):** server TZ Africa/Addis_Ababa; clock-anomaly audit rule §3.1.

---

## 16. Build order (phase gates; do not skip)

Each phase = code + pytest suite + the listed acceptance checks green.
**RG** = review gate: a stronger model reviews this phase's code before the
next phase starts (posting, money, and tax are where silent bugs live).

- **P0 — Skeleton.** Project, apps, auth + roles, settings singleton + form,
  audit_log, number_sequences, base templates (Tailwind + HTMX + Alpine
  wired), i18n wiring, Ethiopian calendar module (§12) with tests.
  *Accept:* login works; owner can edit settings; every settings change audited;
  calendar tests pass; DB configured per D66 (PostgreSQL, localhost — verified by test).
- **P1 — Master data + imports.** Items (+units), customers, suppliers,
  accounts, expense categories, fixed assets; duplicate search-as-you-type
  (D26); CSV importers with validate-first (§14).
  *Accept:* re-importing the same file cleanly rejects duplicates; a dirty CSV
  posts nothing.
- **P2 — Posting engine core. [RG]** documents/lines/ledgers/balances,
  Post()/Void() (§4), gapless numbering under concurrency, no-negative CHECK,
  zone model. Prove with the two simplest types: EXPENSE and TRANSFER.
  *Accept:* invariants I1–I6 (§17) pass, including the parallel-posting test.
- **P3 — Receiving + supplier return.** Batches, cost lots, bonus goods
  (D21), D5 void rules, supplier returns (§7.7).
  *Accept:* I7; bonus math; re-receipt same batch new price → two lots.
- **P4 — Sales. [RG]** Sale/proforma/customer return; tax engine §5 (+D64),
  discounts, charges, FEFO + expiry rules, credit check, COGS consumption,
  cash-sale auto-payment.
  *Accept:* I8–I11; golden tax cases (§17) byte-exact.
- **P5 — Payments + withholding. [RG]** RC/PV, allocations/partials (D44),
  withholding both sides + certificates + WR remittance (§6).
  *Accept:* I12–I13.
- **P6 — Consignment.** Issue/settlement (frozen values), partial
  settlements, terms + dashboard reminders (D60), exposure in credit check.
  *Accept:* I14–I15.
- **P7 — Stock ops.** Zone moves, adjustments, stock count with snapshot
  freeze (D27) and movement warning.
  *Accept:* I16.
- **P8 — Opening + go-live tooling.** §7.13 documents wired to the §14
  importers; opening consignment/expired (D39).
  *Accept:* opening AR ages correctly from original dates; opening rows
  excluded from sales/purchase reports.
- **P9 — Reports + dashboard + printing.** §8–§10, §13, CSV export
  everywhere.
  *Accept:* every report total reconciles with its ledger (spot tests);
  employee sees no cost/margin anywhere (assert in view tests).
- **P10 — Hardening + ops.** Backups job + tested restore, update runbook,
  reset_owner_password, deployment as Windows services, R45 checklist,
  Ethiopic print test.
  *Accept:* full backup/restore drill on a scratch machine documented.

---

## 17. Invariant test suite (mandatory, written per phase, never deleted)

- **I1** Posted documents are immutable: any UPDATE to ※ fields fails at the
  model layer (except §7.12 fields).
- **I2** Void reverses exactly: for every ledger, Σ(doc) + Σ(reversal) = 0;
  balances return to pre-post state.
- **I3** No negative stock: concurrent posts of qty 60 + 60 against stock of
  100 → exactly one succeeds (run with real parallel transactions).
- **I4** Gapless numbers: 50 concurrent posts → doc_nos are a gapless
  sequence, no duplicates.
- **I5** Money/cash balance == Σ money_ledger for every account, always
  (property-based over random document sequences).
- **I6** Document dates are non-user-controlled; clock-anomaly writes an
  audit row.
- **I7** Batch cost frozen: re-receiving at a new price never changes an old
  lot's unit_cost or the COGS of already-posted sales.
- **I8** Golden tax cases (D32/D50/D64) — exact expected values, including:
  all-exempt invoice (tax 0); mixed invoice with doc discount (pro-rata,
  remainder on last line); taxable charge on exempt-goods invoice; TOT
  regime; rounding edge `taxable_base = 0.005`.
- **I9** FIFO: sale spanning two lots consumes oldest first; COGS = exact
  Σ qty×lot cost.
- **I10** Expired sale blocked; near-expiry warned at exactly the D59
  boundary.
- **I11** Customer return restores stock as a new lot at original COGS cost
  and writes negative tax equal to §5 over returned lines.
- **I12** Withholding never changes revenue or profit (D53): identical sale
  with/without withholding → identical revenue, COGS, profit; only bucket
  placement differs; invoice fully settled in both.
- **I13** Partial payments: allocations never exceed open balance; aging uses
  original dates.
- **I14** Consignment settlement uses **frozen** prices/tax even after the
  item's price and vat_exempt flag change post-issue.
- **I15** Consigned expired goods can only reach EXPIRED via settlement
  return — a direct ZONE_MOVE on consigned stock is impossible (D6).
- **I16** Stock count compares against the frozen snapshot, not live qty;
  mid-count movement triggers the warning and correct variance.

D66 rider: the suite runs against PostgreSQL — the shipped database. I3 and
I4 exercise real parallel transactions with row locks.

---

## 18. Explicitly out of scope for v1 (do not build, even if "easy")

Full GL/journal/trial balance · depreciation display (D49) · template editor
(D49) · daily cash close (D49) · advances/overpayments/write-offs (D44) ·
master-data merge (R8b) · period locking (D38) · multi-branch, multi-currency,
barcode, mobile, offline sync, internet exposure, e-invoice API (01 §NOT) ·
per-customer standing price lists (R46) · input VAT tracking (D63) ·
free-form returns beyond D41 (R9).
