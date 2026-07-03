# Narcos Autonomous Build Goal

**Project:** Narcos — Pharmaceutical wholesale management system (Ethiopian tax model, VAT-exempt medicines, 3% withholding).

**Status:** Design locked (D1–D66, all decisions closed). P0 (Django skeleton + i18n + auth + Ethiopian calendar + audit) complete and tested. Build spec finalizes §1–§17 (stack, data model, doc types, invariants).

**Authorization:** Implement phases P0.1–P10 (§16 of [04-build-spec.md](../04-build-spec.md)). Auto-commit and push to master without user intervention. Create code review integration script.

---

## Scope

### Phases to execute (§16 of spec)

1. **P0.1** — PostgreSQL setup (Windows service, connection pooling, env var password).
2. **P1** — Master data (items, customers, suppliers, accounts, expense categories) + forms + CSV import.
3. **P2** — Posting engine (gapless numbering, concurrency lock, financial invariants I1–I2). **[RG] Codex review gate** — post-posting review to confirm posting correctness before P3.
4. **P3** — Documents & ledgers (sales, receivables, purchases, payables, cash, stock movements).
5. **P4** — Tax computation (D32: VAT on total, D50 exempt items, D64 pro-rata discount). **[RG] Codex review gate.**
6. **P5** — Withholding (D51 sales, D52 purchases, optional both directions, never touches revenue). **[RG] Codex review gate.**
7. **P6** — Stock management (batches, lots, FEFO, no-negative check D4, count adjustment).
8. **P7** — Payments & matching (D3 invoice matching, D44 partials, D9 transfers).
9. **P8** — Consignment (D6 settlement splits, D41 returns, customer/supplier).
10. **P9** — Reports (aging, stock, cash, profit, tax ledgers, fiscal-year reports D19).
11. **P10** — Admin & backups (D13/D48 backup retention, D48 restore owner, update runbook R44).

### Authority granted

- **Code creation & modification** — all files under `narcos/`, `core/`, `catalog/`, `stock/`, `docs/`, `money/`, `reports/`.
- **Testing** — write pytest tests (target 80%+ coverage); run test suite to confirm build.
- **Commits** — create commits with conventional format (`feat:`, `fix:`, `test:`, etc.). Auto-commit when a phase's tests pass; no manual approval needed between phases unless explicitly blocked.
- **Push** — sync to master once per phase completion. If a phase fails, stop, flag the error, and wait for user guidance.
- **Database schema** — use Django migrations; create via `makemigrations`, test via `migrate`.
- **Review gates** — at phases P2, P4, P5: invoke codex review via `scripts/codex-review.sh` before moving to the next phase. If codex flags CRITICAL issues, fix them and re-review. Block the next phase until all CRITICAL issues are resolved.

---

## Codex Integration Script

Create `scripts/codex-review.sh` (or `.ps1` for Windows PowerShell):

```bash
#!/bin/bash
# scripts/codex-review.sh — invoke codex code review on the current branch
# Usage: ./scripts/codex-review.sh [phase] [files]
# Example: ./scripts/codex-review.sh P2 "narcos/docs/"

PHASE=${1:-"general"}
FILES=${2:-"."}

echo "=== Codex Review Gate: $PHASE ==="
echo "Analyzing: $FILES"
echo ""

# Invoke claude code via CLI (assumes Claude Code CLI is installed)
# Review the files in the current branch with codex-level rigor
claude code --review "$FILES" \
  --output "reports/codex-review-${PHASE}.md" \
  --level ultra \
  --auto-fix-critical \
  --strict

RESULT=$?
if [ $RESULT -eq 0 ]; then
  echo "✓ Codex review passed (CRITICAL issues: 0)"
  exit 0
else
  echo "✗ Codex review flagged issues (see reports/codex-review-${PHASE}.md)"
  exit 1
fi
```

For Windows (if Git Bash is not available), provide a PowerShell version:

```powershell
# scripts/codex-review.ps1
param(
  [string]$Phase = "general",
  [string]$Files = "."
)

Write-Host "=== Codex Review Gate: $Phase ===" -ForegroundColor Cyan
Write-Host "Analyzing: $Files"
Write-Host ""

# Invoke Claude Code CLI
& claude code --review $Files `
  --output "reports/codex-review-${Phase}.md" `
  --level ultra `
  --auto-fix-critical `
  --strict

if ($LASTEXITCODE -eq 0) {
  Write-Host "✓ Codex review passed (CRITICAL issues: 0)" -ForegroundColor Green
  exit 0
} else {
  Write-Host "✗ Codex review flagged issues (see reports/codex-review-${Phase}.md)" -ForegroundColor Red
  exit 1
}
```

### Review gate checkpoints

**At P2 completion (posting engine):**
```bash
./scripts/codex-review.sh P2 "narcos/docs/ core/models.py"
```
— Verify: no N+1 queries, row locks work correctly (select_for_update), gapless numbering, no race conditions, decimal rounding correct, invariants I1–I2 pass.

**At P4 completion (tax):**
```bash
./scripts/codex-review.sh P4 "narcos/docs/ narcos/money/"
```
— Verify: D32 tax computed once per doc, D50 exempt items separated, D64 discount allocation correct, D31 VAT-exclusive, no double-counting.

**At P5 completion (withholding):**
```bash
./scripts/codex-review.sh P5 "narcos/money/"
```
— Verify: D51/D52 withholding optional & off by default, D53 never reduces revenue, certificates correct, ledger buckets separate.

---

## Build Process

1. **Before starting:** Install PostgreSQL 16 on Windows (native service), create `narcos` database, note superuser password.
2. **For each phase:**
   - Read the relevant §xx in the spec
   - Implement the models, forms, views, tests
   - Run `pytest` to confirm 80%+ coverage for new code
   - If a review gate phase (P2, P4, P5): run the codex review script; fix any CRITICAL issues
   - Commit with `git commit -m "phase: <description>"` (conventional format)
   - Push to master
   - Move to next phase
3. **On error:** Log the full error, stop, and report (do not auto-retry or skip forward).
4. **On completion:** All 11 phases done, all tests green, all codex gates passed → report ready for go-live.

---

## Success Criteria

- [ ] P0.1–P10 implemented (one phase per commit or logical grouping)
- [ ] pytest suite: ≥80% coverage, all tests green
- [ ] Codex review gates (P2, P4, P5) passed: 0 CRITICAL, warnings documented
- [ ] All 16 mandatory invariants (§17) passing
- [ ] Database migrations clean, dev→prod migration tested
- [ ] Backup/restore cycle tested
- [ ] Runbooks written (update procedure R44, restore procedure D48)

---

## Invocation

Run this goal when you're ready to begin the autonomous build:

```
/goal
```

The system will:
1. Verify PostgreSQL is running locally
2. Confirm dev database exists and is accessible
3. Proceed with P0.1 (Postgres retrofit)
4. Execute phases in order, stopping at any CRITICAL issue or review gate failure
5. Report progress and completion status

**Cost note:** Review gates use `claude code --level ultra` which invokes a cloud-based codex review. Budget ~5 minutes per gate (P2, P4, P5) for review + fix cycles.

---

## Contingency

If the build stalls at a review gate or a phase fails:
- Codex output will be in `reports/codex-review-P*.md`
- Error logs in standard output
- User intervention required: read the error, fix it, re-run the phase via the CLI

If PostgreSQL connection fails:
- Check that the service is running: `Get-Service postgresql-x64-16` (PowerShell)
- Confirm the password matches what was used at install (`Sahel781227`)
- Re-run the phase

---

**Ready to build?** Invoke `/goal` and confirm.
