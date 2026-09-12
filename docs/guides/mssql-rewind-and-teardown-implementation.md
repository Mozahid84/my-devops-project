# MSSQL Lab Rewind & Teardown — Implementation Plan

> This is the concrete, MSSQL-specific implementation of the generic pattern
> sketched in [`mssql-rewind-and-teardown-design.md`](mssql-rewind-and-teardown-design.md).
> That doc is a template shared with the MySQL/Oracle design docs; this one is
> traced from the actual task files in `python-fastapi-mssql/ansible/` and is
> meant to be followed step by step, by hand, to implement and learn the change.

## Context

Today the only reverse path that exists is the manual one written down in
`RUNBOOK.md` §7 (SSH in, `rm -rf` directories, `yum remove`). This plan turns that
into real Ansible task files + FastAPI endpoints in the tree that's actually
live-tested: `python-fastapi-mssql/ansible/` (per `CHANGELOG.md`, this is the tree
where Always On AG was built and debugged against the real VMs — `ansible-mssql-deploy/`
has no AG support at all, so there's nothing to tear down there).

Decisions:
- **Scope**: `python-fastapi-mssql/ansible/` only, not `ansible-mssql-deploy/`.
- **Safety**: new endpoints fire immediately, same as `install`/`backup`/`build` today — no confirmation gate.
- **`reset-baseline`**: wipes MSSQL back to a bare VM only. It does not reinstall — call `POST /deploy/install` (or `/full-ag`) afterward.

The end goal: get the code changes in place, then run a **reset-baseline → full-ag**
cycle as the real proof that the AG build now goes straight through on a genuinely
bare VM, using only the bugs-already-fixed code (no more manual SSH intervention
like the first build needed).

## What state actually needs reversing

Traced from the real task files (not the aspirational design doc):

| Created by | State | Reversed by |
|---|---|---|
| `install.yml` | `mssql-server`/`mssql-tools` packages, 2 yum repos, `/var/opt/mssql` | `uninstall.yml` (new) |
| `configure.yml` | `backup_dir`, `data_dir`, `log_dir` (owned `mssql:mssql`) | `uninstall.yml` (new) |
| `adventureworks.yml` | `AdventureWorks2019.bak` in `data_dir`, `AdventureWorks` DB | `teardown.yml` (new) |
| `backup.yml` | `backup_dir/striped/adv_stripe_{01..10}.bak` on vm1 | `teardown.yml` (new) |
| `restore.yml` | same 10 files copied to vm2, `local_backup_dir` on controller | `teardown.yml` (new) |
| `alwayson.yml` | master key, `dbm_certificate` (+`.cer`/`.pvk` files), `Hadr_endpoint`, `AG1` availability group, `aw_full_seed.bak`/`aw_log_seed.bak`, `local_cert_relay_dir` on controller | `teardown.yml` (new) |
| `site.yml` post_tasks | `/tmp/mssql_deployment_<host>.txt` | both |

Firewalld's port-5022 rule is left alone by `teardown.yml` — re-enabling it is a
no-op (`state: enabled`) and leaving it open is harmless in this lab.

**Ordering note (why `teardown.yml` does AG cleanup before dropping the DB):** with
`CLUSTER_TYPE=NONE` there's no shared cluster state, so `DROP AVAILABILITY GROUP`
must run independently on *both* vm1 and vm2 (unconditional, no `when:
inventory_hostname` — unlike `alwayson.yml` where CREATE is vm1-only and JOIN is
vm2-only). Once dropped on a given node, that node's copy of `AdventureWorks`
reverts to a normal standalone database and `DROP DATABASE` works normally.

## Pre-implementation review findings (2026-08-31)

Before writing any of this for real, the plan below (still just a plan at
that point — nothing in this section had been implemented yet) was reviewed
against everything actually learned live in the failover and sync-rebuild
guides. Six gaps came out of that review; all six are fixed in the
"File-by-file changes" code below. Kept here as a standalone list for later
reference — this is what a naive first implementation would have shipped
with, and why it didn't ship that way.

| # | Gap | Where fixed |
| --- | --- | --- |
| 1 | `teardown`/`rewind`/`reset-baseline` weren't going to be covered by the concurrency guard (`AG_MUTATING_OPERATIONS`) added in the failover guide — the exact double-submit hazard that caused the 2026-08-30 split-brain, but on strictly more destructive operations. | §5 (`app/deployer.py`), §6 (`app/routes/deploy.py`) |
| 2 | This guide's own "practice a mid-cycle rewind" example chained three bare `curl` calls with no wait-for-completion step — inviting exactly the race #1 fixes against. | "Commands to run it yourself" §7 |
| 3 | `teardown.yml` would run `DROP AVAILABILITY GROUP` on vm1 and vm2 in the same task step, concurrently (no `serial`) — an untested combination of concurrent AG mutations, the exact class of thing that surprised us before. | §3 (`ansible/playbooks/teardown.yml`) |
| 4 | `DROP AVAILABILITY GROUP` has only ever been tested live against a SECONDARY (both the 2026-08-30 recovery and the sync-rebuild Path B drill) — never against whichever replica happens to be PRIMARY, which `teardown.yml` also hits. | §3, flagged as still unresolved — see the note there |
| 5 | `uninstall.yml`'s own header comment says to run `teardown.yml` first if an AG might exist, but `deploy_reset_baseline` called `uninstall.yml` directly — a doc/code mismatch. | §5 (`app/deployer.py`) |
| 6 | "Drop AdventureWorks database" reported `changed: true` unconditionally regardless of whether the inner `IF EXISTS` body actually ran — same cosmetic gap already found and fixed in `sync_rebuild.yml`'s "Drop a stale standalone copy" task. | §1 (`ansible/roles/mssql/tasks/teardown.yml`) |

Gap #4 is **not** fully resolved by anything below — see §3's note for exactly
what's still unverified and what to watch for the first time this actually
runs.

## File-by-file changes

### 1. New: `python-fastapi-mssql/ansible/roles/mssql/tasks/teardown.yml`

Reverses `alwayson.yml` + `backup.yml` + `restore.yml` + `adventureworks.yml`.
Leaves MSSQL installed/configured. Every step is `IF EXISTS`/`state: absent`, so
it's safe to call on a host that never had an AG, or to re-run twice in a row.

```yaml
---
# Reverse alwayson.yml + backup.yml + restore.yml + adventureworks.yml.
# Leaves MSSQL installed and configured; safe to re-run.

- name: Check whether Availability Group exists
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -h -1 -W -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM sys.availability_groups WHERE name = '{{ ag_name }}'"
  register: ag_exists_check
  changed_when: false
  failed_when: false
  tags:
    - teardown

- name: Drop Availability Group (removes this replica from the AG)
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -Q "DROP AVAILABILITY GROUP [{{ ag_name }}]"
  when: (ag_exists_check.stdout | trim) == '1'
  changed_when: true
  tags:
    - teardown

- name: Take AdventureWorks out of HADR if still flagged (safety net)
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -Q "
    IF EXISTS (SELECT * FROM sys.databases WHERE name = 'AdventureWorks' AND is_hadr_enabled = 1)
    ALTER DATABASE AdventureWorks SET HADR OFF
    "
  changed_when: false
  failed_when: false
  tags:
    - teardown

- name: Check whether AdventureWorks exists
  # Split from the drop itself (same pattern as ag_exists_check above) so
  # changed_when reflects reality -- see finding #6: an unconditional
  # `changed_when: true` around an IF EXISTS block reports "changed" even
  # on a host where there was nothing to drop.
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -h -1 -W -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM sys.databases WHERE name = 'AdventureWorks'"
  register: aw_exists_check
  changed_when: false
  failed_when: false
  tags:
    - teardown

- name: Drop AdventureWorks database
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -Q "
    ALTER DATABASE AdventureWorks SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
    DROP DATABASE AdventureWorks;
    "
  when: (aw_exists_check.stdout | trim) == '1'
  changed_when: true
  tags:
    - teardown

- name: Drop Always On endpoint
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -Q "
    IF EXISTS (SELECT * FROM sys.database_mirroring_endpoints WHERE name = '{{ ag_endpoint_name }}')
    DROP ENDPOINT [{{ ag_endpoint_name }}]
    "
  changed_when: true
  tags:
    - teardown

- name: Drop AG certificate
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -Q "
    IF EXISTS (SELECT * FROM sys.certificates WHERE name = '{{ ag_cert_name }}')
    DROP CERTIFICATE {{ ag_cert_name }}
    "
  changed_when: true
  tags:
    - teardown

- name: Drop database master key
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -Q "
    IF EXISTS (SELECT * FROM sys.symmetric_keys WHERE name = '##MS_DatabaseMasterKey##')
    DROP MASTER KEY
    "
  changed_when: false
  failed_when: false
  tags:
    - teardown

- name: Remove AG certificate files from data_dir
  file:
    path: "{{ data_dir }}/{{ ag_cert_name }}.{{ item }}"
    state: absent
  loop:
    - cer
    - pvk
  tags:
    - teardown

- name: Remove striped backup files
  file:
    path: "{{ backup_dir }}/striped"
    state: absent
  tags:
    - teardown

- name: Remove AG seed backups
  file:
    path: "{{ backup_dir }}/{{ item }}"
    state: absent
  loop:
    - aw_full_seed.bak
    - aw_log_seed.bak
  tags:
    - teardown

- name: Remove downloaded AdventureWorks source backup
  file:
    path: "{{ data_dir }}/AdventureWorks2019.bak"
    state: absent
  tags:
    - teardown

- name: Remove deployment summary file
  file:
    path: "/tmp/mssql_deployment_{{ inventory_hostname }}.txt"
    state: absent
  tags:
    - teardown

- name: Clear controller-side backup relay directory (vm1 only, runs once)
  file:
    path: "{{ local_backup_dir }}"
    state: absent
  delegate_to: localhost
  become: false
  when: inventory_hostname == "vm1"
  tags:
    - teardown

- name: Clear controller-side certificate relay directory (vm1 only, runs once)
  file:
    path: "{{ local_cert_relay_dir }}"
    state: absent
  delegate_to: localhost
  become: false
  when: inventory_hostname == "vm1"
  tags:
    - teardown
```

### 2. New: `python-fastapi-mssql/ansible/roles/mssql/tasks/uninstall.yml`

Deep wipe — packages, repos, `/var/opt/mssql`, and the three data directories.
Returns the host to a bare VM, matching `RUNBOOK.md` §7's manual steps.

```yaml
---
# Deep wipe: removes MSSQL entirely, returning the host to a bare VM.
# Run teardown.yml first if an AG/database might still exist -- this file does
# not attempt AG-aware cleanup, it just stops the service and deletes everything.

- name: Stop MSSQL service
  systemd:
    name: mssql-server
    state: stopped
  failed_when: false
  tags:
    - uninstall

- name: Remove MSSQL Server package
  yum:
    name: mssql-server
    state: absent
  tags:
    - uninstall

- name: Remove MSSQL Tools package
  yum:
    name: mssql-tools
    state: absent
  tags:
    - uninstall

- name: Remove Microsoft SQL Server repo definition
  yum_repository:
    name: mssql-server
    state: absent
  tags:
    - uninstall

- name: Remove Microsoft MSSQL-Tools repo definition
  yum_repository:
    name: mssql-tools
    state: absent
  tags:
    - uninstall

- name: Remove MSSQL config/state directory
  file:
    path: /var/opt/mssql
    state: absent
  tags:
    - uninstall

- name: Remove data directory
  file:
    path: "{{ data_dir }}"
    state: absent
  tags:
    - uninstall

- name: Remove log directory
  file:
    path: "{{ log_dir }}"
    state: absent
  tags:
    - uninstall

- name: Remove backup directory
  file:
    path: "{{ backup_dir }}"
    state: absent
  tags:
    - uninstall

- name: Reset any failed systemd unit state
  command: systemctl reset-failed mssql-server
  failed_when: false
  changed_when: false
  tags:
    - uninstall

- name: Remove deployment summary file
  file:
    path: "/tmp/mssql_deployment_{{ inventory_hostname }}.txt"
    state: absent
  tags:
    - uninstall

- name: Clear controller-side backup relay directory (vm1 only, runs once)
  file:
    path: "{{ local_backup_dir }}"
    state: absent
  delegate_to: localhost
  become: false
  when: inventory_hostname == "vm1"
  tags:
    - uninstall

- name: Clear controller-side certificate relay directory (vm1 only, runs once)
  file:
    path: "{{ local_cert_relay_dir }}"
    state: absent
  delegate_to: localhost
  become: false
  when: inventory_hostname == "vm1"
  tags:
    - uninstall
```

### 3. New: `python-fastapi-mssql/ansible/playbooks/teardown.yml`

```yaml
---
- name: Tear down Always On AG, AdventureWorks, and backup artifacts
  hosts: mssql_servers
  become: yes
  gather_facts: yes
  # Fixes finding #3: without `serial: 1`, Ansible runs "Drop Availability
  # Group" on vm1 and vm2 in the same task step -- both replicas dropping
  # the AG at once, an untested combination of concurrent AG mutations.
  # `serial: 1` forces one host to finish the entire task file before the
  # next starts, removing that race by construction.
  #
  # NOT fully resolved by this (finding #4): with `serial: 1` and no
  # explicit `order:`, hosts are processed in inventory order -- vm1 before
  # vm2 in hosts.ini, which is *not* the same as "secondary before primary"
  # (whichever replica is PRIMARY varies after failovers, as this whole
  # series has shown). `DROP AVAILABILITY GROUP` has only ever been tested
  # live against a SECONDARY. If you want to control the order for a real
  # run, invoke this playbook directly with an explicit `--limit
  # <secondary>,<primary>` (checked via ag-status first) instead of calling
  # it through the API, which always targets `mssql_servers` with no
  # ordering control. Confirm live which order is actually safe before
  # trusting this against a genuinely important AG.
  serial: 1

  pre_tasks:
    - name: Check MSSQL connectivity before teardown
      shell: |
        {{ mssql_tools_path | default('/opt/mssql-tools/bin') }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -Q "SELECT 1"
      register: connectivity_check
      retries: 5
      delay: 5
      until: connectivity_check.rc == 0
      changed_when: false
      failed_when: false
      tags:
        - teardown

  tasks:
    - name: Run teardown tasks
      include_role:
        name: mssql
        tasks_from: teardown.yml
      when: connectivity_check.rc == 0
      tags:
        - teardown
```

The connectivity gate makes it safe to call `/deploy/teardown` on a host where
MSSQL isn't even running (e.g. already torn down) — it skips instead of erroring.

### 4. New: `python-fastapi-mssql/ansible/playbooks/uninstall.yml`

```yaml
---
- name: Remove MSSQL entirely and return host to a bare VM
  hosts: mssql_servers
  become: yes
  gather_facts: yes

  tasks:
    - name: Run uninstall tasks
      include_role:
        name: mssql
        tasks_from: uninstall.yml
      tags:
        - uninstall
```

### 5. Edit: `python-fastapi-mssql/app/deployer.py`

**Fixes finding #1 first — extend the existing concurrency guard.**
`AG_MUTATING_OPERATIONS` and `ag_operation_in_progress()` already exist on
`AnsibleMssqlDeployer` (added in the failover guide's step 7a, and live in
the real `app/deployer.py`). Add the three new operation names to that
existing tuple — don't create a second guard:

```python
# was: AG_MUTATING_OPERATIONS = ("failover", "sync-rebuild", "alwayson", "full-ag")
AG_MUTATING_OPERATIONS = ("failover", "sync-rebuild", "alwayson", "full-ag", "teardown", "rewind", "reset-baseline")
```

**Fixes finding #5 — `reset-baseline` chains `teardown.yml` first.** The
original plan called `uninstall.yml` directly, contradicting
`uninstall.yml`'s own header comment ("run teardown.yml first if an AG/
database might still exist"). `teardown.yml` is safe to call even when
there's nothing to tear down (every step is `IF EXISTS`/idempotent), so
chaining it unconditionally costs nothing on an already-clean host and
avoids stopping `mssql-server` mid-HADR-session on one that isn't clean.

Add these methods to `AnsibleMssqlDeployer` (near `deploy_build`), reusing the
existing `SequenceStepError` pattern from `_run_full_ag_sequence`:

```python
def deploy_teardown(self, task_id: str) -> None:
    self._run_task(task_id, lambda: self.ansible.run_playbook("teardown.yml", extra_vars=self._build_extra_vars()))

def deploy_reset_baseline(self, task_id: str) -> None:
    self._run_task(task_id, self._run_reset_baseline_sequence)

def _run_reset_baseline_sequence(self) -> Dict[str, object]:
    results: Dict[str, object] = {}
    results["teardown"] = self.ansible.run_playbook("teardown.yml", extra_vars=self._build_extra_vars())
    if not results["teardown"]["success"]:
        raise SequenceStepError("teardown step failed; see results.teardown for details", results)

    results["uninstall"] = self.ansible.run_playbook("uninstall.yml", extra_vars=self._build_extra_vars())
    if not results["uninstall"]["success"]:
        raise SequenceStepError("uninstall step failed; see results.uninstall for details", results)

    return results

def deploy_rewind(self, task_id: str) -> None:
    self._run_task(task_id, self._run_rewind_sequence)

def _run_rewind_sequence(self) -> Dict[str, object]:
    results: Dict[str, object] = {}
    results["teardown"] = self.ansible.run_playbook("teardown.yml", extra_vars=self._build_extra_vars())
    if not results["teardown"]["success"]:
        raise SequenceStepError("teardown step failed; see results.teardown for details", results)

    results["reinstall_vm1"] = self.ansible.run_playbook(
        "site.yml",
        limit="vm1",
        extra_vars=self._build_extra_vars(),
    )
    if not results["reinstall_vm1"]["success"]:
        raise SequenceStepError("reinstall_vm1 step failed; see results.reinstall_vm1 for details", results)

    return results

def get_rewind_plan(self) -> Dict[str, object]:
    """Static description of each destructive playbook -- not a live dry-run,
    since these are shell/sqlcmd tasks that Ansible --check can't safely simulate."""
    return {
        "note": "Describes what each playbook does; not a live check-mode run.",
        "teardown": {
            "playbook": "teardown.yml",
            "endpoint": "POST /api/v1/deploy/teardown",
            "leaves_mssql_installed": True,
            "steps": [
                "Drop the Availability Group on both replicas (independently, CLUSTER_TYPE=NONE)",
                "Take AdventureWorks out of HADR if still flagged",
                "Drop the AdventureWorks database on both replicas",
                "Drop the Always On endpoint and AG certificate on both replicas",
                "Drop the database master key",
                "Remove AG certificate files, striped backups, seed backups, and the downloaded AdventureWorks2019.bak",
                "Clear the controller-side backup/cert relay directories",
            ],
        },
        "rewind": {
            "playbooks": ["teardown.yml", "site.yml (limit vm1)"],
            "endpoint": "POST /api/v1/deploy/rewind",
            "leaves_mssql_installed": True,
            "steps": [
                "Everything in teardown, then",
                "Re-run site.yml against vm1 only: reconfirm config and restore a fresh AdventureWorks",
                "Leaves vm1 with a clean AdventureWorks and no AG -- ready to retry backup/restore/alwayson",
            ],
        },
        "reset-baseline": {
            "playbooks": ["teardown.yml", "uninstall.yml"],
            "endpoint": "POST /api/v1/deploy/reset-baseline",
            "leaves_mssql_installed": False,
            "steps": [
                "Teardown first (safe no-op if already clean): drop the AG, AdventureWorks, and backup artifacts",
                "Stop mssql-server",
                "Remove mssql-server and mssql-tools packages and their yum repos",
                "Delete /var/opt/mssql, data_dir, log_dir, backup_dir",
                "Clear controller-side relay directories",
                "Host returns to a bare VM -- call POST /api/v1/deploy/install to rebuild",
            ],
        },
    }
```

### 6. Edit: `python-fastapi-mssql/app/routes/deploy.py`

Add four routes (same try/except/logging shape as the existing ones).
**Fixes finding #1**: `teardown`, `rewind`, and `reset-baseline` each get the
same `ag_operation_in_progress()` 409 check the failover guide's step 7a
added to `/failover`/`/sync-rebuild`/`/alwayson`/`/full-ag` — reuse that
existing helper, don't write a new one. `/rewind-plan` deliberately does
**not** get this check — it's read-only, same reasoning as `/ag-status`.

```python
@router.post("/teardown")
async def deploy_teardown(background_tasks: BackgroundTasks):
    """Tear down the Always On AG, AdventureWorks, and backup artifacts.

    Leaves MSSQL installed and configured. Safe to re-run.
    """
    in_progress = deployer.ag_operation_in_progress()
    if in_progress:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Another AG-mutating operation ('{in_progress}') is already running -- "
                   f"wait for it to finish before starting a teardown.",
        )

    logger.info("Received deployment request - Teardown")
    try:
        task_id = deployer.start_task("teardown")
        background_tasks.add_task(deployer.deploy_teardown, task_id)
        return {
            "status": "initiated",
            "task_id": task_id,
            "message": "Teardown started",
            "engine": "ansible",
            "playbook": "teardown.yml",
            "estimated_duration_minutes": 5,
        }
    except Exception as e:
        logger.error(f"Error initiating teardown: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to initiate teardown: {str(e)}")


@router.post("/rewind")
async def deploy_rewind(background_tasks: BackgroundTasks):
    """Tear down AG/AdventureWorks/backups, then restore a fresh AdventureWorks on vm1.

    Leaves the lab ready to retry backup/restore/alwayson from a clean baseline.
    """
    in_progress = deployer.ag_operation_in_progress()
    if in_progress:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Another AG-mutating operation ('{in_progress}') is already running -- "
                   f"wait for it to finish before starting a rewind.",
        )

    logger.info("Received deployment request - Rewind")
    try:
        task_id = deployer.start_task("rewind")
        background_tasks.add_task(deployer.deploy_rewind, task_id)
        return {
            "status": "initiated",
            "task_id": task_id,
            "message": "Rewind started",
            "engine": "ansible",
            "playbooks": ["teardown.yml", "site.yml"],
            "estimated_duration_minutes": 15,
        }
    except Exception as e:
        logger.error(f"Error initiating rewind: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to initiate rewind: {str(e)}")


@router.post("/reset-baseline")
async def deploy_reset_baseline(background_tasks: BackgroundTasks):
    """Uninstall MSSQL entirely and return both hosts to a bare VM.

    Does not reinstall -- call POST /api/v1/deploy/install afterward to rebuild.
    """
    in_progress = deployer.ag_operation_in_progress()
    if in_progress:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Another AG-mutating operation ('{in_progress}') is already running -- "
                   f"wait for it to finish before starting a reset-baseline.",
        )

    logger.info("Received deployment request - Reset baseline")
    try:
        task_id = deployer.start_task("reset-baseline")
        background_tasks.add_task(deployer.deploy_reset_baseline, task_id)
        return {
            "status": "initiated",
            "task_id": task_id,
            "message": "Reset to bare-VM baseline started",
            "engine": "ansible",
            "playbooks": ["teardown.yml", "uninstall.yml"],
            "estimated_duration_minutes": 8,
        }
    except Exception as e:
        logger.error(f"Error initiating reset-baseline: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to initiate reset-baseline: {str(e)}")


@router.get("/rewind-plan")
async def get_rewind_plan():
    """Return the step-by-step plan for teardown/rewind/reset-baseline without executing anything."""
    try:
        return deployer.get_rewind_plan()
    except Exception as e:
        logger.error(f"Error retrieving rewind plan: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve rewind plan: {str(e)}")
```

### 7. Edit: `python-fastapi-mssql/tests/test_api.py`

Add a GET test (no side effects, safe in CI) and a mocked-sequencing test.
**Do not** add a test that calls `client.post("/api/v1/deploy/teardown")` (or
`/rewind`, `/reset-baseline`) directly — Starlette's `TestClient` runs
`BackgroundTasks` synchronously inside the request, so that would genuinely
shell out to `ansible-playbook` against the real inventory during `pytest`.
That's exactly why the existing suite never calls the other POST endpoints either.

```python
def test_rewind_plan_endpoint(client):
    """GET-only, no side effects, safe to call in CI."""
    response = client.get("/api/v1/deploy/rewind-plan")
    assert response.status_code == 200
    data = response.json()
    assert "teardown" in data and "rewind" in data and "reset-baseline" in data


def test_deploy_rewind_sequence_stops_on_teardown_failure(monkeypatch):
    """Rewind must not attempt site.yml if teardown itself fails."""
    from app.deployer import AnsibleMssqlDeployer, SequenceStepError

    deployer = AnsibleMssqlDeployer()
    calls = []

    def fake_run_playbook(playbook_name, tags=None, limit=None, extra_vars=None, skip_tags=None):
        calls.append(playbook_name)
        return {"success": False, "playbook": playbook_name, "stdout": "", "stderr": "boom"}

    monkeypatch.setattr(deployer.ansible, "run_playbook", fake_run_playbook)

    try:
        deployer._run_rewind_sequence()
        assert False, "expected SequenceStepError"
    except SequenceStepError:
        pass

    assert calls == ["teardown.yml"]


def test_deploy_reset_baseline_sequence_stops_on_teardown_failure(monkeypatch):
    """reset-baseline must not attempt uninstall if teardown itself fails --
    same shape as the rewind test above, for the sequence added to fix
    finding #5 (reset-baseline now chains teardown.yml first)."""
    from app.deployer import AnsibleMssqlDeployer, SequenceStepError

    deployer = AnsibleMssqlDeployer()
    calls = []

    def fake_run_playbook(playbook_name, tags=None, limit=None, extra_vars=None, skip_tags=None):
        calls.append(playbook_name)
        return {"success": False, "playbook": playbook_name, "stdout": "", "stderr": "boom"}

    monkeypatch.setattr(deployer.ansible, "run_playbook", fake_run_playbook)

    try:
        deployer._run_reset_baseline_sequence()
        assert False, "expected SequenceStepError"
    except SequenceStepError:
        pass

    assert calls == ["teardown.yml"]
```

### 8. Docs to update

- `python-fastapi-mssql/RUNBOOK.md` §7 — add the new automated one-liners
  (`curl -X POST .../deploy/reset-baseline`) above the existing manual SSH
  steps, keep the manual steps as a fallback.
- `python-fastapi-mssql/CHANGELOG.md` — new entry describing the teardown/rewind/reset-baseline addition, matching the style of the existing entries.

## Commands to run it yourself

All from `python-fastapi-mssql/` unless noted, on VM1 (the controller).

**1. Syntax-check the two new playbooks before touching real state:**
```bash
cd python-fastapi-mssql
ansible-playbook -i ansible/inventory/hosts.ini ansible/playbooks/teardown.yml --syntax-check
ansible-playbook -i ansible/inventory/hosts.ini ansible/playbooks/uninstall.yml --syntax-check
```

**2. Run the new pytest cases (pure/mocked, no real ansible-playbook calls):**
```bash
source .venv/bin/activate
pytest tests/test_api.py -v -k "rewind"
```

**3. Restart the API so the new routes register** (uvicorn `--reload` should pick up the file changes automatically, but if it doesn't):
```bash
# Ctrl+C the running uvicorn, then:
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**4. Exercise each endpoint individually and watch the log:**
```bash
curl http://localhost:8000/api/v1/deploy/rewind-plan | jq
curl -X POST http://localhost:8000/api/v1/deploy/teardown
tail -f logs/ansible.log        # watch it run
curl http://localhost:8000/api/v1/deploy/history | jq '.executions[0]'
```

**5. The real proof — reset to bare VM, then rebuild straight through with no manual fixes:**

This is the payoff: everything that needed hand-fixing during the first AG build
(directory ownership, `GO` terminators, tag-filter unreliability, `@@SERVERNAME`
vs. inventory hostname — see `CHANGELOG.md`) is now baked into the task files, so
a run against a genuinely bare VM should go straight through without SSHing in
to fix anything mid-run.

```bash
# Wipe both VMs back to bare state
curl -X POST http://localhost:8000/api/v1/deploy/reset-baseline
tail -f logs/ansible.log     # wait for it to finish; check history for status=success
curl http://localhost:8000/api/v1/deploy/history | jq '.executions[0]'

# Rebuild everything in one call: restore AdventureWorks on vm1, stripe+restore to vm2, wire up AG
curl -X POST http://localhost:8000/api/v1/deploy/full-ag
tail -f logs/ansible.log
curl http://localhost:8000/api/v1/deploy/history | jq '.executions[0]'
```

**6. Independently verify the AG is healthy** (don't just trust the playbook's own output — same discipline the original build used):
```bash
/opt/mssql-tools/bin/sqlcmd -S localhost -U SA -P '<sa_password>' -h -1 -W -Q \
  "SELECT ar.replica_server_name, ars.role_desc, ars.synchronization_health_desc FROM sys.dm_hadr_availability_replica_states ars JOIN sys.availability_replicas ar ON ar.replica_id = ars.replica_id"
```
Expect `devops_VM1 PRIMARY HEALTHY` and `devops_VM2 SECONDARY HEALTHY`.

**7. Practice a mid-cycle rewind** (tear down AG only, keep MSSQL installed, retry from a clean AdventureWorks on vm1).

**Fixes finding #2** — the earlier version of this section fired `rewind`,
`backup`, and `alwayson` as three bare `curl` calls with nothing between
them. `rewind` can run for several minutes; firing `backup` before it's
done is the same double-submit hazard finding #1's 409 guard exists to
catch — but *hitting* that 409 here just means you didn't wait long enough,
not that anything's broken. Wait for each step to actually reach
`status: success` in `/history` before firing the next one:

```bash
curl -X POST http://localhost:8000/api/v1/deploy/rewind
# wait for it to finish -- poll /history instead of guessing a sleep duration
while [ "$(curl -s http://localhost:8000/api/v1/deploy/history | jq -r '.executions[0].status')" = "running" ]; do
  sleep 5
done
curl -s http://localhost:8000/api/v1/deploy/history | jq '.executions[0].status'   # expect "success"

curl -X POST http://localhost:8000/api/v1/deploy/backup
while [ "$(curl -s http://localhost:8000/api/v1/deploy/history | jq -r '.executions[0].status')" = "running" ]; do
  sleep 5
done
curl -s http://localhost:8000/api/v1/deploy/history | jq '.executions[0].status'

curl -X POST http://localhost:8000/api/v1/deploy/alwayson
```
Same wait-then-check pattern applies to step 5's `reset-baseline` →
`full-ag` sequence above — the comments there already say to wait; this is
what "wait" concretely looks like instead of eyeballing `tail -f`.

## Live-testing plan (staged)

Written before any of this was run against the real VMs (2026-08-31) — a
deliberate order for validating all six fixes from "Pre-implementation
review findings" without ending up in a state that needs another manual
recovery ordeal if something surprises us. Each stage names which fix(es)
it exercises, for traceability back to that table. Total budget if run
straight through: roughly 35–45 minutes, stages B–E genuinely
destructive/rebuilding in sequence — see the Live-testing findings section
below (once it exists) for what actually happened.

**Stage A — concurrency guard, cheap and low-risk (~1 min). Validates
finding #1.**
```bash
curl -X POST http://localhost:8000/api/v1/deploy/reset-baseline
# immediately, no delay:
curl -i -X POST http://localhost:8000/api/v1/deploy/reset-baseline
```
Expect: first call returns `200`/`"initiated"`. Second call returns `409`
with `"Another AG-mutating operation ('reset-baseline') is already
running..."`. `reset-baseline` is the best target for this specifically —
it now runs for several minutes (teardown+uninstall chained), giving a
wide, reliable window, unlike `/teardown` alone which might finish before a
second call lands. This also kicks off the real teardown+uninstall used by
Stage C below, so the wait isn't wasted.

**Stage B — teardown correctness, against the live healthy AG (~2 min).
Validates findings #3, #6; first live data point on the still-open #4.**

Before anything: snapshot current state via `ag-status`, independently
(not trusting playbook output — same discipline used throughout this whole
series).
```bash
curl -X POST http://localhost:8000/api/v1/deploy/ag-status
curl -s http://localhost:8000/api/v1/deploy/history | jq '.executions[0].results'
```
Then:
```bash
curl -X POST http://localhost:8000/api/v1/deploy/teardown
tail -f logs/ansible.log
```
Watch the log for two things:
1. Does "Drop Availability Group" run *all* of vm1's tasks before vm2
   starts, rather than interleaved — proves `serial: 1` is doing its job
   (**#3**).
2. Does dropping the AG on whichever replica is currently PRIMARY (vm1,
   processed first under `serial: 1` + inventory order) complete cleanly
   with no surprise error — the still-open question (**#4**); record what
   actually happens here either way.

Independently verify via `sqlcmd` (not the playbook's own claim) that
`sys.availability_groups` is empty and `AdventureWorks` is gone on both
VMs. Then **re-run teardown immediately**:
```bash
curl -X POST http://localhost:8000/api/v1/deploy/teardown
```
Everything should now be a fast no-op — specifically check "Drop
AdventureWorks database" reports `changed: false` this time (it couldn't
do that correctly before this fix — **#6**), confirming the idempotency
claim actually holds now.

**Stage C — `reset-baseline` chaining, using Stage A's call (~5–8 min).
Validates finding #5.**

Stage A's `reset-baseline` call is still running (or has finished) by now.
Confirm it actually ran `teardown.yml` first — should show a fast,
mostly-no-op teardown pass (Stage B already tore everything down) before
`uninstall.yml` does the real work:
```bash
while [ "$(curl -s http://localhost:8000/api/v1/deploy/history | jq -r '.executions[0].status')" = "running" ]; do
  sleep 10
done
curl -s http://localhost:8000/api/v1/deploy/history | jq '.executions[0]'
```
Independently verify `systemctl status mssql-server` reports the unit gone
on both VMs and `/var/opt/mssql` no longer exists.

**Stage D — full rebuild from bare VM (~15–20 min). The guide's original
"real proof," now exercised with all six fixes in place.**
```bash
curl -X POST http://localhost:8000/api/v1/deploy/full-ag
while [ "$(curl -s http://localhost:8000/api/v1/deploy/history | jq -r '.executions[0].status')" = "running" ]; do
  sleep 15
done
curl -s http://localhost:8000/api/v1/deploy/history | jq '.executions[0].status'
```
Independently verify `devops_VM1 PRIMARY/HEALTHY`, `devops_VM2
SECONDARY/HEALTHY`, `AdventureWorks SYNCHRONIZED` on both, via `sqlcmd`
directly, not the playbook's own output.

**Stage E — rewind, against the now-healthy AG (~10 min).**
```bash
curl -X POST http://localhost:8000/api/v1/deploy/rewind
while [ "$(curl -s http://localhost:8000/api/v1/deploy/history | jq -r '.executions[0].status')" = "running" ]; do
  sleep 10
done
```
Verify vm1 has a fresh standalone `AdventureWorks` and no AG, and vm2 has
MSSQL installed but no database/AG (rewind only reinstalls vm1, by
design). Then complete the mid-cycle-rewind drill using the wait-pattern
from "Commands to run it yourself" §7 (**#2**) rather than firing calls
back to back:
```bash
curl -X POST http://localhost:8000/api/v1/deploy/backup
while [ "$(curl -s http://localhost:8000/api/v1/deploy/history | jq -r '.executions[0].status')" = "running" ]; do
  sleep 5
done
curl -X POST http://localhost:8000/api/v1/deploy/alwayson
while [ "$(curl -s http://localhost:8000/api/v1/deploy/history | jq -r '.executions[0].status')" = "running" ]; do
  sleep 10
done
```
Verify healthy again, same independent `sqlcmd` check as Stage D.

**Stage F — optional, lower priority. A second data point on the
still-open #4.**

If closing out finding #4 matters more than session time budget: deliberately
fail vm2 to primary first (`POST /failover?target=vm2&mode=planned`), then
run `/teardown` again and compare whether dropping the AG from
vm2-as-primary (still processed *first* under `serial: 1`, since inventory
order doesn't track current role) behaves any differently than Stage B's
vm1-as-primary case. Skippable — leave #4 flagged rather than force this if
time/risk budget is tight.

## Live-testing findings

**2026-09-12 — ran the staged plan above against the real VMs. Stages A–E
executed (F skipped, per its own "optional" note). Found one confirmed
security-relevant gap in the fixes from the pre-implementation review, plus
three entirely new, previously-undiscovered bugs unrelated to that review —
all four required manual intervention to get past. End state: fully
healthy AG, confirmed independently. Read this whole section before
re-running any of this against a real environment — several of these will
bite again unless fixed.**

### Stage A — the concurrency guard (fix #1) does not actually work

Fired two `POST /reset-baseline` calls back to back, no delay between them
(`curl ...; curl ...` in the same shell command). **Both returned `200`/
`"initiated"`** — the 409 guard did not fire. `ps aux` confirmed four
`ansible-playbook` processes running concurrently (two separate
`reset-baseline` sequences, each running `teardown.yml` against both VMs
at once).

**Root cause:** `ag_operation_in_progress()` only treats a task as
"in progress" when its status is `"running"`. But `start_task()` records a
new task with status `"queued"` — not `"running"` — and status only flips
to `"running"` later, inside `_run_task()`, which doesn't execute until
*after* the HTTP response has been sent (that's how FastAPI's
`BackgroundTasks` work) and the `ansible-playbook` subprocess has actually
been spawned. That gap — observed here as roughly half a second to over a
second, dominated by subprocess spawn overhead — is a real window where a
second request sees no `"running"` task yet and sails straight through the
guard. The fix from the pre-implementation review reduced the window
compared to no guard at all, but did not close it.

**What actually happened once the race was let run:**
- On vm1 (`PRIMARY` at the time): two concurrent `DROP AVAILABILITY GROUP`
  calls landed almost simultaneously. One succeeded; the other got `Msg
  15151: Cannot drop the availability group 'AG1', because it does not
  exist` a fraction of a second later — harmless, since the first call had
  already removed it.
- On vm2 (`SECONDARY` at the time): the two concurrent `DROP AVAILABILITY
  GROUP` calls did **not** resolve as fast or as cleanly — one calls took
  **23 seconds** to return and then failed with a different, more specific
  error: `Msg 41156: Cannot drop availability group 'AG1' from this
  instance of SQL Server. The availability group is either being dropped,
  or the local availability replica is being removed... Wait for the
  current operation to complete, then retry.` SQL Server itself detected
  and serialized the concurrent operation rather than corrupting anything
  — but this is a first real data point for finding #4 (dropping the AG
  under concurrency behaves differently, timing- and error-wise, depending
  on which replica's role it's targeting — though in both cases SQL Server
  protected itself rather than corrupting state).
- Both `uninstall.yml` runs then raced on **OS package removal** — a real
  `dnf`/`rpm` transaction failure, not a SQL Server issue:
  `_rpm.error: package not installed` from inside the `dnf` module,
  because one process's package-removal transaction was still in-flight
  when the other process's removal of the *same already-gone* package hit
  a hard error instead of a graceful no-op. This is a genuinely new
  finding: concurrent `uninstall.yml` runs against the same host are
  **not safely idempotent under concurrency**, even though a single serial
  run's `state: absent` tasks are.
- **Both API calls ended with `status: "failed"`** in `/history` — but
  independently checking both VMs afterward (`rpm -q`, `systemctl status`,
  `ls /var/opt/mssql`, `ls /backup`) showed **everything was actually torn
  down correctly on both hosts** — packages gone, directories gone, service
  unit gone, controller relay dirs gone. This happened by luck: between
  the two racing processes, every host ended up having its removal "won"
  by exactly one of the two — but the task ID you'd actually be looking at
  in `/history` says `"failed"`, which is actively misleading. **Do not
  trust a single task's reported status under this race — independently
  verify host state**, exactly the discipline this whole series has used
  throughout.

**Recommended fix, not yet applied:** change `ag_operation_in_progress()`
to treat `status in ("queued", "running")` as in-progress, not just
`"running"`. `start_task()` records `"queued"` synchronously, inside the
same request handler that performs the check — since asyncio is
single-threaded and there's no `await` between the check and
`start_task()` within one request, this closes the race for the
back-to-back-curl case tested here. (It would not necessarily close every
conceivable timing window under a truly adversarial client, but it removes
the specific, easily-triggered gap found here.)

### New bug #1 (unrelated to the review) — `install.yml`'s "already
configured" check is broken on a genuinely fresh VM

Hit independently on **both** vm1 and vm2. After `mssql-server` installs
via `yum`/`dnf`, its own RPM postinstall scriptlet automatically runs
`/opt/mssql/bin/mssql-conf welcome engine` whenever no master database
file exists yet (confirmed by reading the package's own postinstall
scriptlet with `rpm -q --scripts mssql-server`). This Microsoft-shipped
side effect creates `/var/opt/mssql/mssql.conf` (observed content: just
`[sqlagent]\nenabled = false`) **without** accepting the EULA or setting
the SA password. `install.yml`'s "Check whether MSSQL has already been
configured" task tests for exactly that file's existence
(`mssql_config.stat.exists`) to decide whether to run "Run MSSQL
setup/configuration" (`mssql-conf -n setup accept-eula`, the step that
actually persists EULA acceptance and sets the SA password). Since the
file already exists — created moments earlier by the package itself, not
by a completed setup — that guard incorrectly concludes setup already
happened and **skips it entirely**. Every subsequent `sqlservr` start then
exits immediately with `The SQL Server End-User License Agreement (EULA)
must be accepted before SQL...`.

This had never been discovered before because this is, as far as this
project's history shows, the first time `install.yml` has been run against
a *genuinely* from-scratch VM in one shot — every earlier build in this
project's history was either iteratively hand-fixed as it went, or ran
against a host with pre-existing partial state.

**Manual recovery performed (both VMs, identical steps):**
```bash
sudo systemctl stop mssql-server
sudo MSSQL_SA_PASSWORD='<sa_password>' MSSQL_PID='Developer' /opt/mssql/bin/mssql-conf -n setup accept-eula
sudo systemctl reset-failed mssql-server   # needed on vm2 specifically -- see below
sudo systemctl start mssql-server
```
The `reset-failed` step was necessary on vm2 (not vm1) because `install.yml`'s
own "Wait for SQL Server to start" retry loop had already caused several
failed start attempts, which tripped systemd's restart-limiter
(`StartLimitBurst=3` within `StartLimitIntervalUSec=2min`, visible in the
unit's own `systemctl show` output) — once tripped, even a `mssql-conf
setup` that itself tries to restart the service fails with `Start request
repeated too quickly` until the failed-state counter is explicitly reset.

**Recommended fix, not yet applied:** change the "already configured"
guard to check for the actual master data file (e.g.
`{{ data_dir }}/master.mdf`) — mirroring exactly what the RPM's own
postinstall scriptlet checks — instead of `mssql.conf`'s mere existence.
Simpler alternative: drop the guard entirely and always run `mssql-conf -n
setup accept-eula` unconditionally; Microsoft documents this command as
safe to re-run.

### New bug #2 (unrelated to the review) — missing `ansible.posix`
collection breaks `restore.yml`'s VM1→controller fetch step

`ansible-galaxy collection list` showed **no collections installed at
all** in this environment. `restore.yml`'s "Fetch backup files from VM1"
task uses the `synchronize` module, which ships in the separate
`ansible.posix` collection, not ansible-core — so the very first attempt
at `full-ag` (after the EULA bug above was fixed on vm1) failed at
playbook-parse time: `ERROR! couldn't resolve module/action 'synchronize'`.
This is a missing environment dependency, not a logic bug in the task file
itself, but it means this exact task had apparently never been
successfully exercised in this environment before.

**Fix applied (environment-level, not a code change):**
```bash
ansible-galaxy collection install ansible.posix
```
Installed cleanly (v2.2.2). `rsync` itself was already present on both
VMs (`which rsync` confirmed on both), so nothing else was needed. One
informational warning appeared on the next run and can be ignored:
`[WARNING]: Collection ansible.posix does not support Ansible version
2.13.13`.

**Recommended follow-up, not yet applied:** add `ansible.posix` to a
`requirements.yml` (or document the `ansible-galaxy collection install`
step) in the setup docs, so a fresh controller doesn't silently lack it.

### New bug #3 (unrelated to the review, but exposed by Stage A's fallout)
— `reset-baseline` → `full-ag` is not actually a complete rebuild sequence
once vm2 has also been wiped

Because Stage A's race uninstalled MSSQL on **both** VMs (not just the one
`reset-baseline` "officially" targets, since both racing sequences ran
`uninstall.yml` against `mssql_servers` — both hosts, by design), retrying
`full-ag` afterward failed: `_run_full_ag_sequence` only runs `site.yml`
with `-l vm1` (per its existing, documented design — see `CLAUDE.md`) — it
never reinstalls MSSQL on vm2 at all. With vm2 genuinely bare, the restore
step failed outright: `/bin/sh: /opt/mssql-tools/bin/sqlcmd: No such file
or directory` (`rc=127`) — vm2 had no `mssql-tools` package to even find
`sqlcmd` with.

This is not a bug in `full-ag`'s existing design so much as a gap in the
**documented recovery sequence**: the guide's own "Commands to run it
yourself" §5 goes straight from `reset-baseline` to `full-ag` with nothing
in between, which is only valid if vm2 was never actually wiped (true for
a single, non-racing `reset-baseline`, but not true here, and not
guaranteed in general if vm2 ever ends up needing a from-scratch rebuild
too).

**Fix applied to unblock the test (also the correct general recovery
step):**
```bash
curl -X POST http://localhost:8000/api/v1/deploy/install   # site.yml, unlimited -- both hosts
```
This installs MSSQL on both VMs (and, since it's `site.yml` unlimited, ran
straight into the *same* EULA bug on vm2 that vm1 already hit — fixed with
the identical manual recovery steps above). After that, `full-ag` was
retried and succeeded cleanly end to end.

**Recommended follow-up:** document `POST /install` as a required step
before `full-ag` whenever there's any chance vm2 was also wiped (not just
after a normal single `reset-baseline`, which never touches vm2 by
"official" single-call design, but does after this kind of race, or after
a manual uninstall of vm2 for any other reason).

### Confirming what worked as designed

Once all four blockers above were cleared, the rest of the review's fixes
behaved exactly as intended:
- **Fix #5** (reset-baseline chains `teardown.yml` before `uninstall.yml`)
  worked correctly in both racing sequences — confirmed from the log that
  each process ran `teardown.yml` to completion before starting
  `uninstall.yml`.
- **Fix #3** (`serial: 1` on the teardown playbook) correctly serialized
  vm1-then-vm2 *within* each individual `ansible-playbook` process — the
  race in Stage A was two *separate* processes overlapping each other, a
  distinct, already-documented limitation of `serial: 1` (it can't
  serialize across concurrent invocations of the playbook, only across
  hosts within one invocation), not a failure of the fix itself.
- **Fix #6** (`aw_exists_check` split from the drop) — the "Drop
  AdventureWorks database" task correctly reported `changed: false` on
  hosts where nothing needed dropping during this run.
- **Fix #4** remains formally open (no code change was proposed for it),
  but this session added real data: dropping the AG concurrently on the
  then-`PRIMARY` (vm1) resolved almost instantly with a simple "doesn't
  exist" error, while doing the same on the then-`SECONDARY` (vm2) took 23
  seconds and returned a distinct "operation already in progress, retry"
  error — different timing and error text, but SQL Server protected
  itself against corruption in both cases.
- **Stage B** (an isolated, clean single-`teardown`-then-idempotent-rerun
  test) was effectively superseded by Stage A's race tearing everything
  down first — the plan's intended clean isolation between stages didn't
  survive contact with a real, unfixed concurrency bug. Worth re-running
  in isolation later if a clean read on `teardown.yml` alone (with no
  other AG-mutating activity anywhere nearby) is wanted.

### Final state — confirmed healthy

After `full-ag` (Stage D) and then `rewind` → `backup` → `alwayson` (Stage
E, using the wait-for-`/history`-success discipline from fix #2 between
each call), independently verified via `sqlcmd` (not the playbooks' own
claims):
```
devops_VM1  PRIMARY    ONLINE   CONNECTED  HEALTHY
devops_VM2  SECONDARY  (n/a)    CONNECTED  HEALTHY
AdventureWorks  SYNCHRONIZED  (both replicas), is_suspended = 0 (both)
```
Stage F was skipped, per its own note in the plan (optional, lower
priority than the other findings this run already surfaced).

## Fixes required from live testing (applied 2026-09-12)

Consolidated, file-by-file, from the "Live-testing findings" section
above. **All four are now applied** — fixes 1–3 exactly as written below,
fix 4 with Option A (doc-only). Kept here, updated in place rather than
removed, as the record of what changed and why for anyone reading this
guide later.

### 1. `python-fastapi-mssql/app/deployer.py` — close the concurrency-guard race

`ag_operation_in_progress()` currently only treats a task as in-progress
once its status is `"running"` — but `start_task()` records a new task as
`"queued"` first, and status doesn't flip to `"running"` until the
background task actually starts (after the HTTP response is already sent
and the `ansible-playbook` subprocess has been spawned). That gap is what
let two `reset-baseline` calls both through in Stage A.

```python
# current (app/deployer.py:55-61)
def ag_operation_in_progress(self) -> Optional[str]:
    """Operation name of a running AG-mutating task, or None if the AG is free to touch."""
    with self._lock:
        for task in self._history:
            if task["status"] == "running" and task["operation"].startswith(self.AG_MUTATING_OPERATIONS):
                return task["operation"]
    return None
```

```python
# fixed
def ag_operation_in_progress(self) -> Optional[str]:
    """Operation name of a queued-or-running AG-mutating task, or None if the AG is free to touch."""
    with self._lock:
        for task in self._history:
            if task["status"] in ("queued", "running") and task["operation"].startswith(self.AG_MUTATING_OPERATIONS):
                return task["operation"]
    return None
```
`start_task()` records `"queued"` synchronously, inside the same request
handler that calls this check — since there's no `await` between the two
calls, asyncio's cooperative scheduling means a single request can't be
interrupted mid-way, so checking `"queued"` here closes the specific race
observed in Stage A. (A truly adversarial client hammering the endpoint
in a tight loop could still find some edge case — this closes the gap that
was actually found, not every conceivable one.)

### 2. `python-fastapi-mssql/ansible/roles/mssql/tasks/install.yml` — fix the "already configured" guard

The RPM's own postinstall scriptlet runs `mssql-conf welcome engine` on a
genuinely fresh install (confirmed via `rpm -q --scripts mssql-server`),
which creates `/var/opt/mssql/mssql.conf` as a side effect — without
accepting the EULA or setting the SA password. The current guard checks
exactly that file's existence, so it wrongly concludes setup already ran
and skips the step that actually does the real setup.

```yaml
# current (ansible/roles/mssql/tasks/install.yml:67-73)
- name: Check whether MSSQL has already been configured
  stat:
    path: /var/opt/mssql/mssql.conf
  register: mssql_config
  tags:
    - install
    - setup
```

```yaml
# fixed -- check for the master data file instead, mirroring exactly what
# the RPM's own postinstall scriptlet checks for before deciding whether
# to run `mssql-conf welcome engine` in the first place
- name: Check whether MSSQL has already been configured
  stat:
    path: "{{ data_dir }}/master.mdf"
  register: mssql_config
  tags:
    - install
    - setup
```
The downstream task ("Run MSSQL setup/configuration") already keys off
`when: not mssql_config.stat.exists` — no change needed there, just what
`mssql_config` actually points at. Simpler alternative, if a "belt and
suspenders" idempotency check isn't wanted at all: delete both the check
task and the `when:` condition, and always run `mssql-conf -n setup
accept-eula` unconditionally (Microsoft documents this as safe to re-run).

### 3. New file: `python-fastapi-mssql/ansible/requirements.yml` — declare the missing collection dependency

`restore.yml`'s "Fetch backup files from VM1" task uses the `synchronize`
module, which ships in the `ansible.posix` collection, not ansible-core.
Nothing in this repo currently declares that dependency, so a fresh
controller setup silently lacks it until `full-ag` hits `ERROR! couldn't
resolve module/action 'synchronize'` — exactly what happened here.

```yaml
# new file: python-fastapi-mssql/ansible/requirements.yml
---
collections:
  - name: ansible.posix
    version: ">=1.5.0"
```
And add the install step to whichever setup doc currently covers first-time
controller setup (`RUNBOOK.md` / `SETUP_GUIDE.md`):
```bash
ansible-galaxy collection install -r ansible/requirements.yml
```
`rsync` itself doesn't need a doc change — it was already present on both
VMs in this environment, but worth a one-line mention as a prerequisite
alongside the collection, since `synchronize` needs it on both ends.

### 4. `python-fastapi-mssql/app/deployer.py` — `full-ag` needs vm2 to already have MSSQL installed, and nothing currently guarantees that

`_run_full_ag_sequence` only ever runs `site.yml` with `limit="vm1"` — by
design, per the existing documented architecture, not a bug in itself.
But that means `full-ag` silently assumes vm2 already has MSSQL installed;
if it doesn't (as happened here after Stage A's race wiped both VMs), the
restore step fails with a bare `sqlcmd: No such file or directory`
(`rc=127`) — a confusing error for what's really a missing-prerequisite
problem, not a real backup/restore failure.

**Applied: Option A (doc-only, no code change).** `_run_full_ag_sequence`
is untouched. `python-fastapi-mssql/RUNBOOK.md` §7 now explicitly says to
call `POST /deploy/install` (unlimited, both hosts) before `full-ag`
whenever there's any chance vm2 has been wiped, with the wait-for-success
pattern shown inline. Zero code risk — relies on the caller remembering,
which is the tradeoff explicitly accepted here over Option B's added
complexity and untested edge case (see below for what Option B would have
needed).

**Option B (code fix, more invasive, not applied):** would have added a
preliminary step to `_run_full_ag_sequence` that ensures vm2 has MSSQL
installed before `backup_restore_vm2` runs — e.g. running `site.yml`
unlimited (both hosts) as the first step instead of `limit="vm1"` only.
**Why this was passed over:** `adventureworks.yml` (which `site.yml`
includes) has no guard for "is this database already AG-owned" — it
unconditionally runs `RESTORE DATABASE ... REPLACE`. If vm2 ever has a
genuinely broken *but still AG-joined* AdventureWorks (as opposed to fully
wiped, the case actually hit here), running `site.yml` unlimited could
attempt to restore directly over an AG-owned database and fail in a new,
not-yet-tested way. Left here for reference in case Option A's reliance on
the caller remembering turns out to be a recurring pain point — revisit
then, with its own deliberate test for the partially-broken-vm2 case
first.

## Streamlined retests (2026-09-12) — confirming the fixes without a full rebuild

Re-running the whole Stage A–E plan just to re-confirm four already-
understood fixes would cost another ~20+ minutes and tear the AG down
again for no new information. Instead, each fix was re-checked with the
narrowest test that actually exercises its specific mechanism — all four
completed in well under a minute combined, and **the AG was never touched
throughout**: confirmed `devops_VM1 PRIMARY/HEALTHY`,
`devops_VM2 SECONDARY/HEALTHY` immediately before and immediately after.

**Fix 1 (concurrency guard) — unit-tested directly against the deployer
class, no HTTP, no subprocess, no VM:**
```python
from app.deployer import AnsibleMssqlDeployer
d = AnsibleMssqlDeployer()
tid = d.start_task('teardown')          # mimics exactly what the route does
print(d.ag_operation_in_progress())     # -> 'teardown'
```
Result: `ag_operation_in_progress()` returned `'teardown'` immediately
after `start_task()`, while the task's status was still `"queued"` (never
even reached `"running"` — nothing was actually run). This is precisely
the race window Stage A exploited; the fixed check now closes it at the
exact point it used to leak through. A fresh `AnsibleMssqlDeployer()`
instance's in-memory `_history` is entirely separate from the live
`uvicorn` process's — confirmed the running app's `/history` still showed
`total_executions: 0` afterward, so this test had zero interaction with
the real app or VMs.

**Fix 2 (EULA guard) — asked Ansible's own `stat` module the exact
question `install.yml`'s fixed task now asks, against both live VMs, read-
only:**
```bash
ansible -i ansible/inventory/hosts.ini mssql_servers -b -m stat \
  -a "path=/var/opt/mssql/data/master.mdf"
```
Result: `exists: true` on both `vm1` and `vm2`. This proves the fixed
guard's condition (`{{ data_dir }}/master.mdf` existence) correctly reads
as "already configured" on hosts that are genuinely already configured —
the exact case the old `mssql.conf`-based check got right by accident
some of the time, and wrong specifically on a fresh install (the case that
actually broke). Re-triggering the *fresh-install* path for real still
requires an actual `reset-baseline` → `install` cycle — this check
confirms the fixed logic is sound on the currently-healthy hosts, not a
full end-to-end repeat of the original bug.

**Fix 3 (`ansible.posix` collection) — asked Ansible's own module resolver
directly, the same mechanism that produced `ERROR! couldn't resolve
module/action 'synchronize'` before:**
```bash
ansible-doc synchronize
```
Result: resolved cleanly to `ansible.posix.synchronize`, loaded from
`~/.ansible/collections/ansible_collections/ansible/posix`, with the same
informational (non-fatal) compatibility warning seen during the original
fix (`Collection ansible.posix does not support Ansible version
2.13.13`). Worth noting a dead end hit while looking for an even lighter
check: `ansible-playbook ... --list-tasks` does **not** expand
`include_role`'s children (it's a dynamic include, resolved at runtime,
not parse time) — it showed only the top-level `Include restore tasks
from role` task, not what's inside `restore.yml`, so it can't be used to
prove module resolution the way `--syntax-check` normally would for
static content. Also worth noting: `--tags transfer` (an earlier attempt
at scoping the check down) silently skipped the include entirely, because
the `include_role` task itself carries no tags — only `restore.yml`'s
tasks do — which is exactly the "`tags: always` on `include_tasks`/
`include_role` is unreliable for filtered runs" landmine already
documented in `CLAUDE.md`. `ansible-doc` sidesteps both problems by
checking module resolution directly, independent of any playbook
structure.

**Fix 4 (RUNBOOK doc change)** — nothing to execute; re-read
`python-fastapi-mssql/RUNBOOK.md` §7 to confirm the new guidance renders
correctly and sits in the right place (right after the `reset-baseline`
command block, before "Watch progress the same way..."). Confirmed.

**Bottom line:** all four fixes hold up under the narrowest test that
actually exercises each one's mechanism. None of the original bugs'
*triggering conditions* (a genuinely bare VM for fixes 2/3, an actual race
window under load for fix 1) were re-created here — that's the deliberate
trade-off of a streamlined retest. The full Stage A–E plan (or at least a
fresh `reset-baseline` → `install` → `full-ag` cycle) remains the only way
to see fixes 2 and 3 exercised end-to-end again; do that if these fixes
are ever touched again, rather than trusting the streamlined checks alone.

## Verification checklist

- [ ] `--syntax-check` passes on both new playbooks
- [ ] New pytest cases pass, no real `ansible-playbook` subprocess triggered by them
- [ ] `GET /rewind-plan` returns the three sections with no side effects
- [ ] `POST /teardown` on a host with an existing AG succeeds; re-running it immediately after (nothing left to tear down) also succeeds (idempotency)
- [ ] `POST /reset-baseline` leaves `systemctl status mssql-server` reporting the unit as not-found/inactive and `/var/opt/mssql` gone on both VMs
- [ ] `POST /full-ag` after `reset-baseline` reaches `SYNCHRONIZED`/`HEALTHY` on both replicas with no manual SSH intervention
- [ ] `POST /rewind` after a working AG leaves vm1 with a clean `AdventureWorks` and no AG, confirmed via `sqlcmd -Q "SELECT name FROM sys.availability_groups"` returning empty
- [ ] Firing `POST /teardown` (or `/rewind`, `/reset-baseline`) twice in quick succession — the double-submit finding #1 fixes — gets a `409` on the second call, not two concurrent `ansible-playbook` processes. Easiest way to check without real double-clicking: fire one, then immediately fire a second and confirm it returns `409` before the first has finished.
- [ ] Watch `teardown.yml`'s "Drop Availability Group" step specifically the first time it runs against a live AG — finding #4 is still open (never tested against whichever replica is currently PRIMARY). Note which replica was primary going in, and record here whether dropping it there behaved any differently than dropping it on a secondary.
