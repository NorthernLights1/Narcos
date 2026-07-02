# Narcos — AI Context

**Narcos** is the project name for a custom on-prem pharmacy / medical /
lab-supplies wholesale system for a small Ethiopian business. This folder is the
**source of truth** for its design. Read it before writing any code or making
design changes.

It exists so that anyone — human or AI — picking up this project later can see
**what we decided, why, and what is still open**, without re-deriving it from
chat history.

## Files

| File | What it holds |
|------|---------------|
| [01-business-logic.md](01-business-logic.md) | The business in plain words: what it does, the three sales paths, consignment, stock, money, tax, roles. The shared mental model. |
| [02-decisions.md](02-decisions.md) | The decision log. Every locked design decision, with the reason. This overrides anything older. |
| [03-open-risks.md](03-open-risks.md) | Blind spots, pitfalls, and things still to decide before/while building. Each is marked OPEN or DECIDED. |
| [04-build-spec.md](04-build-spec.md) | The buildable spec derived from D1–D64: schema, posting engine, tax/withholding algorithms, per-document rules, screens, reports, build phases, and the mandatory invariant tests. **Implementers build from this file, in phase order.** |

## Rules for this folder

- **Append, don't rewrite history.** When a decision changes, add a new dated
  entry that supersedes the old one and mark the old one superseded. Same
  honesty rule the app itself uses.
- **Plain language first.** The product owner is a developer but not a
  finance/stock expert. Explain in everyday words; keep jargon out of the
  business doc.
- **Every decision needs a reason.** "Because we said so" is not a reason.
- Date format: `YYYY-MM-DD`.
- **Files 01–03 are design truth; 04 is the derived build spec.** If you are
  an AI asked to build: read 01–03 first, then build from
  [04-build-spec.md](04-build-spec.md) in phase order. Where 04 conflicts with
  02, the decision log wins — flag it, don't guess.

_Last updated: 2026-07-02._
