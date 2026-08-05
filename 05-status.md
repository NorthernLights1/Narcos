# Status

Dear Temesgen,

Pre-ship audit of `build` done, two fixes landed on top of it (D115).
**436 / 436 tests green.** The batch is ready to tag.

## What the audit found

29 commits were audited before shipping: full suite, migration graph,
authorization sweep across every view, secrets scan, deployment path.
**Nothing in the batch was broken.** Six findings came out of it — two are
now fixed, four are recorded.

| # | Finding | Outcome |
|---|---------|---------|
| 1 | Pack-factor cost rounding | **Not live** — you buy and sell per pack, so the pack *is* the base unit and nothing is lost. Confirmed in the data: pack conversion already off, 36 of 38 lines at factor 1 (R65) |
| 2 | `notes` editable by staff after posting | **Accepted** — your call; every edit is audited before/after (D115) |
| 3 | Zero-total cash sale cannot post | **Queued** for your consideration (R64) |
| 4 | Missing migration | **Fixed** — `core.0007`, verified no-op (D115) |
| 5 | Receipt number ignored the fiscal-machine switch | **Fixed** — the switch now governs both halves (R63 → D115) |
| 6 | Remittance check runs before the lock | **Open, low** — needs two postings in the same instant on a one-till system (R66) |

## The two fixes

**R63 — the fiscal-machine switch.** Turning off "Fiscal machine present"
hid the machine total but still asked for the receipt number, which is
printed *by* the machine. One change to `fields_hidden_by_settings()`
cascades everywhere: the box disappears from entry forms, the D114 pencil
disappears from posted documents, and the endpoint 404s — no change needed
at any of those call sites. The printout and draft summary row are gated
directly. Three new tests.

**`core.0007` — the migration gap.** Two help texts reworded in D101/D89
never got their migration. `sqlmigrate` prints `(no-op)` for both
operations: no table touched, no data touched. Applied;
`makemigrations --check` is clean.

## Ready to ship

- `build` **already matches `origin/build`** — nothing to push. (The
  previous status file said otherwise; that was stale.)
- `build` is **29 commits ahead of `origin/master`**.
- `v1.0.0` exists. The client image is built by the `v*` tag — so a new
  tag is what actually ships this.

## Still yours

### Before or alongside the tag
- Hard-refresh and walk `ops/MANUAL-TESTING.md`.
- Company phone still blank in Settings.
- Negative-balance policy still "Allowed" — your call.

### Client-side / ops (unchanged)
UPS + backup drive · R43 parallel run · R40 accountant confirms the 3% base
and the 20,000/10,000 thresholds · R39 legal form → withholding switches.

### Watch (deliberately not queued)
R46 per-customer price lists · R8b master-data merge · R9 broader returns ·
R55 recurring · R64 zero-total sale · R65 pack rounding, if you ever buy an
outer unit and sell the inner one · R66 remittance timing.

## Recommended next steps

1. Hard-refresh and test.
2. Cut a `v*` tag when the client should receive this build.
