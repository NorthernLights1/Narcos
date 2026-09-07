# Narcos Manual Testing Guide

A hands-on walkthrough of the whole app in business order: set up → master
data → receive stock → sell → get paid → check the books. Each step says what
to do and **what you must see** — if you see something else, that's a bug.

Written for a dev machine (Linux, `.venv`, PostgreSQL on localhost).

> **2026-09-06 round 22 — five client requests (D123–D130):** **hard-refresh**
> (`?v=20260906a`), then check each of these.
>
> - **Empty batches are gone from the sale picker (D124).** Sell a batch down
>   to zero, then start a new **Sale** and open the batch list for that item —
>   the empty one is not there. Now open a **Customer return**, an
>   **Adjustment**, a **Stock count** and a **Proforma**: it must still be
>   there in all four, and a proforma must still quote it. Then take a draft
>   sale that names a batch, sell that batch dry from another document, and
>   re-open the draft: it must still save, and must still show its batch.
> - **Batch numbers suggest themselves on receiving (D128).** Start a
>   **Receiving**, pick an item you have received before, and type the first
>   character or two of a batch number. Existing batches appear beneath the
>   box with expiry and quantity; click one and both the number **and the
>   expiry** fill in. Type the same number in the wrong case (`b001` for
>   `B001`) — you must get a warning that a different capitalisation makes a
>   second batch.
> - **Retired items disappear from pickers (D125).** Set an item inactive in
>   Master → Items, then start a Sale: it is no longer offered. A draft that
>   already names it must still save.
> - **Two new reports (D126).** Reports → Sales & profit → **Sales by brand**
>   and **Sales by generic**. Check the average, lowest and highest price
>   columns against an item you have sold twice at different prices. As an
>   employee, COGS and Profit must not appear — in the table **or** the CSV.
> - **Who owes who (D127).** Reports → Receivables & payables → **Who owes
>   who**. Give one customer and one supplier the same tax number typed
>   differently (`0012345678` and `001-2345678`) and confirm they pair. They
>   must still pair after you deactivate the supplier.
> - **Corrections keep bonus units (D123).** Receive 100 with 10 free, post,
>   then Correct it. The replacement draft must carry `free_qty = 10` — before
>   this it voided 110 and re-posted 100.
> - **Number boxes ignore the wheel (D129).** Open a **Stock count**, click
>   into a quantity, and scroll the page. The number must not change.
> - **Posting asks first (D130).** Post any draft. A dialog lists item, batch
>   and quantity **in base units**, plus the total, and says a posted document
>   cannot be edited. Cancel must change nothing.

> **2026-08-05 editing in place (D114):** the **Reference fields** button is
> gone. A posted document now has a **"Still editable"** card: fiscal
> receipt no, machine total, withholding certificate no, payment due date
> and notes, each with a small **✎**. Click it, the value becomes a box;
> Save writes just that field and audits it, Cancel changes nothing. Fields
> that moved stock or money have no pencil — that is the rule, not an
> oversight. Payment due date is **owner-only** (it moves AR/AP overdue);
> the rest stay open to staff. To verify: post any document, edit the
> fiscal receipt number inline, then check Administration → Audit log for a
> `DOCUMENT_FIELD_UPDATE` row naming only that field. **Hard-refresh**
> (`?v=20260805a`).

> **2026-08-04 field feedback round (D109–D112):** document entry pages now
> use the **full screen width** and the item picker column is wider. All
> three print layouts show the **full item description** — generic (brand),
> strength, dosage, base unit, pack — and the generic/picking-list tables
> are full **grids** like the attachment. On the item form (Master → Items
> and the receiving dialog): **VAT exempt starts ticked** and follows the
> category (DRUG on, others off) until you touch the box; **Base unit is a
> dropdown** of the common units with *"Other — type it below"* revealing a
> free-text box. To verify: open a new Receiving on a wide monitor (form
> fills the screen), add an item with category EQUIPMENT (exempt box
> unticks itself), pick base unit *Other* and type "pack of 25" (saves
> verbatim), then print any sale — every cell bordered, descriptions full.
> Item pickers now always open **downward** and overlay the page
> cleanly (D113). **Hard-refresh** (`?v=20260804b`).

> **2026-08-03 improvement batch (D102–D108):** items now read
> **generic-first** everywhere — dropdowns, refusal messages, the items list
> (new *Generic name* column) and the Cash Sales Attachment
> (`Generic (Brand), Strength, Dosage`). The generic printout gains a
> **Prepared By** + signature line. "Due date" boxes are labelled **"Payment
> due date"**. A saved draft's per-line net shows as **"Net (preview)"**
> instead of 0.00. With *Fiscal machine present* off, the machine-total box
> is gone from the posted-document **Reference fields** form too. Sales,
> proforma and consignment-issue documents (drafts included) offer a
> **Picking list** print — item, batch, shelf/bin, qty, tick boxes, no
> prices. On a **Receiving**, the Lines card's **+ New item** opens the full
> item form in a dialog; the created item drops straight into the pickers.
> To verify: create a receiving, press *+ New item*, save one with only a
> name+price — it must get an auto code, appear selected on an empty line,
> and show under Master → Items with an audit row. **Hard-refresh** the
> browser first (`?v=20260803a`).

> **2026-07-17 deployment (D83):** production now runs as a Docker stack on a
> Windows 10 host — see [DEPLOYMENT.md](DEPLOYMENT.md). This guide's app
> walkthrough is unchanged; only *where it runs* differs. To exercise the
> production server path on the dev machine (no Docker needed), run the exact
> container command and hit it:
> `NARCOS_DEBUG=0 NARCOS_SECRET_KEY=x NARCOS_ALLOWED_HOSTS=127.0.0.1 .venv/bin/waitress-serve --listen=127.0.0.1:8091 narcos.wsgi:application`
> then browse `http://127.0.0.1:8091/` — you must see the login page (a `302`
> to `/login` for an anonymous request), and `/static/css/app.css` must return
> `200` (whitenoise) after `manage.py collectstatic`. A disallowed `Host`
> header must return `400`. Container build/boot itself is validated by CI on a
> release tag and on the client machine.

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

> **2026-07-17 print fixes (D82):** document printouts no longer show the
> stray "Name only — internal master codes…" paragraph in the party box
> (it was a wrapped template comment rendering literally), and the party's
> **TIN** now prints under their name when the customer/supplier record
> has one. To verify: print any sale or consignment issue for a party
> with a TIN — party box shows *name + TIN, no CUS-/SUP- code, no stray
> text*.

> **2026-07-26 field-testing round 1 (D84–D87):**
> - **Receiving form has no Free box** any more (no bonus goods in this
>   trade). Old documents that carried free units keep their numbers.
> - **Printouts show Subtotal / Tax / Total at the bottom**, after the
>   goods; the party box (name + TIN) stays at the top.
> - **Payment lines start as one row** — use **+ Add row** to split
>   across accounts, ✕ to remove a row.
> - **Clearing a typed payment amount no longer blocks saving**: a
>   never-saved row without an amount is ignored even if an account or
>   method was picked on it. To verify: on a sale, type an amount on a
>   payment row, pick an account, delete the amount, save — no "enter a
>   number" complaint, and no payment line is created.
> - **Rows are removed with the ✕ button** at the end of each row (D88) —
>   the old tick boxes are gone. On a new row ✕ removes it immediately; on
>   a row that was already saved the row disappears and the deletion is
>   written when you save. To verify: add three lines, ✕ the middle one,
>   fill the rest and post — the posted document has exactly the two lines
>   you kept, in order.

> **2026-07-28 field-testing round 2 (D89–D91):**
> - **Settings has four new switches** (D89): *Fiscal machine present*,
>   *Discounts in use*, *Pack conversion (factor) in use*, *Sale price
>   editable at the time of sale*. Turning the first three off hides the
>   machine-total, discount (document + line) and factor boxes; the last
>   one lets staff type a price on sales/proformas/consignment issues
>   instead of taking the item's price. All four start at today's
>   behaviour — **nothing changes until you flip a switch**. Documents
>   posted earlier keep their discounts/factors and still total the same.
> - **"Correct this document"** (D90): on any posted document the owner
>   now sees one **Reason** box with two buttons — *Correct this document*
>   voids it and immediately hands back a draft copy to fix and post;
>   *Void only* is the old behaviour. To verify: post a sale with the
>   wrong quantity, correct it, change the quantity on the draft that
>   opens, post — the original shows VOIDED, the new one carries the note
>   "Corrects SI-0000NN". Where a void is refused (a receiving whose stock
>   was already sold), correcting is refused too and no draft appears.
> - **Company phone on printouts** (D91): fill *Settings → Phone numbers* —
>   it now prints under the TIN on every layout, not just the attachment.

> **2026-07-28 correcting is now reversible (D92/D93):**
> - **Correct no longer voids anything straight away.** Clicking *Correct
>   this document* opens the draft copy; the original **stays posted and
>   still counts** until you post that copy. Posting the copy voids the
>   original at that moment, in one step. **Delete the draft and nothing
>   ever happened.** Posting a correction is owner-only.
> - To verify: correct a sale, then *delete the draft* — the original must
>   still read POSTED. Do it again, fix the quantity (and the cash payment
>   line to match), post — now the original reads VOIDED with your reason,
>   and the new document has its own number. Both documents show a
>   "correction pending" banner while the draft is open.
> - **The stock case worth trying:** with 10 packs on hand, sell 8, then
>   correct to 9 and post. It must succeed — the void hands the goods back
>   inside the same step. If posting fails for any reason, nothing is
>   voided.
> - **Confirmation dialogs** now appear on *Correct*, on *Post* for a
>   correction draft, and on *Void only*. Each states what it will do and
>   quotes your reason back. Note **Void only** is now the dangerous one —
>   it reverses with no replacement.

> **2026-08-02 the void takes the money with it (D94–D98):**
> - **One receipt settles one invoice** (D94). A receipt against two invoices
>   is refused, telling you to enter one per invoice. Partial payments are
>   unaffected — one invoice, part of its balance, is still fine.
> - **Voiding an invoice reverses the receipt that settled it** (D95).
>   Verify: credit sale 200, receipt 200 (customer owes 0), void the sale.
>   The customer must land at **0.00**, not −200.00, and the receipt shows
>   VOIDED with your reason plus "(settled SI-0000NN)".
> - **Voiding a sale reverses its customer return** (D96). Sell 5 on credit,
>   take 2 back as a customer return, void the sale: customer at **0.00** and
>   the warehouse count exactly what it was before the sale. Before this, the
>   warehouse gained two packs that never existed.
> - **A settled consignment issue refuses the void in plain words** (D97):
>   *"CN-0000NN was already settled by CS-0000NN. Void the settlement
>   first…"* — it used to talk about CONSIGNED stock levels.
> - **The dangerous dialogs are type-gated** (D98). *Void only* and *posting
>   a correction* show a red panel listing every consequence and every linked
>   document that will be reversed, and the confirm button stays greyed out
>   until you **type the document number**. *Correct this document* stays
>   calm on purpose — it is reversible.

> **2026-08-03 the last void gaps (D99/D100):**
> - **A payment cannot be voided once its withholding was remitted** (D99).
>   Verify (needs *Withholding on purchases* on): receive 1000 on credit, pay
>   it as 970 cash + 30 withheld, post a WR remittance for the 30. Try to
>   void the payment — **refused**, naming WR-0000NN. Try to void the
>   receiving instead: also refused, same reason. Void the remittance first,
>   then the payment — both succeed and *withholding owed* returns to 0.00.
>   Before this fix, withholding owed went to **−30.00** with the money
>   already at the tax office.
> - **Refusals name the medicine** (D100). Post opening stock of 20 packs,
>   sell 5, void the opening: the refusal must read *"Not enough stock: AMOX
>   — Amoxicillin, batch B-1 in Warehouse (have 15, need 20)"* — not "item 10
>   lot 12". Voiding a receiving whose goods were sold names the documents
>   that took them (e.g. "have already moved on SI-000012").
> - **Negative cash is now your choice** (D101). *Settings → Cash and bank may
>   go negative*: **Allowed** (the default, today's behaviour), **Not when
>   voiding**, **Never**. To verify: with an empty drawer, post an expense of
>   4,000. On *Allowed* it posts and **Work → Finance** shows the account in
>   red with "negative — income or an opening balance has not been recorded".
>   On *Never* it is refused, naming the account and the shortfall. On *Not
>   when voiding* the expense posts normally, but voiding the opening-cash
>   document the money was spent from is refused. **Nothing changes until you
>   move the setting.**

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
