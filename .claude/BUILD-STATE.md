# Build state — 2026-07-03 (session save point)

All work through P5 initial implementation is committed on branch `build`.
Full suite green (~150 tests) EXCEPT: **P5 review gate returned BLOCK — fixes
below are NOT yet applied.** Resume by fixing these, then continue P6.

## P5 review gate findings (django-reviewer, all empirically reproduced)

**MUST FIX before P6 — in `docs/handlers_payments.py` unless noted:**

1. **CRITICAL — WR double-spend:** `WhtRemittanceHandler.validate()` reads
   `withholding_balance("PAYABLE")` unlocked, before `NumberSequence.take()`.
   Two concurrent WRs both pass → pool goes negative (reproduced: −100.00).
   Fix: re-check the payable balance inside `build_effects()` (runs after the
   sequence-row lock serializes same-type postings).

2. **CRITICAL — D44 TOCTOU:** `_PaymentBase.validate()` checks
   Σ allocations == total unlocked; `build_effects()` never re-sums. Allocation
   inserted between the two → invoice settled with zero cash (reproduced).
   Fix: re-verify `Σ allocations == cash_total + withheld_amount` inside
   `build_effects()` under the target locks (mirror `ExpenseHandler._check_lines`
   pattern).

3. **CRITICAL — void-after-remit:** voiding a PV/RC whose withheld amount was
   already remitted drives the withholding bucket negative (reproduced: −30.00).
   Fix: add `check_voidable()` to both payment handlers — block void when
   `withholding_balance(direction) − this doc's withholding delta < 0`.

4. **HIGH — deadlock ordering:** the target-lock queryset at
   `build_effects()` has NO `.order_by("pk")` — comment claims stable order but
   Postgres doesn't guarantee lock order for unordered `IN` + FOR UPDATE.
   Fix: add `.order_by("pk")`.

5. **HIGH — missing concurrency tests:** add threaded tests for I13
   double-settlement and WR double-remittance, mirroring the I3/I4 pattern in
   `docs/tests/test_invariants_p2.py` (transaction=True, barrier, per-thread
   `connection.close()`).

6. **MEDIUM (P6 landmine):** in `_PaymentBase.build_effects()`, the cash-kind
   rejection only checks `doc_type == SALE`. When P6 lands, generalize to
   `doc_type in (SALE, CONSIGNMENT_SETTLEMENT)` — cash settlements have no AR.

7. **LOW:** consider CheckConstraints for positive PaymentLine/Allocation
   amounts; comment that WithholdingLedger.certificate_no is a frozen snapshot
   while the doc field stays §7.12-editable.

## Remaining phases (spec §16)

- **P6** consignment: issue/settlement frozen values, partial settlements,
  terms + reminders (D60), exposure joins credit check (I14/I15).
  Note: `docs/checks.py::consigned_exposure` currently values at lot cost —
  switch to locked issue prices when P6 stores them.
- **P7** stock ops: zone moves, adjustments, stock count freeze (I16).
- **P8** opening docs (§7.13) wired to CSV importers; opening AR/AP age from
  original dates, excluded from sales/purchase reports.
- **P9** reports + dashboard (§8–10), ALL document-entry screens (only master
  data has UI so far — sales/receiving/payments are engine+tests only),
  print layouts (§13), CSV export.
- **P10** pg_dump backups + runbooks, reset_owner_password, Waitress service,
  R45 checklist, Ethiopic print test.

## Deferred/flagged decisions (report to user at the end)

- Cash-now receiving auto-posts a linked SUPPLIER_PAYMENT (§7.1) — deferred to
  a small follow-up; receivings are credit-only for now (AP+, then PV settles).
- §7.2 says cash sale "auto-posts linked RC" but §7 table says SALE writes
  money directly — implemented per the table (money+ on the sale itself).
- §11 "override negative stock" vs §3.3 hard CHECK(qty>=0): implemented the
  conservative reading — negative stock never possible, override applies to
  credit blocks only (D4 title wins).
- D64 allocation got bounded (no negative nets) after P4 gate — deviation from
  literal "last absorbs remainder" only in pathological near-total discounts.

## Environment

- PostgreSQL 18.4 Windows service `postgresql-x64-18`, superuser pw known to
  user. App role `narcos`/`narcos-dev` (CREATEDB for tests), db `narcos`.
- Dev owner login: owner/devpass123.
- Tests: `.venv\Scripts\python.exe -m pytest -q` (full suite needs >2 min —
  run with 480000ms timeout or in background; threaded tests are slow).
