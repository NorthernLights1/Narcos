# Status

Dear Temesgen,

This is the ledger of the client's feature requests: what is built, what is
not, and why. Evidence for every production number below is in
[06-client-data.md](06-client-data.md), derived from the restored `narcos.dump`
of 2026-09-08.

## The headline

**Round 25 is built: 662 tests green, 26 commits waiting on `build`.**
Round 24 closed six requests (D141-D145). Round 25 closed two more: month-only
expiry (D146) and backup settings (D147). One piece of D147 is not verified —
see below.

Round 23 shipped seven features; you looked at them and withdrew two. What
replaced them is smaller and better, and the reasoning is in D141 to D143.

Nothing is on the client's machine. They are still running v1.1.0 from
8 August, and the backlog past that tag is now **36 commits**, of which 22 have
not even reached `origin`. The deployment script still prints "Update complete"
after `compose up -d` and verifies nothing. That, not the feature work, is what
stands between this and the client.

**The push to `origin` is blocked** and needs you: `git push -u origin build`.

## An outside audit, ready for you to run

You asked for an independent review — an outside auditor looking for hidden
bugs that quietly distort numbers, and for what the security picture would be
if this were ever put on the public internet. The brief is written and sits in
[ops/EXTERNAL-AUDIT-BRIEF.md](ops/EXTERNAL-AUDIT-BRIEF.md).

It is a prompt, not a report. I did not run it: you told me not to, and you are
right that the daily allowance drains faster when I fire it than when you do.
So the brief is yours to paste into Codex.

What it does differently from a normal code review:

- It **separates today from later**. Findings are tagged for the offline PC the
  client actually uses, or for the hypothetical hosted future. Otherwise the
  report fills with "you need HTTPS", which is true and useless while the
  machine has no internet.
- It **demands evidence**. Every finding must name a file and line, give the
  exact sequence that reaches the wrong number, and show the resulting rows.
  Opinions are explicitly refused.
- It **lists the 26 risks already known**, so the run is not spent
  rediscovering R79, R85, R102 and the rest.
- It **hunts for features that are correct, tested, and inert** — the round 22
  failure. A report that silently returns nothing is a lie told to the client,
  and the brief ranks it accordingly.
- It **prioritises into four levels**, from silent wrong money down to things
  worth knowing but not stopping for.

The work is split into nine passes so a stalled run does not lose everything.
If you only want three, run passes 1, 2 and 5 — reversal integrity, money
arithmetic, and inert features. Those three answer the question you actually
asked, which is whether the system is lying.

Budget a third of what comes back to be wrong or to be deliberate design.
Section 13 of the brief tells you how to run it and what the known failure
modes on your machine look like.

## Round 25 — the two things you asked for on 2026-09-12

| # | What you asked | Answer | State |
|---|---|---|---|
| 1 | Primary and secondary backup paths, and the interval, in Settings | Built as **D147**. The app hands them to the Windows script through the folder both containers already mount | done, needs testing at the PC |
| 2 | A tick that hides the day picker and stores the month end | Built as **D146**, per line, entry-only, no migration, existing batches untouched | done |

**You revived a cancelled feature and the new shape holds.** Round 23 dropped
month-only because it made 76 batches on the shelf impossible to re-receive. A
per-line tick has the escape the company-wide setting did not — leave it
unticked — and the case that would hit the refusal never needs the tick, because
D128 already fills the expiry from the batch you picked. The refusal message now
names the stored date and says to untick.

**Backups can be stretched but not shortened, and you chose that.** The Windows
task fires daily at 16:00; the script can skip a run, so weekly works from the
app. Running more often than daily needs the Windows task re-registered at the
client's PC, which is not in this round.

**One piece of round 25 is not verified and you should know exactly which.** The
PowerShell changes — the copies to the two folders, the interval skip, and
per-destination pruning — are covered by tests that read the script as text and
by careful reading. **There is no PowerShell on this machine to run them.**
`ops/MANUAL-TESTING.md` has a six-step check to run at the client's PC, including
pulling the USB stick out mid-schedule. Do not treat the backup change as proven
until that is done.

**The settings page now shows the incident.** Its new card prints the last
recorded backup, and on the restored database that reads **2026-08-08** — the day
before the outage. That fact was previously only in a post-mortem file.

## Round 24 — the four things you asked for on 2026-09-11

| # | What you asked | Answer | State |
|---|---|---|---|
| 1 | Keep the sales report, add a linkable document number, generic and brand, per-item money, and three filters | Built as **D141**. Strength added alongside generic and brand, for D134's reason | done |
| 2 | Delete the sales log | Gone — view, template, URL, tests and hub entry. D138 withdrawn | done |
| 3 | Remove the *detailed* tick completely and restore the *New item* button | Built as **D143**. The dialog is exactly as R49 had it | done |
| 4 | A search box and a **Copy from** button on the add-item page, prefilling everything | Built as **D142**, on the Master item page and in the receiving dialog | done |
| 5 | Group the sales report per generic | Built as **D144**. 156 generics from 377 lines, labels matching `sales-by-generic` one for one | done |
| 6 | More professional wording on the reports | Built as **D145**. Receivable and payable throughout; no number changed | done |

**The per-item complaint was about legibility, not arithmetic.** The report was
already per line and the deployed build does the same — `SI-000005` renders six
rows that sum to its grand total, and that function is byte-identical at
`v1.1.0`. What it did not do was say *which item* a row was: the column held
`ITM-0005` and nothing else. Naming the item is the fix, and no number moved.
Verified again after the change: 377 rows, 4,818,156.00 revenue, exactly
matching the untouched profit report.

**You reversed the brand/strength design mid-build, and you were right.** The
first shape was two buttons on every receiving line, *New brand* and *New
strength*, cloning the selected item server-side. It needed new line fields, a
deferred create inside the save transaction and a duplicate guard across rows.
One picker on the form the operator is already looking at does the same job with
none of that. Nothing of the abandoned shape was committed.

**Two traps in the copy that only a real browser would have caught.** Three of
the client's base units — *Bag*, *pcs*, *pk* — are not on the dropdown, and a
`<select>` told to take a value it has no option for silently keeps the old one,
so those would have copied as *unit*. They now go to **Other** with the text
beside them. And R59's rule sets VAT-exempt from the category until someone
touches the box, which would have undone a copied exemption on the next category
change. Both were verified by driving the button in headless Chrome against the
restored database, not by a test.

## Round 23 — the seven requests of 2026-09-10, and two you added

*Rows 2 and 5 were withdrawn by you on 2026-09-11 — see round 24 above.*

| # | What was asked | Answer | State |
|---|---|---|---|
| 1 | Expiry month + year only | **Cancelled by you**, after Astra showed a month-only input makes 75 batches on the shelf impossible to re-receive | dropped |
| 2 | Sales log: brand, customer, price, date, batch cost, gross profit | Built as **D138** — **withdrawn** in round 24. The same questions are answered by the upgraded sales report | removed |
| 3 | The same, grouped per generic | Went with the sales log. `sales-by-generic` (D126) still answers it | removed |
| 4 | Who owes / who we owe, drilling to transactions | Built as **D135**. Level one is the ledger balance, with a reconciling row so the two levels cannot disagree silently | done |
| 5 | Faster new-brand entry inside receiving | Built as **D139**, then **replaced** by D142's copy-from picker and D143's restored dialog | replaced |
| 6 | Confirm batch search + expiry autofill | **Confirmed built** (D128). Manual-testing entry added | done |
| 7 | Confirm sale hides empty and expired batches | **Was half built.** Empty yes, expired no. Fixed as **D133** | done |
| + | Filter persistence per user | Built as **D137**, on the user row rather than the session, because nobody logs in automatically | done |
| + | Strength mandatory for drugs | Built as **D136**, on create **and** on edit, as you confirmed | done |

## Three things worth your attention

**Strength already printed, and still does.** The client believed it did not.
Rendering the real views against their restored database shows `SI-000003`
printing as `ITM-0003 — Suxamethiom (Suxathon), 100/2ml, injection, ampoule, of
1`, and the commit that did it is inside the deployed tag. The belief was true
before round 4 and outlived the fix, because **strength appeared on no screen
at all** — so filling the field looked pointless and the size went into the
name instead. D134 fixes the screens. Tell the client this: filling the field
is what takes the size out of the name.

**D136 will obstruct before it helps.** 45 of their 162 drug items have no
strength, and the rule applies on edit, so the next person to touch one of
those records must supply a strength before saving. That is the cleanup
arriving through the front door, and you chose it knowingly.

**Two open risks are still untouched and both have money attached.** R102:
withholding is switched off for the one tax that applies to them, and staff
ticked the box three times in their first three days with nothing recorded —
4,625.88 Birr of certificates. R106: voided sales leave 544 units counted as
sellable, two items entirely phantom. Neither is in round 23 and neither needs
new code. R106 needs a stock count; R102 needs a settings change and a
conversation.

## Recommended next steps

1. **Push.** `git push -u origin build`.
2. **Harden `ops/deploy.ps1`** so an update verifies itself and shows one
   photographable result. It is required before D132 regardless, so doing it
   now makes this release the rehearsal.
3. **Release the 36-commit backlog** through that hardened path, rehearsed
   against a restored copy first.
4. **Put R102 and R106 to the client** — ask whether Shalom and Alula paid 100%
   or 97%, and count ITM-0096 and ITM-0046 before trusting any stock figure.
5. Then D132's catalogue cleanup, whose readers D134 has now built.
6. **Run the audit** in [ops/EXTERNAL-AUDIT-BRIEF.md](ops/EXTERNAL-AUDIT-BRIEF.md),
   passes 1, 2 and 5 at minimum. Best done before the backlog ships, so a
   silent money defect is caught on your machine rather than theirs.

---

## Round 22 headline (superseded, kept for the record)

**Every round-22 feature is written, tested and committed. None of it is on the
client's machine.** They are running v1.1.0, installed 8 August. There are 14
commits on `build` past that tag and no release since. The 8 September outage
(R97-R101) took the week that would have shipped it.

## Round 22 — the five requests they made on 2026-09-06

| # | What they asked for | Answer | State |
|---|---|---|---|
| 1 | An empty batch should not be offered on a sale | D124 | Built, unreleased. **156 of 236 batches are empty** — two thirds of the picker was unsellable. Best of the five. |
| 2 | Items go out at different prices to different customers | D126 — `sales-by-brand`, `sales-by-generic`, with achieved price | Built, unreleased. Premise confirmed: **58 of 70** repeat-sold items had more than one price. |
| 3 | Who owes who, where a business is both customer and supplier | D127 — `both-faces` report | Built, unreleased, and **inert on their data** (R103). 13 both-faced businesses, **0** match by tax number, 13 match by name. |
| 4 | Set the generic once instead of per brand; duplicate items | Deferred to R95 pending real data | **Not built.** The data has now answered it — see below. |
| 5 | A shortcut when receiving the same brand and batch again | D128 — batch-number search, fills expiry too | Built, unreleased. The literal request was already possible; the search is worth more. |

Shipped alongside, requested by nobody: D123 (correction copied a receiving
wrong and moved lot cost with it), D125 (retiring an item did nothing),
D129 (scroll wheel silently rewrote quantities), D130 (Post now confirms in
base units).

Earlier rounds are all closed and live: R57-R60 (D109-D112), the AR/AP
as-of-date reports, the settings-aware report audit.

## What is left, and why

**1. A release.** Nothing above is in front of the client. This is the largest
single gap and it is not a technical one.

**2. R103 — make D127 match on name.** Found on 2026-09-09, one day after the
feature was written. Six tests pass against fixtures with invented tax numbers.
No migration needed for the interim fix.

**3. R95 — the three schema changes, now decided by the data.**
Held back deliberately: `docker-entrypoint.sh` runs under `set -e` and migrates
before handing off, with `restart: unless-stopped`, so a failing migration on
their box is a silent restart loop, not a defect. The data settled all three:

- `catalog.Generic` — **cleanup value is zero.** 201 items, 187 generics,
  folding case and space merges nothing. Build it for the picker or not at all.
- `Customer.also_supplier` — **justified, seed from normalised name.** Not tax
  number, which matches none of the thirteen.
- `Item.superseded_by` + guarded merge — **earns its place.** Passes the ORS
  pair, correctly refuses the three Fogatery records.

**4. R102 — withholding, and it has money attached.** `withholding_on_sales` is
FALSE and has never been changed since install. It is the only tax that touches
this business. Staff ticked the box on three invoices, **4,625.88 went
unrecorded**, and two of those three are settled in full rather than at 97%.
Two pieces of work: a settings flip at the client, no release needed, and a code
fix — the payment side refuses out loud, the sale side stores the tick and
ignores it, and it is the only switched-off feature still showing a live
control.

**5. One client bug report is blocked on them. The other is now diagnosed.**
"180 registered as 189" — 189 exists nowhere in the database; SI-000035 carries
180 and 16 for the same item, totalling **196**. Ask if 196 is the number they
saw. Still blocked on them.

"More stock left than expected" — **cause found, 2026-09-09, see
[06-client-data.md](06-client-data.md) §9.** Not an engine fault: balance equals
ledger to the unit, voids reverse to zero, every factor is 1. Two real causes.
**Nothing has ever been written off** — zero adjustments, stock counts, zone
moves or returns exist, so breakage, expiry and shrinkage have no record and the
system can only read high. And **opening stock is doing the work of receiving** —
42 documents over six weeks, 36 items holding 15,370 units and **2,909,790 Birr**
never received against a supplier document. `OP-000042` re-declares 700 units of
batch `F24800`, three weeks after `GRN-000047` brought in 100 of the same batch.
The fix needs no new code: `StockCountHandler` already measures the variance and
auto-posts an owner-only adjustment. The screen has never been used.

**6. R69/R83 — the restore drill on the Windows host has still never run.**

**7. "Items sold at a pack factor above 1" — the premise does not hold.**
Checked 2026-09-09 against the restored client copy. **Zero** document lines
carry `factor > 1`: all 647 lines across every type and status have `factor = 1`,
and `catalog_itemunit` is **empty**, so no alternate unit was ever defined.
`unit_conversion_enabled` is FALSE and the factor box is hidden by D89. There is
nothing to correct on this axis and no repair script is warranted.

What does exist is `Item.pack_description`, free text such as "of 100" or
"dozen". **89 of 201 items** describe a pack holding more than one base unit and
**75 of them have been sold**, on 161 of 376 posted sale lines. That field is
descriptive only — no code multiplies by it — so it cannot have inflated stock
or money. Two follow-up checks found nothing either: no sale line on those items
sits within 2x of its master price, and quantities that are exact pack multiples
(11 lines) are ordinary wholesale volumes. **Needs the client's own words before
any fix is designed.**

**8. "Can we ship every known generic, brand and strength?" — asked
2026-09-09. Answer: not into `Item`, and not "everything" (R104).** `Item` is a
trading object with a price, batches and stock, and it is what every counter
picker searches. Their entire catalogue is 201 items, 162 of them drugs; a
national list would bury it. There is also no free, complete, machine-readable
list of what is actually on Ethiopian shelves — their brands are `zitromax`,
`Gabalin`, `Moxipil`, `Suxathon`, not United States registry entries — and a
partial list that looks complete is worse than none, because staff stop reading
the carton. **Strength must never be filled from a shipped table**; this business
invoices hospitals and `full_description` prints onto the paper.

The real defect is smaller than the question. 201 items produce only **19**
dosage forms, four of which are junk (`Euipment` twice, `suspenssion`, `.`, one
blank), and 16 base units with `pcs`/`piece` and `pk`/`pack` synonyms. Closing
those two lists removes the whole class and needs no drug database. The generic
names do have real misspellings — `Suxamethiom`, `Doxycyclline`, `Amoxacillin`,
`Antiheamoroid` — and case folding merges nothing (R95), so a typeahead seeded
from **their own 187 existing generics** is the only thing that stops the 188th
spelling of amoxicillin. A vendored generic-names-only reference is a third
step, if ever.

**9. Two new client reports, 2026-09-09 — one is a real defect, one is not.**
Full evidence in [06-client-data.md](06-client-data.md) §11.

**"Catheter is not in my database."** He is right, and the reason is which
screen he typed into. **The Inventory search filters code and name only; it
never looks at `generic_name`** (`stock/views.py:54`). The Items list does. So
typing `catheter` returns **3 of 10** catheter items on Inventory and 7 on
Master — the four `Folly` catheters are invisible on the one screen whose job is
to say how many he has. This trade reads by generic name and the code says so
(R48), so this is a straight defect. **One-line fix, no migration.**

Separately, three items spell it **`Cathater`** (ITM-0065/66/67, Fogatery), so
the correct spelling misses them on *both* screens. That is data, so it ships
as a management command, not a hand edit. The document line picker is fine — it
is a searchable select over the generic-first label.

**"Problet injection was sold and the number did not go down."** No engine
fault: all **376** posted sale lines move stock by exactly `−qty_base`, balance
equals ledger across all **255** groups, there are **zero** draft sales, and
`free_qty` is 0 everywhere. **No item is named "Problet"** — the nearest are
Promulet (ITM-0010, the ampoule) and Plasil injection (ITM-0176), and both close
to the unit. Both brands exist two or three times in the catalogue, so the
number he read may belong to a different record than the one sold. **Get the
item code from him.**

But the hunt found a **third cause of stock reading high, which §9 missed**.
§9 checked that voided documents' ledger rows net to zero and called that
correct. It proves the reversal is complete; it says nothing about whether the
goods came back. Staff void an invoice to fix a price or quantity, then re-issue
it smaller — or not at all. **Nine lines, 544 units, are still counted as
sellable after the customer took them.** Worst is **ITM-0096 Epifenac
(Diclofenac IV)**: opening 1170, a 1170 sale voided, a 700 sale voided, a 780
sale posted — **its entire remaining balance of 390 is the gap**, and it is an
injection, which matches his words. **ITM-0046 ETT #6** is the same shape: all
50 units on hand come from a voided sale never re-issued. Two of the nine give
the reason "returned", which confirms voids are standing in for the
CUSTOMER_RETURN documents they have never once used.

Correction path is unchanged and needs no code: `StockCountHandler` measures the
variance and auto-posts an owner-only adjustment. ITM-0096 and ITM-0046 are 440
of the 544 units — count those two first.

## Recommended next steps

1. **Fix the Inventory generic-name search.** One line, no migration, and it
   turns a "the item is not in my system" complaint into a non-event. Ship it
   with R103 in the same release.
2. Fix R103 by name matching, then cut a release. Together with 1 this is the
   only outstanding work that turns dead features into working ones with no
   migration.
3. **Ask the client three questions before designing anything else:** which item
   code is "Problet"; what Alula Primary Hospital actually received against
   SI-000057 (780 billed, 390 still on the books); and whether 196 is the number
   he saw on the 180/189 report.
4. Ship the `Cathater` spelling fix as a management command he runs.
5. Flip `withholding_on_sales` at the client and ask the two hospitals question.
6. Fix the silent sale-side withholding tick.
7. Walk him through one stock count on ITM-0096 and ITM-0046. It is the only
   mechanism that closes the shelf-versus-system gap, and the screen has never
   been used.
8. Then the R95 migrations, in one release, with the restore drill done first.
