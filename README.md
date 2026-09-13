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
| [05-status.md](05-status.md) | Where the work stands right now, written to the owner. |

## Installing and running it

| File | What it holds |
|------|---------------|
| [ops/DEPLOYMENT.md](ops/DEPLOYMENT.md) | **Start here for a new machine.** The Windows install, the boot chain, the backup schedule, updates, and the troubleshooting table. |
| [ops/deploy.ps1](ops/deploy.ps1) | Update to a new version: backup, pull, recreate. Never pull and restart by hand; this is what guarantees the backup happens first. |
| [ops/RELEASE-CHECKLIST.md](ops/RELEASE-CHECKLIST.md) | Tick-box pass over the whole app before shipping a release. |
| [ops/MANUAL-TESTING.md](ops/MANUAL-TESTING.md) | The walkthrough for exercising the system by hand. |

## When something breaks

| File | What it holds |
|------|---------------|
| [ops/INCIDENT-2026-09-08.md](ops/INCIDENT-2026-09-08.md) | **Read this first.** The day the client's machine went down after a month with no backup: twelve failures with causes, what saved the data, and a symptom-to-command table. Most faults on that PC are in here already. |
| [ops/backup-now.ps1](ops/backup-now.ps1) | Take one verified backup right now. Deletes nothing, works with the app container down. Run it before any repair. |
| [ops/copy-data-out.ps1](ops/copy-data-out.ps1) | Get the data onto a USB stick when Docker will not start at all. Needs no engine. |
| [ops/fix-docker-config.ps1](ops/fix-docker-config.ps1) | Repair Docker Desktop config that a power cut filled with NUL bytes. The alternative the error dialog offers deletes the database. |
| [ops/docker-restore.ps1](ops/docker-restore.ps1) | Restore a backup. Defaults to a scratch database so a drill cannot touch live data. |
| [ops/docker-backup.ps1](ops/docker-backup.ps1) | The scheduled daily backup. Check `ops/backup.log`, never Task Scheduler's result code. |
| [ops/RUNBOOK.md](ops/RUNBOOK.md) | Backup, restore, update and password recovery, described rather than scripted. |

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
