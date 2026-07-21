# Narcos Deployment Guide (Docker on Windows) — D83

The production deployment is **Docker Desktop on a Windows 10 desktop**,
running two Linux containers. Staff reach the app over the LAN by typing the
machine's **static IP** into a browser — plain HTTP, no domain, no TLS, no
internet dependency at run time. The image is built by CI and pulled from GHCR
(with a USB `docker load` fallback for offline updates).

For the host-installed (no-Docker) alternative and general operational
background, see [RUNBOOK.md](RUNBOOK.md). This guide is the canonical path.

```
┌ Windows 10 host (static IP 192.168.x.y) ──────────────────┐
│  Docker Desktop (WSL2)                                     │
│   ┌ app (Django + waitress) ─ published on host :80        │
│   └ db  (PostgreSQL 16) ─ internal network only, no ports  │
│  C:\narcos\  = compose.yml + .env + backups\               │
└───────────────────────────────────────────────────────────┘
        ▲ LAN workstations → http://192.168.x.y
```

## The stack

| Service | Image | Exposed | State |
|---------|-------|---------|-------|
| `app` | `ghcr.io/northernlights1/narcos` | host **:80** → 8080 | none (stateless) |
| `db`  | `postgres:16` | **nothing** (internal only) | `pgdata` volume |

- User uploads (attachments) live in the `media` named volume.
- Backups are bind-mounted to `C:\narcos\backups`.
- Secrets live only in `C:\narcos\.env` — never in the image or git.

---

## 1. First install

**Prerequisites**
- Windows 10 (64-bit) with virtualization enabled in BIOS.
- The desktop has a **static IP** — set a DHCP reservation on the router, or a
  static address *outside* the router's DHCP pool.
- A GitHub personal access token with `read:packages` (to pull the private image).

**Steps**
1. Install **Docker Desktop** and accept the WSL2 install it offers. Reboot.
2. Create the deploy folder and put the deployment files in it:
   ```
   C:\narcos\
     compose.yml        (from this repo)
     .env               (copy of .env.example, filled in)
     backups\           (created automatically on first backup)
   ```
3. Fill in `.env` — at minimum `NARCOS_SECRET_KEY`, `NARCOS_DB_PASSWORD`,
   `NARCOS_ALLOWED_HOSTS` (the static IP), and `NARCOS_BACKUP_ROOT=C:\narcos\backups`.
4. Log in to GHCR and pull:
   ```powershell
   cd C:\narcos
   docker login ghcr.io          # username = GitHub user, password = the PAT
   docker compose pull
   ```
   *Offline install:* skip login/pull and instead `docker load -i narcos-image.tar`
   from the USB bundle.
5. Start the stack (the app auto-creates the schema on first boot):
   ```powershell
   docker compose up -d
   ```
6. Create the owner account:
   ```powershell
   docker compose exec app python manage.py createowner
   ```
7. Open **Windows Firewall** and allow inbound **TCP 80** on the **Private**
   profile, and confirm the LAN is classified **Private** (not Public):
   ```powershell
   New-NetFirewallRule -DisplayName "Narcos HTTP" -Direction Inbound `
     -Protocol TCP -LocalPort 80 -Action Allow -Profile Private
   ```
8. From another PC on the LAN, browse to `http://<static-ip>` and log in.

---

## 2. Keep it running unattended (the boot chain)

Docker Desktop only runs while a user is signed in, so the machine must come
back up on its own after a reboot or power blip:

- **Auto-login**: create a dedicated local account and enable auto sign-in
  (`netplwiz` → untick "Users must enter a user name and password").
- **Docker Desktop**: Settings → General → *Start Docker Desktop when you sign in*.
- **Containers**: already `restart: unless-stopped`, so they return with Docker.
- **Power**: disable Sleep and Hibernate (Control Panel → Power Options).
- **Windows Update**: set active hours so forced reboots land overnight; the
  auto-login chain then brings the stack back before staff arrive.
- **UPS**: strongly recommended — power is unreliable. PostgreSQL is crash-safe
  (it replays its write-ahead log on restart), so a blackout won't corrupt the
  database, but a UPS protects the hardware and allows clean shutdowns.
- **Cap WSL2 memory** on 8 GB machines so WSL2 doesn't starve Windows. Create
  `%UserProfile%\.wslconfig`:
  ```ini
  [wsl2]
  memory=4GB
  ```
  Then `wsl --shutdown` and restart Docker Desktop.

---

## 3. Nightly backups

Backups are **not** configured in the app — they run from the host on a
schedule. See the design in [RUNBOOK.md](RUNBOOK.md#nightly-backup).

**Set up the schedule (once):** create a Windows Task Scheduler task:
- **Trigger**: Daily at **16:00** (staff are still in; the PC is on).
- **Action**: `powershell.exe -ExecutionPolicy Bypass -File C:\narcos\ops\docker-backup.ps1`
  with **Start in** = `C:\narcos`.
- **Settings**: tick **"Run task as soon as possible after a scheduled start is
  missed"** — so a day the PC was off at 16:00 still gets backed up at next boot.
- **General**: "Run whether user is logged on or not."

**What each run produces** in `C:\narcos\backups\<timestamp>\`:
`narcos.dump` (verified), `media.tar.gz`, and a copy of `.env`.
**Retention**: newest 14 nightly + one per month for a year (auto-pruned).

**Offsite (the human step):** weekly, copy `C:\narcos\backups\` to an external
USB drive kept off the machine. A backup on the same disk dies with the disk.

---

## 4. Updating to a new version

Run one command from `C:\narcos`:
```powershell
powershell -ExecutionPolicy Bypass -File ops\deploy.ps1
```
It takes a fresh backup, pulls the new image, and recreates the app (migrations
apply automatically on start). *Offline:* `docker load` the new image tar from
USB first, then `docker compose up -d`.

> Always update through `deploy.ps1` (or a manual backup first). A bare
> `docker compose pull; up -d` skips the safety backup.

---

## 5. Restore & disaster recovery

**Restore drill (do this before go-live and before every update):** prove the
latest backup restores into a scratch database, without touching live:
```powershell
cd C:\narcos
powershell -File ops\docker-restore.ps1 <timestamp>
docker compose exec app python manage.py migrate --check   # optional sanity
```

**Bare-metal rebuild (dead/wiped machine):**
1. Install Windows + Docker Desktop on the replacement box.
2. Recreate `C:\narcos\` — `compose.yml` + `.env` (from the newest USB backup
   folder) + copy the newest backup folder into `C:\narcos\backups\`.
3. Get the image: `docker login ghcr.io && docker compose pull`
   (or `docker load` from USB).
4. Bring up **only the database** so it's empty when we restore:
   ```powershell
   docker compose up -d db
   ```
5. Restore into live `narcos` (refuses if not empty) with media:
   ```powershell
   powershell -File ops\docker-restore.ps1 <timestamp> narcos /app/media
   ```
6. Start the app: `docker compose up -d` (migrate is a no-op when versions match).
7. Re-add the firewall rule and the Task Scheduler backup job (§2, §3).
8. **Prove it end to end**: log in, open the dashboard, open a document *that
   has an attachment* (proves media returned, not just rows), print one document.

Recovery point = the last nightly backup. Everything entered after it is gone —
make sure the owner understands this.

---

## 6. Troubleshooting

| Symptom | Likely cause / fix |
|---------|--------------------|
| Works on the desktop, LAN PCs can't connect | Firewall rule missing, or network is **Public** not Private (§1.7). |
| A form submit fails with a CSRF error | The browser address isn't in `NARCOS_ALLOWED_HOSTS`; add it, `docker compose up -d`. Origins are derived from it. |
| Stack didn't come back after reboot | No one is signed in → Docker Desktop isn't running. Fix auto-login (§2). |
| Nightly backup didn't run | PC was off at 16:00 and "run missed task" wasn't ticked (§3); or the task's "Start in" isn't `C:\narcos`. |
| Windows feels sluggish | WSL2 memory not capped — add `.wslconfig` (§2). |
| `pull` fails | Not logged in to GHCR, or no internet — use the USB `docker load` path. |

Health check any time:
```powershell
cd C:\narcos
docker compose ps
docker compose logs -f app
```
