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
- **→ Superseded by D66 (2026-07-03):** **v1 ships on PostgreSQL**, not SQLite.
  See D66 for reasoning.

### D66 — v1 database: PostgreSQL (amends D65; final)
- **What:** v1 ships on **PostgreSQL 16** — not SQLite. Windows native service
  with auto-start. Portability rules from D65's original intent still apply:
  no raw SQL; unique constraints via Django expressions only; the posting
  engine calls `select_for_update()` for real row locks (D14); ledger totals
  sum in Python `Decimal`; invariant tests I3/I4 include both SQLite and
  PostgreSQL.
- **Why:** Three reasons override D65:
  1. **Test what you ship.** The real deployment may be on a single PC today,
     but v1 will be a product the owner sells to other clients (D54). Client A
     has a PLC deploying on multiple PCs; client B is a sole proprietor on a
     single PC. We must ship the same codebase. If v1 works on PostgreSQL
     multi-user, it works on SQLite single-writer; the reverse is not true —
     dev on SQLite will mask concurrent bugs.
  2. **PostgreSQL is stable on Windows.** The complexity isn't operational
     overhead (a service that auto-starts, zero babysitting). It's code
     complexity — the portability rules exist precisely because they're
     non-trivial. Keeping those rules but flipping to PostgreSQL *now* means
     writing the posting engine once (correctly), not twice (once on SQLite, once
     retrofitting to Postgres).
  3. **Multi-user within weeks.** The owner confirmed LAN is a "future
     expansion," but based on early adoption patterns in wholesale, it will
     arrive within 6 months. Delaying the multi-user design to "scale-up phase"
     risks a rewrite of the posting engine (the most fragile part of the spec).
     Correct once, on PostgreSQL, from the start.
- **Connection:** Windows native PostgreSQL, localhost-only (D45/R45), password
  via env var (D54/R45). Connection string `postgresql://narcos:$NARCOS_DB_PW@localhost:5432/narcos`
  (development default in settings; production env var).
- **Invariants:** I3/I4 must pass on PostgreSQL (they likely pass on SQLite as
  well due to serialization, but PostgreSQL is the required baseline).
- **No portability penalty.** The code written under the D65 rules is already
  portable; flipping the database is one Django settings change + one migration
  (`manage.py migrate`). The cost of being wrong on the database choice now
  outweighs the cost of flipping.

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

---

## Round 8 (2026-07-10) — pre-demo owner feedback

### D67 — Master codes are auto-assigned (items, customers, suppliers)
- **What:** The item/customer/supplier **code is no longer typed** on the
  forms. A blank code gets the next **`ITM-0001` / `CUS-0001` / `SUP-0001`**
  from the same locked per-key sequence documents use (D8 mechanism). An
  **explicit code still wins** when supplied programmatically — the CSV
  importers keep an optional `code` column so a legacy numbering scheme can
  be migrated; the auto-sequence walks past any number a legacy code already
  occupies. One-time `renumber_master_codes` management command migrates
  hand-typed codes (audited, D47).
- **Why:** Owner: manual codes are busywork and a typo source with no upside
  for this business; the only real use (preserving an existing scheme) lives
  in the import path, not the daily UI.

### D68 — UI workflow layer: entry aids are display-only; the engine stays authoritative
- **What:** The document screens gained: dynamic add-row on line/charge/
  payment/allocation tables; searchable pickers (vendored Choices.js, offline
  like htmx/alpine per D55); batch options labelled `item · batch · expiry ·
  on-hand`; item pick prefills base unit and maintained price (only into
  empty fields); a **live totals preview** on priced forms (mirrors §5 incl.
  D64 allocation and D51 expected withholding); an **expected-totals card on
  draft detail** (server-side, mirrors the handlers' math) so staff confirm
  money **before** posting; a **payment check panel** on RC/PV (money +
  withheld vs. allocations, D44); allocation options show each invoice's
  **open balance** and expected withholding, and list **only unpaid invoices
  of the chosen party**; unit fields offer a datalist of common units (D62's
  free-form entry kept). Every one of these is **display-only**: posting
  recomputes and freezes all numbers through the one engine (D32 unchanged).
- **Why:** Owner reviewed the v1 screens before the client demo: fixed 5-row
  tables, unlabelled pickers, and posting-before-seeing-totals were unusable
  in daily work. Previews may drift in theory; the frozen numbers cannot —
  any mismatch surfaces at post time as a visible bug, not silent corruption.

### D69 — Withholding practice confirmed; threshold automation deferred
- **What:** Owner confirmed the tax reality this install runs under: **all
  medical items are VAT-exempt** (consistent with D50/D63), so the tax story
  is **3% withholding on sales to PLC buyers** (D51 flow): expectation shown
  at sale, actual amount + certificate number entered at payment from the
  customer's certificate, reconciled at filing via the withholding-received
  report. The **checkbox stays manual in v1** — nothing auto-ticks it from
  the customer's withholding-agent flag, and the legal 10,000-birr threshold
  is not encoded. Candidate v1.1 enhancement: default `customer_will_withhold`
  from `is_withholding_agent` (± threshold), owner to decide after go-live.
- **Why:** Captures the owner's stated practice so the config (VAT regime
  kept at VAT, items exempt, withholding-on-sales ON) is a recorded decision,
  not folklore; automation deferred until real usage shows whether staff
  forget the checkbox.

---

## Round 9 (2026-07-12) — owner walkthrough feedback, part 2

### D70 — Consignment withholding is decided at issue; the settlement inherits it
- **What:** The **"customer will withhold"** checkbox moved from the
  consignment settlement to the **consignment issue**. At posting, the
  settlement **inherits the issue's flag** regardless of how the settlement
  was created; the expected 3% is still computed at settlement time, on the
  **sold portion only** (that's when revenue exists). The actual withheld
  amount + certificate stay on the customer payment (D51 unchanged).
- **Why:** Owner: withholding depends on **who the buyer is** (PLC), which is
  known when the goods go out — asking again at settlement invites
  contradiction and forgetting.

### D71 — Settlement is a guided split; its money computes itself
- **What:** A **"Settle consignment"** button on a posted issue creates the
  settlement prefilled: one line per item+batch still out (issued − already
  settled, in base units), with columns **Still out · Sold · Returned ·
  Expired/damaged · Damaged goes to** (EXPIRED/UNFIT only). No unit/factor/
  price columns — settlement quantities are base units and money comes from
  the **issue's frozen prices** (§7.5). The **money due is computed
  automatically** — sold × issue price, taxed at the issue's rate snapshot;
  returned/expired earn nothing — shown live on the form (below the payment
  lines) and server-side on the draft before posting. The blank-form
  settlement path remains for edge cases but shows no live money until an
  issue is linked.
- **Why:** Owner: the settlement form looked like a sale and left the final
  amount to mental arithmetic. The engine already knew every number; the
  screen now says it.

### D72 — Payment amounts prefill; a manual edit always wins
- **What:** Money boxes fill themselves wherever the total is knowable, and
  never overwrite a user's own numbers (so splitting across cash/bank stays
  manual): cash sale/settlement → first payment line tracks the grand total
  (cleared when switched to credit); customer/supplier payment → picking an
  invoice prefills the allocation with its **open balance**, the **withheld
  amount** from the invoice's expected withholding, and the first payment
  line with allocations − withheld; expense → payment mirrors the entered
  total. **Receivings deliberately do not prefill**: empty payment lines mean
  "bought on credit" (the normal case), and auto-filling would silently turn
  every delivery into paid-in-full and spawn auto supplier payments.
- **Why:** Owner: totals must not be left to manual arithmetic at entry time.
  The engine's exact-match rules (D3/D44) still verify everything at posting.

**Also in this round (no separate decisions):** the register page label is
**"Transactions"** (URLs, code, and these docs keep saying *document* — D28's
vocabulary is unchanged); grey placeholder hints on all forms; **D23 auto
pricing implemented** (AUTO items prefill latest lot cost × (1+margin), the
item form shows selling price *or* margin per mode); batch pickers filter to
the line's item and show `exp · on hand` under the box once picked; receiving
column renamed **"Cost paid / unit"** vs the sale's **"Selling price / unit"**;
static assets carry a `?v=` cache-buster (bump when app.css/app.js change).

### D73 — Settlement visibility is derived, never stored
- **What:** Every posted document that can be settled shows a **derived
  settlement state** — computed live from posted payment allocations and
  settlement lines, never written to a column (D11; a stored flag would also
  collide with I1 immutability and drift on voids). Money targets (credit
  sales, credit consignment settlements, receivings, opening AR/AP) walk
  **Unpaid → Partial → Settled**; consignment issues walk
  **Open → Partial → Closed** on base-unit quantities. Cash sales/settlements
  show nothing — their auto payment settles them at posting. Surfaces:
  - **Transactions list:** a Settlement column (badge + `open X of Y` /
    `N of M out` for partials) and a filter (**Outstanding / Settled**) that
    runs in SQL via three subquery annotations — no per-row queries.
  - **Document detail:** a Settlement card — grand total / settled to date /
    outstanding with the **allocation history** (each payment linked);
    payments show the mirror table (allocated to which invoice, still open);
    issues show what is still out per item+batch and which settlements
    closed them. The summary grid links `related_document` (CS→CN, CR→SI).
  - **Reports:** AR aging, AP aging, and Consignment outstanding are now
    **open-item reports as of today** — they deliberately ignore the period
    filter, because an unpaid invoice from last fiscal year must not vanish
    under a "this FY" default. Aging gained a **Settled** column.
- **Why:** Owner: knowing which credits, consignments, and supplier payments
  are still outstanding required opening each customer/supplier. The engine
  already knew (open_balance, settlement-line sums); the screens now say it,
  and voiding a payment reopens the target automatically because nothing is
  cached.

### D74 — One-click settlement entry: buttons and pickers prefill the whole document
- **What:** Three workflow closures on top of D71/D72/D73:
  1. **Record payment / Pay supplier button** on any posted invoice that still
     has an open balance (credit sale, credit consignment settlement,
     receiving, opening AR/AP). It creates the payment draft server-side with
     the party set, the allocation at the invoice's **current open balance**,
     and the **expected withholding** prefilled (when the direction's
     withholding setting is on, capped at the open balance). Staff pick the
     account and post; the cash line computes itself on page load
     (allocations − withheld). The posting handler still re-checks everything
     under lock (I13) — the prefill is display convenience only (D68).
  2. **Picking an invoice on a blank payment fills the party too**: target
     options now carry `data-customer`/`data-supplier`, and an empty
     customer/supplier box is set from the picked invoice. A party the user
     chose is never overwritten.
  3. **Picking an issue on a blank consignment settlement jumps to the guided
     draft**: selecting `related_document` on the *create* form redirects to
     the D71 `?from=` flow, so the lines arrive prefilled with what is still
     out per item+batch. Editing an existing draft never redirects.
  Settlement badges are also color coded now — Unpaid/Open rose, Partial
  amber, Settled/Closed emerald (the D73 classes were being purged by the
  Tailwind content scan because `badge-{{ state }}` is composed at render
  time; they joined the safelist alongside the status badges).
- **Why:** Owner: reaching a settlement screen from the document — and
  having every knowable number already in the boxes — beats retyping what
  the engine can compute. Same principle as D71/D72: the engine already
  knows; the screen should say it.

### D75 — Dedicated Inventory page; the low-stock rule made visible
- **What:** A read-only **Inventory** page (nav: Work → Inventory) showing
  every active item with its **Warehouse · Consigned · Expired/Unfit · Total**
  quantities, reorder level, and an **OK / Low / Out of stock** badge, with
  search and Low/Out filters. Each item drills into a detail page: stock per
  batch (expiry status flagged), who holds the consigned quantity, and the
  last 15 stock movements linked to their documents. Quantities only — no
  costs or margins, so both roles may look (D33 untouched).
  The **low-stock rule is unchanged but now stated on screen**: an item is
  low when its *warehouse* quantity is at or below the reorder level. Goods
  sold and goods out on consignment are both already outside the warehouse,
  so both push an item toward low — no change needed there. The dashboard
  card now shows *qty in warehouse (reorder at N)* per item, links each item
  to its inventory page, and sorts worst shortfall first (it caps at 10).
- **Why:** Owner set a reorder level and could not tell why the dashboard
  didn't react (the item's warehouse stock was above the threshold, but no
  screen showed the two numbers side by side), and had no convenient view of
  available stock beyond the transactions register and the CSV-style
  stock-on-hand report. The inventory page shows the numbers the engine
  already keeps.

## Round 10 (2026-07-15) — reconciliation & finance visibility package

### D76 — Party statement, built on PartyLedger; party+date filters on Transactions
- **What:** **Reports → Statement**: pick customer or supplier plus a date
  range and get *opening balance → every AR/AP movement with a running
  balance → closing balance*, with CSV export and a print view. Rows come
  from **PartyLedger only** (the append-only AR/AP ledger), so the statement
  inherits the engine's exactness: cash documents never appear (they create
  no debt — the auto payment settles them at posting), and voided documents
  show as explicit reversal rows that net to zero instead of silently
  disappearing. Date basis is `document_date` (consistent with every other
  report, and correct for backdated opening docs). The Transactions list
  also gained **Customer / Supplier / From / To** filters; drafts use
  `created_at` as their date fallback so a date filter can't hide them.
- **Why:** Owner: when reconciling with a customer (often a fellow vendor)
  he needs "everything for this party in this period" on one printable page
  both sides can walk through line by line — not a mental assembly from the
  transactions register. Debit = they owe more (customer view) / we owe
  more (supplier view); the header states which reading applies.

### D77 — Attachments: evidence follows the void pattern
- **What:** Any document can carry **attachments** (scanned supplier
  invoices, delivery notes, certificates): PDF/JPG/PNG/WebP, 10 MB max,
  10 per document, magic-byte checked on upload so a renamed executable
  can't pass as a "pdf". Bytes live on disk under `media/attachments/`
  with server-generated UUID names (the user's filename is metadata only);
  the DB row holds the pointer + who/when. Files are served only through a
  login-required view — `media/` has no public URL. Uploads are allowed on
  drafts **and posted documents** (paper evidence often arrives after
  posting; attachments are reference material like `fiscal_receipt_no`,
  so I1 is untouched). Deletion is allowed only while the parent is a
  DRAFT (uploader or owner). After posting, nobody deletes — the owner may
  **void** an attachment with a reason (hidden from staff, visible to the
  owner, bytes preserved). Every add/delete/void writes an audit row.
- **Why:** Owner asked for scanned supplier invoices on receivings. The
  no-delete-after-posting rule mirrors documents themselves: fiscal
  evidence must survive; mistakes are annotated, never erased. Backups
  already cover `media/` (RUNBOOK's media.zip).

### D78 — Cash Sales Attachment print layout; the master fields it needs
- **What:** A third print layout, **Cash sales attachment** (next to
  Compact/Detailed), modelled line-for-line on the paper form the owner's
  trade expects: company header (name/TIN/phones), Sales Date + FS Receipt
  No + CSI No (the document number), buyer block (trade name, TIN, license
  no, phone, mobile, city), a fixed 20-row line table — *(Generic) Brand
  Name, Strength and Dosage · UoM · Batch · Expiry · Qty · Unit Price ·
  Total* — Sub Total, received-in-good-condition line, Prepared/Delivered/
  Approved signature lines, the "not valid unless fiscal receipt is
  attached" note, and the 4-copy distribution footer. Reachable from any
  sale's print page. To feed it, master data gained **CompanySettings.
  phone** and **Customer.license_no / mobile / city** (all optional, all
  audited, on the forms with placeholders).
- **Why:** Owner supplied a competitor's form as the format both sides of
  the trade recognize; pharma buyers must be licensed, so License No. is a
  real field, not decoration. FS Receipt No prints as a fill-in line when
  blank — it is stamped from the fiscal machine after the fact (D18/D43).

### D79 — Finance overview; AP gets due dates; TIN links the two faces of a vendor
- **What:** Owner-only **Finance** page (nav: Work → Finance): one screen
  with net position (money + AR − AP − withholding owed, red when
  negative), per-account cash/bank balances, AR and AP totals with their
  overdue slices and top-3 parties, stock at FIFO cost **and** at selling
  price (D23 rule — the gap is shelf margin), month-to-date revenue/COGS/
  gross/expenses/net, and both withholding positions. Every block is a
  read-only sum over existing ledgers and links to its detailed report;
  no new bookkeeping, no new mutation paths. **Receivings now capture a
  due date** (supplier credit terms) and the dashboard gained an **AP
  overdue** card mirroring AR overdue. A **general ledger was considered
  and deliberately rejected** for v1: the client needs awareness, not
  double-entry bookkeeping; a journal-entry CSV export for the accountant
  can come in v1.1 if asked.
  **Customer-who-is-also-supplier**: no schema merge. The same business
  gets a Customer and a Supplier record sharing a TIN; the statement view
  cross-references them ("same TIN as supplier SUP-x — you owe them Y",
  with a jump link). **No automatic netting** — each side settles with
  real payment documents, which is what tax filing needs.
- **Why:** Owner: "I don't want them to do this in their heads — stocks
  and finances staring them in the face." Estimated revenue = stock at
  price; estimated tax stays out (Ethiopian profit tax depends on
  category — showing a wrong estimate is worse than showing gross profit).

## Round 11 (2026-07-16) — the CN-000002 lesson: prices live on items only

*Trigger: consignment CN-000002 was issued at a hand-typed 0.40/pair while
the item master said 0 (price set to 10.00 only the next morning). The
settlement then correctly billed 160.00 for 400 pairs — right math on wrong
data. Audit log reconstructed the whole sequence in one query.*

### D80 — Sale/proforma/consignment-issue prices come from the item master
- **What:** On SALE, PROFORMA and CONSIGNMENT_ISSUE lines the unit price is
  **no longer typed**. The input is readonly in the UI (still shown, still
  live-prefilled when an item is picked), and the server recomputes it from
  the item master in `DocumentLineForm.clean()` regardless of what the
  browser submits — maintained price, or latest cost × (1 + margin) for
  AUTO items (D23). An item with no usable price is refused on those lines
  with a pointer to fix the item first. **Discounts (line or document) are
  the only sanctioned way to charge less.** Draft lines re-derive their
  price on every save, so re-saving a stale draft picks up a master-price
  fix. CUSTOMER_RETURN and OPENING_CONSIGNMENT keep manual prices (returns
  honour the original sale's price; opening docs carry pre-system
  agreements). RECEIVING costs stay typed — costs come from the supplier's
  invoice, not from us.
- **Why:** Owner rule after CN-000002: "price should not be edited on sale
  or consignment — it can only be edited on items; if they want less, they
  can do a line or doc discount."

### D81 — Every item must carry a usable price
- **What:** ItemForm and the items CSV import now refuse a MANUAL-mode item
  without a maintained price > 0; AUTO mode still requires its margin %
  (existing rule). Employees editing an AUTO item aren't blocked (they
  can't see pricing_mode, D33) — the instance's mode decides. Existing
  priceless items are caught on their next edit, and immediately at the
  sale/issue line by D80's refusal.
- **Why:** Owner: "on items, setting price should be mandatory — either
  auto-margin or maintained price." An unpriced item is unsellable under
  D80, so the gap is closed at both ends.

### Also in this round
- **Mixed-price settlement preview warns instead of undercounting:** if an
  item was issued at more than one price, the sold row has no single frozen
  per-base value; the live preview now says so explicitly ("posting
  computes the exact total and will ask you to split those lines") instead
  of silently pricing those rows at zero. Server-side math was always
  correct — this fixes only the display.
- app.js cache-buster bumped to 20260715d.
- **AR/AP balances as of a date** (client request): two new reports —
  one row per customer/supplier with a non-zero balance on the chosen end
  date, biggest first, grand total at the bottom, CSV. Deliberately
  separate from aging (no due dates, no buckets): aging answers "how
  late", this answers "who owed what on that day". Each figure ties out
  with the party's statement closing balance for the same date and the
  grand total with the Finance page — total → per-client → per-document,
  three views of one ledger.
- **Report audit — no deletions, settings-aware visibility instead**
  (owner asked to "remove what is not necessary"): every builder earns
  its keep for *some* configuration, so nothing was deleted; instead
  reports that are permanently empty under the company's settings vanish
  from the hub and 404 directly — VAT summary when tax regime is NONE,
  withholding-received when withholding-on-sales is off,
  **withholding-payable when withholding-on-purchases is off (this
  client's case — it was the one dead report)**. Flip the setting and
  the report returns. The hub is now grouped (Stock / Sales & profit /
  Receivables & payables / Tax / Money) with the Statement pinned in the
  parties group. Note: the "Withholding remittance" document type in the
  More… menu is dead under the same flag — candidate for the same
  treatment next round.
- **Finance stock block split by location**: "In your warehouse" vs "At
  customers on consignment" (both at FIFO cost), then total at cost and
  at selling price. Money on a consignee's shelf is a different risk
  than money in your own store — it can't be sold to anyone else and
  may come back expired. Same ledger, one extra grouping key.
- **Print hygiene (owner feedback):** every SALE / CONSIGNMENT_ISSUE /
  CONSIGNMENT_SETTLEMENT printout now carries a large diagonal
  **ATTACHMENT** watermark on every page — the legal invoice is the
  fiscal pad printed by government-approved vendors (D18); our page
  accompanies it and must never pass for it. Internal master codes
  (CUS-0001…) no longer print in the party box — the other business
  files this paper and the code means nothing to them (the Cash Sales
  Attachment layout already printed name-only). Internal prints
  (receivings, expenses…) get no watermark. The URL/date line at the
  page edge is the **browser's** print header/footer, not ours — untick
  "Headers and footers" in the print dialog once; the browser remembers.
- **Backup/restore goes Linux-first (deployment: Linux server, Docker
  planned):** `scripts/backup.sh` + `scripts/restore.sh` are canonical;
  the PowerShell pair stays only as a Windows fallback. New in both:
  **media restore** (the gap — restored attachment rows pointed at
  nothing), dump verification at backup time (`pg_restore --list`), and
  a refuse-existing-target guard so a typo can never overwrite live.
  RUNBOOK gained the **bare-metal disaster recovery** procedure (10
  steps, fresh machine → verified app, including "open a document with
  an attachment" as the media proof) and Docker guidance (back up from
  the host via pg_dump, never volume snapshots alone). Drill executed
  for real on the dev machine: backup → scratch restore → identical
  counts (29 docs / 7 ledger rows / 2 attachments) + media files back.

## Round 12 (2026-07-17) — print fixes from the field

### D82 — Party TIN prints in the party box; template-comment leak fixed
- **What:** Sale/consignment (and every other document) printouts showed a
  stray paragraph of template-comment text in the party box: Django only
  treats `{# … #}` as a comment when it stays on **one line**, and this one
  had been wrapped across two, so it rendered literally on paper. The
  comment is now a single line and a regression test asserts no `{#` ever
  reaches the rendered page. In the same box the party's **TIN** now prints
  under the name (customer or supplier; skipped when blank, and free-text
  payees have none). Master codes (CUS-0001…) still never print (D-Round-10
  rule, unchanged). The Cash Sales Attachment layout already printed the
  buyer's TIN and is untouched.
- **Why:** Owner feedback on printed sales/consignments: the explanation
  text was never meant to appear on the document, and "the TIN number of
  the party should be included, not just the name" — the receiving business
  files this paper and identifies parties by TIN.

## Round 13 (2026-07-17) — on-prem Docker deployment

### D83 — Dockerized on-prem deployment: Windows host, plain-HTTP LAN, GHCR pipeline
- **What:** The app now ships as a two-container Docker stack — `app`
  (Django on **waitress**, published on host port 80) and `db` (PostgreSQL 16,
  on the internal network only, **never** published; R45 held tighter than
  before). New artifacts: `Dockerfile` (collectstatic at build, tini as PID 1),
  `compose.yml`, `docker-entrypoint.sh` (wait-for-db → auto-migrate → serve;
  opt out with `NARCOS_AUTO_MIGRATE=0`), `.env.example`, `.dockerignore` (note:
  `docs/` is a Django app, not documentation — it stays in the image), and a
  `.github/workflows/release.yml` that on a `v*` tag runs pytest then builds a
  `linux/amd64` image and pushes it **private to GHCR**. Settings gained
  `CSRF_TRUSTED_ORIGINS` derived from `ALLOWED_HOSTS` (with a
  `NARCOS_CSRF_TRUSTED_ORIGINS` override) and a `NARCOS_BEHIND_TLS_PROXY` flag
  that gates `SECURE_PROXY_SSL_HEADER` + secure cookies — **off by default**
  because the LAN deployment serves plain HTTP and forcing secure cookies would
  break login. Backup/restore got container-aware twins
  (`ops/docker-backup.ps1`, `ops/docker-restore.ps1`) that run `pg_dump` /
  `pg_restore` inside `db` and `manage.py` / `tar` inside `app` via
  `docker compose exec`; the restore refuses a non-empty target so a typo can't
  overwrite live. `ops/deploy.ps1` wraps update as backup → pull → up.
  `ops/DEPLOYMENT.md` is the Windows-first runbook; `ops/RUNBOOK.md` reframed
  (the old "works unchanged in Docker" note was wrong — no host `.venv`/`pg_dump`).
- **Why:** Client requires on-prem (financial pharmacy data, all-LAN users) on
  a **Windows 10** desktop, with internet that can't be relied on. Decisions
  locked with the user: (1) **Windows Task Scheduler** at **16:00** with
  "run missed task at next boot" (staff leave ~17:00, power is unreliable, so
  back up while the PC is on) — not a cron sidecar, since both need Docker/the
  auto-login session running anyway. (2) **Auto-migrate on start**, with the
  deploy wrapper taking a backup first. (3) Retention **14 nightly + one per
  month for a year** (financial records need a longer tail than 14 days).
  (4) **`.env` copied into every backup** — the only recovery input not in git
  or the image. Static IP (DHCP reservation) instead of a domain; a local DNS
  name can be layered on later without touching the containers. 8 GB RAM
  confirmed adequate; `.wslconfig` memory cap documented. Not RAM-driven —
  Docker on Windows adds WSL2 overhead; it's chosen for clean packaging,
  reproducible CI builds, and one-command deploy/DR.

## Round 13 (2026-07-26) — first client field-testing round

*Trigger: the owner ran the app with real trade for a stretch ("so far so
good") and came back with four paper-and-keyboard findings.*

### D84 — Free units come off the receiving interface
- **What:** The receiving form and the document detail table no longer
  show the **Free** box/column. `free_qty` stays on the model and in the
  D21 posting math (amount paid ÷ all units received), so any old
  document that carried bonus goods keeps its numbers — the UI just
  stops asking.
- **Why:** Owner: "there are no free units" — this business never
  receives bonus goods, and the box only confused staff.

### D85 — Printout totals read at the bottom
- **What:** On the generic document printout (compact/detailed layouts)
  the Subtotal / Tax / Total boxes moved from the header to the bottom
  of the page, after the goods (and after charges/payment lines on the
  detailed layout). The party box (name + TIN, D82) stays at the top.
  The Cash Sales Attachment already printed its total under the table
  and is unchanged.
- **Why:** Owner: "the total of the attachment printout should be
  written on the bottom" — that is how the trade reads an invoice:
  goods first, money last.

### D86 — A cleared payment amount is not a payment
- **What:** A never-saved payment row whose amount is empty is treated
  as blank and skipped at save, even when an account or method was
  picked on it. Already-saved rows still validate — real money is
  removed with the ✕ column, never by clearing a box.
- **Why:** Field bug: staff typed an amount, changed their mind and
  deleted it; the leftover account/method selections made Django treat
  the row as filled, so the save bounced with "enter a number" on a row
  the user considered empty.

### D87 — Payment lines start as a single row
- **What:** The payment-lines table renders one blank row instead of
  three; "+ Add row" covers the split-across-accounts case and ✕
  removes a row. (The cash-prefill JS already targeted the first row
  and needs no change.)
- **Why:** Owner: payments almost always go into a single account —
  three blank rows suggested something more was expected.

### D88 — Rows are removed with a ✕ button, not a checkbox
- **What:** Every line/charge/payment/allocation row now carries its own
  **✕ button** in the last column. Clicking it removes that row there and
  then: a row the server has never seen is taken straight out of the page,
  and a saved row is hidden with Django's `DELETE` box ticked behind it so
  the deletion lands on save. The checkbox itself is never shown — it stays
  in the markup because it is the mechanism Django needs on submit.
  `TOTAL_FORMS` deliberately is **not** decremented: it only says how many
  forms to build, and leaving it alone keeps every remaining row on the
  index it was rendered with (renumbering mid-form is how formsets get
  their wires crossed; a removed row's fields simply arrive empty and are
  ignored).
- **Why:** Owner during field testing: the tick boxes at the end of each
  row "have no purpose" — selecting one then saving is not how anyone
  expects to delete a row. The button does what it says, immediately.

## Round 14 (2026-07-28) — field-testing round 2: fit the app to this trade

### D89 — Four settings flags decide which boxes the forms show
- **What:** Company settings gained **Fiscal machine present**, **Discounts
  in use**, **Pack conversion (factor) in use** and **Sale price editable
  at the time of sale**. Off/on they hide or show the machine-total box,
  both discount boxes (document and line), and the line factor box; the
  last one hands pricing back to the counter. All four default to today's
  behaviour (present / in use / in use / **not** editable), so nothing
  changes until the owner flips a switch.
- **How:** `fields_hidden_by_settings()` subtracts names from the field
  lists `DocumentForm` and `DocumentLineForm` already filter by, and
  `formsets_for` turns `master_priced` off when the price is editable.
  Hiding is **entry-only**: the columns stay on the models and in the
  posting math, so documents posted while a flag was on keep their
  discounts, machine totals and pack factors, and still total the same.
  The totals preview already read those boxes defensively, so a missing
  one simply counts as zero.
- **Why:** Owner after field testing: this business has no fiscal machine,
  gives no discounts and buys in base units, so three boxes were dead
  weight on every screen; and staff sometimes need to agree a price at the
  counter.
- **Note:** `sale_price_editable` deliberately reverses D80 (the CN-000002
  lesson — a hand-typed price is what caused it). It stays **off** by
  default and the safer route is still a line or document discount.

### D90 — "Correct this document": void and reopen in one click
- **What:** A posted document shows one **Reason** box with two buttons:
  **Correct this document** (voids it *and* hands back an editable draft
  copy — party, lines, charges, payments, allocations, with a note
  pointing at the document it replaces) and **Void only** (the old
  behaviour). Owner only; the reason is still required and still audited.
- **How:** `_duplicate_as_draft()` copies exactly the fields each doc type
  asks staff to type, read from `DOC_CONFIG` unfiltered — so a discount
  captured before D89 hid the box is still carried over. Void and copy run
  in one transaction: when the void is refused (D5, the goods have already
  moved on) nothing is written and no orphan draft survives.
- **Why:** Owner asked for editable posted documents. Editing them would
  break the ledgers those documents wrote — stock, money, party,
  withholding and the FIFO cost lots later sales already consumed — and
  leave the paper disagreeing with every report built on them. The real
  complaint was that fixing a mistake meant retyping the whole document.
  This removes the retyping and keeps the books reversible rather than
  erasable.

### D91 — The company phone prints on every layout
- **What:** `print.html` now prints **Tel** under the company TIN, as the
  Cash Sales Attachment already did.
- **Why:** Reported as "phone number not showing on attachments". The
  attachment layout was in fact already printing it — the field was simply
  **empty in Settings** (it was added with D78, after this install last
  edited its settings, so it had never been filled). Filling *Settings →
  Phone numbers* makes it appear; the generic layouts were the real gap.

## Round 15 (2026-07-28) — correcting becomes reversible

### D92 — The void waits for the replacement to be posted
- **What:** Amends D90. **Correct this document** no longer reverses
  anything: it opens the draft copy and records what that copy replaces
  (`corrects` + `correction_reason`). The original stays **live and
  counted** until the copy is posted; posting it voids the original
  **first, inside the same transaction**, then applies the replacement.
  Delete or abandon the draft and nothing ever happened. Posting a
  correction is **owner-only** (void always was).
- **Why:** Field testing: "it should not be voided until the new document
  is posted." Correct — under D90 an interrupted correction left the books
  holding a reversal with nothing in its place: the sale gone, stock back,
  money undone, and no replacement. That is worse than the mistake being
  corrected.
- **How, and why the order matters:** the original still *holds* the stock
  and money it consumed, so the replacement cannot pass its own checks
  while the original stands — the void has to run before them, not after
  the post. One transaction covers both, so a failure in either half
  leaves both untouched: never a voided original without its replacement,
  never both live at once. (A test proves it: a sale of 8 packs out of 10,
  corrected to 9, posts only because the void hands the goods back first.)
- **Guards:** one open correction per document; the original must still be
  posted when the replacement lands (otherwise the correction is refused
  with a message, not a crash); the D5 voidability check runs early at
  click time as **advice** and again binding at post time, because the
  goods can move in between. Both documents carry a banner saying a
  correction is pending.

### D93 — Destructive buttons say what they will do
- **What:** A single `<dialog>` in `base.html`, filled from
  `data-confirm-*` attributes on whichever button was pressed, so each
  action states its own consequence and reads the owner's typed reason
  back to them. Wired to three buttons: **Correct** (reassuring — nothing
  changes yet), **Post** on a correction draft (the real warning — this is
  when the void fires and it cannot be undone), and **Void only**.
- **Why:** Owner: "there should be a clear warning ... so the user
  understands what the platform is doing." D92 also flipped which button
  is dangerous — correcting is now reversible, while **Void only** still
  reverses a document with nothing replacing it, and it previously had no
  confirmation at all.
- **How:** the click is intercepted, not the submit, because Correct and
  Void share one form and differ only by `formaction`;
  `requestSubmit(button)` replays the exact button after the owner agrees.
  `reportValidity()` runs first so the browser's own "reason is required"
  still fires. Native `<dialog>` brings the focus trap and Esc handling;
  with JS off the buttons simply work as before.

## Round 14 (2026-07-30) — the money follows the void

*Trigger: a probe showed that voiding a settled invoice left the customer
at −200.00 — the business owing them the money they had paid — with the
allocation still pointing at a document that no longer existed.*

### D94 — One payment settles one invoice
- **What:** A receipt (RC) or payment voucher (PV) may allocate to exactly
  **one** invoice. Posting one with two or more targets is refused with a
  pointer to enter a separate payment per invoice. Partial payments are
  untouched (D44) — one invoice, part of its balance, still fine.
- **Why:** Owner: "there should never be a single receipt to settle
  multiple invoices, it should be a single invoice a single receipt." It
  also makes D95 unambiguous: a receipt reversed along with its invoice
  can never be un-settling somebody else's invoice at the same time.
  Existing data already complied (10 allocations, all single-target), so
  nothing needed converting.
- **Cost accepted:** a customer settling three invoices with one bank
  transfer is now three receipts against that transfer — clearer books,
  slightly more typing, marginally more work at bank reconciliation.

### D95 — Voiding a document reverses the payment that settled it
- **What:** `void()` already cascaded to documents linked by
  `related_document` (a cash sale's auto receipt, a stock count's auto
  adjustment). It now also reverses any **posted payment allocated to the
  document being voided** — the case that was missed, because such a
  payment is a separate document linked only through `PaymentAllocation`.
  The cascade records why: *"<reason> (settled SI-000012)"*. A payment the
  owner had already voided is skipped, not voided twice.
- **Why:** Reversing an invoice only undid what the invoice itself wrote.
  The receipt's own ledger rows survived it, so the books read −200.00
  against the customer. Measured before the fix: sale 200 → owes 200;
  payment 200 → owes 0; **void → owes −200**. After: **0**.
- **Warning first:** the void and correct dialogs (D93) now name the
  payment that will be reversed — *"The payment that settled it (RC-000004)
  is reversed with it, so the money goes back too."* Voiding stays a
  deliberate, confirmed act rather than a block; the owner asked for a
  clear warning, not a refusal.

## Round 15 (2026-08-02) — the rest of the void gaps, and warnings that get read

*Trigger: after D95 fixed invoice↔payment, the owner asked for the other
document pairs to be checked. One was clean, one was safe by accident, one
was worse than the original bug.*

### D96 — Voiding a sale reverses its customer return
- **What:** `CUSTOMER_RETURN` joins the `related_document` void cascade
  alongside payments and adjustments. A sale voided while a return sits
  against it now takes the return with it.
- **Why:** Probed on real data: sale of 5 on credit → owes 500; customer
  returns 2 → owes 300; **void the sale → owes −200 and the warehouse
  gained two packs that never existed** (the return handed goods back
  against a sale that no longer existed, and the void handed the original
  five back on top). Worse than the D95 case, because it corrupted
  **stock** as well as money. After D96: balance 0, warehouse unchanged.

### D97 — A settled consignment issue explains why it cannot be voided
- **What:** `ConsignmentIssueHandler.check_voidable` refuses with
  *"CN-000004 was already settled by CS-000002. Void the settlement first
  — that puts the goods back on consignment — then this issue can be
  voided."*
- **Why:** It was already impossible (the goods have left CONSIGNED, so
  the reversal failed the no-negative stock check) — but it surfaced as
  *"Not enough stock: item 10 lot 12 in CONSIGNED (have 0, need 10)"*.
  Right answer, useless words. Voiding the settlement itself was probed
  and is correct: consigned stock restored, warehouse adjusted, balance
  cleared.

### D98 — Destructive confirmations are over-explained and type-gated
- **What:** The D93 dialog gained a **danger** variant: red rule and
  heading, an itemised list of every consequence, a highlighted
  "cannot be undone" panel, and — the part that stops reflex clicking —
  the confirm button stays **disabled until the operator types the
  document number**. Applied to **Void** and to **posting a correction**
  (the moment the void actually fires). The warning names every linked
  document that will be reversed alongside, by number and type.
- **Why:** Owner: "do an over explainer on the warning, scary warnings so
  people don't just randomly do it." Correcting stays deliberately calm —
  it is reversible, and dressing it in red would teach staff to ignore
  red. Only the two irreversible actions are dangerous, so only they look
  it.

## Round 16 (2026-08-03) — the last void gaps, and messages that name things

*Trigger: the remaining unprobed void shapes from the D96/D97 sweep —
withholding remittance, and the opening documents. One was a real hole, one
was safe, one was refused in words nobody could act on.*

### D99 — A payment cannot be voided after its withholding was remitted
- **What:** `void()` now refuses when reversing a document would push a
  withholding bucket below zero, naming the remittance to void first:
  *"Cannot void: the 30.00 withheld here was already paid to the tax office
  by WR-000001. Void that remittance first — the amount goes back into what
  you owe the tax office — then this document can be voided."* The check
  lives in the engine, not one handler, so it covers the direct void **and**
  the D95 cascade (voiding the receiving behind the payment).
- **Why:** Stock cannot go negative — a DB CHECK constraint says so (D4).
  The withholding buckets had no such backstop. Measured on real posting:
  receiving 1000 → pay 970 cash + 30 withheld → PAYABLE 30 → remit 30 →
  PAYABLE 0. Void the payment: **PAYABLE −30.00**, cash back to −30.00, AP
  1000. The 30 was sitting at the tax office and the books said the tax
  office owed it back.
- **Consistent with what already existed:** `WhtRemittanceHandler.validate`
  already refused to remit more than is owed. The rule "this bucket never
  goes negative" was therefore already the design; the void was simply the
  one path that skipped it.
- **The way out is the message:** void the remittance (which refills the
  bucket), then the payment. Both directions are covered by tests.

### D100 — Refusals name the medicine and the document, not row ids
- **What:** Two messages rewritten. The stock shortfall now reads
  *"Not enough stock: AMOX — Amoxicillin, batch B-1 in Warehouse (have 15,
  need 20)"* instead of *"item 10 lot 12 in WAREHOUSE"*. Voiding a receiving
  whose goods have moved now names the documents that took them instead of
  saying *"sold or moved … use a supplier return"*.
- **Why:** The same complaint D97 fixed for consignment: the refusal was
  correct and unusable. The receiving one was worse than unusable — when a
  **supplier return** was what moved the goods, it advised the owner to do
  the thing they had already done. Naming the documents turns a dead end
  into an instruction.
- **Scope:** the shortfall message is raised by the posting engine, so every
  stock refusal in the app reads better, not only voids.

### Probed and found clean — opening documents
Voiding an **opening AR** after a receipt settled it is correct: the D95
cascade reverses the receipt, the customer lands at 0.00 and the cash goes
back. Voiding **opening stock** after some of it was sold is correctly
refused by the D4 stock rule (in D100's new words). No change needed.

### D101 — Whether cash and bank may go negative is a setting
- **What:** `CompanySettings.negative_balance_policy`, three positions:
  **Allowed** (default) — a negative balance shows in red on the Finance page
  with the reason; **Not when voiding** — daily entry is unrestricted but a
  void may not push an account below zero; **Never** — any posting that would
  overdraw an account is refused. Both refusals name the account and where the
  balance would land, and point at the setting.
- **Why it was found:** probing the D99 hole showed money has no backstop at
  all. `_write_money` wrote ledger rows unconditionally: an expense of 4000
  against an empty drawer posts and leaves cash at **−4000.00**, and voiding
  an opening-cash document after the money was spent does the same. Stock has
  a DB CHECK constraint (D4); money had nothing.
- **Why a setting and not a rule:** Temesgen — *"make all options available in
  settings, since people without a PLC may not declare all their finances they
  can choose."* A business that does not run every birr through the books has
  real payments with no recorded income behind them; refusing those stops real
  work. Same principle as **D54**: the legal form is configuration, not code.
- **Default is today's behaviour**, per the D89 rule that a new switch changes
  nothing until it is flipped. Migration `core.0006`.
- **Not the same as D99.** The withholding bucket was fixed outright because
  the codebase already declared it must never go negative — the remittance
  form has refused to over-remit since D52. Money had no such existing rule,
  so choosing one would have been inventing policy.

### Defect found in the D98 tests (fixed, no decision needed)
`test_document_correct.py` still asserted the **D93** dialog titles
("Void SI-000001?", "Post this correction?") that D98 deliberately replaced
with warning-shaped ones. Two tests were failing at `499cfbf`, and the
2026-07-30 status file's "full suite green" was wrong. Assertions updated to
the D98 copy and strengthened to check the type-gate.

---

## Round 17 (2026-08-03) — the field-testing improvement batch ships

*Trigger: Temesgen greenlit the whole outstanding queue at once — the seven
decided improvements (R48a/R48b/R50/R51/R52/R54/R56), answered the R53 open
question ("picking list for store room"), and agreed the R49 scope.*

### D102 — Items read generic-first everywhere (R48a/R48b/R51)
- **What:** `Item.__str__` is now `CODE — Generic (Brand)` (brand alone when
  no generic is recorded). Because every dropdown in the app and every D100
  refusal message name items through `__str__`, the whole app flipped at
  once. The items list gains a **Generic name** column (it was searchable
  but invisible), and the Cash Sales Attachment line reads
  `Generic (Brand), Strength, Dosage` — its header flipped to match.
- **Why together:** R48b and R51 had to land in one round so the wording
  agrees everywhere — a dropdown, a refusal and a printout must name the
  same medicine the same way.
- **Bonus:** master-list column headers now come from the fields'
  verbose names (`field_label` filter) — the new column would otherwise
  have been headed `generic_name`.

### D103 — Prepared By + signature on the generic printout (R50)
- **What:** `print.html` (the "Attachment / not a fiscal receipt" layout,
  COMPACT default) prints **Prepared By: <full name>** from the document's
  `created_by` with a ruled signature line beneath, at the bottom of the
  page. `break-inside: avoid` keeps name and line on one page.
- **Scope held:** no stamp box, no Received By — the client confirms those
  later. "Prepared" = who entered it, same meaning as the Cash Sales
  Attachment.

### D104 — "Due date" is labelled "Payment due date" (R52)
- **What:** one `verbose_name` on `Document.due_date`. The same field is
  the supplier's credit terms on receivings (feeds AP overdue) and the
  customer's terms on credit sales — "Payment due date" reads correctly for
  both. State-only migration `docs.0009`.

### D105 — Draft lines show a computed net preview (R54)
- **What:** a draft's per-line **Net** column read 0.00 because `line_net`
  freezes at posting (※). Drafts now show `DocumentLine.net_preview` —
  the same `qty × price − discount` the sales handler will freeze — under a
  column deliberately headed **"Net (preview)"**. Display only; posting
  stays authoritative (tax allocation and D80 re-derivation can move it).

### D106 — The Reference form obeys the fiscal-machine switch (R56)
- **What:** `DocumentReferenceForm` hardcoded its three fields, so turning
  off *Fiscal machine present* (D89) hid the machine-total box on entry
  forms but left it on the posted-document Reference form. It now runs
  through the same `fields_hidden_by_settings()` as the other forms.

### D107 — A draft prints as a picking list for the storeroom (R53)
- **What:** the R53 question ("picking list or quote?") is answered:
  **picking list**. New `/documents/<pk>/picking-list/` for SALE, PROFORMA
  and CONSIGNMENT_ISSUE, drafts included — its own layout with item
  (generic-first), batch, **shelf/bin**, quantity and a tick box per line,
  plus a "Picked by" sign-off. **No prices, no totals, no number slot**: a
  draft has no number (D8) and this paper must never read like an invoice
  (D18) — it is labelled *"Internal — not an invoice, carries no prices"*.
- **Not built:** a quote layout. If the client ever wants to hand a draft
  to a customer, that is a new request with its own rules.

### D108 — Create an item without leaving Receiving (R49)
- **What:** the Receiving lines card gains **+ New item**, opening a dialog
  that runs the **full `ItemForm`** — D67 auto-codes and the D81 price
  rules apply, and the creation is audited exactly like Master → Items
  (`MASTER_CREATE`). On success the item is injected into every item picker
  on the page — the live Choices instance, the pre-enhancement option
  snapshot and the add-row template — and selected on the first empty line
  row (a fresh row is added when none is empty). Endpoint:
  `/master/items/quick-new/` (GET = blank fields partial, POST = JSON or a
  400 re-render with errors).
- **Why not a simplified form:** the R49 scope note was explicit — a
  parallel "quick" form would bypass D81/D67 and half-formed items would
  accumulate. Employees see the same form minus the margin fields (D33).
- **Scope:** Receiving only. Sales staff pick, they don't create.

---

## Round 18 (2026-08-04) — the round-4 field feedback ships

*Trigger: Temesgen answered the two open questions the same day the batch
was recorded — "make the encapsulating container wider too", grid
separators on printing, VAT-exempt on drugs only, combobox approved.*

### D109 — Document entry uses the full screen width (R57)
- **What:** the entry form page opts out of the 72rem page cap
  (`page_class` block → `.page-wide`), and the line-table item picker grows
  from 14rem to 22rem so generic-first names stop truncating. Other pages
  keep the cap — reading pages want a measure; entry pages want room.

### D110 — Printouts carry the full item description, in a grid (R58)
- **What:** one shared composition, `Item.full_description` — *generic
  (brand), strength, dosage form, base unit, pack description*, blanks
  skipped — used by all three layouts: the generic printout and the picking
  list print `CODE — full description`, the Cash Sales Attachment prints it
  under a header extended to "…Strength, Dosage, Unit, Pack". The generic
  printout and picking-list tables switch from row-lines to a **full grid**
  (border around every cell), matching the attachment, which already had
  one — his "separator border between each field" ask.

### D111 — New items default to VAT-exempt, following the DRUG category (R59)
- **What:** the item form starts with *VAT exempt* ticked (the default
  category is DRUG and medicines are exempt by law — the help text always
  said so). Changing the category flips the box with it — DRUG → ticked,
  anything else → unticked — **until the user touches the box**, which
  always wins. Model default unchanged (no migration): this is a data-entry
  default, not a data rule, and existing items are untouched.

### D112 — Base unit is a dropdown that accepts a typed unit (R60)
- **What:** the invisible datalist becomes a real `<select>` of the common
  units plus **"Other — type it below"**, which reveals a text box; the
  form swaps the typed unit in at clean(). A saved custom unit joins the
  dropdown on edit so nothing ever renders unselected. Applies to
  Master → Items and the D108 receiving dialog alike (same form).

### D113 — Item dropdowns always open downward (bug fix)
- **What:** the pickers flipped upward at random and sat under other parts
  of the page. Two causes, two fixes: Choices.js ran with
  `position: "auto"`, which measures free space against the scrollable
  line-table container and misjudges it — now `position: "bottom"`, always
  downward. And the vendored dropdown ships `z-index: 1`, losing to cards
  and panels — now 25 (below only the sticky topbar), with the line table's
  scroll container releasing its clipping while a picker is open
  (`.table-wrap:has(.choices.is-open)`).

---

## Round 19 (2026-08-05) — editing where the field is

*Trigger: "instead of a dedicated reference field i want to place small edit
next to the fields that can be edited" — plus, after discussion, "pencil on
everything that are low risk editable" and "lets not implement the expiry
correction".*

### D114 — The Reference page becomes a pencil per field (R61)
- **What:** the *Reference fields* button and the form behind it are gone.
  A posted document now shows a **"Still editable"** card listing each
  field it may change, each with a ✎ that opens that one field in place
  (htmx swaps the value for an input and back). Saving writes and audits
  that field alone; Cancel restores the value and writes nothing.
- **Why:** the page needed explaining — its own owner asked what "Reference
  fields" meant (2026-08-03). A pencil beside the box explains itself, and
  the fields *without* one now teach the D90 rule better than a separate
  screen did: everything that moved a ledger is untouchable.
- **The set widened to five.** D90 named `notes` and `due_date` as safe to
  add "if the client asks"; he asked. So: `fiscal_receipt_no`,
  `machine_total`, `withholding_certificate_no` (numbers copied off someone
  else's paper, §7.12), `notes` (commentary), `due_date`.
- **`due_date` is owner-only.** It moves what counts as overdue in AR/AP
  reporting — never what is owed, so it stays ledger-free and editable, but
  the decision belongs to the owner. The other four stay open to staff, who
  are the ones holding the fiscal receipt.
- **The guard did not move.** `Document.save()` still refuses any change to
  a posted document outside `POST_EDITABLE_FIELDS` (I1), so a field outside
  the whitelist cannot be written even if the endpoint were tricked into
  naming one. The view whitelists as well — defence in depth, not the only
  defence.
- **D106 survives the move:** a box switched off in Settings has no pencil
  and its endpoint 404s. The test moved with it.
- **Audit action renamed** `DOCUMENT_REFERENCE_UPDATE` →
  `DOCUMENT_FIELD_UPDATE`. Existing rows keep the old name; the diff is
  naturally one field now.
- **htmx finally earns its place** — it was vendored for the duplicate-name
  search and nothing else. No new JavaScript in `app.js`.

### Not built — expiry correction without voiding (R62, declined)
Temesgen: *"lets not implement the expiry correction."* Recorded because
the analysis is worth keeping: expiry lives on `Batch.expiry_date`, not on
the document, so a correction would have to edit the batch every rule reads
(D46 expired-sale block, D59 near-expiry, D61 FEFO) — and one batch number
is shared across every receiving of it. Today a typo may be genuinely
uncorrectable, because void-and-repost is refused once any of the stock has
been sold. If it is ever revisited: owner-only, audited with a reason, and
a D98-style dialog showing which documents share the batch and what the
change does to stock on the shelf.

---

## D115 — Pre-ship audit: the fiscal-machine switch governs both halves (R63)

Before shipping the 29-commit batch to the client, the whole branch was
audited for integrity and business logic: full suite, migration graph,
authorization sweep across every view, secrets scan, and the deployment
path. **Nothing in the batch was broken** — 433/433 green at the time of
the audit. Six findings came out of it; this entry records what was done
about them.

### Built — the receipt number follows the machine

`fiscal_machine_present = False` hid the machine total but left
`fiscal_receipt_no` on every entry form, on the generic printout, and — new
in D114 — as a pencil on posted documents. The number is printed *by* the
machine, so without one it is a box staff can never fill.

`fields_hidden_by_settings()` now hides both halves of D18/D43. Everything
else follows for free, because that one function is what the entry forms,
the D114 pencil list and the `document_field_edit` endpoint all read: the
box disappears, the pencil disappears, and the endpoint 404s, with no
change at any of those call sites. The generic printout and the draft
summary row are gated on `company.fiscal_machine_present` directly.

The cash-sales attachment layout keeps its FS Receipt No line on purpose —
that layout *is* the fiscal-machine artefact, so a business without a
machine would not be printing it.

### Built — the missing migration (`core.0007`)

`makemigrations --check` wanted an `AlterField` for two help texts reworded
in D101 and D89. `sqlmigrate` prints `(no-op)` for both operations — it
touches no table and no data, it only brings the migration state level with
the models. Left undone it would have been swept silently into whatever
migration came next, and any `makemigrations` run on the client's box would
have written a file absent from the repo, quietly forking that machine's
history from ours.

### Not built — `notes` narrowed to owner-only

D114 widened the post-editable set to include `notes`, owner-gated only for
`due_date`. But `notes` is where the engine writes provenance ("Auto
payment for SI-000001", "Corrects SI-000123", "Stock count adjustment for
SC-000004"), and it carries the adjustment reason that `AdjustmentHandler`
makes owner-only to *enter* — so an employee could blank an owner's
justification after the fact.

Temesgen: *"not a problem."* Recorded rather than acted on, because the
reasoning holds either way: every edit is audited before/after, so nothing
is destroyed, only moved from the document's face into the log. Revisit if
an auditor ever asks why a posted adjustment has no reason on it.

### Not built — R64, R65, R66

A zero-total cash sale cannot post (R64, queued at Temesgen's request); the
pack-factor cost rounding, which the working data shows is not live for a
wholesale business buying and selling per pack (R65); and a withholding
remittance whose payable check runs a moment before the lock (R66,
practically unreachable on one till). All three are written up in
[03-open-risks.md](03-open-risks.md) with their trigger conditions.

## D116 — A correction may not delete what it cannot put back (R70)

Correcting a document duplicates it as a draft and voids the original when
that draft posts (D92). The void cascades into the original's linked customer
returns (D96) and the separate receipt that settled it (D95) — and the
replacement carries none of them, because `_duplicate_as_draft` copies only
the document's own fields, lines, charges and payment lines. So correcting a
sale that had been returned against, or paid by a receipt, quietly reversed
those documents and billed the customer a second time for money they had
already handed over.

Correction is now refused when the original has posted dependents that a
replacement cannot recreate, naming them: void those first, then correct.
A cash sale's own auto payment (D3/D44) is deliberately *not* a blocker —
`after_post` rebuilds it from the copied payment lines. The check runs twice,
in the view for a fast refusal and again inside `post()`, because the return
or receipt can land while the draft sits open; the second one is the binding
one.

**This was the only defect in the batch that `v1.0.0` did not already have.**
It is why the batch was not tagged when `05-status.md` said it was ready.

## D117 — A credit note is worth what the invoice charged (R67)

A referenced customer return took its price from whatever was in the box, and
the entry form prefills the *current* catalogue price (D80) — so a price rise
between sale and return refunded more than the customer ever paid. Cost was
weighted across the sale's matching lines while price came off the first one:
two different answers to the same question. Tax was frozen at today's rate,
not the sale's.

A referenced return is now valued pro rata from the sale's own frozen lines —
`sale_value × qty_base ÷ qty_sold` over the lines matching item and batch —
with `line_discount` forced to zero because it is already inside `line_net`,
and totals frozen at the sale's `tax_rate_snapshot`. Cost and price now come
from the same set of lines. Unreferenced returns are unchanged: the owner
still enters the cost, and today's rate is the only rate there is.

Codex asked for a source-line foreign key on `DocumentLine` instead. That
needs the return form to make staff pick a specific sale line, which is a
larger change than this round is for; the pro-rata share mirrors the
`value_per_base` pattern consignment settlement already uses.

## D118 — A return credits the invoice it came from (R68)

`open_balance()` counted only payment allocations, and a return with no refund
writes none — it credits the customer's account directly. The customer's total
AR fell but the invoice still read fully open, so aging chased money that was
no longer owed and a receipt could be allocated against a balance that was not
there. Unrefunded posted returns are now subtracted from the invoice's open
balance. Refunded returns are not: that money went back over the counter, so
the invoice itself is still owed in full.

## D119 — The owner draws a line under a closed month (R71)

Voiding stamps its reversal rows at the current time but flips the document to
VOIDED, and the reports only ever show currently-posted documents. A June sale
voided in August therefore disappears out of June and turns up in no other
month: a June report already printed and filed silently stops matching.

The real fix is reversal-aware reporting, which is a bigger piece of work.
Meanwhile there is a **Books closed through** date in Settings — empty by
default, so nothing changes until it is used. Once set, documents dated on or
before it can no longer be voided or corrected, and the message says to enter
a correcting document dated today instead. The owner moves the date forward as
each month is finished.

## D120 — Small server-side guards that were missing (R72-R78)

Six defects that all had the same shape: a rule the business obviously has,
enforced nowhere the server could see it.

- **A supplier return must go back to the supplier it came from** (R72). Lots
  remember who sold them (D40); returning one to somebody else took the money
  off the wrong supplier's payable. Lots with no recorded origin — opening
  balances, stock counts, customer returns — still go wherever the owner says.
- **Units per pack must be at least 1** (R73). Stock moves `qty × factor` while
  revenue uses `qty` alone, so a factor of 0 invoiced the customer and moved
  nothing. Only receiving checked it. Now `post()` checks it for every document
  type, whichever route the draft arrived by — hidden (D89) is not absent.
- **A stock count is refused when stock moved after its snapshot** (R74). The
  variance is `counted − frozen` applied to whatever is on the shelf now; with
  2 sold after the snapshot, the shelf ended up holding neither the counted
  figure nor the real one. It was written to the audit log and posted anyway.
  Recount those items.
- **Reports agree with the invoice** (R75). Revenue summed `line_net`, which
  carries line discounts but not delivery charges or whole-document discounts,
  so reported revenue differed from invoiced revenue by `charges − discount`.
  Both now appear as their own rows.
- **Opening stock cost is per base unit** (R76). Receiving divides what was
  paid by every base unit received (D21); opening stock stored the entered-unit
  cost directly, so 10 cartons of 12 at 120 booked 120 per tablet — twelve
  times over.
- **A discounted consignment issue cannot be settled** (R77). Settlement values
  goods from the issue's `line_net`, which never carried the issue's
  document discount, so the customer was billed the undiscounted price. Put the
  discount on the issue's lines instead.

Django also moved 6.0.6 → 6.0.8, the 2026-08-04 security release (R78). No
disclosed path was shown reachable here; this is overdue patching, not a
demonstrated exploit.

## D121 — A mistyped expiry can be corrected, by the owner, in the open (R62)

*Trigger: it happened. The client typed 22/07/2026 for batch EP241208S of
ITM-0032 on a multi-item opening stock, had already sold from that document,
and every route was closed.*

R62 was declined on 2026-08-05 with the trap written down: *"a typo may be
genuinely uncorrectable, because void-and-repost is refused once any of the
stock has been sold."* Three days later it bit, and the only fix available was
editing the database by hand on the live machine — unaudited, unreviewed, and
undoable only from a backup.

**What was built** is exactly what that note specified if it were ever
revisited: owner-only, audited with a reason, and a dialog showing which
documents share the batch and what the change does to stock on the shelf.

- **A pencil on the expiry, on the inventory page.** Owners only — staff see
  no pencil, and the endpoint refuses them too, because hiding a control is
  not access control.
- **Two steps, not one.** Type the date and the reason, and the first submit
  *reviews* rather than saves: it names every document sharing the batch, the
  stock on hand by zone, and what the date does. Confirm posts a second time.
  All three inputs to those warnings are echoed back — the date proposed, the
  date it replaces, and the day it was judged on — and any of them differing
  at confirm time sends you round again, because what was on screen no longer
  describes what would happen. The no-change check runs under the row lock,
  not before it, so a retry cannot log "from X to X".
- **The reason is mandatory** and lands in the audit row beside the old date,
  the new date, and the documents affected.
- **Warnings name the direction.** Pushing a date out puts warehouse stock
  back on sale; pulling it back stops it selling. Both are stated with the
  quantity, and only about warehouse stock — consigned and expired goods do
  not move because a date moved.
- **The recall case is called out.** If the new date is earlier than a sale or
  consignment issue of that batch, the dialog names those documents and says
  the goods went out expired. It does not block the correction: the truth is
  the truth. It makes sure nobody records it without seeing what it implies.
- **The change and its audit row commit together**, under a row lock, or
  neither does.

**Why the batch and not the document.** Expiry lives on `Batch.expiry_date`,
never on the line. One manufacturer batch has one real expiry, so every
document that ever received or moved it shares the answer — which is why the
dialog lists them rather than pretending the edit is local to one page.

**What was declined.** Codex asked for a server-signed review token binding
the reviewed values. The reviewed date is carried in a plain hidden field
instead. Signing would defend the change against the only person permitted to
make it; the review step is a guard against a mistake, not against an
attacker.

**Still open, with a rule instead of a fix:** the correction does not
serialize against posting. An owner changing an expiry in the same instant a
sale is being posted could let that sale commit against the old date. Locking
the posting path against batch rows is a change to the posting engine, and the
last small change made there cost a money-losing bug. So it is R91, and until
it is closed the rule is: **correct an expiry when nothing is being posted** —
not mid-sale, not from a second tab with a document open. One till makes that
easy to honour. Codex accepted the deferral only on condition that rule was
written down; it is also in the release checklist.

## Round 22 (2026-09-06) — five client requests, sorted by what they actually need

*Trigger: five comments from the client after real use. They arrived as five
feature requests and turned out to be two reports, one entry-form fix, one
duplicate-data problem, and one request that was already possible. Rounds 20
and 21 produced risks rather than decisions, so the numbering resumes here.
Anything needing a schema change is deliberately **not** in this round — those
wait for a copy of the client's database (see R95).*

### D123 — What a form asks for and what a correction copies are two questions
- **What:** `_duplicate_as_draft` built its line copy from
  `DOC_CONFIG[doc_type]["lines"]`, the same list that decides which boxes the
  entry form shows. D84 took `free_qty` off the receiving form because the box
  confused staff — and posting still computes stock as
  `(qty_entered + free_qty) × factor`. So correcting a receiving of "100 paid
  + 10 free" **voided 110 units and re-posted 100**, and moved the lot cost
  with it. A new `ENGINE_LINE_FIELDS` tuple names the fields the posting engine
  reads regardless of form visibility, and the copy is their union with the
  form's list.
- **Why:** the two lists answer different questions and only coincidentally
  matched. Hiding a box must never silently drop a value the engine consumes.
  Found by review, confirmed against the working tree, and reproduced.

### D124 — An empty batch is not offered on documents that sell from the shelf
- **What:** on **SALE** and **CONSIGNMENT_ISSUE** the batch picker now lists
  only batches with warehouse stock. The annotation is `NULL`, not `0`, for a
  batch with no balance rows at all, and `> 0` excludes both. A draft whose
  batch has since run dry keeps **its own** batch in the queryset, scoped to
  that line.
- **Deliberately not filtered:** `PROFORMA`, whose handler returns a bare
  `Effects()` — quoting from a shipment that has not landed is ordinary
  wholesale practice and posting a quote is never refused for stock;
  `CUSTOMER_RETURN`, where goods come back *to* an empty batch; `ADJUSTMENT`,
  where writing stock up starts from nothing; `STOCK_COUNT`, where a count of
  zero is a real count; and `CONSIGNMENT_SETTLEMENT`, which consumes the
  `CONSIGNED` zone, so warehouse quantity is the wrong question entirely.
- **Why the rescue is not optional:** without it there are two failures, and
  the second is worse. Re-submitting a stale draft raises `invalid_choice`, and
  because `_draft_form` gates on every formset validating, the **whole
  document** stops saving. Then re-opening it drops the batch from the rendered
  options, the browser submits blank, `batch` is nullable so the form **accepts
  it and saves** — silently clearing the batch, which only surfaces at posting
  as `pick a batch (D29)`. Correcting the very sale that emptied a batch hits
  this too, because the original's stock returns only when the replacement
  posts.
- **Client's words:** "when a batch has no stock left it should not show up on
  sale to be selected to be sold even though posting will force it not to be
  sold to not waste the operators time." Agreed without reservation — this was
  the best of the five requests.

### D125 — Retiring an item finally stops it being offered
- **What:** the line-item picker filters on `is_active`, with the same
  per-line rescue as D124 for a draft that already names a retired item.
- **Why:** `is_active` was editable in Master and written to the audit log, and
  **no picker read it**, so deactivating an item changed nothing. Found while
  checking whether "supersede" could work as the answer to duplicate brands; it
  cannot until this holds. Not requested by anyone — it is a defect.

### D126 — Two reports that show what each product actually sold for
- **What:** `sales-by-brand` and `sales-by-generic`, both grouping posted
  revenue and adding **average price achieved per base unit**, with the
  lowest and highest. Cost and profit columns stay owner-only, decided in the
  builder, which covers the CSV export too since it reuses the builder's rows.
- **Two arithmetic traps, both handled:** quantity is `qty_base`, never
  `qty_entered` — posting computes revenue as `qty_entered × unit_price`
  while stock moves `qty_entered × factor`, so dividing by the entered
  quantity would mix carton prices with single prices the moment a pack
  factor appears. And `line_net` carries **line** discounts only; document
  discounts and delivery charges live on the document (R75), so this is a
  line-level achieved price that will not reconcile to an invoice carrying a
  document discount. The column heading says so.
- **Grouping by generic folds case and surrounding space** and displays the
  most common exact spelling, tie-broken alphabetically — the same rule the
  eventual `Generic` backfill will use, so the report previews its grouping.
  A real misspelling is **not** folded: `Paracetamoll` stays its own row.
  The grand total is unaffected by grouping; only the split moves, which is
  the whole argument for giving the catalogue a generic of its own.
- **Why the client's premise checks out:** D89's `sale_price_editable` hands
  pricing back to the counter, and it is **on** in the development database
  with discounts off. On this data one item shows achieved prices of 8.00,
  0.40 and 8.01; another 3.00 and 1000.00. "Items are sold at different
  prices to different customers" is a description of the configuration, not
  a request to change the pricing model. **Confirm the flag on the client's
  machine** — if it is off, this is R46 territory instead.

### D127 — Who owes who, and a tax-number match that works both ways
- **What:** a `both-faces` report listing every business that is both a
  customer and a supplier, with what they owe, what we owe, and the
  difference. The statement page's counterpart lookup is repaired with the
  same normaliser.
- **The lookup was wrong in five ways**, all now covered by tests: it
  stripped only the *selected* party's tax number, so a stored `" 0012 "`
  linked one way and not the other; it compared exactly, so `001-2345678`
  linked neither way; it ended in `.first()`, so two suppliers sharing a
  number resolved to whichever sorted first; it required `is_active`, hiding
  a deactivated supplier still owed money — deactivating a record does not
  settle a debt; and a blank number cannot express the relationship at all.
  Blank still never matches: pairing empty strings would marry every business
  without a tax number to every other.
- **Ambiguity is shown, not resolved.** Where several records share a number,
  every code on each side is named and their balances summed, so a human sees
  the ambiguity instead of the system silently picking one.
- **No netting.** D79 settled that and it stands: each side settles with its
  own payment documents, which is what tax filing needs. The difference here
  is information on a report, and the sign convention is in the column name.
- **Still matched by tax number.** An explicit link needs a migration and
  waits for a look at the real data (R95).

### D128 — The receiving desk searches batch numbers instead of retyping them
- **What:** typing in the batch-number box on receiving (and the opening
  documents) suggests existing batches for the selected item, matched
  case-insensitively, showing expiry and quantity on hand. Picking one fills
  the number **and its expiry**.
- **Why this and not a "receive again" button:** the client asked for a
  short-cut when receiving the same brand and batch again. Temesgen's
  objection was right — a new delivery rarely repeats the same combination,
  so a prefilled copy saves little, and the capability already exists
  (`get_or_create` reuses the batch, a new cost lot is written; proven by
  `test_i7_rereceipt_same_batch_new_price_makes_second_lot`).
- **Why batch numbers are worth more than keystrokes:** a batch number is the
  one master string in this system that can **never** be corrected. `Batch`
  is unique on (item, batch_no) and four models point at it with PROTECT —
  cost lots, the stock ledger, balances, document lines. A typo, once posted,
  is permanent: the stock sits under a label nobody will search for, and a
  recall on that batch misses it. Generics can be merged and items can be
  retired; a batch has neither escape, so entry is the only place to defend.
- **Two things it also fixes:** posting refuses an existing batch whose
  expiry differs from the one typed, so filling the expiry turns a hard
  failure at posting into no failure at all. And `get_or_create` matches
  case-sensitively, so `b001` silently becomes a second batch of the same
  goods — the suggestion warns when the typed value differs only in case.
- **Delivered client-side** from a JSON index, not HTMX: rows are cloned from
  a template and nothing re-processes them, which is the same reason
  `filterBatches` works the way it does.

### D129 — Number boxes ignore the scroll wheel and arrow keys
- **What:** a focused `<input type="number">` blurs on wheel and refuses
  arrow keys. The page still scrolls normally.
- **Why:** the stock-count screen pre-fills every line with the system's own
  figure and is long enough to force scrolling, so a scroll over a focused
  box silently rewrote a counted quantity with no trace. This is the cheapest
  candidate explanation for the still-undiagnosed report of a quantity of 180
  registering as 189.

### D130 — Posting asks first, and shows base units
- **What:** the ordinary Post button now uses the shared confirmation dialog
  (D93), listing item, batch and quantity **in the item's own base unit**,
  the document total, and a plain statement that a posted document cannot be
  edited. A new `DocumentLine.base_preview` derives `qty_entered × factor`,
  because `qty_base` is zero until posting computes it.
- **Why:** validation cannot tell a typo from an intention, so the only real
  protection is showing people what they are about to commit and making them
  say yes. The dialog has existed since D93 and the **correction** Post
  button already used it well; the ordinary one was a plain form. This was
  wiring, not machinery — and base units are exactly where a mistyped
  quantity and a silently-applied pack factor both become visible.

### D131 — No auto-login; the system waits for a person

**Date:** 2026-09-08. Supersedes the auto-login step in
[DEPLOYMENT.md section 2](ops/DEPLOYMENT.md) for this client.

**What:** Windows auto sign-in stays **off**. The PC boots to the lock screen
and nothing starts until the owner signs in. The other two links of the boot
chain stay as designed: Docker Desktop launches on sign-in, and the containers
return by themselves through `restart: unless-stopped`.

**Why:** auto-login means anyone who switches the machine on is inside the
system, with no password between them and the customer ledger. The owner is on
site through the working day, so the power cuts that matter happen while
somebody is there to sign in. The security cost is permanent; the convenience
it buys is a few minutes, a few times a day, with a person already present.

**What this costs, accepted knowingly:**

- After every power cut the system is down until someone signs in and waits a
  few minutes for Docker. It does not heal itself.
- The 16:00 backup runs as the signed-in user, so a day nobody signs in is a
  day with no backup. The catch-up setting fires at the next sign-in, not at
  the next boot.
- An overnight or weekend restart leaves the machine at the lock screen until
  the shop opens.

**What this obliges us to do instead:** the recovery routine stops being
automatic and becomes something the owner must know. It is written down at the
machine, not left in a document nobody at the site has read. See the recovery
card in DEPLOYMENT.md.

---

## Round 23 (2026-09-10) — the catalogue gets a generic, and the order of work changes

*Trigger: the client clarified the "one generic, many brands" request — on
receiving they want to search brand and strength, with a default, and to add a
new brand or strength without the full item form. Measuring that against the
restored production database overturned R95's verdict. The design below was put
to Codex (gpt-6-astra, ultra) over three adversarial rounds; it corrected four
things and we converged. Nothing here is built.*

### D132 — A generic is a record; a brand is not

**What:** `catalog.Generic` becomes a real row — a display name plus a
normalised unique key, and optional presets used when creating an item under
it. `Item` gains a **nullable** FK to it. `Item.name` (brand) and
`Item.strength` stay free text on the item, with type-ahead suggestions scoped
to the chosen generic and brand, reusing the D128 batch-number mechanism.
`Item.generic_name` is retained.

**Why a generic is worth a row.** Not for deduplication as R95 measured it —
that measurement was wrong and is corrected there and in
[06-client-data.md](06-client-data.md) §3. The real numbers: **52 of 187
generic strings are restatements of 19 generics**, because the size is being
typed into the name. And a `Generic` row is the only place in this schema where
a **rename or a merge is safe**, because a generic owns no stock, no batches,
no cost lots and no document lines. Merging two generics re-points items.
Nothing posted moves. That is the whole argument, and it is what the free-text
field can never offer.

**Why a brand is not worth a row.** Strength is not a child of brand. The
clinical standards (dm+d, RxNorm) put strength *with* the generic and hang the
brand off that: ingredient → ingredient at a strength in a form → branded
version → pack. Fogatery 3FH/4FH/5FH is not one brand with three strengths; it
is three products sharing a name. The **item already is** the fully-specified
product — brand, strength, form, pack — and it is what holds stock, price,
batches and history. A `Brand` row would own none of those. Every general ERP
checked (SAP materials, Dynamics variants, NetSuite matrix items, Odoo
templates) keeps the stocked, priced thing at the fully-specified variant and
differs only in how it *groups* them for searching. Promoting brand to a row
later, on top of the generic layer, is a smaller job than building both now;
the reverse is not.

**Odoo-style template-and-variants was considered and rejected for now.** It
would serve the client's mental picture best, but it presumes structured
attributes — strength as a number with a unit. 58 of 201 items have no strength
and the populated ones include `3FH`, `2/0 round`, `.` and `-`. Structure
follows cleanup, not the other way round.

**Defaults default an existing item, never brand and strength independently.**
Independent defaults can name a combination that does not exist. A preferred
item supplies a valid brand + strength + form + unit together; validate it
belongs to the selected generic and is active, with the D125 rescue for a draft
that already names a retired one. *(Codex's correction, and better than what was
proposed.)*

**Generic presets are creation-time only.** Never inherited dynamically, never
applied when linking an existing item, never decided by majority vote across
disagreeing siblings, and "unset" is distinct from `False`. The three Fogatery
records disagree on category and `vat_exempt`; that disagreement is carried
forward as a review item, not resolved by a script. "Otherwise the backfill
fails" is **not** a valid reason to choose presets over constraints — the
domain decides the relationship, and dirty data becomes review work.

**Size has exactly one home: `Item.strength`**, relabelled *Strength / size /
specification*. A generic name never carries a number. Dosage form and pack
description stay separate. Compound device specifications ("2 way", "3 way")
are preserved verbatim for human review, never normalised by script, and `16G`
is never silently rewritten to `16Fr`.

**The backfill is a reviewed management command, not a `RunPython`.**
`docker-entrypoint.sh` migrates under `set -e` before handing off. A raise is an
outage. A guarded `RunPython` does not fix this: raising restarts the loop,
skipping marks the migration applied so the work is never retried, and creating
187 exact-name rows completes the population while leaving the semantics
undone. So: the command proposes the groupings, a human accepts or rejects each,
and only the approved plan applies. The plan is keyed by item code and refuses
to apply if the catalogue changed after it was drawn. This also follows the
standing rule that data fixes ship as commands the owner runs.

**Two deployment stages, not six releases.** Stage 1 installs the code and the
schema with the grouped features **off** and ordinary trading unaffected.
Stage 2 applies and activates the reviewed catalogue change. Development phases
are a different axis and are not deployment events.

**This amends D126.** The generic report reads `item.generic_name` directly
(`_generic_key`, reports/views.py), which is the field the cleanup rewrites — so
the report's grouping changes whether or not we intend it, and leaving it on the
old grouping was never an available option. Consolidating paracetamol syrup,
tablets and IV puts bottles and packs in one quantity denominator. Therefore:
the **generic** report carries revenue and owner-only COGS/profit; **quantity,
average achieved price, lowest and highest move to the item-level report**,
which already exists and is keyed on code + name. Historical periods read the
current catalogue grouping, and regrouping must leave monetary grand totals
unchanged.

**D108 stands.** The receiving dialog keeps the full `ItemForm` and gains
prefilled values from the sibling item, which is not a simplified parallel form.
A genuinely collapsed dialog would need an explicit amendment to D108 and is not
decided here.

**Four things this review corrected, recorded because they were stated wrongly
first:**
- A failed migration is **not** unrecoverable. `NARCOS_AUTO_MIGRATE=0` exists
  (docker-entrypoint.sh:37, compose.yml:43). It is a prolonged, manually
  recoverable outage with an untested recovery procedure — not a dead machine,
  and not an hour either.
- "An additive migration cannot fail" is too strong. `ALTER TABLE` takes locks
  and can fail operationally.
- **`generic_name` is a compatibility mirror, not a rollback path.** Once
  synchronised to canonical names the original text is gone. Original
  before-values must live in the audited cleanup record, and the sequence
  upgrade → cleanup → downgrade → edit → upgrade must be tested. Note two
  writers besides the form: `catalog/importers.py` (CSV) and
  `fix_item_spellings.py`.
- **Fix readers before moving text.** `Item.__str__` omits strength and
  `MASTER["items"].search_fields` is `["code","name","generic_name"]`, so
  extracting `#3` from an ETT generic name makes it unfindable until the label
  and the search cover strength.

**Order of work, agreed:**
1. The `ItemForm` label and placeholder fix **alone**, cut from the deployed
   baseline, not from `build`. The brand placeholder currently reads
   *"e.g. Paracetamol 500mg tablets"* (catalog/forms.py:53) — it instructs the
   operator to type generic + strength + form into the brand box. It is a proven
   bad instruction and a plausible contributor; it is **not** demonstrated to be
   the root cause of most of the smearing, and must not be described as a fix
   for the data.
2. Harden `ops/deploy.ps1` — it prints "Update complete" after `compose up -d`
   and verifies nothing. It must verify application health, show a
   one-photograph result, keep that status across restarts, and reach the same
   checks on the offline `docker load` path. Plus the restore drill on the
   client's own hardware: database **and media** into isolated targets, and a
   **separate** rehearsal of falling back to the retained image against the
   schema the update left. A restore drill does not prove image rollback.
3. Release the 14-commit backlog and the R103 name fix through the hardened
   path, rehearsed against a restored copy first. "Let it run" means observed:
   receiving, sales, printing, attachments, restart recovery, and one scheduled
   backup that actually ran.
4. Then D132, in its two stages.

**Why this order:** step 2 is required by step 4 regardless, so doing it first
makes the backlog release the rehearsal for the risky one — on real hardware,
with rollback demonstrated — before anything touches the catalogue. It keeps
deployment uncertainty, accumulated application changes and semantic data
cleanup out of the same support incident.

**Still open:** whether "catheter" is one generic or several products; where
"2 way"/"3 way" belongs; the 58 blank strengths (review, never invent); the 14
DRUG items marked not `vat_exempt`; and R88 — a generic rename rewrites how
already-printed documents re-render, which bulk canonicalisation makes routine.

### D133 — An expired batch is not offered where stock is sold from the shelf

**What:** the sale and consignment-issue batch pickers exclude a batch whose
expiry has passed, alongside D124's exclusion of empty ones. The picker label
also marks near-expiry batches, reading `near_expiry_months` rather than
assuming six.

**Why:** exactly D124's argument on the other axis. Posting already refuses an
expired batch — D46, a block with no override,
[docs/handlers_sales.py:127](docs/handlers_sales.py) — but only once the whole
line has been typed. The operator types a complete line and is told to start
again.

**Why now rather than later:** it is live. §5 and §9 of
[06-client-data.md](06-client-data.md) show item ITM-0109 batch `B-03225`,
expired 2026-08-08, holding **50 units in the WAREHOUSE zone** on the client's
machine, offered on every sale. The client listed this as request 7 believing it
was already built; it was half built.

**Three boundaries the tests pin, because each is a way to get this wrong:**
- **The expiry day itself is still sellable.** D46 says expired means *past* its
  date, so the comparison is `>=`. Off by one here silently destroys a day of
  shelf life on every batch in the catalogue.
- **A null expiry is not an expired one.** `expiry_date` is null for an item
  with no expiry (D22); reading null as expired would make those unsellable.
- **Disposal still needs the picker.** Adjustments, stock counts, customer
  returns and proformas must still reach expired stock — writing it off is how
  it leaves the building. Filtering those would trap it permanently, which
  matters because §9 found that nothing has ever been written off.

**The D124 draft rescue extends to the expiry axis.** A draft that already names
a batch which has since expired must still validate, or the whole document stops
saving and re-opening it submits blank. The rescue stays scoped to that one
line.

**The posting refusal is untouched.** The picker is convenience; the handler is
the guard.

### D134 — Strength was printed everywhere and shown nowhere

**What:** strength joins `Item.__str__`, the Master item list and its search
fields, and the Inventory search. **No print template changes.**

**Why, and the diagnosis is the point.** The client reported that strength does
not print and that staff leave the field empty and type the size into the name
so that it will. Rendering the real views against the restored database
disproves the first half: `full_description` puts strength on the compact
invoice, the cash sales attachment and the picking list, and `SI-000003` renders
as `ITM-0003 — Suxamethiom (Suxathon), 100/2ml, injection, ampoule, of 1`.
`git tag --contains 940b280` returns **v1.1.0**, the deployed tag, so this has
been true on the client's own machine since round 4.

**The belief is nonetheless honest, and self-reinforcing.** Before 940b280 a
filled strength genuinely did not reach the paper. The habit outlived the fix
because nothing on screen ever confirmed it: fill `strength` and it appears in
no picker, on no document line, in no search — so it looks inert, and the size
goes into the name, where it shows up everywhere including the printout.

**So this fixes readers, not writers.** D132 already required exactly this, as
*"fix readers before moving text"*, as a precondition of the catalogue cleanup.
This request is that item arriving from the field, and it is what makes filling
the field visibly worth doing.

**Blank strength changes nothing.** 58 of 201 items have none, so the separator
appears only when there is something to separate.

**What was deliberately not done:** no test was added for strength on the
printed forms. Three already assert it — `500mg` on the sales attachment, on the
compact layout and on the picking list — and duplicating them would claim credit
for coverage that already existed.

### D136 — A drug without a strength is not a described drug

**What:** `ItemForm` refuses to save an item whose category is DRUG with an
empty strength, on **create and on edit**, and in the receiving quick-add
dialog, because that dialog runs the same full form (D108). Other categories
are exempt.

**Why:** the catalogue's real defect is the size being typed into whichever
field the operator happened to be looking at — §3 of
[06-client-data.md](06-client-data.md). D134 made strength visible so that
filling it is visibly worth doing; this makes it required where it always
applies.

**Why edits too, confirmed by the owner 2026-09-11.** 45 of the client's 162
drug items are blank today. A rule that applied only to new items would leave
those 45 permanently blank and the cleanup would never happen. Applying it on
edit means the next time anyone touches one of those records — to change a
price, say — the strength gets filled in. That is deliberate friction with a
purpose, and the owner chose it knowing the cost.

**Why not every category.** Gloves, syringes and reagents have no strength, and
13 non-drug items are blank. Demanding one would invite a junk value, which is
worse than a blank.

**The message names the fix,** because support happens over a phone photo of
the screen: it says to type the strength and to put the size there rather than
in the name.

### D137 — A filter the user set stays set

**What:** the filters on the documents list, the inventory list and every
report are remembered per user and restored on the next visit. Stored in
`User.filter_state`, a JSON field keyed by screen.

**Why not the session.** D131 settled that nobody is logged in automatically,
so staff sign in every morning on a machine that was switched off overnight. A
session-backed memory would reset daily — which is precisely the complaint.

**Two rules that matter more than the happy path:**
- **An explicit filter always wins.** Otherwise the screen argues with the
  person using it.
- **Clearing a filter sticks.** The filter form submits its boxes even when
  empty, so `?type=` is a deliberate "show me everything". Presence of the key
  decides, never truthiness — a memory that overruled a cleared filter would be
  unusable.

**Scoped per screen,** or filtering documents would silently re-filter
inventory. Reports are scoped per report slug.

**It rewrites `request.GET` once at the top of the view.** Every filtered view
already reads its parameters from there, in a dozen places between them.
Replacing the mapping once leaves that code correct and unchanged; threading a
second mapping through would touch every read and invite one to be missed.
These are read-only list views.

**Nothing here is audited and nothing affects money or stock.** It is a screen
preference, deliberately kept out of `AUDITED_FIELDS`.

### D138 — The sales log: what went out, to whom, at what price, at what cost

**What:** one row per posted sale line — date, document, customer, brand,
strength, batch, quantity, achieved unit price, revenue, unit cost, cost and
gross profit — grouped with subtotals and a grand total, switchable between
brand-and-strength and generic. **Owner only** (D33).

**Three rules, each of them a way to get money reporting wrong:**
- **Charges and document discounts get their own group (R75).** `line_net`
  carries line discounts only, so a log built from lines alone disagrees with
  the invoice it came from by exactly `charges − doc_discount`.
- **Lot cost is the weighted average for the line,** with the lot count shown
  when a line consumed more than one. A blended figure must never read as a
  single purchase price. One line in the client's data does exactly this.
- **At generic level the money is reported and the quantity is not (D132).**
  Folding a syrup and a tablet into one row puts bottles and packs in one
  denominator. Regrouping never changes a monetary total, and a test pins that.

**A separate grouping key.** `_brand_key` (D126) is untouched: the client asked
for the new reports to be kept clear of the old ones, so D138 has its own.

**Verified on the restored client database, not fixtures:** 167 product groups,
156 generic groups, revenue 4,817,556.00 and gross profit 786,559.00 identical
under both groupings. It also immediately shows `zitromax` going out at a gross
loss of 500.00 — the first thing this report was built to catch.

### D139 — One screen for receiving and for the item that arrived with it

**What:** the full `ItemForm` moves out of R49's dialog and onto the receiving
page, collapsed behind a **detailed** tick. A *Same as* picker copies from a
nominated existing item.

**Why the tick.** The owner's objection to an inline form was that it would look
cluttered. The tick is the answer: nothing shows until it is asked for, so the
page is unchanged for the ordinary case of receiving stock we already list.

**It replaces the dialog rather than joining it.** Two entry surfaces for one
form is the real risk, and one unified interface is what was asked for.

**Defaults come from a nominated item, never from brand and strength defaulted
independently (D132).** Independent defaults can name a combination that does
not exist. The preset therefore carries generic, dosage form, pack, base unit,
category and the two flags — and deliberately **not** `name` or `strength`,
because those two are what make it a different product; copying them would clone
the sibling instead of describing the new brand. Retired items are not offered
(D125).

**Still the full form (D108).** Not a simplified parallel form, so D67
auto-codes and D81 price rules keep applying, and D136 means a drug created here
needs its strength like any other.

**The placeholder that taught the smearing is gone.** The brand box read
*"e.g. Paracetamol 500mg tablets"*, instructing the operator to type generic,
strength and form into the brand field. It now reads *"Brand only, e.g.
Panadol"*. As D132 records, this is a proven bad instruction and is **not**
demonstrated to be the root cause of the data.

**One defect found by looking at the page rather than by testing it.** Alpine is
loaded deferred, and no `[x-cloak]` rule existed, so the entire item form
flashed open on every load of the receiving page before Alpine hid it — exactly
the clutter the tick exists to prevent. The rule is now in `input.css`.

### D140 — Two defects Astra found in D135 and D138, and how they were found

Round 23's review was run through `codex exec -m gpt-6-astra` at ultra effort.
All three calls returned **zero bytes on stdout** because the account hit its
daily usage cap mid-run. The findings below were recovered from **stderr**,
where the model's narration is streamed as it works — roughly 550 KB of
transcript across the three. Both were then reproduced with a failing test
before being fixed.

**The as-of date did not reach the drill-down (D135).** Astra: *"The report
applies `end` to the party ledger and invoice dates, but calls `open_balance()`
without a cutoff."* Correct. `open_balance()` nets every posted allocation
whenever it happened, which is right for "is this still open today" and wrong
for "what was owed on the 30th". Level one respected the cutoff and level two
did not, so asking about July would show an invoice reduced by an August
payment — and the reconciling row built to expose disagreements would have
absorbed it silently instead. `_settled_as_of()` now filters allocations and
unrefunded return credits (R68) by the payment's own date.

**A customer return read as free (D138).** Astra: *"a normal customer return
creates a new cost lot but no lot-consumption rows, so the log shows its unit
cost as 0.00. Its total COGS and return sign are correct."* Also correct. A
return creates a lot rather than drawing on one, so there are no consumption
rows to divide by. No total was ever wrong, but the per-unit column is the one
the client reads to judge a price, and 0.00 beside a real cost is a lie.
`_line_lot_cost()` now falls back to the line's own quantity.

**Neither was reachable on the client's current data,** which is exactly why a
reviewer that reads code earns its place: they have posted zero customer
returns, and the as-of bug needs someone to ask about a past date. All 376
posted sale lines check clean, and both reports still tie out exactly against
the old ones — 4,817,556.00 against `sales`, 2,072,840.00 against
`ar-balances`.

**Recorded because the method matters more than the two fixes.** A zero-byte
Codex run is not an empty run. The transcript holds what it reached, and this
time that was two real defects in code written the same day.

**Still unanswered:** the third review died while checking whether the filter
memory (D137) leaks between request paths and whether the inline panel (D139)
preserves an unsaved receiving draft. It had already dismissed the blocked
price edit as intentional under D136. That question goes first when the cap
resets.

### D141 — One sales report, with the item named and the invoice a click away

*2026-09-12. Supersedes D138, which is withdrawn.*

The owner's verdict on round 23: keep **Sales by period/customer/item**, delete
the sales log built beside it. Two reports answering nearly the same question is
one report too many, and the log was the newer and less familiar of the pair.

**Four asks, and one of them was already true.** The owner asked that quantity,
COGS, revenue and profit be "for a single item in the received document not for
the entire document". They already were, and the deployed build does the same:
`SI-000005` renders six rows whose revenues sum to its grand total, and
`git show v1.1.0:reports/views.py` is byte-identical in that function. What the
report did not do was **say which item a row was** — the Item column held
`ITM-0005` and nothing else, so the money read as if it belonged to the invoice.
The complaint was about legibility and was reported as arithmetic. Naming the
item is the fix; no number changed.

**Generic, brand and strength now sit beside the code.** Strength is not on the
owner's list and is added anyway, for the reason D134 gives: it prints on every
document, appeared on no screen, and the gap is what drives the size into the
item name.

**The document number is a link.** Reading a line and opening the invoice behind
it was two searches.

**Three filters — document, generic, brand.** Each a case-insensitive fragment,
all three combinable, and the total follows what is on screen rather than the
unfiltered period. A delivery charge or a document discount (R75) belongs to no
item, so a question about a brand or a generic excludes it; a question about a
document keeps it.

**It leaves the slug registry and gets its own view.** A report with filters and
a link per row cannot go through the generic `detail.html` without teaching every
other report about links. `reports/sales.html` and `sales_report` join
`statement`, `party_positions` and `finance`, which were separated for the same
reason. The URL stays `/reports/sales/`.

### D142 — Copy from an item you already stock, and edit what differs

*2026-09-12. Supersedes the "same as" picker in D139.*

D139 put a preset picker on the receiving page that copied generic, form, pack,
unit and category from a nominated item, and **deliberately withheld name and
strength** on the argument that copying them clones the sibling rather than
describing a new product. The owner's answer: prefill everything, because
clearing one box is easier than remembering which four to fill. Overruled, and
the reasoning is sound — the catalogue's defect is boxes left *empty*
(06-client-data.md §3), and a form that arrives blank in four places is what
produces them.

**The shape is a search box and a Copy from button**, at the top of the item
form. It appears on the Master item page and in the receiving dialog, since both
render the same `ItemForm`, and **only when creating**: copying into an item that
already exists would overwrite a description someone chose on purpose.

**Everything the form shows is copied except the code**, which D67 assigns at
save like a document number, and `is_active`, which only active items can supply
anyway (D125 keeps retired ones out of the picker).

**Two traps the fill has to handle.** A base unit the common list does not carry
would be silently dropped by a `<select>` that has no option for it, so it goes
to "Other" with the text beside it (R60). And R59 follows the category to set
VAT-exempt until someone touches the box — a copy counts as touching it, or the
copied exemption is undone by the next category change.

**An intermediate design was abandoned before it was built.** Two buttons beside
each receiving line, *New brand* and *New strength*, revealing a text box each
and cloning the selected item server-side. The owner reversed it mid-build: one
picker on the form the operator is already looking at beats two buttons on every
line of a document. Recorded because the rejected shape was the more complicated
one — it needed new line fields, a deferred create inside the save transaction,
and a duplicate guard across rows.

### D143 — The detailed tick is gone; the New item button is back

*2026-09-12. Supersedes D139's panel.*

D139 moved the item form out of R49's dialog and onto the receiving page behind
a *"Detailed"* tick, and removed the **+ New item** button in the same change.
The owner asked for the tick removed completely and the button restored. Both
done: the dialog is exactly as R49 had it, and the button sits beside *Add row*
on the lines card.

The `[x-cloak]` rule D139 added stays even though nothing on the page uses Alpine
now. The flash it prevents was found by screenshotting the page, not by any
test, and the next `x-show` would rediscover it the same expensive way.

### D144 — The sales report groups per generic, money only

*2026-09-12.*

The owner asked for grouping on the report they already read rather than as a
fourth sales report. **Group by** offers *Every line* (unchanged) or *Generic*;
one row per generic, the lines still underneath in a drill-down, each linking to
its document.

**Money adds up across a generic and quantity does not.** D132 settled this and
it is easy to lose: one generic covers several strengths, and 100 tablets of
500 mg plus 100 of 250 mg is not 200 of anything. The group row carries revenue,
cost and profit and no quantity column at all — absent by decision, not by
omission — with a line on the page saying so. The lines inside keep their own
quantities.

**The two generic reports must split the same way.** D126's folding rule — case
and surrounding space folded, a real misspelling left as its own row — is now a
function both call, and both pick the label the same way, commonest exact
spelling first with an alphabetical tie-break. On the client's data the grouping
produces **156 generics from 377 lines** and the labels match `sales-by-generic`
exactly, one for one. Grouped revenue equals ungrouped revenue to the cent.

**Charges and discounts get a group of their own.** R75 money belongs to the
invoice, not to a generic. Dropping it would leave the grouped view disagreeing
with its own total, so it sits last under *Other charges and discounts*.

**One layout defect, found by looking.** A drill-down table nested inside a cell
widens that column and pushed Profit off the right edge the moment a row was
opened. The grouped table now fixes its column widths and the nested table
scrolls inside its own box, so opening a row cannot move the money. The same
shape in D135's drill-down got the same treatment.

### D145 — The reports use the trade words, not "they owe us"

*2026-09-12.*

The owner asked for more professional language on the reports, without going
overtly technical. These are shown to an accountant and sometimes to the
business on the other side of the balance, and "Who we have not paid" does not
survive that reading.

The vocabulary was already half there — the report group is called *Receivables
& payables* — so the change is to finish it rather than to introduce jargon.

| Was | Now |
|---|---|
| Who owes us money | Receivables by customer |
| Who we have not paid | Payables by supplier |
| They owe us / We owe them | Receivable / Payable |
| Who owes who (customer and supplier in one) | Net position by business (customer and supplier in one) |
| Net (+ = in our favour) | Net (+ = due to us) |
| Other side | Show payables / Show receivables |
| money + owed to you − you owe | cash and bank + receivables − payables |
| Owed to you (AR) / You owe (AP) | Receivables (AR) / Payables (AP) |
| You owe the tax office | Due to the tax office |
| Balance = what this customer owes you | Balance = the amount receivable from this customer |

Wording only. No number, column or query changed, and the whole suite passed
untouched — which is the evidence that nothing but language moved.

### D146 — "Month and year only", per line, entry-only

*2026-09-12. Revives the feature cancelled in round 23, in a shape that survives
the objection that killed it.*

The carton often carries `09/2026` and nothing more, and inventing a day is how a
wrong expiry gets typed. A tick beside each expiry box swaps the day picker for a
month picker on **that line alone**; the server stores the **last day** of that
month.

**Nothing changes in the database, by the owner's instruction.**
`expiry_entered` stays a plain date column, `Batch.expiry_date` stays a plain
date, and the tick itself is never stored — it describes how the value was typed,
not what it means. No migration, so nothing new can fail on the client's machine
at boot (R95).

**Month end is the safe direction.** D46 blocks a sale *after* the expiry date, so
resolving `09/2026` to the 30th is the latest the goods can still be sold, which
is what the carton actually claims.

**Why the per-line shape survives what the company-wide one did not.** Round 23's
version removed the day picker everywhere. `Batch.get_or_create()` matches on item
and batch number only, so an existing batch keeps its stored expiry and
`docs/handlers.py` refuses a different one — and with no day picker anywhere the
operator could not express the stored day. Measured again today: 236 batches carry
an expiry, 226 are not month-end, and **76 of those still hold stock**.

A tick has an escape the setting did not: leave it unticked. And the case that
would hit the refusal — receiving more of a batch already on the shelf — never
needs the tick at all, because D128 fills the expiry from the batch that was
picked, exactly as stored. The tick is for a *new* batch.

**The refusal now says what to do**, not only what is wrong: it names the stored
expiry and tells the operator to type it, or to untick the box on that line.

**A mis-tick does not cost the typed day.** Ticking remembers the full date;
unticking restores it if the month is unchanged, and falls back to the month end
if the operator changed the month while it was ticked. Verified in a browser
across all three paths, because none of it is reachable from a test.

**Rejected: remembering the tick per line** and comparing expiry at month
granularity at posting, which is what Astra proposed in round 23. It would keep
the tick working on those 76 batches, and it costs a migration on a box where a
failed migration is a silent restart loop rather than an error message. The owner
chose the cheap shape, and the untick escape is what makes it safe.

### D148 — The month box has to work in a browser with no month picker

*2026-09-12. Corrects D146, found by the owner within the hour.*

D146's tick sets the input to `type="month"`. Chrome and Edge render a month
picker for that. **Firefox renders nothing at all** — the type is not supported,
the element silently falls back to a plain text box, and the operator is left
with a blank box, no calendar and no clue what to type. That is what the owner
saw.

Confirmed rather than assumed: a detached `<input type="month">` reports
`type === "month"` in Chrome and `type === "text"` in Firefox 155, which is both
the proof and the feature test.

**Three changes.**

*The browser is asked, not assumed.* Where the month picker exists it is used,
unchanged. Where it does not, the box keeps a placeholder showing the shape it
wants — `2026-09` — with a title spelling it out. The hint lives on the widget so
it can be translated, not in `app.js`.

*Four month shapes are accepted, not one.* A picker always submits `2026-09`, but
a text box receives whatever a person types, so `2026/09`, `09/2026`, `9-2026`
and a single-digit month all resolve. Year-first and month-first are told apart by
which half has four digits, so none of them is ambiguous.

*The refusal names both shapes it will take* — "Enter a date as 2026-09-15, or a
month as 2026-09" — instead of Django's bare "Enter a valid date."

**The lesson is the browser matrix, not the feature.** D146 called this out as a
risk and answered it server-side only, which left the entry surface broken for
anyone on Firefox. A fallback that is only handled in the parser is not handled.

### D147 — Backup folders and interval in Settings, carried to the script that backs up

*2026-09-12.*

The owner asked to set a primary and a second backup folder and the interval from
Settings. **The app runs in a container; the backup does not.**
`ops/docker-backup.ps1` runs on Windows under Task Scheduler and reaches into the
containers with `docker compose exec`. Django cannot see `E:\`, cannot create a
scheduled task and cannot restart the stack.

**The road between them already existed.** Both containers mount the host's
`NARCOS_BACKUP_ROOT` at `/backups`. Saving Settings writes one small
`schedule.json` there, and the script reads it on its next run. No new mount, no
new service, nothing over the network.

**Four settings, every one of them read by the script** — a setting no code
enforces must not ship. Primary folder, second copy folder, interval in days, and
how many nightly copies to keep.

**The dump still lands in the mounted folder**, because that is the only path both
containers can write. The configured folders are copies made on the host
afterwards, each verified file by file by size — a drive that silently truncates
is the classic way an offsite copy turns out not to exist. **The primary copy is
fatal if it fails; the second only warns**, because an unplugged USB stick must
never cost the backup that did work.

**The interval only ever stretches the gap.** Task Scheduler fires the script
daily and the script can skip a run, so weekly works from the app. Running *more*
often than daily needs the Windows task re-registered on the PC, which the owner
chose not to have in this round; the field's minimum is 1 and its help text says
so. The skip is written to `backup.log`, and it can never skip when there is no
good backup to fall back on.

**Retention is the dangerous part, so it gained two floors.** R97: a folder is a
backup only if it holds a non-empty dump *and* the media archive, or a run cut
short by a power failure fills the keep slots and the next success deletes the
last good copy. On top of that, the newest complete backup is now explicitly
unprunable, and a destination holding **no** complete backup is never pruned at
all. Retention runs per destination.

**The page shows evidence, not intent.** It prints what the script will read,
when it was handed over and by whom, and the last BACKUP row from the audit log.
A backup setting you cannot check is how this client went a month with no backup
(`ops/INCIDENT-2026-09-08.md`). On the restored database the card reads *last
backup recorded 2026-08-08* — which is the incident, visible on the settings page
rather than in a post-mortem.

**What the app deliberately cannot do:** write `.env` or restart the stack. That
is a deployment action, and an app that rewrites its own deployment is how a boot
loop starts. The mounted folder stays where `.env` says.

**Not machine-verified:** the PowerShell changes are checked by tests that assert
on the script's text, the way `test_p10_ops.py` already does, and by reading. There
is no PowerShell on this machine to run them. They must be exercised on the
client's PC before the release, and `ops/MANUAL-TESTING.md` says how.

### D149 — Month-only is the default, and the closed-books date gets a picker

*2026-09-12. Two of the owner's observations, an hour after D148.*

**The tick is on by default.** The ordinary receiving case is new goods and a
carton showing `09/2026`, so making the operator tick a box every line was the
wrong way round.

**But only for an empty box.** A row that already holds a date renders unticked
and keeps its exact day. Without that rule, re-opening a saved draft would show
`2026-09-15` as `2026-09` and store `2026-09-30` on the next save — silently
moving a stored expiry by fifteen days, which is precisely the kind of quiet
wrong number this system exists not to produce.

**And the batch autofill releases the tick.** D128 fills the expiry from the
batch that was picked, and that is a full date — the one value a month picker
cannot hold. Setting it on a month input clears the box in Chrome and shows a
malformed value in Firefox. Re-receiving is exactly the case D146 says must not
use the tick, so the row now unticks itself before the date lands. Verified in a
browser: picking batch `73021`, stored `2028-07-23`, leaves the row unticked on a
day picker holding `2028-07-23`.

**Books closed through had no picker and no hint** — a `DateField` with no widget
renders as a bare text box, so the owner met an empty rectangle with nothing
saying what shape a date takes. It is a date input now, which Firefox does
support (unlike D148's month input), with `format="%Y-%m-%d"` so a stored date
actually displays instead of rendering blank and reading as lost.

That field is the one the owner did not remember asking for. It is **D119**,
answering **R71**, shipped 7 August with the joint-audit fixes: voiding a June
sale in August makes it vanish out of June, so a June report already printed
stops matching. Enforced in `docs/posting.py`, empty by default, does nothing
until a date is set. Kept, on the advice that an empty setting costs a row on a
page and a closed month with no guard costs a filed report.
