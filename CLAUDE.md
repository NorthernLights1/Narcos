# Narcos — agent orientation

This is the single orientation file for every coding agent working on this
repository. `AGENTS.md` points here rather than repeating any of it, so there is
one copy to keep current. Keep this file to what is *structural* — the map, the
commands, the rules that hold across releases. Anything that changes per round
lives in the numbered docs below; cite them instead of copying them here.

On-prem wholesale system for a small Ethiopian pharmacy / medical / lab-supplies
distributor. Django + PostgreSQL, server-rendered with htmx and Alpine, Tailwind
for CSS. Single company, single warehouse, Ethiopian Birr only. It ships as a
Docker stack onto **one offline Windows PC** at the client's site, so there is no
CDN, no external API, and no network dependency at runtime.

Working branch is `build`. Latest tag is `v1.1.0`.

## Read this before proposing anything

Design truth lives in the numbered files at the repo root. They are the asset;
the code is downstream of them. The first five are design, the sixth is evidence
about production, and the seventh is the handoff from the last session.

| File | Holds |
|---|---|
| `01-business-logic.md` | The business in plain words. The shared mental model. |
| `02-decisions.md` | Numbered decision log (`D1`…). Every locked decision, with its reason. |
| `03-open-risks.md` | Numbered risks (`R1`…), each marked OPEN, WATCH, or DECIDED. |
| `04-build-spec.md` | Buildable spec derived from the decisions: schema, posting engine, tax rules, invariant tests. |
| `05-status.md` | Where the work stands right now. Written to the owner. |
| `06-client-data.md` | What the client's **real** database actually contains, from a restored backup. Read it before sizing anything — round 22 shipped a feature that passes its tests and is inert in production. |
| `07-session-handoff.md` | The newest session written down: what changed, what is open, what the owner still has to decide. Replaced each round, not appended. |

Precedence: **`02-decisions.md` wins over `04-build-spec.md`.** If they conflict,
say so rather than picking one. Decisions are appended, never rewritten; when one
changes, the old entry is marked superseded and a dated new entry is added.

`ops/` holds the deployment runbook, manual-testing log, release checklist, and
`INCIDENT-2026-09-08.md` - the post-mortem of the day the client's machine went
down after a month with no backup. Read its troubleshooting table before
diagnosing anything on that PC.

## Repo map

Django apps live at the root, not under a `src/` or project package.

- `core` — users, `CompanySettings`, `AuditLog`, `NumberSequence`, Ethiopian
  calendar, dashboard. Mounted at `/`.
- `catalog` — master data: `Item`, `ItemUnit`, `Customer`, `Supplier`,
  `Account`, `ExpenseCategory`, `FixedAsset`. Mounted at `/master/`.
- `stock` — `Batch`, `CostLot`, `StockLedger`, `StockBalance`, zones. Mounted at
  `/inventory/`.
- `docs` — **transactions, not documentation.** `Document`, `DocumentLine`,
  `DocumentCharge`, `LotConsumption`, `Attachment`, plus the posting engine,
  settlement, and tax. Mounted at `/documents/`.
- `money` — append-only ledgers: `MoneyLedger`, `PartyLedger`,
  `WithholdingLedger`, and payment allocation. No URLs of its own.
- `reports` — read-only reporting views. Mounted at `/reports/`.
- `narcos` — settings, root URLconf, wsgi.

**Trap:** the directory `docs/` is the transactions app. Documentation is the
numbered files at the root and `ops/`. Do not confuse them, and do not put prose
in `docs/`.

Exclude `.venv/`, `staticfiles/`, `__pycache__/`, and `.agents/` from searches.
`.agents/skills/` is vendored tooling, not project code.

## Commands

```bash
.venv/bin/python -m pytest              # whole suite
.venv/bin/python -m pytest docs/tests   # one app
.venv/bin/python manage.py runserver 8000 --noreload
./scripts/build_css.sh                  # after editing static/src/input.css
```

Tests need PostgreSQL; connection comes from `NARCOS_DB_*` environment variables
and defaults to a local `narcos` database. See `.env.example`.

**The local `narcos` database is a restored copy of the client's real data**
(snapshot 2026-09-08), because designing against fixtures shipped an inert
feature — see `06-client-data.md`. Log in locally as `Admin` /
`narcos-dev-2026`; that password was set on the local copy only. The original
seven-item fixtures are still available:

```bash
NARCOS_DB_NAME=narcos_testdata .venv/bin/python manage.py runserver 8000 --noreload
```

Two things follow. **Never change the `NARCOS_DB_NAME` fallback in
`narcos/settings.py`** — that file ships in the image, and pointing it at
anything but `narcos` makes the client's container fail on boot. And the
default database now holds 70 real businesses with names and balances, so it is
what appears in every screenshot unless you switch.

After changing `static/css/app.css` or `static/js/app.js`, rebuild the CSS and
bump the `?v=YYYYMMDD<letter>` stamp on both tags in `templates/base.html`.

## Hard rules

- **Never modify the client's live data**, and never hand-edit rows to fix a
  problem. Data fixes ship as management commands the owner runs. Read-only
  shell queries are fine.
- **Ledgers are append-only.** `money.AppendOnlyModel` enforces it. Correct a
  posted document by writing a reversing entry, never by editing history.
  Posted documents raise `ImmutableDocumentError` on mutation.
- **The UI never computes money or stock.** Totals, balances, tax, withholding,
  and stock levels are produced server-side. A template that does arithmetic is
  a defect.
- **Every failure needs a photographable surface**: a message on screen, a line
  in the log, and a version stamp. Support happens over a phone photo of the
  screen, with no remote access to the machine.
- **No new runtime dependency on the network.** Vendored assets only.
- Work stays inside this repository. Do not write to paths outside it.

## Tax, because it is easy to get wrong

As of 2026-09-06 the owner runs **no sales tax at all** — no VAT, no TOT. The
only tax in play is the **3% a PLC withholds** when it pays them. The code still
ships with `tax_regime` defaulting to VAT, so setting the regime to *None* is a
mandatory step in `ops/RELEASE-CHECKLIST.md`. Treat the VAT and TOT paths as
dormant but live: they must keep working for a future registration, and they
must not fire today.

**Confirm the current regime in `02-decisions.md` before relying on this
paragraph** — it is the one fact here that a business decision can change.

## What useful review output looks like here

Produce **evidence, not opinion**. A finding is worth reading when it names the
file and line, gives a concrete sequence of inputs that reaches the wrong state,
and shows the resulting rows or values. "Consider refactoring X" is noise.
"Post a credit sale, then a supplier return against it, and the party balance is
off by the return amount, here are the two ledger rows" is a finding.

Money bugs in this codebase are invariant violations. The invariants worth
testing against are listed in `04-build-spec.md`.

If a risk already appears in `03-open-risks.md`, reference its `R##` rather than
re-reporting it as new.
