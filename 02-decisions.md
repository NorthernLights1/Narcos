# Decision Log

Locked design decisions. Newest reasoning wins. Each has: what, why, and (where
relevant) the smallest implementation note. Entries are in **decision-number
order**; a "→" tag on an entry means a later decision changed it — the later
decision wins. All decided **2026-06-29** unless stated otherwise.

> These came out of a skeptical design review of the original build spec. The
> overall architecture (documents → money/stock/party ledgers → read-only
> reports, fix-by-void) is kept. These decisions close the gaps found in it.

---

### D1 — Costing method: batch-actual, frozen
- **What:** Cost of a sale = what we paid for **that exact batch**. The batch
  cost is **frozen after the first receipt** and never overwritten.
- **Why:** One clear source for cost = trustworthy profit and inventory value.
  Overwriting a batch's cost when re-receiving it would silently revalue stock
  already on hand.
- **Note:** Snapshot the batch cost onto the sale line at posting. If the same
  batch is received again at a different price, treat it as a separate cost lot —
  do not overwrite the old cost.

### D2 — Opening balances: detailed
- **What:** At go-live, enter **each old unpaid invoice separately** (customer,
  original date, amount, due date) for receivables, and the same for payables;
  plus opening cash/bank balances.
- **Why:** Real dates on each old invoice mean **aging works correctly from day
  one**. The client wanted full digitized history.
- **Note:** Opening entries record the debt only — they must **not** move stock
  and must **not** appear in the current period's sales/purchase figures. Opening
  cash is a ledger entry, not a separate balance column (see D11).

### D3 — Payments matched to invoices
- **What:** Each customer payment / supplier payment is **tied to the specific
  invoice(s)** it settles.
- **Why:** Without it you can't tell how old a debt is; overdue/aging reports
  become guesses. Pairs with D2.

### D4 — Void cannot create negative stock
- **What:** Voiding a document runs the **same no-negative-stock check** as
  posting. If the reversal would push any item/batch/location below zero, it is
  blocked (owner override, same as posting).
- **Why:** Protects stock integrity, the core promise of the app.

### D5 — No undo of a receiving once sold/moved
- **What:** Once any part of a receiving has been sold or moved, **undoing it is
  blocked outright** (no override).
- **Why:** There's no honest reason to undo a receipt after the goods have left.
- **Future:** Real-world "we sent goods back to the supplier" becomes a
  **separate supplier-returns process** (out of scope for v1). Design so it can
  be added later **without rework** — don't assume returns can never exist.

### D6 — Consignment model
- **What:** Price + tax **locked at issue**; the sale becomes **real at
  settlement/return**; issued quantity splits into sold / returned-good /
  expired-or-unfit. Expired consignment stock reaches the expired pile **only by
  being returned first** (single path, no overlap).
- **Why:** Matches physical reality (goods come back when they settle) and avoids
  double-counting.

### D7 — Tax regime at company level
- **What:** The tax regime (VAT / TOT / none) is a **company setting**, not a
  per-invoice or per-line free choice. Documents can only use that regime or
  none. The stored tax rate must match the tax type.
- **Why:** An Ethiopian business uses one regime; mixing VAT and TOT on one
  invoice is invalid.
- **Refined then simplified:** VAT-exempt items (D30) were considered but
  **deferred for v1 by D45** — every VAT line is 15%. The regime stays
  company-level.
- **→ Round 4 (D50):** VAT-exempt items are **back in v1** — client and law
  confirmed medicines are exempt. The regime still stays company-level.

### D8 — System-generated invoice numbers
- **What:** Sales/tax document numbers are **system-generated and gapless**, not
  hand-typed.
- **Why:** Manual numbers create gaps and duplicates — a compliance problem.
- **Note:** Generate the next number atomically under the posting lock (see D14)
  so two users can't grab the same one.

### D9 — Bank transfer has two accounts
- **What:** A bank/cash transfer records a **"from" account and a "to" account**.
- **Why:** The original design had only one account slot, making transfers
  unbuildable.

### D10 — Payment lines are the source of truth for money
- **What:** When a document is paid, the **per-payment lines** (account, method,
  amount) drive the money ledger — supporting split cash + bank payments. The
  single header account is only a default.
- **Why:** Removes the contradiction between one header account and multiple
  payments.

### D11 — One source for cash balance
- **What:** Cash/bank balance comes **only from the money ledger**. Opening
  balance is a seeded **opening ledger entry**, not a separate column.
- **Why:** Two sources (a column + the ledger) drift apart.

### D12 — Stock-count corrections create a proper adjustment document
- **What:** Posting a stock count creates a real **adjustment document** that the
  stock changes attach to.
- **Why:** Stock changes require a parent document; the count worksheet isn't one.
- **Note:** Snapshot/freeze the system quantity cleanly at count start (see open
  risks for timing).

### D13 — Backups: complete and tested
- **What:** Back up the **database + attached files/media** together, to **PC and
  external drive and/or cloud**, with a **tested restore** before go-live.
- **Why:** The DB dump alone loses scanned invoices/payment proofs; local-only
  copies die with the PC; an untested backup isn't a backup.

### D14 — Concurrency control on posting
- **What:** During posting, **lock** the affected stock rows and the number
  sequence so two simultaneous saves can't oversell or duplicate a number.
- **Why:** The app runs on multiple LAN computers; without this, the
  no-negative-stock and gapless-numbering promises can both fail.

### D15 — No tax fields on cash receipts
- **What:** Tax lives on the **invoice/document**, not on the "money came in /
  went out" records.
- **Why:** Tax on money movements is redundant and invites double-counting.

### D16 — Non-sale items (assets/supplies) — tracked, simple write-off
- **What:** Keep tracking office assets, consumables, and spare parts.
  - **Consumables/supplies:** full cost is an expense the moment bought.
  - **Fixed assets:** store cost, purchase date, and useful-life-in-years; the
    system shows a **simple straight-line yearly write-off** (cost ÷ years).
- **Why:** They're real expenses needed for tax returns. Straight-line is one
  line of math — **not** the full depreciation engine that's out of scope.
- **Decided:** Option A (simple). Full depreciation (schedules, partial-year,
  disposals) can come later if needed.
- **→ Amended in Round 3 (D49):** the write-off/depreciation **display** is
  **deferred to a future version**; v1 still **records** non-sale items and
  **expenses consumables** when bought (client doesn't need depreciation now).

### D17 — Keep flexible print templates
- **What:** Keep the configurable print-layout mechanism (multiple selectable
  layouts per document type).
- **Why:** Product owner wants the flexibility. (Reviewer had suggested
  hard-coding; owner overrode — kept by choice.)
- **→ Amended in Round 3 (D49):** v1 ships **selectable built-in layouts**; the
  template **editor is deferred** (no structural blocker — templates are
  file/record-based).

### D18 — Legal receipt comes from an external fiscal machine
- **What:** The client issues the **legal VAT receipt from a separate
  government-approved fiscal machine** (its own app). This app issues an
  **internal/commercial document only** (order / delivery note / our invoice
  copy). We still compute tax on our documents, but only **for our own totals and
  profit** — the machine is the legal record.
- **Why:** Can't design to a machine we haven't seen; the legal record isn't ours.
- **Note / keep open:** leave a spare field to later record the **machine's
  receipt number** beside our document, so the two can be matched. No machine
  integration in v1. Supersedes open risk R1.

### D19 — Reports use the business fiscal year (Ethiopian calendar)
- **What:** "Annual" / period reports follow the **business fiscal year in the
  Ethiopian calendar**. Start month is **configurable, default Hamle 1**
  (≈ 8 July). Dates may be shown in the Ethiopian calendar.
- **Why:** Annual numbers must match the owner's and accountant's real business
  year, not Jan–Dec. Supersedes open risk R2.

### D20 — Discounts are supported
- **What:** Sales support **discounts at the line level and the invoice level**,
  entered as a **percentage or a fixed amount**. A discount **reduces the taxable
  amount**.
- **Why:** Wholesalers discount routinely; faking it corrupts price and profit.
- **Note:** Store the discount on both the line and the document. Exact UI shape
  to be confirmed. Supersedes open risk R4.

### D21 — Bonus / free goods on purchase are supported
- **What:** A receiving can include **free units**. The batch's actual unit cost
  = **total amount paid ÷ total units received (paid + free)**, so free units
  **lower** the per-unit cost. Consistent with D1 (batch-actual cost).
- **Why:** Pharma suppliers give bonus goods; entering them as normal stock would
  overstate cost. Supersedes open risk R5.

### D22 — "No expiry" flag per item
- **What:** Items can be flagged **"no expiry."** When set, the interface
  **hides/disables the expiry field** and those batches need no expiry date.
- **Why:** Devices/equipment/supplies never expire; forcing a date creates fake
  data. Supersedes open risk R6.

### D23 — Pricing model: maintained price (default), optional auto
- **What:** **Default = maintained price (A):** the owner types a selling price
  per item; it does **not** auto-change. The system **shows the margin** =
  price vs the item's **latest purchase cost** (cost is known because every
  receiving records the batch cost — D1), plus a **low-margin flag/report** for
  items whose margin falls below an owner-set line, so the owner is alerted
  instead of having to watch.
- **Optional auto (B):** a **per-item switch** (off by default) makes the price
  **auto = cost + margin %**. Use it only for items the owner wants to track cost
  automatically.
- **Actual sale price** stays **editable per sale** in both modes.
- **Why:** Most items should hold a market price the owner controls; auto-pricing
  is there for the few that should follow cost. The margin display + alert means
  the owner never has to track cost changes by hand. Supersedes open risk R13.
- **→ Round 6 note:** per-customer **standing price lists** ("pharmacy X always
  gets item Y at price Z") were considered and **deferred** — it's an additive
  feature (a customer×item price table + a default lookup at sale entry) that
  can land later without touching posted history. Tracked as R46.

### D24 — Withholding tax: optional, applied at payment
- **What:** Withholding tax (e.g. 2%) is an **optional** feature chosen **at the
  moment a payment is recorded** against an invoice. When on for a payment: the
  invoice is marked fully settled, the supplier receives the amount **minus** the
  withheld portion, the withheld portion is recorded as **owed to the tax
  office**, and a simple **certificate** can be printed. Off by default.
- **Why:** Only applies to certain vendors/situations; an option lets the client
  use it when needed without imposing it on every transaction.
- **Note:** More than a checkbox — needs a "withholding payable" bucket and a
  certificate print. Keep scope small. Supersedes open risk R3.
- **→ Superseded for v1 by D45:** withholding (both directions — paid and
  received) is **removed from v1 entirely.** Owner: "not a thing unless large
  corporations." Cheap to add later.
- **→ Round 4 (D51, D52):** withholding is **back in v1**, both directions,
  optional, at **3%** (the law changed the rate from 2% in Aug 2025). D51/D52
  are the current word; this entry is kept for the mechanics it pioneered
  (withholding bucket + certificate print).

### D25 — Credit limit: per customer, warn or block
- **What:** A credit limit is the most a **customer** may owe at once (credit
  sales + consignment goods still out there count as exposure; cash sales never
  do). There is a **company default limit**, but each customer can have **their
  own limit**. **Per customer**, the action when exceeded is configurable:
  - **Warn** — staff may proceed; the over-limit is flagged.
  - **Block** — staff cannot proceed; the **owner can override**.
  Both the default limit and the default action are set once and adjustable per
  customer.
- **Why:** Guards against over-extending credit while keeping control where the
  business wants it. Supersedes open risk R7.

### D26 — Duplicate master data: prevent by search, merge later
- **What:** When creating an item/customer/supplier, **show existing matches as
  the user types** so they pick the existing one; enforce unique codes. A
  controlled owner-only **merge tool is deferred** (not v1).
- **Why:** Prevention is cheap and stops most duplicates; merge is tricky under
  the never-erase rule and rare enough to defer. Supersedes open risk R8.

### D27 — Stock count: freeze expected quantity at count start
- **What:** When a stock count starts, **snapshot the system's expected quantity**
  for each item at that moment. Compare the physical count to that **frozen
  number**, not the live one. **Warn** if any stock moved during the count so the
  owner reviews variance before posting.
- **Why:** Counting takes time; sales during the count otherwise create fake
  gains/losses. Supersedes open risk R12.

### D28 — How mistakes are corrected
- **What:** Correction depends on when the mistake is caught:
  - **Before posting** → **edit the draft** directly (drafts are fully editable).
  - **After posting, nothing has used it yet** → **void** it (reverses its
    effect) and enter a corrected one.
  - **After posting, and the stock already moved** (so a void is blocked, D5) →
    the **owner makes a stock adjustment** for the difference, **with a reason
    logged**. Correction of last resort.
  - **During a count** → counted numbers can be **re-typed freely until the count
    is posted**; after posting, fix via another adjustment.
- **Why:** Nothing is ever truly stuck, but large corrections after stock has
  moved go through an owner-approved, reasoned adjustment — keeping the never-erase
  history honest. Ties together D4, D5, D12.

### D29 — Mixed catalog: item kinds and batch tracking
- **What:** The catalog is **not only drugs.** An item can be a **drug, reagent,
  medical supply, or equipment** (microscope, stethoscope, BP machine, etc.).
  - Drug-only fields (generic, dosage form, strength, pack description) are
    **optional** and left blank for non-drugs; the **category** identifies the
    kind.
  - Each item has an **`is_batch_tracked` flag**:
    - **Batch-tracked** (drugs, reagents): every movement records batch +
      (usually) expiry → full recall/expiry tracking.
    - **Not batch-tracked** (equipment, general supplies): movements carry **no
      batch** and no expiry (pairs with D22).
  - Therefore **`stock_entries.batch_id` becomes nullable**, required only when
    the item is batch-tracked. Enforce at posting.
- **Why:** Forcing a batch on every movement (original design) makes equipment
  unsellable without a fake batch. The kind drives two switches — *batch-tracked?*
  and *has expiry?*
- **Don't confuse with D16:** equipment the wholesaler **sells** is a normal
  sellable item; equipment the wholesaler **owns and uses** is a non-sale item.

### D30 — VAT-exempt items (item-level flag)
- **What:** Each item has a **`vat_exempt`** flag. Within the company VAT regime
  (D7), exempt items are charged **0% VAT**, others **15%**. The TOT and none
  regimes are unaffected.
- **Why:** Ethiopia exempts many medicines/medical goods from VAT, so a
  VAT-registered seller mixes 15% and exempt items on the same invoice. Tax is
  company-regime *plus* an item flag — not purely company-level. Resolves R14.
- **→ Deferred for v1 by D45:** VAT-exempt items are **not in v1** — every VAT
  line is 15%. Owner unsure it applies. **Caveat:** exemption on medicines *is*
  real in Ethiopia; it's a **one-boolean add later** and the fiscal machine is the
  legal backstop, so deferring is low-risk.
- **→ Reinstated for v1 by D50 (Round 4):** the caveat came true — client
  confirmed medicines are VAT-exempt. This decision is **live as written**.

### D31 — VAT-exclusive pricing
- **What:** Sale prices are entered **VAT-exclusive**; VAT is **added on top**.
  Company setting.
- **Why:** Standard for B2B wholesale; keeps net and tax cleanly separate.
  Resolves R15.

### D32 — Rounding: VAT computed on the total, once
- **What:** Line **nets** are stored per line. **Tax is computed once at the
  document level** on the **taxable base** = the sum of the **non-exempt** line
  nets (see D30), **rounded once to 2 decimals (half-up)**. Exempt lines
  contribute 0. The document's **`tax_total` is authoritative** — every screen and
  report uses it and **never recomputes tax a different way** (e.g. per line).
- **Why:** Owner confirmed VAT is calculated **on the total, not per item**. A
  single document-level computation, reused everywhere, keeps invoices and reports
  reconciled. (If a per-line tax is ever shown, it's only a display split, never
  the source of truth.)
- **Corrected 2026-06-29:** earlier drafted as per-line rounding; changed to
  total-level per owner. Resolves R16.
- **Schema impact:** store `subtotal`, `taxable_base`, `exempt_base`, `tax_total`
  at the **document** level; per line store the **net** + a **taxable/exempt
  marker**. Do not store per-line tax as a source of truth.
- **→ Simplified for v1 by D45:** with no exempt items, `taxable_base = subtotal`
  and `exempt_base = 0`; VAT = (subtotal − discount) × 15%, rounded once. Keep the
  fields so exemption can be switched on later without a schema change.
- **→ Un-simplified by D50 (Round 4):** exempt items are back, so the full
  taxable/exempt split above is **live**. The D45 shortcut no longer applies.

### D33 — Hide cost and profit from employees
- **What:** Purchase cost, margin, and profit reports are **owner-only**;
  employees cannot see them.
- **Why:** Owners don't want staff seeing cost and margins. Resolves R17.

### D34 — Low-stock / reorder alert
- **What:** An **optional reorder level per item**; the dashboard lists items
  at/below their level. No level set → no alert.
- **Why:** They need to know what to reorder. Resolves R18.

### D35 — Daily cash close: optional, off by default
- **What:** An optional end-of-day cash reconciliation (count the drawer vs
  system cash in/out, flag the difference), enabled in **settings**. **Off by
  default.**
- **Why:** Useful for cash-heavy retail, but this is wholesale — kept available,
  not on. Resolves R19b.
- **→ Amended in Round 3 (D49):** **not built in v1** at all; door left open.

### D36 — CSV export on reports
- **What:** Report screens offer **CSV export** (opens in Excel). A4 HTML
  printing stays as-is.
- **Why:** People pull reports into Excel; CSV is cheap. Resolves R20.

### D37 — Sales: optional extra charges to the customer
- **What:** A **sale** (and proforma) can include optional **non-item charge
  lines** billed to the customer — e.g. **shipping, delivery, handling** — each a
  **label + amount**. They **add to the invoice total and the receivable/cash**,
  count as **revenue** (no stock movement, no COGS), and are **taxable like the
  rest of the sale unless marked exempt** (their taxable amount joins the D32
  taxable base).
- **Why:** The wholesaler bills customers for delivery/shipping on top of goods.
- **Scope:** **sales side only** in v1. Charges on *purchases* (freight /
  landed cost) are out of scope. Recording shipping you *pay* as a standalone
  **expense** is already supported via expense categories.
- **Schema impact:** a small **`document_charges`** table (document_id, label,
  amount, taxable marker). Resolves R24.

### D38 — Documents are dated by system time; no user-chosen dates
- **What:** Every document's date is set **automatically to the system date at
  the moment it is posted**. Users **do not pick it**. "A sale happens when it is
  made; you don't choose when it happened."
- **Exceptions:**
  1. **Go-live opening/migration data** (opening stock, opening receivables/
     payables — D2) may carry **historical dates**, owner-only, during setup.
  2. **Reference-only dates** (e.g. the supplier's invoice date) are stored
     **separately as information** and do **not** change the posting date.
  3. **`due_date`** on credit sales stays user-set — it's a *future* promise, not
     a claim about when something happened.
- **Consequence:** **period locking (R21) is dropped.** With no backdating, nobody
  can quietly change a reported period, so a lock is unnecessary. Corrections
  happen in the current period (consistent with D28).
- **Why:** Honest, simpler, and removes a whole feature.
- **Schema impact:** `document_date` is **auto = system date**, not user-editable;
  keep an optional **`supplier_invoice_date`** reference on receiving.

---

## Round 3 amendments (2026-06-29)

An external senior critique reopened several items. Resolved below; earlier
decisions they change are tagged "→ … by Round 3" above.

### D39 — Opening consignment / expired / unfit at go-live
- **What:** Go-live setup can record stock already **out on consignment** (per
  customer, at the locked issue price) and stock already **expired/unfit**, on top
  of opening warehouse stock and opening AR/AP/cash (D2). Owner-only, historical
  dates allowed (D38 exception).
- **Why:** The business may already have goods at pharmacies / in the expired pile
  on day one. Resolves R27.

### D40 — Manufacturer batch + cost lots (refines D1)
- **What:** Separate two ideas: a **manufacturer batch** (item, batch_no, expiry —
  used for **recall and expiry**) and **cost lots** beneath it (each receipt's
  quantity + cost — used for **valuation/COGS**). The same maker batch received at
  two prices = **one batch, two cost lots**.
- **Costing:** within a batch, consume cost lots **oldest-first (FIFO)** for COGS.
- **Why:** D1's "freeze cost / separate lot on re-receipt" means batch ≠ cost lot;
  modeling both stops recall, expiry, and profit from fighting. Resolves R28.

### D41 — Minimal returns workflow (customer + supplier)
- **What:** v1 includes a **customer-return** and a **supplier-return** document.
  - **Customer return:** stock back (to warehouse / expired / unfit), **refund
    cash or credit the customer's receivable**, **reverse the sale's internal
    tax**, and record the **fiscal-machine credit reference**.
  - **Supplier return:** stock back to supplier, **reduce the payable or record a
    refund**.
- **Why:** For pharma, returns/damage/recall are normal; a stock adjustment can't
  refund a customer or fix tax. Resolves R29; supersedes the R9/D5 deferral
  (scope still bounded to these two documents — no free-form returns).

### D42 — Receiving staff may see/enter purchase cost (refines D33)
- **What:** Staff who **receive goods** can see and enter the **purchase cost**
  (it's on the supplier invoice in their hand). D33 still hides **margin, profit,
  and selling-price analytics** from employees.
- **Why:** Hiding the number they must type in is pointless. Resolves R30.

### D43 — Fiscal-machine reconciliation (refines D18)
- **What:** The **machine's total is the legal/final figure.** The machine receipt
  number is **optional when saving** a sale and can be **filled in later**. If our
  internal total differs from the machine's, **flag it for review** (rare); the
  machine wins. Resolves R32.

### D44 — Payments: partial yes; advances/overpay/write-off deferred (refines D3)
- **What:** v1 supports **partial payments/settlements** against an invoice.
  **Advance payments, overpayments, and write-offs are out of scope for v1.**
- **Why:** Partial is essential; the rest is rarer and can wait. Resolves R33.

### D45 — VAT simplified for v1 (supersedes D30; supersedes withholding in D24)
- **What:** For v1: **no VAT-exempt items** (every VAT line is 15%) and **no
  withholding tax** (neither paid nor received). VAT = (subtotal − discount) ×
  15%, rounded once (simplifies D32 — no separate taxable/exempt base in practice,
  though the fields stay for a later switch).
- **Purchase input VAT (R34 — TABLED):** owner will discuss with the client.
  **Provisional working assumption:** not modeled — stock cost = the goods cost
  you enter; VAT reclaim is the accountant's / fiscal machine's job. Low-risk to
  revisit: tracking VAT-paid separately (option B) is an **additive** change, not
  a rebuild. **Confirm with the client before building the receiving cost logic.**
  Resolves R25, R26; defers R14/D30.
- **Caveat (owner accepted):** VAT exemption on medicines is real in Ethiopia and
  may need revisiting; it's a cheap add later and the fiscal machine is the legal
  backstop, so the risk is low.
- **→ Largely superseded by Round 4:** D50 reinstates VAT-exempt items; D51/D52
  reinstate withholding (at 3%). What survives of D45: the **purchase input VAT
  working assumption** (not modeled; stock cost = entered goods cost — R34 still
  tabled, though now mostly moot since exempt purchases carry no VAT anyway).
- **→ Round 6 (D63):** the input-VAT assumption is **confirmed by the owner**
  — purchases are exempt medical goods. R34 closed.

### D46 — Expiry sale rule
- **What:** **Block** selling **expired** stock; **warn (allow)** on
  **near-expiry** stock. Resolves R35.

### D47 — Audit coverage + clock audit (keeps D38)
- **What:** The audit log explicitly captures **settings changes, overrides,
  master-data edits, and role changes** — not only document posting/voiding. Also
  **audit system-clock changes** and lock the timezone (R11). D38 system-time
  dating stays; **no backdating** is reintroduced. Resolves R31, R37.

### D48 — Backup retention / encryption / restore owner (refines D13)
- **What:** Keep a **retention window** (e.g. last N daily backups), **restore is
  owner-only**, and off-site/cloud backups **may be encrypted**. Resolves R36.

### D49 — v1 scope trims
- **Print templates (D17):** v1 = **selectable built-in layouts**; **editor
  deferred**.
- **Asset write-off (D16):** **defer the depreciation display**; v1 still records
  non-sale items and expenses consumables. *(confirmed by owner.)*
- **Daily cash close (D35):** **not built in v1**; door left open.

---

## Round 4 amendments (2026-07-02) — client tax clarification

The client clarified the real tax picture, and independent research confirmed
it: **medicines are VAT-exempt in Ethiopia** (VAT Proclamation 1341/2024), and
**domestic withholding tax is now 3%** (raised from 2% by Income Tax Amendment
Proclamation 1395/2025, effective 2025-08-01; thresholds ETB 20,000 for goods /
ETB 10,000 for services per transaction). Withholding agents are **"bodies"**
(PLCs, share companies, government offices, NGOs) and specified large sole
proprietors — ordinary sole-proprietor pharmacies do not withhold. This
overturns the D45 simplifications. The project was also named **Narcos**.

### D50 — VAT-exempt items are back in v1 (supersedes the D45 deferral; reinstates D30)
- **What:** The per-item **`vat_exempt`** flag (D30) ships in v1, exactly as
  written there. Invoices mix 15% and 0% lines; VAT is computed on the
  **taxable base only** — the D32 `taxable_base` / `exempt_base` fields are now
  used for real, not just reserved. On the **purchase** side, exempt goods
  arrive with **no VAT** on the supplier invoice — nothing special to model;
  the entered goods cost is the cost (consistent with the surviving D45
  assumption on input VAT).
- **Why:** The client confirmed medicines are VAT-exempt, and the law agrees.
  Most of this catalog **is** medicine, so "every VAT line is 15%" (D45) would
  be wrong on nearly every invoice.
- **Note:** The flag defaults **off (taxable)**; the owner marks exempt items.
  Do **not** auto-derive exemption from the item category — medicines are
  clearly exempt, but reagents/supplies are murky and the owner (with the
  accountant) decides per item. Help text should say "medicines are VAT-exempt
  by law."

### D51 — Withholding on sales (customer keeps 3%) — v1, optional
- **What:** When enabled, big customers ("bodies": PLCs, government, NGOs)
  keep back **3%** of what they pay us and remit it to the tax office in our
  name; we receive the rest plus a **withholding certificate**.
  - **Company setting:** `withholding_on_sales` on/off (default **off**) and
    `withholding_rate` (default **3%** — a setting, because the rate changed
    once already: 2% → 3% in 2025).
  - **Customer flag:** `is_withholding_agent` (default off). Marks PLCs /
    government / NGO customers.
  - **On the sale:** a **"customer will withhold" checkbox**, pre-ticked from
    the customer flag, freely overridable. Ticking it changes **nothing** about
    the invoice's totals or the receivable — it stores the **expected
    withholding** = rate × (invoice total − VAT), shown on screen so staff
    know how much cash to actually expect.
  - **At payment recording (where it becomes real):** the payment form allows a
    **withheld portion** alongside cash/bank lines. Cash + withheld together
    settle the invoice (keeps D3 invoice matching and D44 partials). The
    withheld portion posts to the **"withholding receivable"** bucket (money
    the tax office owes us), with an optional **certificate number** field.
  - **Report:** withholding certificates listed per Ethiopian fiscal year
    (D19) with a total — this is what the accountant uses at year end.
- **Base:** rate × the **VAT-exclusive** amount. Since most goods are exempt
  (D50), that is usually just the invoice total.
- **Why:** The law forces body-customers to withhold. Without modeling it,
  every PLC invoice would carry a fake 3% "unpaid" tail forever, corrupting
  aging and receivables.
- **Thresholds:** the legal thresholds (ETB 20,000 goods / 10,000 services) are
  **not enforced** by the app — the human ticking the checkbox decides. Put the
  numbers in help text only.

### D52 — Withholding on purchases (we keep 3% from supplier payments) — v1, optional, off by default
- **What:** The mirror of D51, for when **our own business** is legally a
  withholding agent. Company setting `withholding_on_purchases` (default
  **off**). When on: a checkbox at **supplier-payment** time withholds 3% of
  the payment (VAT-exclusive base); the supplier's payable is settled in full
  (cash + withheld); the withheld amount posts to the **"withholding payable"**
  bucket (we owe the tax office); a simple **certificate** can be printed for
  the supplier (D24's original mechanics, now at 3%). Remitting to the tax
  office is recorded as a **payment out of that bucket** (normally monthly).
  A small report shows withheld / remitted / still owed.
- **Why:** Whether the client's business is itself a "body" is **unconfirmed**
  (open risk R39). An off-by-default switch costs nothing if unused and avoids
  a rebuild if the answer is yes.

### D53 — Withholding never touches revenue or profit
- **What:** Revenue is always the **full invoice amount**. The withheld 3% is
  **never** recorded as a discount, an expense, or reduced income — it only
  moves money between buckets (receivable → withholding receivable on sales;
  payable → withholding payable on purchases). Profit (D: sale − batch cost −
  expenses) is completely unaffected by withholding.
- **Why:** Withholding is **pre-paid income tax**, not a cost. The owner
  phrased it as "3% less revenue" — that is the natural but wrong intuition,
  and booking it that way would understate sales and corrupt profit. Locked as
  its own decision so no builder "helpfully" subtracts it.
- **Year-end:** the withholding-receivable pile = the year's income-tax
  credit (refundable if it exceeds the tax due); the withholding-payable pile
  should be near zero (remitted monthly). Both reports follow D19's fiscal
  year. The app **reports** these totals; filing itself stays with the
  accountant (same boundary as D18).

### D54 — Legal form is configuration, not code
- **What:** The app does **not** model or assume the business's legal form
  (PLC vs sole proprietorship). All withholding behavior is driven entirely by
  the D51/D52 **settings** — which switches are on, and the rate. Setting up a
  new client = flipping settings at go-live, never changing code. Do not
  hard-code any "this business is a sole proprietorship" shortcut, and do not
  remove the D52 purchase-side switch even if the first client never uses it.
- **Why:** The owner wants to sell this system to other clients. A PLC client
  must withhold on purchases; a sole-proprietor client must not. Both must work
  out of the same build.
- **Consequence:** R39 stops being a design question — it becomes a per-client
  **go-live checklist item** ("what is your legal form? → set the two
  withholding switches accordingly").

---

## Round 5 decisions (2026-07-02) — tech stack + owner answers

The owner accepted the technology recommendation and answered the round-5
questions (R41–R45 and the buildable-spec details) in one pass.

### D55 — Tech stack: Django + PostgreSQL + HTMX/Alpine + Tailwind
- **What:** A **LAN web app**. One PC runs everything (Django + PostgreSQL);
  any other computer just opens a browser. v1 may well run on a **single PC**
  (owner: LAN is a future expansion, not today's reality) — adding more PCs
  later is plugging in browsers, **zero code change**. Server-rendered Django
  templates + **HTMX** for partial page updates + **Alpine.js** for instant
  in-browser math (notably the sales-entry screen) + **Tailwind CSS** with a
  component kit for the look. **PostgreSQL from day one — not SQLite** —
  because D14's row locking and concurrent posting need it, and it makes any
  future hosted/corporate deployment a deployment change, not a migration.
- **Why:** Smallest ops footprint on a modest Windows PC (two services; no
  Node build, no Redis, no Docker); the largest possible training corpus for
  the cheaper implementation model; browser printing covers D17's A4 layouts.
  A Core i3 / 8GB / SSD box is ample — the DB will be a few GB after years and
  the workload a few writes per minute; the UPS (R11) covers the one real risk
  (power loss mid-write).
- **Considered and rejected:**
  - **ERPNext** — no native consignment (D6), its valuation engine contradicts
    D1/D40 cost lots, it forces the full-ERP apparatus that "What v1 is NOT"
    excludes, and GPL complicates resale to future clients.
  - **Bare Frappe framework** — ops stack (bench/MariaDB/Redis/workers) is
    Windows-hostile; MariaDB-first with second-class Postgres; it accelerates
    only the easy CRUD; its niche internals are where a cheaper model errs.
  - **SQLite** — single-writer; fights D14.
  - **React SPA** — doubles the codebase for zero visual gain on a
    forms-and-tables LAN app; a JS frontend can still be bolted onto the same
    backend later if ever wanted.
- **→ Amended by D65 (2026-07-03):** the v1 **database** is **SQLite**;
  PostgreSQL becomes the scale-up path. Everything else in D55 stands.

---

## Round 7 (2026-07-03)

### D65 — v1 database: SQLite; PostgreSQL is the scale-up path (amends D55)
- **What:** v1 ships on **SQLite** — WAL journal mode, `busy_timeout`, and
  Django's `transaction_mode: IMMEDIATE` so every posting transaction takes
  the write lock up front. **Portability rules are binding** so Postgres stays
  a half-day config swap: no raw SQL; unique constraints via Django
  expressions only; the posting engine calls `select_for_update()`
  unconditionally (no-op on SQLite, real row locks on Postgres);
  ledger-reconciliation report totals sum in Python `Decimal`, not SQL;
  invariant tests **I3/I4 must pass against PostgreSQL before any
  multi-user/LAN/hosted deployment**.
- **Why:** The real v1 deployment is one shared everyday desktop (Word etc.)
  run by a non-technical owner. SQLite has **no service to fail or restart** —
  the database is a file, backups are file copies, and the failure surface
  collapses into the app itself. D14's invariants still hold: SQLite has a
  single writer by construction, so IMMEDIATE posting transactions are fully
  serialized — no oversell, no duplicate numbers — and the workload is a few
  writes per minute. The one conceded trade-off: SQLite stores decimals as
  floats under the hood (hence the `Decimal`-summing rule); Postgres remains
  the technically stronger money store, which is why it stays the scale-up
  target rather than being dropped.
- **Migration trigger:** sustained concurrent multi-user posting on a LAN, or
  a hosted/corporate client. Procedure: stand up Postgres → `migrate` →
  dump/load data → run the §17 invariant suite on Postgres → repoint one
  settings entry.

### D56 — English-only UI, translation-ready from day one
- **What:** v1 ships **English only**, but **every user-facing string is
  wrapped in Django's translation system from the first line of code**. Adding
  **Tigrigna and/or Amharic** later = producing translation files, no code
  changes. Unicode names (Ethiopic script in customer/item names) work
  regardless; test print layouts with Ethiopic fonts once.
- **Why:** Wrapping is nearly free now and painful to retrofit across every
  screen. Resolves R41.

### D57 — Go-live CSV import tooling (owner-only)
- **What:** v1 includes **owner-only CSV imports** for: items, customers,
  suppliers, opening stock (with batch + expiry), and opening AR/AP invoices
  (the D2/D39 data). Imports validate first and report row-level errors —
  nothing posts partially or silently.
- **Why:** Hand-typing a pharma catalog is the classic go-live killer, and the
  tooling is reused for every future client (D54). Resolves R42.

### D58 — One unit per item; no pack-breaking
- **What:** Every item is stocked, bought, and sold in **one unit** (its pack).
  Quantity is a plain whole number; the item's "unit" is a **label** (e.g.
  "carton of 100", "pack of 10 strips"), nothing more. **No unit-conversion
  tables, no fractional packs.**
- **Why:** Owner confirmed: the client is a **wholesaler, not a retailer** —
  he never opens a box to sell pieces. "Resells in smaller quantities" means
  *fewer packs*, not *broken packs*. This deletes the R38 unit-conversion
  complexity from v1 entirely.
- **Caveat (owner aware):** unit conversion is one of the few genuinely
  expensive retrofits (it touches stock, costing, and history). Re-confirm
  "never sells broken packs" at go-live sign-off; if it ever changes, it's a
  planned v2 feature, not a patch.
- **→ Superseded by D62 (Round 6, same day):** the caveat itself convinced the
  owner — the conversion model is **kept** so the retrofit can never be needed.

### D59 — Near-expiry horizon: configurable, default 6 months
- **What:** Company setting `near_expiry_months`, **default 6**. Feeds D46's
  warn-on-near-expiry rule and the expiry dashboard/report.
- **Why:** Owner's number; a fixed constant would be wrong for some goods.

### D60 — Consignment term + reminders
- **What:** Each consignment carries a **settlement term** (company default
  **3 months**, adjustable per consignment). The dashboard reminds **2 weeks
  before** and again **1 week before** the term ends, and flags the
  consignment **overdue** once it passes (same dashboard-alert pattern as
  D34's low-stock list — no email/SMS infrastructure).
- **Why:** Consignment is the owner's money on someone else's shelf; per the
  owner, chase *before* the 3-month mark, not after.

### D61 — Batch picking on sale: FEFO suggestion, staff may override
- **What:** When selling a batch-tracked item, the system **suggests the
  earliest-expiry batch first** (FEFO — first-expiry, first-out); staff may
  pick a different batch deliberately. D46 still blocks expired and warns on
  near-expiry; COGS follows D40's cost lots within whichever batch is chosen.
- **Why:** Standard pharma practice, and without a stated rule the
  implementation model would have to invent one. *(Proposed by the design
  reviewer; **confirmed by the owner 2026-07-02**.)*

---

## Round 6 (2026-07-02) — owner's closing answers

### D62 — Units: conversion model kept (supersedes D58)
- **What:** Keep the **unit/pack-conversion model** from the original spec
  (R38): each item has a **base stock unit**; it may define **alternate units**
  (e.g. "carton") with a **fixed conversion factor** to the base unit. Stock is
  **always stored and counted in the base unit**; documents record quantity +
  unit and convert to base at posting. Costing (D40), FEFO (D61), and the
  no-negative-stock check all operate in base units. Day-1 reality: the client
  sells whole packs only, so most items will use a single unit — the
  capability ships anyway.
- **Why:** Owner reversed D58 the same day it was made: retrofitting unit
  conversion later touches stock, costing, and history — exactly the
  "problems later" he wants to avoid. Cheap to carry from the start, expensive
  to bolt on.

### D63 — Purchase input VAT: confirmed not modeled (closes R34; finalizes D45's assumption)
- **What:** Input VAT is **not modeled**. Stock cost = the goods cost entered
  on the receiving. Owner confirmed the premise: purchases are (almost
  entirely) **VAT-exempt medical goods**, so there is normally no input VAT at
  all. If a taxable purchase ever occurs (e.g. equipment), the entered cost is
  simply the full amount paid; any reclaim is the accountant's business.
- **Why:** D45 held this as a provisional assumption pending client
  confirmation — now confirmed. R34 closes.

### D64 — Invoice-level discount on mixed invoices: pro-rata allocation
- **What:** When an invoice carries both taxable and exempt lines (normal
  under D50) **and** an invoice-level discount (D20), the discount is
  **allocated pro-rata across line nets by value** before computing
  `taxable_base` and `exempt_base`. Allocation rounds per line to 2 decimals;
  the last line absorbs the rounding remainder so the allocated parts sum
  exactly. Line-level discounts already belong to their own lines.
- **Why:** Reinstating exempt items (D50) silently **revived R25**, which had
  been declared moot by D45. Without a stated rule, the discount's effect on
  VAT is ambiguous. Pro-rata is the standard, defensible allocation.
  *(Spec-level decision by the design reviewer — flag if the client's
  accountant prefers a different allocation.)*
