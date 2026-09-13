# UI fixes — accessibility and feedback

Written 2026-09-13. Scope is **defects only**: no restyle, no new fonts, no
motion, no new dependency. The existing look (`ink`/`paper`/`accent`, the slim
shell, the card grid) is deliberate and stays exactly as it is.

Two design skills were consulted and largely rejected — see "What was rejected"
at the bottom, so the next round does not re-litigate it.

---

## F1 — Hint text fails WCAG AA contrast (HIGH)

`text-slate-400` (#94a3b8) at `text-xs` (12px):

| On | Ratio | AA needs |
|---|---|---|
| white (`.card`, `.sidebar`) | **2.56:1** | 4.5:1 |
| paper (`.page`) | **2.39:1** | 4.5:1 |

This is the least readable text in the app, and it is where the app puts things
a clerk must not miss: near-expiry warnings, batch-spelling suggestions (D128),
credit-limit notes. On a shared PC under office lighting it is close to
invisible.

Replacements (`static/src/input.css`):

| Line | Class | Now | Change to | New ratio |
|---|---|---|---|---|
| 54 | `.hint` | `text-slate-400` | `text-slate-600` | 7.07:1 on paper |
| 69 | `.field-help` | `text-slate-400` | `text-slate-600` | 7.07:1 |
| 210 | `.net-label` | `text-slate-400` | `text-slate-600` | 7.07:1 |
| 218 | `.placeholder` | `text-slate-400` | `text-slate-600` | 7.07:1 |
| 222 | `.summary-grid dt` | `text-slate-400` | `text-slate-600` | 7.07:1 |
| 32 | `.nav-group` | `text-slate-400` | `text-slate-500` | 4.76:1 on white |
| 174 | (nav-group variant) | `text-slate-400` | `text-slate-500` | 4.76:1 |
| 85 | `.btn-inline-edit` | `text-slate-400` | `text-slate-500` | 4.76:1 |
| 120 | (row-delete button) | `text-slate-400` | `text-slate-500` | 4.76:1 |

`slate-600` for the 12px body hints because they appear on both white and paper
and `slate-500` is 4.44:1 on paper — 0.06 short. `slate-500` for the nav labels
and the two icon buttons: those are UI components, where WCAG 1.4.11 asks 3:1,
and 4.76:1 clears it without making the chrome heavier than the data.

**Leave alone:** `.who` and `.btn-quiet` are `slate-300` on `ink` = 10.19:1.

---

## F2 — Messages are never announced (MEDIUM)

Zero `role="alert"` or `aria-live` in 34 templates. `templates/base.html:55`
renders Django messages into a plain `<ul>`.

On a full page load this is survivable — a screen reader meets the list in
reading order. It is not survivable on the htmx swaps in F3, and it matters more
than it looks because the double-post path (below) *communicates entirely
through a message*.

```html
<ul class="messages" role="status" aria-live="polite">
```

`role="status"`/`polite` rather than `alert`/`assertive`: these are mostly
confirmations, and assertive interrupts whatever the user is typing.

---

## F3 — No feedback on the three htmx actions that can be slow (LOW–MEDIUM)

7 request-triggering attributes exist; 3 warrant an indicator:

| File | Line | Action |
|---|---|---|
| `templates/docs/_field_edit.html` | 7 | `hx-post` — save an inline field edit |
| `templates/stock/_batch_expiry_edit.html` | 7 | `hx-post` — save a corrected expiry |
| `templates/catalog/form.html` | 38 | `hx-get` — master-data typeahead |

The other four are open/cancel toggles against local Postgres; they are
instantaneous and need nothing.

Add to those three only:

```html
hx-indicator="#…" hx-disabled-elt="this"
```

Ingredients, per the animate skill's tables: CSS transition (cheapest tool that
works), `opacity` only, `ease-out`, 150ms. `hx-disabled-elt` is the part that
actually matters — the visual is secondary to the button refusing a second click.

---

## F4 — WITHDRAWN. Not a defect.

Both icon buttons already carry `aria-label` alongside `title`
(`templates/docs/_field_value.html:9`, `templates/stock/_batch_expiry_value.html:10`).

The original finding was a false positive: the audit grepped for `<button`
lines lacking `aria-label`, and in both files the attribute sits on the *next*
line of a multi-line tag. **Lesson for the next audit: do not line-grep
multi-line HTML tags.**

---

## Not a defect — verified, no change

- **Double-clicking Post is already safe.** `docs/posting.py:318-321` re-reads
  the document under `select_for_update` and refuses anything not still `DRAFT`.
  The second click produces an error message, which is correct. This is why F2
  matters: that message is the only thing the clerk gets.
- **Zero motion in 26KB of compiled CSS is correct, not an oversight.** This is a
  keyboard-driven tool used hundreds of times a day. Animating high-frequency
  actions is a defect, not a polish item. Do not add hover transitions here.
- **`.who` / `.btn-quiet` contrast** — 10.19:1, fine.

---

## Order and verification

1. F1 — edit `static/src/input.css`, `./scripts/build_css.sh`, bump `?v=` on both
   tags in `templates/base.html`.
2. F2 + F4 — template attributes only; no CSS rebuild.
3. F3 — three templates plus one small CSS rule; rebuild and bump `?v=` again.

**Tailwind purge trap (cost one rebuild to find).** Rules in `@layer components`
are tree-shaken when their class names never appear in the scanned content.
`htmx-request` is applied by htmx at runtime, so `#dupe-matches.htmx-request`
compiled to nothing on the first build. It now sits in the `safelist` in
`tailwind.config.js`, next to the `badge-*` entries that exist for the same
reason. Any future rule keyed on a runtime class needs the same treatment —
check the compiled `static/css/app.css`, not just the source.

Ship F1 alone first. It is the only one a user will notice, it touches one file,
and it is trivially revertible.

Verify: `.venv/bin/python -m pytest` (no test asserts on these classes, so a
green suite only proves nothing broke), then look at Inventory and a document
detail page at the real 70-business database — the hints are what changed.

---

## What was rejected, and why

- **`ui-ux-pro-max --design-system`** returned a marketing-landing pattern
  ("Hero", "Start trial"), an "Exaggerated Minimalism" style whose own
  description says it is for *fashion, portfolios, luxury brands*, Fira Code via
  `fonts.googleapis.com` (breaks the no-network rule), and GSAP ScrollTrigger.
  All rejected. Its `--domain ux` corpus is what produced F1–F4.
- **Its checklist item "hover states with smooth transitions (150–300ms)"** is
  wrong for this app and is the reason "zero motion is correct" is written down
  above.
- **A restyle of any kind.** `static/src/input.css` is a coherent 261-line
  system. It does not need a direction; it needs four defects fixed.
