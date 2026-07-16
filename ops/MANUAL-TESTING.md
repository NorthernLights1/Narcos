# Narcos Manual Testing Guide

A hands-on walkthrough of the whole app in business order: set up → master
data → receive stock → sell → get paid → check the books. Each step says what
to do and **what you must see** — if you see something else, that's a bug.

Written for a dev machine (Linux, `.venv`, PostgreSQL on localhost).

> **2026-07-10 UI update (D67/D68):** master codes are now auto-assigned
> (`ITM-0001`…) — the forms no longer ask for one. Document line tables have
> an **+ Add row** button; item/batch/party pickers are searchable; batch
> options show `item · batch · expiry · on-hand`. Priced forms show a **live
> totals preview**, drafts show an **Expected totals** card before posting,
> and payments show a **Payment check** panel (paid + withheld vs allocated).
> Where the steps below say "enter code X", skip it — codes assign themselves.

> **2026-07-12 UI update (D70–D72):** the register page is labelled
> **Transactions** (same URLs). All forms carry grey placeholder hints.
> Batch pickers **filter to the line's item** and show `exp · on hand` under
> the box once picked. AUTO-priced items prefill *latest cost × (1+margin)*.
> **Payment amounts prefill** (cash sale total; allocation open balances;
> withheld from the invoice's expectation) — a manual edit always wins, and
> receivings never prefill (empty = bought on credit). Consignment:
> withholding is ticked **on the issue**; settle via the **"Settle
> consignment" button** on the posted issue — the split lines and the money
> due compute themselves.

> **2026-07-15 finance & reconciliation package (D76–D79):**
> - **Reports → Statement**: pick a customer *or* supplier + period →
>   opening balance, every movement with a running balance, closing
>   balance. CSV + Print. This is the reconciliation page to walk through
>   with the other business. If the party shares a TIN with a record on
>   the other side (vendor who both buys and sells), a note links to
>   their other statement — books stay separate, no netting.
> - **Transactions list** now filters by **Customer / Supplier / From / To**.
> - **Attachments** on every document (bottom of the detail page): scan of
>   the supplier invoice, delivery note… PDF/JPG/PNG/WebP, 10 MB. Delete
>   only while draft; after posting the owner can *void* one with a reason
>   (hidden + audited, never destroyed). 📎 count shows on the list.
> - **Print → Cash sales attachment** on any sale: the trade's paper form
>   (20-row table, buyer TIN/license, signature lines). Fill company
>   phones in Settings and the buyer's license/city/mobile on the customer
>   for a complete header.
> - **Work → Finance** (owner only): net position, cash/bank per account,
>   AR/AP with overdue slices, stock at cost vs at price, month P&L,
>   withholding. **Receivings now take a due date** — set it and overdue
>   payables surface on the dashboard (new **AP overdue** card).

> **2026-07-16 pricing rules (D80/D81) — the CN-000002 lesson:**
> - **Prices are no longer typed on sales, proformas, or consignment
>   issues.** The price column fills itself from the item when you pick it
>   and is read-only; the server enforces it too. To charge less, use a
>   line or document discount. Picking an item with no usable price is
>   refused with a message to fix the item first.
> - **Items now require a price**: maintained price > 0, or auto-margin
>   with a margin %. The CSV import refuses priceless rows. Old items
>   without a price get caught on their next edit — or immediately if
>   someone tries to sell them.
> - Settlement preview: if an item was issued at two different prices, the
>   preview now says it can't price those rows (before, it silently
>   under-counted; the posted totals were always correct).
> - **Reports → AR balances by customer / AP balances by supplier**: who
>   owed what *as of the end date* — one row per party, grand total,
>   CSV. Separate from aging on purpose: no due dates here, just the
>   snapshot. Each row's figure equals that party's Statement closing
>   balance for the same date.
> - **Reports hub is grouped** (Stock / Sales & profit / Receivables &
>   payables / Tax / Money) and hides reports your settings make
>   permanently empty — with withholding-on-purchases off you won't see
>   "Withholding withheld/remitted/owed"; enable the setting and it
>   returns. Nothing was deleted.

---

## 0. One-time setup

```bash
cd ~/Documents/Project/Narcos

# 1. Confirm the app and DB are healthy
.venv/bin/python manage.py check
.venv/bin/python manage.py migrate

# 2. Make sure you have an owner login you know the password to.
#    (The DB currently has one user: 'testowner', role OWNER.)
.venv/bin/python manage.py reset_owner_password testowner --password "pick-a-password"
#    — or create a fresh owner:
.venv/bin/python manage.py createowner owner --password "pick-a-password"

# 3. Start the server
.venv/bin/python manage.py runserver
```

Open <http://127.0.0.1:8000/>. You should be **redirected to the login page**
— nothing in this app is reachable without logging in.

### Fixing the automated test suite (one-time)

`pytest` currently fails with *"permission denied to create database"*: the
`narcos` PostgreSQL role can't create the throwaway `test_narcos` database.
Fix once as the postgres superuser:

```bash
sudo -u postgres psql -c "ALTER ROLE narcos CREATEDB;"
.venv/bin/python -m pytest   # 185 tests should now run
```

The automated suite covers the invariants (I1–I13); this manual guide covers
what the tests can't — the screens, the flow, and the feel.

---

## 1. Screen map

| Area | URL | Notes |
|------|-----|-------|
| Login | `/accounts/login/` | |
| Dashboard | `/` | |
| Company settings | `/settings/` | Owner-relevant: tax regime, rates, credit policy |
| Users | `/users/` | Create employee accounts here |
| Audit log | `/audit/` | Every change shows up here |
| Master data | `/master/items/`, `/master/customers/`, `/master/suppliers/`, `/master/accounts/`, `/master/expense-categories/`, `/master/fixed-assets/` | Each has list, new, edit, CSV import |
| Transactions | `/documents/` | The register: list + filter; create via `/documents/new/<TYPE>/` |
| Reports | `/reports/` | 16 reports; some owner-only |

Document types you can create: `RECEIVING`, `SALE`, `PROFORMA`,
`CONSIGNMENT_ISSUE`, `CONSIGNMENT_SETTLEMENT`, `CUSTOMER_RETURN`,
`SUPPLIER_RETURN`, `CUSTOMER_PAYMENT`, `SUPPLIER_PAYMENT`, `WHT_REMITTANCE`,
`EXPENSE`, `TRANSFER`, `ZONE_MOVE`, `ADJUSTMENT`, `STOCK_COUNT`, and the six
`OPENING_*` types.

---

## 2. Seed the company (5 minutes)

Log in as the owner.

1. **Settings** (`/settings/`): set company name, TIN, leave tax regime
   **VAT 15%**, withholding on sales **on**, rate 3%, credit action **BLOCK**.
   - ✅ Save, then open `/audit/` — the settings change is logged with
     before/after values.
2. **Accounts** (`/master/accounts/`): create `Cash` (type cash) and `CBE Bank`
   (type bank).
3. **Suppliers**: create one, e.g. `Addis Pharma Import` — note the code is
   assigned on save (`SUP-0001`), like document numbers (D67).
4. **Customers**: create two:
   - `Mekelle Clinic` — normal customer, credit limit 5,000.
   - `Ayder Hospital` — tick **is withholding agent** (they'll withhold 3%).
5. **Items** (`/master/items/`): create two (base unit comes from a dropdown;
   you can still type an unusual unit):
   - Paracetamol 500mg, base unit `tablet`, taxable.
   - Exam gloves, base unit `pair`, **VAT exempt** — gives you a mixed-tax
     invoice later. *(For the real client every medical item is exempt — D69.)*
6. Optional: test **CSV import** on `/master/items/import/` — upload a file
   with one bad row; ✅ nothing at all should import (validate-first, D57),
   and the errors are listed.

---

## 3. Receiving stock (GRN)

`/documents/new/RECEIVING/`

1. Supplier: Addis Pharma. Add lines:
   - PARA-500, batch `B001`, expiry ~2 years out, unit `box` ×100,
     qty 10, unit cost 200 (that's 1,000 tablets at 2.00 each).
   - PARA-500, batch `B002`, expiry ~3 months out (near expiry!), unit `box`
     ×100, qty 2, cost 200, **free qty 1** (bonus box, D21: cost spreads over
     paid+free units).
   - GLOVE-L, batch `G001`, qty 500 pairs, cost 5.
2. Leave payment lines empty → the whole invoice becomes a payable (on
   credit). **Post** it.
   - ✅ It gets number `GRN-000001` and becomes read-only.
   - ✅ `/reports/stock-on-hand/` shows 1,300 tablets (10×100 + 3×100) and
     500 pairs.
   - ✅ `/reports/valuation/` (owner-only) shows stock value at cost; the
     B002 lot's unit cost is 200×2/300 = 133.33/box ÷ 100 ≈ 1.33/tablet
     because of the bonus box.
   - ✅ `/reports/ap-aging/` shows you owe Addis Pharma the invoice total.
   - ✅ `/reports/expiry/` flags batch B002 as near-expiry (within 6 months).
3. **Immutability check (I1):** open the posted GRN → there is no edit of
   lines/amounts; only reference fields (fiscal receipt no. etc.) are
   editable. This is the core promise of the system.

---

## 4. Sales + tax engine

### 4a. Cash sale with mixed VAT

`/documents/new/SALE/` — customer Mekelle Clinic, kind **CASH**:

- PARA-500 ×200 tablets at 3.00 (taxable)
- GLOVE-L ×50 pairs at 8.00 (exempt)
- Document discount 100.
- Add a payment line: Cash, full grand total.

Before posting, check the totals box:
- Subtotal = 600 + 400 = 1,000. Discount 100 spreads pro-rata (D64):
  taxable base 540, exempt base 360, VAT = 540 × 15% = **81**,
  grand total = **981**.
- ✅ Post → `SI-000001`. Stock drops; `/reports/vat/` shows output VAT 81.
- ✅ FIFO check (owner): the profit report's COGS for the 200 tablets is
  200 × 2.00 = 400 — it consumed the oldest lot (B001), not the cheap bonus
  lot.

### 4b. No negative stock, ever (D4)

New SALE: try to sell 10,000 tablets. ✅ Posting fails with *"Not enough
stock"* and **nothing is saved** — no partial ledger rows, no doc number
consumed on the retry once you fix the qty.

### 4c. Credit limit (D25)

New SALE to Mekelle Clinic, kind **CREDIT**, total above their 5,000 limit.
- ✅ As employee (see §8): blocked outright.
- ✅ As owner: blocked, but you can post with an **override reason** —
  then check `/audit/` for the OVERRIDE entry.

### 4d. Expiry rule

Try selling from batch B002 with a sale date past its expiry — ✅ blocked
(you can't sell expired goods, I10).

### 4e. Proforma

Create a PROFORMA, post it, then use **Convert to sale** on the document
page. ✅ A new SALE draft appears with the same lines; the proforma itself
never touched stock or money.

### 4f. Customer return

`/documents/new/CUSTOMER_RETURN/` — pick the original sale (SI-000001),
return 50 tablets.
- ✅ Stock comes back in; the return is costed at the **original** COGS
  (2.00), not current cost.
- ✅ Try returning more than was sold across two returns — the cumulative cap
  blocks the second one (the double-return exploit is closed).

---

## 5. Money

### 5a. Customer payment (RC)

`/documents/new/CUSTOMER_PAYMENT/` — Mekelle Clinic. The allocation picker
lists **only their unpaid invoices**, each labelled with its open balance
(`SI-000002 · … · open 80.10`); picking one **prefills the allocation with
the open balance** — and the withheld amount, when the invoice expects
withholding — and the first payment line fills with allocations − withheld
(D72; edit any of them and your number wins). The **Payment check** panel
tracks paid vs allocated as you type and must reach difference 0.00 (D44).
- ✅ Over-allocating beyond an invoice's open balance is rejected (I13).
- ✅ Fully-settled invoices disappear from the picker (the auto-paid cash
  sale never appears at all).
- ✅ `/reports/ar-aging/` shrinks accordingly; `/reports/cashbook/` shows the
  cash in.

### 5b. Withholding (the tricky one)

Make a CREDIT sale > 10,000 birr to **Ayder Hospital** with
**customer will withhold** ticked. The sale shows *withholding expected*
(3% of the taxable subtotal) as display-only info.

Then a CUSTOMER_PAYMENT from Ayder: pay the invoice **minus** the 3%, enter
the withheld amount + their certificate number.
- ✅ The invoice settles **in full** (AR reaches zero) even though cash is
  short by 3% — the difference lands in `/reports/withholding-received/`
  as a certificate you'll use against your own profit tax. Revenue is
  untouched (I12).

### 5c. Supplier payment (PV) and remittance (WR)

- PV: pay Addis Pharma part of the GRN. ✅ `/reports/ap-aging/` drops.
- If withholding-on-purchases is on and you withheld from a supplier:
  `WHT_REMITTANCE` sends it to the tax authority. ✅ It can never remit more
  than what's actually in the withholding-payable bucket.

### 5d. Expense and transfer

- EXPENSE: rent 2,000 from Cash, category Rent. ✅ Cashbook and
  `/reports/expenses/` show it.
- TRANSFER: move 1,000 Cash → CBE Bank. ✅ Both account balances move; net
  money unchanged.

---

## 6. Consignment

1. `CONSIGNMENT_ISSUE` to Mekelle Clinic: 100 tablets. If the customer is a
   withholding agent, tick **customer will withhold** here — on the issue,
   not later (D70). ✅ Stock moves out of the warehouse into a **consignment
   zone tagged to that customer** — it's still yours; `/reports/consignment/`
   shows it outstanding, and no revenue or AR was created.
2. Open the posted issue and press **"Settle consignment"** (D71). The draft
   arrives prefilled: one line per item+batch with **Still out** already
   filled. Enter the split: sold 60, returned 30, 10 expired.
   - ✅ The totals panel (below the payment lines) prices the **60 sold** at
     the *issue's* frozen price as you type — returned/expired add nothing.
   - ✅ Cash settlement: the payment line prefills with that total (split it
     manually if paid part cash / part transfer).
   - ✅ If the issue was withholding-flagged, the settlement inherits it —
     there is no checkbox to remember here.
   - Post, then: the 60 became revenue + AR/cash **now** (not at issue time);
     the 30 are back in the warehouse; the 10 sit in expired/unfit and show
     in `/reports/losses/` at lot cost.
   - ✅ Settling more than is out is refused; pressing Settle again offers
     only the remainder; a fully-settled issue refuses politely.

---

## 7. Stock operations

- `ZONE_MOVE`: move damaged goods warehouse → unfit zone. ✅ Sellable stock
  drops, `/reports/losses/` grows.
- `ADJUSTMENT` (owner-only): correct a count by −5. ✅ Employee can't post it.
- `STOCK_COUNT`: opening it snapshots every warehouse balance into lines;
  enter counted quantities; posting writes the differences as an adjustment.
  ✅ Recount → stock-on-hand now matches what you entered.

---

## 8. Roles and the audit trail

1. `/users/new/` — create `staff1`, role **Employee**. Log in as staff1 in a
   private window and verify each of these is refused:
   - ❌ Voiding any posted document.
   - ❌ Posting an ADJUSTMENT.
   - ❌ Reports: valuation, profit, losses (owner-only — the hub hides them
     and the URL returns forbidden).
   - ❌ `/settings/` and `/users/`.
   - ❌ Credit-limit override.
   - ✅ Everything else (sales, receiving, payments) works.
2. **Void** (owner): void the customer return from §4f with a reason.
   - ✅ Stock and money reverse exactly; the doc shows VOIDED with who/when/why;
     the original rows stay visible (nothing is ever erased).
   - ✅ Voiding a sale that has a payment allocated: the payment voids with it
     (cascade), so nothing dangles.
   - ✅ Voiding the GRN after its stock was sold is **blocked** (D5) — the
     stock is already consumed.
3. `/audit/` — the whole session is there: settings changes, posts, voids,
   overrides, user creation. ✅ Nothing is editable or deletable.

---

## 9. Printing

Open any posted sale → **Print**. ✅ A clean print layout (compact/detailed
per settings) with doc number, TIN, VAT breakdown. For the withholding sale,
print the **withholding certificate** page too.

## 10. When you're done

Reset to a clean slate whenever you want:

```bash
dropdb -h localhost -U narcos narcos   # or: sudo -u postgres dropdb narcos
sudo -u postgres createdb -O narcos narcos
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createowner owner
```
