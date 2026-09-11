# What the client's real database contains

**Source:** `narcos.dump`, taken 2026-09-08 07:13 from the client's emergency
backup folder. Restored and queried read-only. Every number here came from a
query against that dump, not from dev data and not from reasoning.

**Why this file exists.** Round 22 was designed against a seven-item
development database. One of its features — the both-faces report (D127) —
passes six tests and returns **nothing at all** on the client's real data. That
is the failure this file exists to prevent: design against the shape below, not
against fixtures.

**Currency of this file.** A frozen snapshot. It will drift. Re-derive before
trusting anything time-sensitive; the queries are cheap.

---

## 0. How to work against this data

The client copy is the **default** local database. The old fixtures are still
available and unchanged.

```bash
.venv/bin/python manage.py runserver 8000 --noreload          # real client data
NARCOS_DB_NAME=narcos_testdata .venv/bin/python manage.py ... # the 7-item fixtures
```

- Local login on the client copy: `Admin` / `narcos-dev-2026`. **The password
  was set on the local copy only.** The client's real passwords are unknown and
  were not touched.
- The swap was done by renaming databases, **not** by editing
  `narcos/settings.py`. Line 96's fallback is `"narcos"` and that file ships in
  the Docker image; changing it would make the client's container look for a
  database that does not exist and fail on boot.
- **Tests are unaffected.** pytest builds `test_narcos` from migrations.
- The dump's schema is **identical** to the repo's migration state — 23 app
  migrations on both sides, nothing pending either way. It is drop-in
  compatible with current code.
- This copy holds 70 real businesses with names, phone numbers and outstanding
  balances. It is now what appears by default in every screenshot and shell
  output. Treat accordingly.
- Remove with `dropdb -h localhost -U narcos narcos` and restore the fixtures
  by renaming `narcos_testdata` back.

---

## 1. Settings — read this before sizing anything

| Setting | Value | Consequence |
|---|---|---|
| `sale_price_editable` | **TRUE** | Staff type prices at the counter. **R96 is answered.** D126 is a report, not R46. |
| `discounts_enabled` | FALSE | Price variation comes from typed prices only, never discounts. |
| `unit_conversion_enabled` | FALSE | Combined with §5, R93 is theoretical. |
| `tax_regime` | NONE | Correct. The release-checklist step was done. |
| `withholding_on_sales` | **FALSE** | **Wrong — see §7.** The only tax that applies is switched off. |
| `withholding_on_purchases` | FALSE | Correct. Sole proprietorship, so they never withhold when buying. |
| `withholding_rate` | 3.00 | Correct. |
| `fiscal_machine_present` | FALSE | Consistent with `tax_regime = NONE`. |

**Audit log — the only two settings changes ever made:**

| When | What |
|---|---|
| 2026-07-22 06:48 | Company identity set; `tax_regime` VAT → NONE |
| 2026-08-08 05:34 | `discounts_enabled` → False, **`sale_price_editable` → True**, `fiscal_machine_present` → False, `unit_conversion_enabled` → False |

**`withholding_on_sales` has never been changed.** It still holds its install
default.

**Consequence for reading D126's reports:** typed prices only begin on
**2026-08-08**. Sales before that carried item-master prices. A price spread
that straddles that date has two different causes.

---

## 2. Scale and what they actually use

| Document | Posted | Voided | Range |
|---|---|---|---|
| SALE | 175 | 14 | 2026-07-22 → 2026-09-05 |
| RECEIVING | 117 | 8 | same |
| CUSTOMER_PAYMENT | 78 | 1 | from 2026-07-30 |
| SUPPLIER_PAYMENT | 62 | 0 | from 2026-07-23 |
| OPENING_STOCK | 42 | 0 | 2026-07-22 → 2026-09-02 |

**Zero of every other document type.** No consignment issues or settlements, no
customer or supplier returns, no adjustments, no stock counts, no transfers, no
expenses, no withholding remittances.

Two things follow, and both should change how work is prioritised:

- **Consignment is unused.** It is a large, intricate part of the system (D6,
  D60, D70, settlement splitting) carrying zero production traffic.
- **The stock-count screen is unused**, which is where the wheel-guard (D129)
  was expected to matter most. It still matters on sale and receiving lines.

**Opening stock is being used continuously** — 23 in July, 17 in August, 2 in
September — rather than once at go-live. The taper suggests catalogue loading
spread over weeks. It creates stock with no supplier and no payable, so if it
is being used for real purchases, payables are understated. Worth confirming.

---

## 3. Items and generics — this decides the `Generic` migration

| Measure | Value |
|---|---|
| Items | 201 |
| Items with a generic name | **201** (all of them) |
| Distinct generic names | 187 |
| Distinct after lowercase + trim | **187** |

**Case folding merges nothing.** The mechanical half of the proposed migration
would create 187 rows and consolidate zero. This is the same result dev showed,
now confirmed at production scale.

> **CORRECTION, 2026-09-10 — the measurement above is right and it measured the
> wrong thing.** Case folding was never how these duplicate. They duplicate by
> the *size or dosage form being typed into the generic name*. Strip a trailing
> size/form token and **187 collapses to 154: 52 of the 187 strings are
> restatements of 19 real generics.**
>
> | Real generic | Entered as |
> |---|---|
> | ng tube | size #4, #10, #12, #16, #18 |
> | endothracheal tube | #3, #5.5, #6, #7 |
> | catheter | catheter, 2 way, 3 way 16g, 3 way 18fr, 3 way 22fr |
> | paracetamol | 120mg/5ml syrup, 500mg, 500mg of 1000, iv |
> | metronidazole | 125mg/5ml, 250mg of 50*10, injection |
> | syringe | syringe, 10cc, 5cc |
> | ibuprofen | ibuprofen, ibuprofen 400mg tablet, ibuprofen tab |
> | metoclopramide | metoclopramide, 5mg/ml in 2ml, syrup |
> | loratadine | 10mg tablet, 5mg/5ml syrup |
>
> Nineteen groups in total, plus true misspellings on top ("tanxamic acid"
> against "tranxamic acid", and "Embolectomy Cathater"). **The generic list
> really is duplicated, by about 28%.** The 154 figure is a count of
> *candidates*, not proof of 154 correct generics — stripping a suffix cannot
> decide whether "3 way", "iv" or "of 1000" is a variant, a formulation or a
> pack. The grouping needs human review, which is why the backfill is a
> reviewed command (D132).
>
> **The same size is also being recorded in three different fields**, depending
> on who typed it: in the generic name (the NG tubes), in the brand field (the
> four Vicryl records hold "2/0 R", "1 C", "2 R", "2/0 C"; also "Syringe
> 20cc"), in `strength` (Fogatery 3FH/4FH/5FH), and sometimes in two at once —
> "endothracheal tube #3" also carries `strength = "#3"`. That, not the
> spelling, is the actual data defect.

**Only 9 generics carry more than one brand** — the scenario the client
described when asking to "set the generic once":

| Generic | Brands |
|---|---|
| Vicryl | 1 C, 2/0 C, 2/0 R, 2 R |
| Azithromycin | Azithro, Azithromycin (CAZITHRO), zitromax |
| Embolectomy Cathater | Fogatery, Fogatery, Fogatery |
| Ibuprofen | Gofen, Ibuprofen, IBUT |
| Gabapentin | Gabalin, Gabapen |
| Metoclopramide | metimid, Plasil |
| Oral Rehydration Salt | ORS, ORS |
| Syringe | Syringe, Syringe 20cc |
| Tramadol | RISEOL, Tolax |

**Conclusion for R95 — superseded 2026-09-10.** The original conclusion read:
*"the migration's cleanup value is near zero; its only value is the picker."*
That followed from the case-folding measurement and does not survive the
correction above. **The cleanup value is real: 19 generics are recorded as 52
strings.** The picker argument stands and is now the lesser of the two. Note
also that "Embolectomy Cathater" is itself misspelled, which no migration may
correct — a rename on a `Generic` row can, which is the point of D132.

---

## 4. Duplicate items — this decides `superseded_by` and the merge guard

Two real duplicate sets exist out of 201 items.

**Fogatery — three records, and a guarded merge must refuse:**

| Code | vat_exempt | category | base_unit | price | lines | batches |
|---|---|---|---|---|---|---|
| ITM-0065 | **t** | **SUPPLY** | piece | 18800.00 | 2 | 1 |
| ITM-0066 | **f** | **DRUG** | piece | 18800.00 | 2 | 1 |
| ITM-0067 | **t** | **DRUG** | piece | 18800.00 | 2 | 1 |

They disagree on VAT exemption and category. The guard proposed in R95 requires
both to match, so it correctly refuses. (VAT exemption is dormant today under
`tax_regime = NONE`, but would wake on registration.)

**ORS — two records, and a guarded merge would pass:**
ITM-0103 and ITM-0156. Identical name, generic, base unit `sachet`, and every
flag. Only price differs (33.00 vs 28.00). Batch numbers do not collide
(`04126020150`, `K-02223` against `356546`, `4120098`).

**Not duplicates, despite sharing a generic:** Ibuprofen's three brands have
different base units (pack, bottle, pack) and prices (1950, 88, 290). Syringe's
two are probably different sizes. These are the multi-brand case, working as
intended.

**Conclusion for R95:** duplicates are real but rare — about 5 records in 201.
A guarded merge passes on one pair and correctly refuses the other. The guard
earns its place.

---

## 5. Batches — this is D124's payoff, and a live D128 case

| Measure | Value |
|---|---|
| Batches | 236 |
| With warehouse stock | 80 |
| **Empty** | **156 (66.1%)** |

**Two thirds of the batch picker was unsellable** before D124. This is the
strongest single justification in the dataset for anything shipped in round 22.

**A case-variant duplicate exists in production:** item ITM-0035 carries both
`s35224043` and `S35224043`. One physical batch, two permanent records, because
`get_or_create` matches the number case-sensitively. This is exactly what
D128's warning was built to catch, and it happened before D128 shipped. It
cannot be repaired — four models point at `Batch` with PROTECT.

**Pack factor:** all **617** posted document lines have `factor = 1`. Combined
with `unit_conversion_enabled = FALSE`, **R93 has never fired.**

---

## 6. Prices — this is D126's payoff

Of 70 items sold more than once, **58 (83%) went out at more than one price.**
The variation tracks the buyer, which is exactly what the client described.

| Item | Prices across customers |
|---|---|
| ITM-0001 fluco-ssp | 700, 720, 730, 750, 750, 780 across six pharmacies |
| ITM-0003 Suxathon | 98, 98, 100, 120, 125 |

Largest spreads: Ibuprofen 218%, PEG 148%, Miso 48%, Vitamin D injection 47%.

**Conclusion:** the client's premise was literally accurate. D126 answers it
from existing data. **R46 (per-customer standing price lists) is not needed to
report this** — but the per-customer pattern is real enough that R46 may be
worth revisiting as a follow-on, since staff are holding these prices in their
heads today.

---

## 7. Withholding — a live configuration gap with money attached

The client is a **sole proprietorship**, so they never withhold when
purchasing. Their customers — hospitals and PLCs — withhold 3% when paying
them. So `withholding_on_purchases = FALSE` is correct and
`withholding_on_sales = FALSE` is **wrong**.

**Staff ticked the withholding box three times in their first three days, and
nothing was recorded:**

| Invoice | Customer | Total | 3% never recorded | Settled |
|---|---|---|---|---|
| SI-000001 | Shalom primary hospital | 44,200.00 | 1,326.00 | fully open |
| SI-000002 | Shalom primary hospital | 49,446.00 | 1,483.38 | **in full** |
| SI-000003 | Alula Primary Hospital | 60,550.00 | 1,816.50 | **in full** |

Total 4,625.88. `withholding_expected` is 0.00 on all three. There are **zero**
rows in `money_withholdingledger`, zero payments carrying a withheld amount,
and zero certificates.

Only **1 of 70** customers is flagged `is_withholding_agent` (Alula), yet staff
ticked the box for Shalom, which is not flagged. The customer master is not
being maintained for this.

**The code defect behind it.** The two halves of the feature behave
differently:

- **Payment side is correct** — `_PaymentBase.validate()` raises
  `PostingError("Withholding is disabled in settings (D51/D52).")` when an
  amount is entered while the switch is off.
- **Sale side is silent** — `if settings.withholding_on_sales and
  doc.customer_will_withhold:` in `handlers_sales.py`. The tick is stored and
  ignored. `fields_hidden_by_settings()` hides boxes for the fiscal machine,
  discounts and pack conversion, but **not** withholding, so it is the only
  switched-off feature that still shows a live control.

**The risk that matters most.** Staff tick at sale time and see nothing. At
payment time the system refuses the withheld amount. The invoice will not
balance, and the tempting move is to record a **full** payment to close it —
which is consistent with SI-000002 and SI-000003 being settled in full. If
those hospitals did withhold, cash is overstated by roughly 3,300 and the
certificates are lost.

**Cannot be determined from data. Ask the client:** did Shalom and Alula pay
100%, or 97% with a certificate that was never entered?

---

## 8. Parties — D127 does not work on this data

| Measure | Value |
|---|---|
| Customers | 70 |
| Customers with a tax number | **3** |
| Suppliers | 50 |
| Suppliers with a tax number | 7 |
| Businesses appearing as both | **13** |
| Of those, matching by tax number | **0** |
| Of those, matching by name | **13** |

**D127, D79's statement counterpart, and the tax-number normaliser all return
nothing on this data.** The feature is inert as shipped.

Eight of the thirteen carry live balances:

| Business | They owe us | We owe them | Net |
|---|---|---|---|
| Bethel w/s | 182,050.00 | 411,480.00 | −229,430.00 |
| Girmay Wholesale | 225,410.00 | 98,190.00 | +127,220.00 |
| Abel w/s | 112,500.00 | 3,200.00 | +109,300.00 |
| Afewerki Araya | 97,440.00 | 4,000.00 | +93,440.00 |
| Kibrom tewlde | 33,050.00 | 0.00 | +33,050.00 |
| Merwa pharma | 12,100.00 | 0.00 | +12,100.00 |
| Vital w/s | 0.00 | 7,600.00 | −7,600.00 |
| Mihret pharmacy | 0.00 | 2,500.00 | −2,500.00 |

**Conclusion for R95:** the `Customer.also_supplier` FK is now clearly
justified, and it must be **seeded from normalised name, not tax number**. The
thirteen names are exact matches on both sides. D127 needs the same fallback or
it shows an empty table.

---

## 9. The two client bug reports

### "Entered a quantity of 180, it registered 189"

**189 exists nowhere in the database.** Zero matches in `qty_entered`,
`qty_base`, `stock_stockledger.qty_delta`, `stock_stockbalance.qty`, and
`stock_costlot.qty_received`. The ledger is append-only, so a corrected value
would still leave a trace. **The system never stored 189.**

The only 180s belong to item ITM-0085 (PEG): `OP-000020` opening stock, and
`SI-000035`. That sale carries **two lines for the same item, 180 and 16**,
each consuming its own lot exactly. The document total for that item is **196**.

**Best available explanation:** the operator typed 180, saw a larger figure for
the same item on the finished document, and reported it. The cause is the
per-batch line split, not arithmetic. **Put 196 to the client and ask whether
that is the number they saw.**

### "After a sale, more stock left in inventory than expected"

Re-investigated 2026-09-09 after the client restated it as a gap between what he
has sold and what the shelf holds, with the system reading **higher** than
reality.

**The posting engine is not the cause. Four invariants hold exactly:**

| Check | Result |
|---|---|
| `StockBalance.qty` vs `sum(StockLedger.qty_delta)` per item/lot/zone | **0 drift**, 255 rows |
| Ledger groups with no balance row and a non-zero sum | **0** |
| Voided documents' ledger rows | net to **exactly 0** (28 receiving, 32 sale) |
| `qty_base` vs `qty_entered × factor` | **0** mismatches in 647 lines |

Arithmetic closes: opening 21,703 + received 18,290 − sold 18,108 = **21,885**,
which is the balance total. All stock is in `WAREHOUSE`; the Total-column
hypothesis stays dead.

**Cause 1 — nothing has ever been written off.** There are **zero** documents of
type ADJUSTMENT, STOCK_COUNT, ZONE_MOVE, CUSTOMER_RETURN and SUPPLIER_RETURN in
the database. Every unit that ever entered is still counted as sellable unless a
sale removed it. Breakage, expiry, samples, and shrinkage have no record, so the
system can only ever read **higher** than the shelf — which is the direction the
client reports. Only 50 units (ITM-0109, batch `B-03225`, expired 2026-08-08)
sit in an expired batch, so expiry alone does not explain the size of it.

**Cause 2 — opening stock is doing the work of receiving.** 42 opening-stock
documents span 2026-07-22 to 2026-09-02, six weeks, not one go-live event, and
they account for **21,703 of the 39,993 units ever taken in** — more than every
supplier receiving combined. **36 items holding 15,370 units (70% of stock on
hand) and 2,909,790 Birr (45% of stock value) have never been received against a
supplier document at all.** Their entire quantity rests on a number typed once,
with no invoice to check it against and no payable raised. If any of those
figures was typed wrong, nothing in the system can contradict it.

**Named suspects, in order of how little supports them:**

| Item | Opened | Sold | On hand | Value | Why it stands out |
|---|---|---|---|---|---|
| ITM-0007 Tolax | 5,800 | 200 | 5,600 | 179,200 | Largest single opening line in the database, `OP-000006`. One sale line ever. |
| ITM-0037 Blood group reagents | 850 | 62 | 788 | 535,840 | Highest value with no supplier document behind it. |
| ITM-0024 Credanil | 440 | 9 | 431 | 431,000 | `OP-000040`, entered **after** the item had already been sold. |
| ITM-0041 TRADMIN | 1,200 | 50 | 1,150 | 40,250 | |
| ITM-0010 Promulet | 1,200 | 174 | 1,026 | 143,640 | |
| ITM-0011 Amoxid | 800 | 20 | 780 | 78,000 | |

**Cause 3 — four opening lines were entered after the item was already trading**,
adding 1,176 units to items that now hold 1,147. Genuine opening stock is an
item's first event; these are not.

| Opening doc | Date | Item | Qty | Earlier activity |
|---|---|---|---|---|
| `OP-000042` | 2026-09-02 | ITM-0004 zitromax, batch `F24800` | 700 | received + sold since 2026-08-13, **same batch** |
| `OP-000040` | 2026-08-30 | ITM-0024 Credanil | 440 | sold since 2026-08-29 |
| `OP-000025` | 2026-08-03 | ITM-0063 Syringe 20cc | 18 | sold since 2026-07-25 |
| `OP-000026` | 2026-08-03 | ITM-0063 Syringe 20cc | 18 | sold since 2026-07-25 |

`OP-000042` is the strongest single case: 700 units of batch `F24800` declared as
opening stock three weeks after 100 units of **that same batch** arrived on
`GRN-000047`. One physical delivery, recorded twice.

**Ruled out.** Pack-factor inflation — all 647 lines are factor 1 and
`catalog_itemunit` is empty (§5). Bonus units — `free_qty` is receiving-only and
zero on every sale line. Unit-label confusion — 16 items carry a line whose
`unit_label` differs from their base unit, but every one of them reconciles
arithmetically; the labels are sloppy free text, not a quantity error.

**The correction path, and it needs no new code.** `StockCountHandler` already
does exactly this job: it freezes a warehouse snapshot, measures `counted −
frozen`, refuses to post if anything moved mid-count (R74), and auto-posts an
owner-only ADJUSTMENT for the variance. That respects append-only — history is
never edited, the difference is written as a new entry. The screen has simply
never been used. Sequence: count the 36 items above, heaviest value first;
post one stock count per session; then `OP-000042` separately, since a
double-entered delivery is a void, not a variance.

---

## 10. What this file changes

| Was | Now |
|---|---|
| R96 open — is `sale_price_editable` on? | **Answered: yes.** D126 is a report. R46 not needed. |
| R95 — `Generic` migration value unknown | **Corrected 2026-09-10: real.** Folding merges nothing, but 52 of 187 names are 19 generics with the size typed in. |
| R95 — is a guarded item merge feasible? | **Yes, narrowly.** Passes on ORS, correctly refuses Fogatery. |
| R95 — is the party FK worth it? | **Yes, and seeding must use name.** 13 pairs, 0 by tax number. |
| R93 — factor exposure live? | **No.** All 617 posted lines are factor 1. |
| D127 assumed to work | **Inert on real data.** |
| Withholding assumed configured | **Off, with 4,625.88 unrecorded.** |
| "More stock than expected" — no hypothesis | **Two causes named.** Nothing is ever written off; 45% of stock value has no supplier document. |

---

## 11. Two more client reports (2026-09-09)

### "Catheter is not in my database, I added it before"

**Confirmed, and the client is right — from the screen he was looking at.**
Ten catheter items exist. How many he can find depends entirely on which screen
he types into, because the two search boxes filter different columns.

| Screen | Code | Name | Generic | Finds typing `catheter` |
|---|---|---|---|---|
| Inventory, `stock/views.py:54` | yes | yes | **no** | **3 of 10** |
| Master → Items, `catalog/views.py` `MASTER["items"]` | yes | yes | yes | **7 of 10** |

Item-by-item, typing the correct spelling `catheter`:

| Code | Name | Generic | Inventory | Master |
|---|---|---|---|---|
| ITM-0052 | Folly cathater | Catheter 3 way 16G | no | yes |
| ITM-0053 | Folly | Catheter 3 way 18Fr | no | yes |
| ITM-0054 | Folly | Catheter 3 way 22fr | no | yes |
| ITM-0055 | Folly | Catheter 2 way | no | yes |
| ITM-0065 | Fogatery | Embolectomy Cath**a**ter | **no** | **no** |
| ITM-0066 | Fogatery | Embolectomy Cath**a**ter | **no** | **no** |
| ITM-0067 | Fogatery | Embolectomy Cath**a**ter | **no** | **no** |
| ITM-0109 | catheter | catheter | yes | yes |
| ITM-0110 | Thoracic catheter | chest tube #28FG | yes | yes |
| ITM-0111 | Thoracic catheter | chest tube #32FG | yes | yes |

**Two separate causes, and they need different fixes.**

**Cause 1 — the Inventory search ignores `generic_name`.** This trade reads by
generic name; `Item.__str__` says so in as many words (R48) and puts the generic
first in every dropdown label. The Items list searches it. Inventory does not.
So the four Folly catheters are in the database, appear in Master, appear in the
sale picker, and are invisible on the one screen whose job is to answer "how
many have I got". A one-line code fix: add `generic_name__icontains` to the
filter. Same gap will hit any brand-named item — Fogatery, ETT, NG tube, BOSO.

**Cause 2 — three items spell it `Cathater`.** ITM-0065/66/67 carry the typo in
the generic, so the correct spelling misses them on **both** screens. ITM-0052
has it in the name as well. This is data, not code, so it ships as a management
command the owner runs — never a hand edit. Note the same three are the
duplicate group §4 uses as the case a merge guard must **refuse**; correcting
the spelling does not merge them.

**Not a cause:** the document line picker. It is a Choices.js searchable select
(`data-search`, `docs/forms.py:330`) over the label `CODE — Generic (Brand)`, so
the sale and receiving screens do find "catheter". The complaint is about
Inventory.

### "Problet injection — we sold it and the number did not go down"

**The posting engine is clean. The name does not resolve. A third cause of
over-reading stock does exist, and it is new.**

**Engine, re-checked at this snapshot:** all **376** posted sale lines move
stock by exactly `−qty_base`; **0** exceptions. Balance equals ledger across all
**255** item/batch/lot/zone groups; **0** drift. **Zero** draft sales, so nothing
is sitting unposted. `free_qty` is 0 on every posted line, so the D84 bonus-unit
path cannot be leaking either.

**No item is named "Problet".** The two closest, and both are arithmetically
correct:

| Candidate | In | Sold | On hand | Closes? |
|---|---|---|---|---|
| ITM-0010 Promulet (Hydroxyprogesterone, ampoule — the injection) | 1200 | 174 | 1026 | yes |
| ITM-0117 Promulet tab | 10 | 10 | 0 | yes |
| ITM-0176 Plasil injection (Metoclopramide 5mg/ml) | 1000 | 100 | 900 | yes |

Both brands exist **twice or three times** in the catalogue (Promulet ×2,
Plasil ×3), so "the number" may well belong to a different record than the one
that was sold. **Put the item code to the client before designing anything.**

**Cause 3, and §9 missed it — a voided sale is not the same as an undone sale.**
§9 checked that voided documents' ledger rows net to zero and treated that as
proof of correctness. It is proof the reversal is *complete*; it says nothing
about whether the goods came back. Staff void an invoice to fix a price or a
quantity and then re-issue it. When the re-issue is smaller than the void, or
never happens, the difference stays on the books as sellable stock while the
customer already has it.

**Nine lines, 544 units, still counted as on the shelf:**

| Code | Item | Date | Doc | Voided | Re-issued | Gap | On hand now | Reason given |
|---|---|---|---|---|---|---|---|---|
| ITM-0096 | Epifenac (Diclofenac **IV**) | 2026-08-06 | SI-000045 | 1170 | 780 | **390** | **390** | ERROR |
| ITM-0046 | ETT #6 | 2026-07-22 | SI-000001 | 50 | 0 | **50** | **50** | ERROR |
| ITM-0001 | fluco-ssp | 2026-07-22 | SI-000001 | 40 | 0 | 40 | 0 | ERROR |
| ITM-0094 | Pethidine | 2026-09-03 | SI-000161 | 100 | 70 | 30 | 950 | ERROR |
| ITM-0002 | Gabalin | 2026-07-25 | SI-000006 | 20 | 0 | 20 | 50 | returned |
| ITM-0086 | Actirapid (insulin) | 2026-08-20 | SI-000085 | 10 | 0 | 10 | 150 | selling price adj |
| ITM-0169 | Omni | 2026-08-28 | SI-000123 | 2 | 0 | 2 | 0 | returned |
| ITM-0088 | URS-2MAC | 2026-08-21 | SI-000090 | 1 | 0 | 1 | 15 | ERROR |
| ITM-0010 | Promulet | 2026-08-25 | SI-000102 | 13 | 12 | 1 | 1026 | qty error |

Re-issue is matched as same item, same customer, posted within 14 days.

**ITM-0096 Epifenac is the one to put to the client first.** It is an injection,
which matches the words used, and its entire remaining balance is the gap:

```
2026-08-06  OP-000033   OPENING_STOCK  POSTED  1170   →  1170
2026-08-06  SI-000045   SALE           VOIDED  1170   →  1170   (Alula Primary Hospital, "ERROR")
2026-08-11  SI-000056   SALE           VOIDED   700   →  1170   (same hospital, "ERROR")
2026-08-11  SI-000057   SALE           POSTED   780   →   390
```

They billed the hospital for the whole 1170, voided it, tried 700, voided that,
and settled on 780. If the hospital in fact took more than 780, the missing
units are the 390 the system still shows. **Ask what Alula actually received.**

**Two of the nine say "returned".** There are zero CUSTOMER_RETURN documents in
the database (§2), so a return is being recorded by voiding the original sale.
That restores the quantity, which is numerically right for a *full* return and
silently wrong for a partial one, and either way it erases the fact that a sale
happened. §9's write-off gap and this are the same wound.

**Correction path.** Same as §9 and still no new code: `StockCountHandler`
measures the variance and auto-posts an owner-only ADJUSTMENT. Count ITM-0096
and ITM-0046 first — those two are 440 of the 544 units, and for both the phantom
is most or all of what the screen claims.
