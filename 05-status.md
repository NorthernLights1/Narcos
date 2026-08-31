# Status

Dear Temesgen,

**D122 is implemented: unit conversion and `factor` are gone.** Suite green at
**481 passed**. Codex reviewed it, returned **DO NOT SHIP** with six findings,
**all six were real and all six are fixed** — two of them were bugs I would not
have found. Codex round 2 has now run. It confirmed four of the six round-1 fixes and
returned **DO NOT SHIP again**, on two new HIGH findings — both about the part
I had already flagged as my weakest. Both were right, both are fixed, and the
migration is now a different design. Suite: **483 passed**.

Full rationale and the Codex findings are recorded as **D122** in
[02-decisions.md](02-decisions.md). What follows is the state of play.

## What shipped

| Component | Action |
|---|---|
| `DocumentLine.factor` | **deleted** (`docs/0010`) |
| `DocumentLine.qty_base` | **kept** — five sites write it from something other than the typed quantity |
| `catalog.ItemUnit` + formset + item-form block + CSV `alt_units` | **deleted** (`catalog/0003`) |
| `CompanySettings.unit_conversion_enabled` | **deleted** (`core/0009`) |
| `_check_conversion_factors`, the receiving factor guard | **deleted** |
| `lines_posted_on_a_pack_scale` + refusal on correction / proforma→sale | **new** |
| `manage.py diagnose_quantities` | **new**, read-only, with `--export` |

Also closed for free: **R87** — the item form's save-then-validate hole existed
only because the units formset was validated after `form.save()`.

## Round 2 — the migration design was wrong, and I had rested it on an unchecked premise

**HIGH — converted drafts were silently postable with wrong money.** My
migration scaled `qty_entered` but left `unit_cost_entered` per pack, on the
argument that "a total twelve times too high gets noticed before posting".
Codex reproduced the case and disproved the premise: a draft opening stock of
10 cartons x12 at 120/carton would post an opening lot at **120.00 per base
unit instead of 10.00 — frozen forever, because `CostLot` is immutable**. And
the total is not visible: opening-stock drafts get no total preview, the
detail page has a direct Post button, and — the part I should have checked —
**`doc.notes` is never rendered on that page at all**, so my "impossible to
miss" warning was invisible. I asserted a UI behaviour without opening the
template.

**The migration now quarantines instead of converting.** Affected draft lines
have `qty_entered` and `free_qty` set to 0, which makes them impossible to
post — every handler refuses a non-positive quantity — so the failure lands
loudly when someone tries, instead of silently in a frozen cost lot. The unit
label is reset to the item's base unit so it stops claiming a pack, and the
original figures go to `notes` and an audit row.

**HIGH — the pre-flight could never have worked.** CHECK 0b asked
`DocumentLine._meta` whether a `factor` field existed. In the new code it never
does, so it would report "already gone" against an unmigrated database and
pass silently — while the old image does not carry the command at all. It now
queries `information_schema` and the column directly, and the checklist says
to start with `NARCOS_AUTO_MIGRATE=0`. The checklist also still said `web`;
that was my error too, now `app`.

**MEDIUM — the migration had no behavioural test.** Correct: mine asserted
operation ordering and warning text, which could not have caught either defect
above. There is now a real one
([test_d122_migration.py](docs/tests/test_d122_migration.py)) that rewinds the
database to 0009 via `MigrationExecutor`, builds factor-12, factor-1, factor-0,
bonus, long-note and POSTED rows through the historical models, migrates
forward and checks what actually happened — including that posted history is
untouched. Writing it immediately found a second bug of my own: the fixture
rewound `core` but only migrated `docs` forward, leaving
`unit_conversion_enabled` NOT NULL and breaking two concurrency tests.

## The round-1 findings I would have missed

Codex earned its keep on these:

1. **Correcting a receiving with bonus goods was already broken.** D84 took
   `free_qty` off the receiving form, and `_duplicate_as_draft` copies
   *exactly* the form's field list — so correcting "100 + 10 free" voided 110
   units and re-posted 100, moving the lot cost with it. That bug predates this
   round. `free_qty` is now carried explicitly.
2. **A draft carries `factor` but no `qty_base` yet**, so my guard could not
   see it: a saved "5 × 12" draft would have posted as five base units after
   deployment. The migration now converts draft quantities before dropping the
   column and stamps the document. It does **not** raise — `docker-entrypoint.sh`
   runs `migrate` under `set -e`, so a raising migration crash-loops the
   container with nothing on screen.

I also made a process mistake worth recording: I bulk-edited the test suite
with a regex despite the review explicitly saying "read that diff by hand; do
not sed it". It silently mangled a helper. Reverted and redone by hand.

## "Can we just fix it in SQL?"

Not a rule — here is what actually happens. I posted the reported situation
(189 received, 50 already sold), applied the naive two-table `UPDATE`
(`documentline` qty + `stockbalance` qty), and measured:

| | before | after the SQL "fix" |
|---|---|---|
| line `qty_entered` / `qty_base` | 189 / 189 | **180 / 180** ✓ |
| `StockLedger` sum (the truth) | 139 | **139** — untouched |
| `StockBalance` sum (what the UI shows) | 139 | **130** |
| ledger == balance | yes | **no — drift of 9** |
| `CostLot.qty_received` | 189 | **189** — still claims 189 arrived |
| `line_net` / `grand_total` / AP | 1890.00 | **1890.00** — supplier still owed for 189 |
| `AuditLog` row | — | **none** |

Three consequences, in order of nastiness:

1. **You fix the stock and leave the money.** The payable still says 1890.00
   for 189 packs. The stock now says 180. Nothing reconciles them again.
2. **You lock yourself out of the app's own correction path.**
   `ReceivingHandler.check_voidable` ([handlers.py:185](docs/handlers.py#L185))
   refuses a void unless `warehouse_qty == lot.qty_received`. Edit the balance
   and leave `qty_received`, and those two can never be equal again — the
   receiving becomes **permanently unvoidable and uncorrectable** through the UI.
   The SQL fix forecloses the proper fix.
3. **It is invisible and unattributable.** No `AuditLog` row, and the next
   pre-migrate dump carries the edit forward indistinguishably from real
   history. In six months nobody can tell what happened.

To do it *properly* in SQL you would have to update, in one transaction:
`docs_documentline` (qty_entered, qty_base, line_net), `docs_document`
(subtotal, grand_total), `stock_costlot` (qty_received **and** unit_cost, since
`lot_cost = amount_paid / total_base`), `stock_stockledger` (qty_delta),
`stock_stockbalance` (qty), `money_partyledger` (amount_delta), plus every
`docs_lotconsumption` row and the `cogs_total` of every sale that drew on that
lot. That is the same arithmetic the posting engine already does — except
without the transaction guarantees, without the invariants, and without a
record that it happened.

**What the database still protects.** Only two things are DB-level rather than
Python-level: `stock_never_negative` and the unique constraints
([stock/models.py:106](stock/models.py#L106)). Everything else — the
append-only ledger, frozen cost lots, posted-document immutability — is
enforced in `save()` and is **silently bypassed by raw SQL**.

**Where a direct correction *is* legitimate:** a field nothing derives from.
That is exactly what D121 did for batch expiry — guarded, owner-only, audited,
in-app. Quantity is the opposite case: it is the root of the derivation tree.

The supported answer stays an owner `ADJUSTMENT` posted through the engine,
driven by a management command you run. It reaches the same shelf number,
moves the money correctly, and leaves an audit trail explaining why.

## Regularizing stock already posted on a pack scale

Designed with Codex, and its critique changed the shape substantially. My draft
had one per-item action covering both stock and money; that is wrong in four
ways.

**There is a fourth harm I had missed.** Beyond (A) revenue understated,
(B) stock wrong, (C) nothing — there is **(D) valuation and COGS
classification**. A sale that deducted too little stock also recorded too
little COGS. A later negative adjustment removes the phantom inventory, but the
profit reports keep the original understated COGS; and a positive adjustment
priced at "latest cost" can double-value the stock. `CostLot` is frozen, so
this needs an explicit valuation policy, not just a counted quantity.

**Stock and money need separate paths.**

- **Money must stay report-only for now.** I was going to tell you to raise a
  supplementary sale. Codex caught that **every sale consumes FIFO stock
  again** — so invoicing the shortfall would deduct the goods a second time.
  Recovering it properly needs a new stock-neutral document type
  (`CUSTOMER_DEBIT`) that reaches revenue, tax and AR without touching stock.
  Until that exists: report the gap, settle it outside the system.
- **The shortfall formula I proposed was wrong.** `qty_base x unit_price -
  line_net` overstates it by any line discount. It is
  `round2(qty_base x unit_price - line_discount) - line_net`, and the honest
  version reconstructs the whole document through the canonical tax function
  so document discounts, allocation and rounding come out right.
- **Consigned stock has no repair path at all.** `ADJUSTMENT` accepts only
  warehouse/expired/unfit zones and carries no consignee identity. Consigned
  corrections must be refused until a dedicated document exists — not
  bodged through an adjustment.
- **`ADJUSTMENT` is not the only option for (B).** For a physical count,
  `STOCK_COUNT` is the better evidence document — it freezes lot-level
  quantities and auto-posts the adjustment itself. `ZONE_MOVE` fits when the
  total is right but the zone is wrong. A direct adjustment is for an
  irreversible warehouse variance with no existing lot.
- **Scope is per `item + batch + lot + zone + consignment_customer`**, not per
  item. A per-item adjustment can fix the warehouse total while leaving
  consignee balances wrong and future settlements consuming phantom quantity.
- **Idempotency cannot live in `notes`** — notes are editable after posting and
  have no uniqueness. It needs marker tables (`RegularizationRun` /
  `RegularizationAction`) with unique constraints, each action posted inside a
  transaction that commits the marker and the document together.
- **The selector needs widening for investigation.** `qty_base != qty_entered
  + free_qty` stays as the root marker, but a factor-1 *outflow* is exactly how
  an in/out mismatch arises and will never match it. The report must follow the
  affected cost lots forward through their consumptions, later movements,
  linked returns and settlements.

My rule "writes nothing outside the posting engine" becomes **"no ledger or
balance writes outside the posting engine"** — marker rows are required.

**This may still be a no-op.** If CHECK 1 is clean on their box there is
nothing to regularize. I would not build any of it until the diagnostic says
it is needed — and I would build the stock half first, warehouse-only, with
money strictly report-only.

## Next task — confirm-before-post (agreed, not built)

**Temesgen's call, and the right one:** we cannot validate a typo into a
correct number. R85 and the entry-error class generally are not defensible by
more server rules — the only real protection is showing people exactly what
they are about to commit, and making them say yes.

**The mechanism already exists — this is wiring, not machinery.** D93 built one
shared confirm dialog for the whole app: it lives in `base.html`, buttons carry
`data-confirm-*` attributes, and `app.js` fills it in and only submits once the
user agrees. The **correction** post button already uses it well — title, body,
a list of consequences, and type-the-document-number to proceed. The
**ordinary** Post button on `templates/docs/detail.html` is a plain form with
none of it.

**Shape for next session:**
- Put the shared dialog on the ordinary Post button for every document type.
- Body shows what is about to be committed, per line: item, batch, **quantity
  in the item's own base unit**, and the document total. This is exactly where
  a mistyped 189 becomes visible, and where a `unit_label` that says "carton"
  next to a tablet count stops being invisible.
- Name the irreversibility plainly: posted documents cannot be edited, only
  voided by the owner.
- Consider surfacing `qty_base` here when it differs from `qty_entered` — a
  receiving with bonus goods is the honest case, and it is the same number the
  pack-scale guard reads.

Not started. No code written for it this session.

## What I need from you

1. **Go / no-go on D122 as implemented** — and Release A only (leave the
   columns in the database) or A+B (drop them). Codex's round-2 verdict lands
   before you have to decide.
2. **Run the diagnostic on their box** using the walkthrough below and send me
   the two files. Everything downstream depends on what CHECK 0b, CHECK 1 and
   CHECK 3 say.
3. **Is `GRN-000001` real or dev junk?** It carries the only `factor != 1`
   lines found anywhere, and whether it is real decides whether the
   regularization command is needed at all.
4. **Nothing is committed.** Say the word and I will commit D122 as one change.

## How the client exports data for analysis

**Correction:** earlier in this file I wrote `docker compose exec web`. The
service in [compose.yml:26](compose.yml#L26) is **`app`**, not `web`. The
commands below use the right one.

Two tiers. Start with tier 1 — it is almost always enough, and it carries no
customer names, no prices and no money.

### Tier 1 — the findings file (send this first)

Have them open **PowerShell** in the folder holding `compose.yml` and paste
these three lines:

```powershell
cd $HOME\Narcos     # wherever compose.yml lives
docker compose exec app python manage.py diagnose_quantities > .\backups\diagnostic.txt
docker compose exec app python manage.py diagnose_quantities --export /backups/findings.json
```

No `docker cp` step is needed: [compose.yml:46](compose.yml#L46) already mounts
the host's `backups` folder into the container at `/backups`, so anything
written there appears on the Windows side immediately. Both files land in
**`.\backups\`**:

| file | what is in it |
|---|---|
| `diagnostic.txt` | the whole readable report — every check, in order, meant to be read by a person |
| `findings.json` | the same findings as data: item codes, document numbers, quantities, and the two money columns per affected line |

**What is not in them:** no customer or supplier names, no addresses, no TINs,
no account balances, no passwords. Item codes and document numbers only — safe
to send over WhatsApp or email.

**For one specific medicine** (use this when they name an item — it adds the
full movement history with a running balance):

```powershell
docker compose exec app python manage.py diagnose_quantities --item AMOX-500 > .\backups\item.txt
```

### Tier 2 — a full database copy (only if I ask for it)

Needed only if tier 1 shows something I cannot explain without reproducing it.
This contains **everything** — customers, prices, margins, balances. Treat it
as the business's books, because it is.

They already have the script:

```powershell
.\ops\docker-backup.ps1
```

It writes `narcos.dump`, `media.tar.gz` and a copy of `.env`. **Send only
`narcos.dump`. Never send `.env`** — it holds the database password and the
Django secret key. If it goes out by mistake, both must be rotated.

### The message to send them

> Open PowerShell in the Narcos folder and paste these two lines. It only
> reads — it changes nothing, and it is safe to run while people are working.
> Then send me the two files it leaves in the `backups` folder.

### What I can answer from it, without another round trip

Whether any line registered a different quantity than was typed (CHECK 1);
whether the balance cache still equals the append-only ledger (CHECK 3 — a
mismatch is the signature of a hand-edited database); which items are
affected; and the money gap per line. **If CHECK 1 and CHECK 3 are both clean,
the reported discrepancies are not in the data**, and the next place to look
is the entry screens — which is where the unguarded number inputs live.
