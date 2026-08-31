# Handover — 2026-08-31

Written because the session was cleared mid-compaction. Everything below is
verified against the working tree, not recalled.

**State:** `build` is clean and level with `origin/build` at **`5ce5b42`**.
Full suite **483 passed, 0 failed**. Nothing is uncommitted.

---

## 1. Release A — settled: the columns are KEPT

**Decided 2026-08-31.** D122 ships as release A — the pack-conversion objects
leave Django's model state but stay in the database, so rollback is a `.env`
edit and `docker compose up -d`. Removal is deferred and tracked as **R94**.

| object | state |
|---|---|
| `docs_documentline.factor` | kept, DB default `1` |
| `core_companysettings.unit_conversion_enabled` | kept, DB default `false` |
| `catalog_itemunit` | table + rows kept, **FK to `catalog_item` dropped** |

Two traps, both found by test rather than reasoning: the first two columns are
`NOT NULL` with Django-level defaults only, so they needed database defaults
the moment Django stopped writing them; and leaving `catalog_itemunit`'s FK in
place blocked `TRUNCATE` on `catalog_item`, breaking the suite.

<details><summary>Superseded — the original A+B note</summary>

The migrations as first committed **dropped the columns**:

| migration | operations |
|---|---|
| `docs/0010_remove_documentline_factor` | `RunPython(quarantine_pack_scaled_drafts)` then **`RemoveField(factor)`** |
| `catalog/0003_remove_itemunit_…` | 2 × `RemoveConstraint`, **`DeleteModel(ItemUnit)`** |
| `core/0009_remove_companysettings_unit_conversion_enabled` | **`RemoveField`** |

Earlier in the session I recommended an **expand/contract** rollout — Release A
removes the UI and the math but *keeps* the columns (fully reversible), Release
B drops them a cycle later — because on this client's box a dropped column is
**not recoverable**:

- `NARCOS_IMAGE` defaults to `:latest` ([compose.yml:27](compose.yml#L27)), so
  rolling back is not a pinned operation.
- `ops/docker-restore.ps1:32` **refuses a database that already has tables**, so
  restore-in-place is blocked by design.

Temesgen was asked "Release A only, or A+B?" and **never answered**. I then
implemented A+B without flagging the contradiction. That is the one thing to
settle before any deployment.

This was resolved in favour of release A, above.

</details>

---

## 2. How this session got here

It began with **two client bug reports**, not with a refactor:

1. "Entered a quantity of 180, it registered 189."
2. "After a sale, more stock left in inventory than expected."

Investigation (probe tests, all run) established:

- Plain receiving is exact — 180 typed registers 180.
- `factor` was a whole number; **no integer turns 180 into 189**.
- `free_qty` is the only arithmetic that could (180 + 9), and the receiving
  form rejects it even in a hand-crafted POST.
- The inventory list's **`Total` column is `warehouse + consigned +
  expired/unfit`** — 180 on the shelf plus 9 elsewhere reads 189. Confirmed by
  test. Cheapest explanation, and it fits exactly.
- Quantity inputs are bare `<input type="number">` with **no wheel/arrow
  guard** anywhere in `app.js`. The stock-count screen is the dangerous one: it
  pre-fills every line with the system's own figure and is long enough to
  force scrolling.

**Neither report is diagnosed.** They are still open. See §4.

Then the investigation turned up **R93**, which changed the priority.

---

## 3. R93 — why unit conversion was removed (D122)

`factor` and **D80 master pricing are mutually incompatible**, and the
collision is a *money* bug, not a quantity bug.

D80 forces every sale price from the item's `maintained_price`, which is per
**base** unit. `factor` makes `qty_entered` a **pack** count. Revenue is
`qty_entered × unit_price`; stock and COGS are `qty_entered × factor`.

Verified by executing it — receive 10 cartons ×12 at 120.00/carton, sell 5
cartons at 15.00/pack:

```
stock leaving warehouse : 60 packs
cogs_total              : 600.00
line_net (invoiced)     :  75.00   <-- 525.00 loss, silently, per line
```

Staff cannot compensate: typing the carton price 180.00 comes back 15.00,
because D80 overwrites it. **A correct factor makes the invoice wrong**, so
"keep it and validate it properly" was never available without reopening D80.

D62 had reversed D58 purely on retrofit fear, never on a business need; R65
confirmed against the live database that the feature has never been used.
D62's other purchase — the base-unit skeleton — is kept, which is what makes a
future retrofit cheap (`ADD COLUMN factor DEFAULT 1`, no back-fill).

Logged as **R93** in `03-open-risks.md`. Decision **D122** in `02-decisions.md`.

---

## 4. What is NOT done

1. **The two original client reports are still undiagnosed.** The tool to
   answer them exists and has never been run on their machine. Do not let
   D122 feel like these were resolved.
2. **Regularization is not built** — nothing repairs data already posted on a
   pack scale. Design (with Codex's corrections) is in `05-status.md`.
3. **Confirm-before-post is not built.** Agreed as the right answer to
   data-entry error, since validation cannot tell a typo from an intention.
   Design in `05-status.md`; the mechanism already exists (D93's shared dialog
   in `base.html` + `data-confirm-*` + `app.js`) and is already used by the
   *correction* Post button — the ordinary Post button on
   `templates/docs/detail.html` is a plain form.
4. **No wheel/arrow guard on number inputs.** Cheap, unrelated to D122, and
   the most plausible silent-corruption path left.
5. **Codex round 3 never ran.** Rounds 1 and 2 both returned DO NOT SHIP; all
   eight findings are fixed, but the round-2 fixes are themselves unreviewed.

---

## 5. Deploying D122 — the pre-flight is not optional

```powershell
# service is `app`, NOT `web`
docker compose exec app python manage.py diagnose_quantities
```

Start the container with **`NARCOS_AUTO_MIGRATE=0`** or the entrypoint migrates
before you can look.

- **CHECK 0b must find no draft carrying a pack multiplier.** Any it finds will
  have its quantities **cleared to zero** by the migration and must be re-typed.
  That is deliberate — such a draft cannot then post the wrong number — but it
  *is* loss of typed work on unposted drafts.
- **CHECK 1** must show no line whose registered quantity differs from the
  typed one. Anything it lists is regularization work.
- **CHECK 3** compares the balance cache against the append-only ledger. A
  mismatch is the signature of a hand-edited database.

If CHECK 0b is clean, `docs/0010`'s `RunPython` provably does nothing — the
riskiest part of the change becomes a no-op against their real data.

**Client data export** (for offline analysis) is written up at the end of
`05-status.md`. Short version: `--export /backups/findings.json` lands on the
Windows host directly via the volume at [compose.yml:46](compose.yml#L46) — no
`docker cp` needed. It carries item codes, document numbers and quantities;
**no customer names, no balances, no secrets**. A full DB dump is
`ops/docker-backup.ps1` — send only `narcos.dump`, **never `.env`**.

---

## 6. Gotchas that cost time this session

- **`qty_base` is NOT a copy of `qty_entered`.** It is "base units this line
  actually moved". It legitimately differs in four places, none involving a
  factor: receiving (`+ free_qty`, D21), stock count (frozen pre-count
  snapshot), settlement (`sold+returned+expired`), adjustment (`|qty_delta|`).
  Assuming otherwise is the main way this area goes wrong.
- **`unit_label` is inert** — free text, never multiplies, never checked
  against `Item.base_unit`. A line can say "carton" while the number means
  tablets.
- **`free_qty` is still engine-live** but off every form since D84.
- **A raising migration crash-loops the container** — `docker-entrypoint.sh` is
  `set -e` and runs `migrate` before `exec`. Never put a guard that raises
  inside a migration. That is why `docs/0010` quarantines instead of refusing.
- **`CompanySettings.load()` uses `get_or_create`** — it can INSERT. Do not
  call it from anything advertised as read-only.
- **Do not sed the test suite.** A regex over `factor=` mangled
  `factor=spec.get("factor", 1)` into a glued line. Codex's round-1 advice was
  explicitly "read that diff by hand".
- **Rewinding migrations in a test must migrate *every* app forward again.**
  `test_d122_migration.py` rewound `core` to 0008 (re-adding
  `unit_conversion_enabled` NOT NULL) but only migrated `docs` forward, which
  broke two concurrency tests suite-wide.
- **`pytest.ini` now collects `tests.py` as well as `test_*.py`.**
  `stock/tests.py` held **21 real tests, including all of D121**, that the
  suite had never run. All pass. Check collection counts, not just green.
- **The full suite takes ~6–8 minutes.** Piping it through `tail` swallows the
  summary line — redirect to a file instead.

---

## 7. Codex review — what it caught that I missed

Two rounds, both **DO NOT SHIP**, eight findings, all fixed. The ones that
mattered:

- **`_duplicate_as_draft` copied only `DOC_CONFIG["lines"]`**, and D84 took
  `free_qty` off that list — so correcting "100 + 10 free" voided 110 units and
  re-posted 100, moving the lot cost with it. **Bug predates D122.**
- **My first migration would have frozen a cost lot at 12×.** It scaled
  `qty_entered` but left `unit_cost_entered` per pack, on my argument that a
  wrong total gets noticed. Codex disproved the premise: opening-stock drafts
  get no total preview, the detail page has a direct Post button, and
  **`doc.notes` is never rendered there** — my "impossible to miss" warning was
  invisible. I had asserted a UI behaviour without opening the template.
- **CHECK 0b could never have worked** — it asked `DocumentLine._meta` for a
  `factor` field the new code never has, so it would pass silently against an
  unmigrated database.

Review transcripts lived in the session scratchpad and are **not** in the repo.

---

## 8. Orphaned background tasks

Notifications reported stopped tasks from the previous session
(`banh37co9`, `bmsy9a8ma`, `byo79yap2`, workflow `wf_60b82344-732`). **No
action needed** — the workflow's decision was made and implemented, and its
five investigations are cached if anyone wants them
(`Workflow({scriptPath, resumeFromRunId: "wf_60b82344-732"})`).

---

## 9. Open questions only Temesgen can answer

1. ~~Release A only, or A+B?~~ **Answered: A. See §1 and R94.**
2. **Is `GRN-000001` real client data or dev junk?**
3. Which item and which GRN do the two field reports refer to? CHECK 1 answers
   report #1 outright; `--item <CODE>` gives report #2's movement history with
   a running balance.
4. Was the 189 read off the inventory **`Total`** column? If so, report #1
   closes with no code change.

---

## Files worth opening first

| file | why |
|---|---|
| `05-status.md` | full narrative, both designs, the export walkthrough |
| `03-open-risks.md` | R93 (new), R85, R87 (closed by D122) |
| `02-decisions.md` | D122, and D58/D62 for why this was reversed twice |
| `docs/posting.py` | `lines_posted_on_a_pack_scale`, `PACK_SCALE_CHECKED_TYPES` |
| `docs/migrations/0010_remove_documentline_factor.py` | the draft quarantine + rationale |
| `stock/management/commands/diagnose_quantities.py` | the support tool |
| `ops/RELEASE-CHECKLIST.md` | the pre-flight step |
