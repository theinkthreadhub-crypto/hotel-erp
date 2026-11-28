# Runbook: 24-Hour Cloud Outage Run (Milestone 3.5d.3)

**Purpose:** produce the full 24-hour evidence that milestone 3.5d.3 requires. The milestone stays OPEN until a run of at least 24 h passes on stable hardware and its JSON result is recorded in `docs/AI_HANDOVER.md` §4.
**Data:** synthetic only. The harness creates its own temporary hotel database; it never opens a real hotel's data folder and never contacts a production URL.

## 1. Machine

- A machine that stays on for 25 hours: the Gate C Windows PC (4 GB RAM) is the target; any Windows 10/11 or Linux PC is acceptable for a first run.
- Python 3.11 and the repository at the commit under test (`git rev-parse HEAD` goes in the record).
- Disable sleep and automatic restarts for the duration:
  - Windows (Administrator prompt): `powercfg /change standby-timeout-ac 0` and `powercfg /change hibernate-timeout-ac 0`; pause Windows Update for 1 day.
  - Linux: run under `systemd-inhibit --what=sleep:idle` or keep the session awake.
- Close other heavy applications; note free RAM and disk at the start.

## 2. Command

From the repository root:

```bash
python tests/phase35d_outage_stress.py --hours 24 --bill-every 2 --sample 600 --json outage-24h.json > outage-24h.log 2>&1
```

- `--bill-every 2` gives about 43,200 bills in 24 h (a very busy restaurant day is under 2,000).
- `--sample 600` writes one line to the log every 10 minutes (RSS, database size, Python object count, threads, pending ops).
- Optional recovery check at the end: start a local Worker (`cd cloud && npx wrangler dev --local --port 8799 --persist-to <temp folder> --var ADMIN_KEY:<random>`), create a synthetic hotel with `POST /api/admin/create`, then add `--hotel <code> --key <syncKey> --recover-url http://127.0.0.1:8799`. Never point `--recover-url` at a production Worker.

## 3. Pass criteria (all printed under `checks` in the JSON)

1. `completedHours` is at least 24.0. A shorter run is recorded with its real duration and does not close the milestone (TEST-004).
2. No bill lost, nothing marked sent while offline, every bill pending in the outbox.
3. Dispatcher thread alive, no thread growth.
4. Settle p99 below 250 ms.
5. With recovery: the outbox drains (`pendingLeft` 0) and `heldForReview` is 0.
6. Memory: look at the 10-minute samples, not only the totals. RSS growth that follows `dbMB` and flattens once the SQLite page cache (64 MB cap) is full, with `pyObjects` flat, is cache fill. `pyObjects` or RSS still rising steadily in the last 8 hours is a suspected leak: record it as a bug with the samples; do not mark the run passed.

## 4. Record the result

- Copy the JSON summary (without `samples`) into `docs/AI_HANDOVER.md` §4 with the commit SHA, machine (CPU, RAM, OS) and start/end time.
- Update TD-0012 in `docs/TECH_DEBT_REGISTER.md` and milestone 3.5d.3 in `docs/MASTER_CHECKLIST.md` (tick it only if every criterion above passed).
- Keep `outage-24h.json` and `outage-24h.log` outside Git (attach them to the PR or store them with the release evidence).
