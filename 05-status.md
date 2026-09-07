# Status

Dear Temesgen,

**Round 22 is built.** Five client comments turned into eight decisions
(D123–D130), and **not one of them needs a database migration** — this whole
round deploys as an image swap, with `migrate` running as a no-op. The three
changes that *would* need schema work are deliberately unbuilt and written up
as R95, waiting on a copy of the client's database.

Nothing is committed yet. Say the word.

## What the five requests turned out to be

| They asked for | It became |
|---|---|
| A log and totals per brand / per generic | Two reports, with the **price actually achieved** — average, lowest, highest |
| Who owes who, per customer | One report across all parties, plus five repairs to the tax-number matching |
| Empty batches off the sale picker | Exactly that, scoped to the two document types that sell from the shelf |
| A short-cut for repeat receiving | **Refused, and replaced** — see below |
| Enter the generic once | Deferred to R95; the report already folds case so you can see the cost |

## The two things worth your attention

**1. One settings read decides how big the first request was (R96).**
My first reading of this plan said sale prices cannot be typed, so "different
prices to different customers" had to mean per-customer price lists. That was
wrong. **D89's `sale_price_editable` hands pricing back to the counter**, and
it is **on** in the dev database with discounts off. The posted rows prove it:
one item sold at 3.00 and at 1000.00, another at 8.00, 0.40 and 8.01.

The flag ships **off** by default. If the client's machine has it off, this
request becomes R46 instead, which is much larger. **Read the setting before
estimating anything else.**

**2. Your objection to the receiving short-cut was right, and better than my
reasoning for it.** A new delivery rarely repeats the same combination, so a
prefilled copy saves little — and the capability already existed, with a
passing test. Your batch-number alternative targets something sharper:
**a batch number is the one master string here that can never be corrected.**
Four models point at `Batch` with PROTECT, so a typo is permanent, the stock
sits under a label nobody searches for, and a recall on that batch misses it.
Prevention at entry is the only defence there is. It also removes a hard
posting failure (mismatched expiry) and closes a silent duplicate path
(`b001` vs `B001`).

## Verified, not assumed

- **Suite:** 506 tests, up from 479. The jump from 458 is `pytest.ini` finally
  collecting `stock/tests.py` — 21 tests that had never run. **Count collected
  tests, don't trust green.**
- **Red-green checked:** with the fixes reverted, 14 of the new tests fail.
- **Rendered in the running app:** all four new/changed pages return 200, the
  batch index reaches the receiving form, and the empty batch `G001` is absent
  from the sale picker while stocked `B0112` is present.
- **A guard test caught me.** Two multi-line `{# #}` comments I wrote would
  have printed to the page. `core/tests/test_template_comments.py` failed the
  build over it, which is exactly what it is for.

## Corrections to things I told you earlier

- I said merging two items was **impossible** because the stock ledger refuses
  writes. Wrong — `QuerySet.update()` bypasses those guards and moves the rows.
  The real barriers are correctness (base-unit divergence, batch collision,
  FIFO order), not mechanism. Recorded in R95.
- I recommended filtering proformas to in-stock batches. Reversed: a proforma
  has zero ledger effect, so filtering removes legitimate quoting for goods
  that have not landed.

## Next

1. **Read `sale_price_editable` on the client's machine** (R96).
2. Get `narcos.dump` from their nightly backup — the folder also holds `.env`,
   which must **not** leave that machine.
3. Then decide R95's three migrations against real data rather than argument.
4. Still open from before: restore drill on the Windows host, and the two
   undiagnosed reports (180 → 189, leftover stock). D129 and D130 are the
   cheapest candidate explanations for the first and are now in.
