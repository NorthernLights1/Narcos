# Business Logic (plain words)

The shared mental model. No tech, no schema. If something here is wrong, fix it
here first — everything else depends on it.

## What the business is

- A **middleman / wholesaler**. Buys medicine and medical/lab supplies in
  **big quantities** from large suppliers, resells in **smaller quantities** to
  pharmacies and clinics.
- "Smaller quantities" means **fewer packs**, not opened packs — he's a
  wholesaler, not a retailer; today a box is bought, stocked, and sold as a
  box. The system still keeps a **unit-conversion model**: an item has a
  **base unit** and may have bigger units (e.g. "carton of 100") with fixed
  factors; stock always counts in the base unit (D62). That way, if selling
  in other units ever starts, nothing needs rebuilding.
- Makes nothing. Just **buys, holds, resells**.
- Earns the **gap**: buy cheap in bulk, sell a bit higher.
- Single company, single main warehouse. Money is **Ethiopian Birr only**.

## The three ways they sell

- **Cash sale** — pharmacy takes goods, pays now. Done.
- **Credit sale** — pharmacy takes goods now, **pays later**. They now owe us.
- **Consignment** — the special one (see below).

## Consignment (the model we locked)

- We hand goods to a pharmacy, but **we still own them** the whole time they sit
  on the pharmacy's shelf.
- **Price and tax are fixed at the moment of consignment** (locked on the
  consignment note).
- The sale **only becomes real when the pharmacy settles up** (returns / reconciles),
  usually after about 3 months.
- Each consignment has a **settlement term** (default 3 months). The dashboard
  **reminds 2 weeks before and again 1 week before** the term is up, and flags
  the consignment **overdue** once it passes (D60) — chase before the
  deadline, not after.
- At settlement, the issued quantity splits into **three buckets**:
  - **Sold** → counts as a real sale now, at the locked price → pharmacy pays
    cash or owes us → **tax becomes due now**.
  - **Returned good** → comes back into our warehouse as normal stock.
  - **Expired / damaged** → comes back, then goes to the expired or unfit pile.
- **Expiry risk is ours.** If it expires on their shelf, that's our loss.
- **Expired consignment goods can only become "expired" by being returned
  first** (the honest path) — never marked expired while still sitting at the
  pharmacy. Direct "mark as expired" is only for goods already in our own
  warehouse.

## The goods ("stock")

- The catalog is a **mix**, not just drugs: **drugs** (tablets, capsules,
  syrups), **reagents**, **consumable supplies**, and durable **equipment**
  (microscope, stethoscope, BP machine, etc.). The **category** says which kind.
- Stock = **physical things** sitting somewhere.
- **Drugs and reagents are batch-tracked**: each has a **batch number**
  (production run) and an **expiry date**.
- **Equipment and general supplies are not batch-tracked** and usually **never
  expire** — they move without a batch or expiry.
- Each item carries two switches that follow its kind: *batch-tracked?* and
  *has expiry?* (drugs/reagents = yes/yes, equipment = no/no).
- Note: an item the wholesaler **sells** is a sellable item; equipment the
  wholesaler **owns and uses** internally is tracked separately as a non-sale
  item.
- We always know **where each box is**: main warehouse, a specific shelf/bin,
  out on consignment (still ours), expired, unfit/damaged, or disposed.
- **Why batch + expiry matter so much:** medicine expires, and whole batches can
  be **recalled**. We must be able to say "batch X went to these pharmacies — get
  it back."
- **No negative stock.** Can't sell 100 if only 80 exist. The system blocks it.
  Only the **owner** can force it, and only with a written reason.

## The money side — five separate buckets

1. **Cash we actually have** (cash in hand + bank). Up when paid, down when we
   pay someone or pay an expense.
2. **Money owed to us** (receivables). A credit sale creates it; a payment
   shrinks it.
3. **Money we owe** (payables). A credit purchase creates it; paying the supplier
   shrinks it.
4. **Tax office owes us** (withholding credits). When a big customer keeps back
   3% of a payment, that 3% lands here — it's income tax we've already paid.
   Used up at year-end tax filing. (See the tax section.)
5. **We owe the tax office** (withheld from suppliers). If we keep back 3% when
   paying a supplier, it lands here until we remit it to the tax office.
   (Optional — see the tax section.)

**Profit** = what we sold it for − what that exact stock cost us − expenses
(rent, salary, delivery, etc.).

## The "notebook" rule (core design idea)

- Every action is a line in a notebook. **You never erase a line.**
- Mistakes are fixed by writing a **cancelling line** (a "void"/reversal) and
  then a correct one — never by editing the original.
- So a finished document (invoice, receipt) is **locked**. History stays honest
  and fully auditable.

## Tax — two separate games

Two different taxes touch this business. Don't mix them up:
**VAT** is a tax on the *sale itself*. **Withholding** is *income tax collected
early* out of a payment. They live in different places and different buckets.

### VAT (tax on the sale)

- ETB only.
- A business uses **one** tax regime, set at company level: **VAT (15%)**,
  **TOT (2%)**, or **none**. You don't mix *regimes* (VAT and TOT) on one invoice.
- **But within VAT:** individual *items* can be **VAT-exempt**. In Ethiopia
  **medicines are VAT-exempt by law** (VAT Proclamation 1341/2024); equipment
  and general supplies are not. So a VAT invoice can have some lines at 15% and
  some at 0%. VAT is charged on the **taxable lines only**. *(Confirmed by the
  client and by law — this is real for this business, since most of the catalog
  is medicine. See D50.)*
- Same on the buying side: when we buy medicines from big suppliers, the
  invoice carries **no VAT** — that's normal, they're exempt goods.
- The tax that applied is **frozen onto the document**, so old invoices always
  show the tax that was correct then.

### Withholding (income tax collected early) — the 3% game

- The law makes **big buyers collect income tax on behalf of the government**.
  "Big buyer" = a **body**: a PLC, share company, government office, or NGO.
  Small buyers (ordinary sole-proprietor pharmacies) do **not** withhold.
- **When we sell to a PLC:** they pay us only **97%** of what they owe and hand
  the other **3% to the tax office in our name**. We get the cash **plus a
  withholding certificate** worth the 3%.
- **The 3% is NOT lost money and NOT less revenue.** Revenue is still the full
  invoice. The 3% is **our own income tax, pre-paid**. Think of the certificate
  as a voucher: at year end the accountant subtracts all our collected
  certificates from the business's annual income-tax bill. If the certificates
  add up to more than the tax bill, the difference is **refundable**.
- **When we pay suppliers**, the mirror may apply: *if the business itself
  counts as a body*, it must keep back 3% of the payment, give the supplier a
  certificate, and pass that 3% to the tax office (a debt to the government
  until remitted, normally monthly). Whether this applies **depends on each
  client's legal form** — the app never assumes it; it's a switch set at
  go-live (D52, D54), so the same system serves a PLC or a sole proprietorship.
- Both directions are **optional, org-wide settings**, applied per transaction
  with a checkbox. Current rate **3%** (raised from 2% in Aug 2025); the rate is
  a setting, not hard-coded.
- Legal thresholds exist (withholding applies to goods purchases above
  ETB 20,000, services above ETB 10,000 per transaction) — the app does **not**
  enforce them; the human ticking the checkbox decides. The threshold note
  belongs in help text.

### How the year end lands

- **VAT**: handled per month via the fiscal machine / accountant, as before —
  our numbers are internal cross-checks (D18).
- **Withholding we suffered (customers kept 3%)**: sits in the
  **"tax office owes us"** bucket all year. Year-end report = list of
  certificates + total → the accountant uses it as a **credit against the
  annual income tax**. The pile then resets for the new fiscal year.
- **Withholding we took (from supplier payments, if enabled)**: sits in the
  **"we owe the tax office"** bucket until remitted (monthly). Year end it
  should be near zero; the report shows what was withheld, what was remitted,
  and what's still owed.
- Both reports follow the **Ethiopian fiscal year** (D19).

## People

- **Owner** — everything: approve, void, override rules, settings, all reports.
- **Employee** — daily work (enter sales, receive goods, record payments, look up
  stock, limited reports). **Cannot void or override.**

## What v1 is NOT

Full ERP, full general-ledger screens, journal entries, trial balance, balance
sheet, depreciation engine, payroll, multi-branch, multi-currency, barcode,
mobile app, offline sync, public internet exposure, e-invoice/regulatory API,
contract-pricing engine, manufacturing, CRM, forecasting, per-tablet tracking,
and **editing posted documents**.
