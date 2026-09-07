# Handover — 2026-09-06

Session ended by choice, not by running out of road. Everything below is
verified against the working tree and the running system, not recalled.

**Bottom line:** a large piece of work was built, reviewed twice, shipped, and
then **deliberately reverted**. The code is back where it started. What
survives is a set of findings — two of which describe bugs live on `build`
right now.

---

## 1. Current state

| | |
|---|---|
| branch | `build`, clean, level with `origin/build` |
| HEAD | `7a4f9f0` — the revert commit |
| tree | **byte-identical to `f3ad111`** (verified: `git diff f3ad111` is empty) |
| suite | **458 passed, 0 failed** |
| deployed anywhere | **no** — nothing ever reached the client |

```
7a4f9f0  Revert "D122: remove unit conversion" — diagnose the client first
06c7b72  fix: D122 ships as release A — keep the columns (reverted)
5ce5b42  feat: remove unit conversion (reverted)
f3ad111  feat: correct a mistyped batch expiry (D121/R62)  <- effective state
```

**Local environment, changed this session:**

- Dev database had one pending migration applied:
  `core.0008_companysettings_books_closed_through`. Local only; the client's
  box was never touched.
- `testowner` password reset to **`narcos-dev-2026`** (role OWNER). Local dev
  database only. Change with
  `.venv/bin/python manage.py reset_owner_password testowner --password '...'`
  — that command **force-sets `role = OWNER`** on whichever account it
  targets, so never aim it at `Finance`.
- **Dev server is still running** on http://127.0.0.1:8000. Stop it with
  `pkill -f "manage.py runserver"` (exits 144 — benign, it matches its own
  shell). Routes: `/documents/`, **`/inventory/`** (not `/stock/`),
  `/master/items/`, `/reports/`.

---

## 2. What happened, in order

**It began with two client bug reports**, and those are still the open item:

1. "Entered a quantity of 180, it registered 189."
2. "After a sale, more stock left in inventory than expected."

**Investigation (probe tests, all executed) established:**

- Plain receiving is exact — 180 typed registers 180.
- `factor` is a whole number; **no integer turns 180 into 189**.
- `free_qty` is the only arithmetic that could (180 + 9), and the receiving
  form rejects it even in a hand-crafted POST.
- The inventory list's **`Total` column is `warehouse + consigned +
  expired/unfit`**. 180 on the shelf plus 9 sitting consigned or expired reads
  **189**. Confirmed by test. Cheapest explanation and it fits exactly.
- Quantity inputs are bare `<input type="number">` with **no wheel or arrow
  guard** anywhere in `app.js`. The stock-count screen is the dangerous one —
  it pre-fills every line with the system's own figure and is long enough to
  force scrolling.

**Then the investigation turned up R93**, which redirected the session into
removing unit conversion (D122). That work was built, reviewed by Codex twice
— both rounds returned DO NOT SHIP, eight findings, all fixed — shipped, and
then reverted.

**Why reverted (Temesgen's call, and it was right):** D122 removed a feature
because of a *latent* bug, while the two reports that prompted the
investigation were never diagnosed and nobody had looked at the client's
machine. Changing the domain model before knowing what actually went wrong is
backwards.

---

## 3. Findings that survive the revert

These are the session's real output. **The first two are live on `build`
today.**

### 3a. LIVE BUG — corrections silently drop bonus units

`_duplicate_as_draft` ([docs/views.py](docs/views.py)) copies line fields from
`DOC_CONFIG["lines"]`, and **D84 removed `free_qty` from that list**. So
correcting a receiving of "100 + 10 free" **voids 110 units and re-posts 100**,
moving the lot cost with it.

Nothing to do with unit conversion. Found by Codex. **Not fixed** — the fix
was inside the reverted commit. Reproducing it needs only a receiving with
`free_qty > 0` and the Correct button.

### 3b. LIVE EXPOSURE — R93, factor and D80 are mutually incompatible

D80 forces every sale price from the item's `maintained_price`, which is per
**base** unit. `factor` makes `qty_entered` a **pack** count. Revenue is
`qty_entered × unit_price`; stock and COGS are `qty_entered × factor`.

Verified by executing it — receive 10 cartons ×12 at 120.00/carton, sell 5
cartons at 15.00/pack:

```
stock leaving warehouse : 60 packs
cogs_total              : 600.00
line_net (invoiced)     :  75.00     <-- 525.00 loss, silently, per line
```

Staff **cannot** compensate: typing the carton price 180.00 comes back 15.00,
because D80 overwrites it. A *correct* factor makes the invoice wrong, so
"keep it and validate it properly" is not available without reopening D80.

Latent only while `unit_conversion_enabled` stays **off** — which R65 confirmed
against the working database on 2026-08-05, with 36 of 38 lines at `factor = 1`.
**The switch is back after the revert, so the exposure is back.** If anyone
turns it on and types a factor, this arms.

**This finding is no longer written down anywhere in the repo** — the R93 entry
went with the revert. It survives only in commit `5ce5b42`'s message and here.

### 3c. No wheel or arrow guard on quantity inputs

Focus a quantity box, scroll the page, and the number changes with no trace.
Worst on the stock-count screen. Cheap: one listener in `app.js` plus a `?v=`
cache-buster bump.

### 3d. Silent test-coverage gap

`pytest.ini` sets `python_files = test_*.py`, so **`stock/tests.py` — 21 real
tests including the whole of D121 — has never run**. All 21 pass when
collected. One-line fix (`python_files = test_*.py tests.py`), reverted with
the rest. Check collected counts, not just green.

---

## 4. Recovering the reverted work

Both commits remain reachable. Nothing is lost.

```
git show 5ce5b42                 # the D122 removal + the diagnostic tool
git show 06c7b72                 # release A: keep columns, model-state only
git cherry-pick 5ce5b42          # brings back everything (will conflict)
```

**The piece most likely wanted back is `manage.py diagnose_quantities`** — a
read-only support tool (309 lines) built to answer the two client reports. It
reports: lines whose registered quantity differs from the typed one, bonus
units, balance-cache vs append-only-ledger drift, adjustments and counts, and
a full per-item movement history with a running balance. It had `--export` for
offline analysis.

It will **not** cherry-pick cleanly onto current `build`: it was written for a
world without `factor` and uses `qty_base != qty_entered + free_qty` as its
marker. With `factor` restored it should read the column directly. Rebuilding
it against current semantics is roughly an hour.

---

## 5. What to do next — the thing that started all this

**Diagnose the client's machine.** Nobody has looked. Both reports are
unexplained, and the leading hypotheses cost nothing to check:

1. **Ask which screen the 189 was read from.** If it was the inventory list's
   `Total` column, report #1 closes with no code change at all.
2. **Ask for the item code and the GRN number.** With those, a short read-only
   `manage.py shell` query answers both reports without rebuilding the command.
3. **Check whether the client's `unit_conversion_enabled` is still off** and
   whether any posted line carries `factor != 1`. That decides whether R93 is
   theoretical or has already happened. R65's data is a month old.

Order matters: diagnose first, then decide what — if anything — to change.

---

## 6. Agreed but not built

**Confirm-before-post.** Temesgen's framing, and the right one: validation
cannot tell a typo from an intention, so the only real protection is showing
people what they are about to commit and making them say yes.

The mechanism already exists — D93 built one shared dialog for the whole app
(`base.html`, `data-confirm-*` attributes, `app.js` submits only on agreement),
and the **correction** Post button already uses it well. The **ordinary** Post
button on `templates/docs/detail.html` is a plain form with none of it. So this
is wiring, not machinery.

Shape: on Post, show item, batch, quantity **in the item's own base unit**, and
the document total; say plainly that posted documents cannot be edited, only
voided by the owner. That is exactly where a mistyped 189 becomes visible.

---

## 7. Environment gotchas that cost time

- **The full suite takes ~6–8 minutes.** Piping it through `tail` swallows the
  summary line — redirect to a file.
- **`pkill -f "manage.py runserver"` exits 144** because it matches its own
  shell. In a compound command everything after it dies too — start the server
  as its own command.
- **`CompanySettings.load()` uses `get_or_create`** — it can INSERT. Never call
  it from anything advertised as read-only.
- **Never put a raising guard inside a migration.** `docker-entrypoint.sh` is
  `set -e` and runs `migrate` before `exec`, so a raising migration exits the
  container and Docker restarts it forever, with nothing on screen.
- **Do not `sed` the test suite.** A regex over `factor=` mangled
  `factor=spec.get("factor", 1)` into a glued line and broke 17 tests.
- **Dropping a column is irreversible on the client's box:** `NARCOS_IMAGE` is
  an unpinned `:latest` ([compose.yml:27](compose.yml#L27)) and
  [docker-restore.ps1:32](ops/docker-restore.ps1#L32) refuses a database that
  already has tables.
- **The compose service is `app`, not `web`.** Any client instructions using
  `docker compose exec web` are wrong.
- **`qty_base` is not a copy of `qty_entered`.** It is "base units this line
  actually moved", and differs legitimately in four places even at factor 1:
  receiving (`+ free_qty`), stock count (frozen snapshot), settlement
  (`sold+returned+expired`), adjustment (`|qty_delta|`).

---

## 8. Process notes worth carrying

Three times this session a claim of mine was wrong and something else caught
it, not me:

- I asserted `doc.notes` renders on the draft detail page, to justify a
  migration design. It does not. Codex opened the template; I had not.
- I called a lingering foreign key "harmless" in a migration comment. It
  blocked `TRUNCATE` on the parent table and broke the suite immediately.
- I ran a regex over the test suite one turn after a review said to read that
  diff by hand.

The pattern is reasoning about behaviour instead of exercising it. Where a
claim decides a design, run it.

Separately: I gave three positions on the same question (remove; remove but
keep the columns; then implemented dropping them anyway). That is what made
the final answer hard to get. State one recommendation, and flag it loudly
when the implementation diverges from it.

---

## 9. Open questions only Temesgen can answer

1. Which screen was the **189** read from? (The inventory `Total` column would
   close report #1 outright.)
2. Which **item code** and **GRN number** do the two reports refer to?
3. Is the client's `unit_conversion_enabled` still off, and does any posted
   line carry `factor != 1`?
4. Is `GRN-000001` real client data or dev junk?
5. Rebuild `diagnose_quantities` against current semantics, or answer the
   reports with ad-hoc shell queries?
