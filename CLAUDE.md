# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A home lab project that automates installing MSSQL Server 2019 on two Linux VMs, restoring the
AdventureWorks sample database, striping a backup from VM1 to VM2, and standing up an Always On
Availability Group between them. There are two independent automation paths to the same goal:

1. **`ansible-mssql-deploy/`** — driven from AWX (`devops_AWX`, `192.168.70.128`), source-of-truth
   repo is GitLab, GitHub is a mirror. This is the "enterprise orchestration" path.
2. **`python-fastapi-mssql/`** — a FastAPI service that shells out to its own embedded copy of the
   Ansible playbooks/roles (`python-fastapi-mssql/ansible/`) via `subprocess`. This is the actively
   live-tested path (see `python-fastapi-mssql/CHANGELOG.md`) — Always On AG was verified end to end
   against the real VMs through this path, not the AWX one.

**Important:** `ansible-mssql-deploy/roles` and `ansible-mssql-deploy/playbooks` are a *separate,
diverged copy* of `python-fastapi-mssql/ansible/roles` and `python-fastapi-mssql/ansible/playbooks`
(diff them before assuming a fix in one applies to the other — `diff -rq` shows every task file
differs). The FastAPI copy additionally has `alwayson.yml` (playbook + task file) and is the one
with real-bug fixes from live testing. When fixing a bug in the MSSQL role/playbooks, check which
tree the report/log came from and be deliberate about whether the fix belongs in one tree or both.

Within `python-fastapi-mssql/ansible/`, `playbooks/roles` is a symlink to `../roles` (added to stop
Ansible's playbook-relative role resolution from creating a second physical copy) — don't recreate
it as a real directory.

### Lab topology

| VM | Role | Hostname | IP |
| --- | --- | --- | --- |
| AWX server | Runs AWX, pulls from GitLab | `devops_AWX` | `192.168.70.128` |
| SQL VM 1 | Primary SQL Server / AG primary | `devops_VM1` | `192.168.70.129` |
| SQL VM 2 | Secondary SQL Server / AG secondary | `devops_VM2` | `192.168.70.130` |

**VM1 doubles as the Ansible/FastAPI controller.** The FastAPI app and `ansible-playbook` normally
run on `devops_VM1` itself, targeting both itself and VM2 over SSH — so "controller-side" logs and
paths mentioned below are local files on VM1, not something to SSH for. VM2 is the only genuinely
remote host. A Claude Code session opened against this repo may itself be running on VM1 (see
`SESSION_HANDOFF.md`) — check `hostname` if it matters.

SSH user for both target VMs is `devops` (not `root`), with key auth
(`ansible_ssh_private_key_file` in the relevant inventory).

## Commands

### FastAPI service (`python-fastapi-mssql/`)

```bash
cd python-fastapi-mssql
source .venv/bin/activate        # venv already exists in-repo; python -m venv .venv to recreate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# API docs: http://localhost:8000/api/docs
```

Run tests (pytest config in `pytest.ini` sets `testpaths = tests`, `pythonpath = .`):

```bash
cd python-fastapi-mssql
pytest tests/ -v
pytest tests/test_api.py::test_deployment_status -v   # single test
```

Config comes from `python-fastapi-mssql/.env` (copy from `.env.example`), loaded via
`app/config.py` (`pydantic-settings`). Key vars: `VM1_HOST`/`VM2_HOST`, `VM1_USER`/`VM2_USER`
(`devops`), `SSH_KEY_PATH`, `MSSQL_SA_PASSWORD`, `ANSIBLE_INVENTORY`, `ANSIBLE_PLAYBOOK_DIR`.
`python-fastapi-mssql/ansible.cfg` sets `log_path = ./logs/ansible.log` — it resolves relative to
whatever directory `uvicorn` was started from, so always launch it from `python-fastapi-mssql/`.

### AWX / direct Ansible path (`ansible-mssql-deploy/`)

```bash
cd ansible-mssql-deploy
ansible-playbook -i inventory/hosts.ini playbooks/site.yml -v      # full install + AdventureWorks restore + backup
ansible-playbook -i inventory/hosts.ini playbooks/backup.yml -v    # backup on vm1, restore on vm2 only
ansible-playbook -i inventory/hosts.ini playbooks/site.yml --syntax-check
ansible-playbook -i inventory/hosts.ini playbooks/site.yml -t adventureworks   # tag-scoped run
```

The root `ansible.cfg` (repo root) sets `roles_path = ./ansible-mssql-deploy/roles` — only relevant
when invoking `ansible-playbook` from the repo root rather than from inside `ansible-mssql-deploy/`.

## Architecture notes

- **Two Python "deployer" implementations exist in `python-fastapi-mssql/app/`:** `deployer.py`
  (`AnsibleMssqlDeployer`, wired into `routes/deploy.py`, shells out via `ansible_runner.py`) is the
  live one. `python_deployer.py` (`PythonMssqlDeployer`, raw Paramiko SSH, no Ansible) is the
  earlier approach the service was refactored away from — don't wire new routes to it without
  checking with the user first, and don't trust docs that describe the service as SSH/Paramiko-based.
- **Deployment flow:** a route in `app/routes/deploy.py` calls `deployer.start_task()` (returns a
  `task_id`), queues the actual work via `BackgroundTasks`, and returns immediately. Progress is
  polled via `GET /api/v1/deploy/status` or `/history` (in-memory only, lost on process restart) —
  cross-reference with `logs/ansible.log` for output that survives a restart.
  `AnsibleMssqlDeployer._run_full_ag_sequence` (the `full-ag` endpoint) chains `site.yml` (vm1
  only) → `backup.yml` → `alwayson.yml`, raising `SequenceStepError` (carrying partial results) if
  any step's playbook exits non-zero, so a failed step stops the sequence instead of silently
  continuing.
- **`mssql` role phases** (both trees, task files under `roles/mssql/tasks/`): `install.yml` →
  `configure.yml` → `adventureworks.yml` (restore DB) → `backup.yml` (10-stripe backup, VM1 only)
  → `restore.yml` (fetch stripes to controller, copy to VM2, restore) → `alwayson.yml`
  (FastAPI tree only — HADR enable, firewalld for the 5022 mirroring endpoint, certificate-based
  endpoint auth generated on vm1 and relayed to vm2 via the same fetch/copy pattern as
  `restore.yml`, `CREATE AVAILABILITY GROUP` declaring both replicas, `CLUSTER_TYPE=NONE` /
  `FAILOVER_MODE=MANUAL` since there's no cluster manager in this lab).
- **`mssql_build` role + `build.yml` playbook** is a separate idempotent "prepare + install" flow
  (dirs, service account, repos, packages, `mssql-conf setup`), exposed via
  `POST /api/v1/deploy/build`. It duplicates some of what `mssql`'s `install.yml`/`configure.yml`
  do — they aren't unified into one role.
- **Backup/restore cross-VM transfer** always goes through the Ansible controller (VM1), never
  directly VM1→VM2: `fetch` pulls the 10 stripe files from VM1 to the controller's local
  `LOCAL_BACKUP_DIR` (`./backups/vm1_striped` under `python-fastapi-mssql/`), then `copy` pushes
  them to VM2. AG certificates use the same relay pattern via `LOCAL_CERT_RELAY_DIR`.
- Replica identity in AG DDL must use `vmware_name` (`devops_VM1`/`devops_VM2`, matching
  `@@SERVERNAME`) from the inventory hostvars — the Ansible inventory hostname (`vm1`/`vm2`) does
  not match what SQL Server expects for `REPLICA ON`.
- Data/backup/log directories must be owned by the `mssql` service account, not `root:root` — a
  root-owned directory fails `RESTORE DATABASE`/`BACKUP DATABASE` with OS error 5 without an
  obviously-related error message.
- `sqlcmd` heredocs passed through `shell` need an explicit `GO` batch terminator; without it
  `sqlcmd` exits 0 and prints nothing while silently executing no SQL.
- `tags: always` on `include_tasks` is not reliable for forcing child-task execution under a
  `--tags`-filtered run on the Ansible version in use here; prefer running full playbooks
  (optionally with `--limit`) over relying on tag filtering for correctness-critical steps.

## Logs (when running on VM1, the normal case)

- `python-fastapi-mssql/logs/ansible.log` — full persistent `ansible-playbook` stdout/stderr for
  every run (via `ansible.cfg`'s `log_path`), independent of API process restarts.
- `python-fastapi-mssql/logs/app.log` — FastAPI request events/tracebacks only, not Ansible output.
- `sudo tail -100 /var/opt/mssql/log/errorlog` — SQL Server's own error log; the most useful source
  for HADR/AG/certificate failures. Rolls to `errorlog.1`, `errorlog.2`, etc.
- `/tmp/mssql_deployment_<hostname>.txt` — one-off summary written by `site.yml`'s `post_tasks`.
- For VM2, everything above requires `ssh devops@192.168.70.130 ...` since it's genuinely remote.

## Documentation map

Several top-level docs (`ARCHITECTURE.md`, `INDEX.md`, `PROJECT_INDEX.md`, `DELIVERY_SUMMARY.md`,
`COMPLETION_SUMMARY.txt`, `IMPLEMENTATION_HANDOFF.md`) were generated early in the project and are
not reliably kept in sync with the code (e.g. `ARCHITECTURE.md` still diagrams the retired
Paramiko/SSH design). Prefer, in order: `SETUP_GUIDE.md` (root — explicitly the current source of
truth for the VMware/GitLab/AWX setup), `python-fastapi-mssql/RUNBOOK.md` and `CHANGELOG.md` (most
current, written from live-testing sessions), then the actual playbooks/roles/code. Root
`README_Local.md` itself defers to `SETUP_GUIDE.md` for current setup steps.
