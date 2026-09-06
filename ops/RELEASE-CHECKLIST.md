# Narcos Release Checklist

Dear Temesgen,

A tick-box pass over **the whole app**, not just what changed recently. Use
this before cutting a `v*` tag. [MANUAL-TESTING.md](MANUAL-TESTING.md) tells
you *how* to drive each screen; this tells you *what must be true* when you
have.

Work top to bottom — later sections reuse the data earlier ones create.

**Legend:** 🔒 = owner-only, must be **refused** for an employee ·
❌ = the app must *refuse* this · 📄 = check a printout

---

## 0. Before you start

- [ ] **Hard-refresh** every browser (`Ctrl+Shift+R`). Assets are versioned
      `?v=20260805a` — a stale cache makes working code look broken.
- [ ] App answers on the LAN address staff actually type, not just `localhost`.
- [ ] Log in as **owner**, then in a second browser as an **employee**.
      Keep both open — half this list is "what the employee cannot do".
- [ ] Administration → Audit log opens and already has rows.

---

## 1. Settings

- [ ] 🔒 Settings page refuses an employee outright.
- [ ] Company name, address, **TIN** and **phone** are filled in.
      *(Phone was still blank at last check.)*
- [ ] Tax regime, VAT/TOT rate and "prices entered tax-exclusive" match how
      the business actually quotes prices.
      *For this client (confirmed 2026-08-07): **regime = None** — they charge
      no VAT and no TOT. The code ships defaulting to **VAT**, so this must be
      changed or every invoice adds 15% that does not exist. Their only tax is
      the **3% withholding** a PLC customer keeps back when paying, so
      **withholding on sales = on** (it ships off) and the rate stays 3.
      Tick this only after posting one real sale and reading the printed total.*
- [ ] Fiscal year start month, near-expiry months, consignment term set.
- [ ] Default credit limit + credit action (warn / block) set.
- [ ] Changing any setting writes an audit row naming the old and new value.

### The switches (D89) — flip each, confirm, flip back

- [ ] **Fiscal machine present → off:** the machine-total box *and* the
      fiscal receipt number box both vanish from sales entry, from the
      printout, and from posted documents. ← *newly fixed, check it*
- [ ] **Discounts in use → off:** both the document and line discount boxes
      vanish. Documents posted earlier still show their discounts.
- [ ] **Pack conversion → off:** the factor box vanishes; lines count in
      base units. *(This is your live setting.)*
- [ ] **Sale price editable → off:** the price comes from the item and
      cannot be typed; use a discount to charge less.
- [ ] **Negative balances:** try each of the three positions and confirm the
      wording matches the behaviour — *Allowed* (goes through, flagged red on
      Finance), *Not when voiding*, *Never*.

---

## 2. Users and roles

- [ ] 🔒 Only the owner reaches Administration → Users.
- [ ] Create an employee; they can log in and do daily entry.
- [ ] Employee is refused on: **void**, **correct**, settings, users, audit
      log, CSV import, stock adjustments, stock counts, disposal, returns
      with no sale reference, and moving a **payment due date**.
- [ ] Deactivating a user blocks their login without deleting their history.

---

## 3. Master data

- [ ] Create an item: code auto-generates, name shows **generic first**
      (`Generic (Brand)`).
- [ ] **VAT exempt** starts ticked for a DRUG and unticked for other
      categories, until you touch it yourself.
- [ ] **Base unit** is a dropdown of common units with "Other — type it
      below"; a typed custom unit saves exactly as typed and reappears in the
      list when you edit that item.
- [ ] Batch-tracked + has-expiry flags behave: an item with expiry demands
      one at receiving, an item without one refuses it. ❌
- [ ] Duplicate-name warning appears as you type a name that already exists.
- [ ] Customers, suppliers, accounts (cash + bank), expense categories all
      create and edit.
- [ ] Customer credit limit and credit action can be set per customer.
- [ ] 🔒 CSV import: items, customers, suppliers all import; a bad row is
      reported with its line number and **nothing** is imported from a file
      with errors.

---

## 4. Opening balances

Only if you are still setting the client up — skip once live.

- [ ] Opening stock, AR, AP, cash, consignment and expired/unfit each post.
- [ ] Opening documents keep **the date you typed**, not today's date.
      *(Every other document stamps system time at posting.)*
- [ ] Opening cash shows on the Finance page; opening AR/AP show in the aging
      reports.

---

## 5. Receiving (GRN)

- [ ] Receive a batch-tracked item: batch number and expiry are **required**. ❌
- [ ] Unit cost is required. ❌
- [ ] Same batch number re-received with a **different expiry** is refused,
      naming both dates. ❌
- [ ] Same batch, new price → **two separate cost lots**, the old one
      untouched.
- [ ] **+ New item** from inside the receiving form: the full item form
      opens, saves, and the new item is selected in the line without losing
      anything already typed.
- [ ] Item dropdowns open **downward** and sit cleanly over the page.
- [ ] Payment lines present → stock arrives *and* the money leaves, in one
      step. No payment lines → supplier balance (AP) goes up instead.
- [ ] Document number `GRN-…` appears **only after posting**.
- [ ] 🔒 Void a fresh receiving: allowed. Sell some of it first, then try —
      **refused, naming the documents that took the goods**. ❌

---

## 6. Sales

- [ ] **Cash sale**: payment lines must equal the total exactly. ❌ if not.
- [ ] **Credit sale**: due date required; customer balance goes up. ❌ without.
- [ ] Mixed VAT-exempt and taxable lines: tax is charged on the taxable part
      only, and the totals add up.
- [ ] Document discount spreads across lines proportionally and the parts sum
      to exactly the discount entered.
- [ ] **Selling more than you have is refused**, naming the medicine, batch
      and zone — never row numbers. ❌
- [ ] **Expired batch is refused** outright, no override. ❌
- [ ] Near-expiry batch warns but allows.
- [ ] Credit limit: over the limit **warns** or **blocks** per settings; 🔒
      only the owner can override a block, and the override is audited.
- [ ] Cost of goods comes out oldest-lot-first (FIFO).
- [ ] Drafts show a per-line **"Net (preview)"** before posting.
- [ ] Entry pages use the **full screen width**; the item picker column is
      wide enough to read.

---

## 7. Proforma

- [ ] Posts with totals frozen for print, but moves **no stock and no money**.
- [ ] **Convert to sale** creates a draft sale carrying lines, charges and
      discount across.

---

## 8. Returns

- [ ] **Customer return against a sale**: cannot return more than was sold —
      cumulative across several returns. ❌
- [ ] Returned goods come back at the **original cost**, not the sale price.
- [ ] Destination zone respected: warehouse / expired / unfit.
- [ ] 🔒 Return with **no** sale reference is owner-only and demands a cost. ❌
- [ ] Refund lines pay cash out; no refund lines credits the customer instead.
- [ ] **Supplier return**: pick the lot, stock leaves at that lot's cost,
      supplier balance drops (or a refund comes in).

---

## 9. Consignment

- [ ] **Issue**: stock moves warehouse → on-consignment for that customer.
- [ ] Due date defaults from the consignment term in settings.
- [ ] **Settlement**: sold / returned / expired-unfit quantities split
      correctly — sold bills the customer, returned comes back to warehouse,
      expired goes to the zone you pick.
- [ ] Settling **more than is still out** is refused. ❌
- [ ] Settlement uses the **issue's frozen price and tax rate**, not today's.
- [ ] 🔒 Voiding a **settled** issue is refused, naming the settlement to
      void first. ❌
- [ ] Consignment report shows what is still out, per customer.

---

## 10. Payments

- [ ] **Customer payment (RC)** settles a credit sale; balance drops.
- [ ] **Supplier payment (PV)** settles a receiving.
- [ ] Payment lines start as **a single row**; the ✕ removes a row.
- [ ] Clearing a payment amount does not block saving.
- [ ] **One payment settles one invoice** — two invoices on one receipt is
      refused. ❌
- [ ] Allocation must equal the payment exactly — **no advances or
      overpayments**. ❌
- [ ] Allocating more than an invoice's remaining balance is refused. ❌
- [ ] Paying an invoice belonging to a **different party** is refused. ❌
- [ ] With *Never* negative balances set: paying more than a cash account
      holds is refused, naming the account and both figures. ❌

---

## 11. Withholding and the tax office

- [ ] Withholding on sales/purchases each obey their settings switch. ❌ when off.
- [ ] Customer withholds on a receipt → certificate number captured, the
      amount lands in "tax office owes us".
- [ ] You withhold on a supplier payment → the amount lands in "we owe the
      tax office".
- [ ] **Remittance (WR)** pays the bucket down; remitting more than is owed
      is refused. ❌
- [ ] 🔒 Voiding a payment whose withheld tax was **already remitted** is
      refused, naming the remittance to reverse first. ❌
- [ ] 📄 Withholding certificate prints.

---

## 12. Expenses and transfers

- [ ] Expense needs a category and at least one payment line; total must
      match the lines. ❌
- [ ] Transfer needs two **different** accounts and a positive amount. ❌
- [ ] Both show correctly on the cashbook and Finance page.

---

## 13. Stock operations

- [ ] **Zone move**: warehouse → expired / unfit works.
- [ ] 🔒 Moving to **disposed** is owner-only. ❌
- [ ] Source and destination must differ. ❌
- [ ] 🔒 **Adjustment** is owner-only and demands a reason. ❌
- [ ] Positive adjustment creates a lot; negative consumes oldest-first.
- [ ] 🔒 **Stock count** is owner-only; posting it auto-creates the variance
      adjustment.
- [ ] Voiding a stock count reverses its adjustment too.

---

## 14. Void and correct

- [ ] 🔒 Void is owner-only and **demands a reason**. ❌ without one.
- [ ] Destructive buttons say **what they will do** before you confirm.
- [ ] Voiding an invoice also reverses **the payment that settled it**.
- [ ] Voiding a sale also reverses **its customer return**.
- [ ] Voiding a cash sale reverses its automatic payment.
- [ ] A voided document is **immutable** — no edits, no pencils.
- [ ] 🔒 **Correct this document**: creates an editable copy; the original
      stays **posted and live** until the copy is posted.
- [ ] Abandoning the correction draft leaves the original untouched.
- [ ] Posting the correction voids the original **in the same step** — the
      books never hold a reversal without its replacement.
- [ ] Only one open correction per document at a time. ❌

---

## 15. Editing a posted document

- [ ] Posted document shows a **"Still editable"** card with a ✎ per field.
- [ ] Five fields: fiscal receipt no, machine total, withholding certificate
      no, payment due date, notes.
- [ ] ✎ opens **that field alone**; Save writes only it; **Cancel changes
      nothing**.
- [ ] 🔒 **Payment due date** is owner-only. ❌ for an employee.
- [ ] Every edit writes a `DOCUMENT_FIELD_UPDATE` audit row naming **one**
      field, with before and after.
- [ ] Anything that moved stock or money has **no pencil** — totals,
      quantities, prices, party.
- [ ] With **fiscal machine off**, neither the receipt number nor the machine
      total has a pencil. ← *newly fixed*
- [ ] Drafts still open the full edit form, not the pencil card.

---

## 16. Attachments

- [ ] Upload a PDF, a JPG and a PNG to a document.
- [ ] A renamed non-image (e.g. `.exe` renamed `.pdf`) is **refused**. ❌
- [ ] Over 10 MB refused; more than 10 files per document refused. ❌
- [ ] Delete works while the document is a **draft**; once posted, deletion
      is refused. ❌
- [ ] 🔒 Owner can **void** an attachment — it hides, the file is never
      destroyed, and the reason is audited.

---

## 17. Printing 📄

- [ ] **Compact** and **Detailed** layouts both print.
- [ ] **Cash sales attachment** layout prints.
- [ ] Company name, address, TIN and **phone** appear on every layout.
- [ ] Item lines show the **full description** — generic (brand), strength,
      dosage, unit, pack.
- [ ] Totals sit at the **bottom** of the page.
- [ ] **Prepared by** + signature line present.
- [ ] Party shows **name and TIN**, never internal codes.
- [ ] Grid separators render on the generic and picking-list layouts.
- [ ] **Picking list** for the storeroom: no prices, drafts included.
- [ ] Draft printouts carry the **draft watermark**.
- [ ] With fiscal machine **off**, the fiscal receipt line is gone from the
      printout. ← *newly fixed*
- [ ] Print on real paper once — margins and page breaks are only real on paper.

---

## 18. Reports

Open every one, with a date range that has data:

- [ ] Stock on hand · Stock movement · Low stock · Expiry
- [ ] **Valuation at lot cost** — cross-check one item by hand
- [ ] Sales · **Profit** (revenue, COGS, gross) · Losses
- [ ] AR aging · AP aging · AR balances · AP balances
- [ ] Consignment outstanding
- [ ] VAT · Withholding received · Withholding payable
- [ ] Expenses · Cashbook
- [ ] **Customer statement**
- [ ] Cost columns are hidden from employees, shown to the owner.
- [ ] A **customer return** shows as a **negative** on the sales and profit
      reports — not as another sale.
- [ ] A **voided** document appears nowhere in any report total.
- [ ] Reports disabled by a settings switch (e.g. VAT with no VAT) are hidden.

---

## 19. Dashboard and Finance

- [ ] Dashboard shows overdue AR, overdue AP and consignments coming due.
- [ ] Moving a payment due date (owner) changes what counts as overdue. ← ties to §15
- [ ] Finance page: every cash and bank balance is right — **count the actual
      drawer against it once**.
- [ ] A negative account shows **red**, not hidden.
- [ ] Month figures (revenue, COGS, gross, expenses, net) look sane.

---

## 20. The audit trail 🔒

- [ ] Every post, void, override, correction, settings change, master-data
      change and field edit has a row.
- [ ] Rows name **who**, **when**, **what**, and before/after values.
- [ ] Nothing in the app can delete or edit an audit row.

---

## 21. Reality checks

Worth more than any single tick above:

- [ ] Pick one medicine. Count it **on the shelf**. Compare to Stock on hand.
      They must match.
- [ ] Pick one customer with history. Add up their invoices minus payments by
      hand. Compare to their AR balance.
- [ ] Count the **cash drawer**. Compare to the Finance page.
- [ ] Pick one posted sale. Check the printout against the screen against the
      audit log — same numbers in all three.

---

## 22. Sign-off

- [ ] Everything above passes, or every failure is written down as a risk.
- [ ] Backup taken and a **restore actually tested** — a backup you have never
      restored is not a backup.
- [ ] UPS in place; the client knows what to do on a power cut.
- [ ] Staff have been shown: posting, voiding, correcting, and where the
      picking list is.

**Tested by:** ______________  **Date:** ____________
**Version tag shipped:** `v________`

## Batch expiry corrections (D121 / R91)

The owner can correct a mistyped batch expiry from the inventory page. Until
R91 is closed, **do it when nothing is being posted** — not mid-sale, not from
a second tab with a document open. The correction does not lock against
posting, so a sale in flight could commit against the old date.

Every correction is audited with the reason, the old and new dates, and the
documents that share the batch. If the new date is earlier than a sale of that
batch, the dialog says so before you confirm — that is a recall question, not
a bookkeeping one.
