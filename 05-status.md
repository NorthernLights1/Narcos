# Status

Dear Temesgen,

**`v1.1.0` is tagged and pushed.** The twelve whole-app findings and the
thirteen Codex objections behind them are committed as `307cd37`; the tag points
at that commit and so does `origin`. `build` is level with the remote, 34
commits past `v1.0.0`. The previous version of this file said "nothing is
committed yet" — that was true when it was written and has not been true for a
while.

Uncommitted right now: two documentation files, both from today, both described
below. No code has changed since the tag.

## Today — round 21, a disposition review

Six findings were put to you. I verified every one against the working tree
before asking, rather than trusting the summary they arrived in. All six are
real. **You chose to write them up rather than fix them**, so no code moved;
they are now R85–R90 in [03-open-risks.md](03-open-risks.md).

| # | What it does | Disposition |
|---|--------------|-------------|
| R85 | Changing an item's base unit reinterprets 120 tablets as 120 cartons; turning batch tracking off strands batched stock as unsellable | `OPEN` (high) |
| R86 | Nothing on the server refuses one item paired with another item's batch — the check is browser-side only | `OPEN` (medium) |
| R87 | The item form commits the price, *then* validates conversions; on failure you are told it did not save, but it did, unaudited | `OPEN` (medium) |
| R88 | Reprinting an old invoice shows today's customer details, not the ones it was printed with | `WATCH` — you accepted it |
| R89 | `vat_exempt` would suppress TOT as well as VAT | `WATCH` — dormant here |
| R90 | Opening consignment freezes no tax rate, so settlement charges none | `WATCH` — dormant here |

R79 (a supplier return not reducing the receiving's open balance) was confirmed
again and stands unchanged from round 20b.

## The thing your answer actually surfaced

I asked which tax regime you run, expecting VAT or TOT. You said **neither** —
no sales tax at all, just the 3% a PLC withholds when it pays you.

That makes R89 and R90 dormant: under the *None* regime the rate resolves to
zero for every line anyway, so R89 suppresses a tax that is already nothing, and
R90's frozen zero is the *correct* answer rather than a wrong one. Both are
recorded so that registering for VAT later does not wake them silently.

But it exposed something with real money attached. The code ships with
`tax_regime` defaulting to **VAT** and `withholding_on_sales` defaulting to
**off**. If Settings on the client machine is not changed, every invoice adds
15% VAT that does not exist and no withholding is ever shown. The withholding
rate already defaults to 3, so that part is fine. I have written the concrete
values into `ops/RELEASE-CHECKLIST.md` §1.

**This is configuration, not a defect — and it is the highest-consequence
setup step you have left.** Worth checking on the machine before the next real
sale, not at leisure.

## What I did not do

- **No code changes.** Your instruction was to write up first.
- **No fix for R88.** You chose "as they are today"; master records stay live
  and reprints follow them. Recorded, not silently dropped.
- **No reconciliation script** for data already on the client machine. Still
  the next piece of work after this, unchanged from the last round.
- **No restore drill.** R69 remains fixed-as-code and unproven — there is no
  Windows host here, and it is still the one finding whose failure mode is
  losing everything.

## Where the numbers stand

- `v1.1.0` → `307cd37`, tagged and pushed. `build` level with `origin/build`.
- 34 commits past `v1.0.0`.
- Uncommitted: `03-open-risks.md` (R85–R90), `ops/RELEASE-CHECKLIST.md` (the
  regime note). Say the word and I will commit them.
- Tests were 456/456 green at the tag. I have not re-run them today — nothing
  executable changed.

## Recommended next steps

1. **Check Settings on the client machine**: regime → *None*, withholding on
   sales → on. Then post one real sale and read the printed total.
2. Run the restore drill on the Windows host.
3. Decide R85 — it is the only one of the six that can corrupt stock silently,
   and the fix does not restrict ordinary editing.
4. Then the data-checking script.

## Still yours, unchanged

Company phone still blank in Settings · negative-balance policy still
"Allowed" · UPS + backup drive · R43 parallel run · R40 accountant confirms the
3% base and the 20,000/10,000 thresholds.

**Watch, deliberately not queued:** R46 per-customer price lists · R8b
master-data merge · R9 broader returns · R55 recurring · R64 zero-total sale ·
R65 pack rounding · R66 remittance timing · R83 restore ordering · R84 granular
draft permissions · R88 document identity snapshot.
