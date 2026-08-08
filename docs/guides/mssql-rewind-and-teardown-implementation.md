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

- name: Drop AdventureWorks database
  shell: |
    {{ mssql_tools_path }}/sqlcmd -S localhost -U SA -P "{{ sa_password }}" -Q "
    IF EXISTS (SELECT * FROM sys.databases WHERE name = 'AdventureWorks')
    BEGIN
      ALTER DATABASE AdventureWorks SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
      DROP DATABASE AdventureWorks;
    END
    "
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

Add these methods to `AnsibleMssqlDeployer` (near `deploy_build`), reusing the
existing `SequenceStepError` pattern from `_run_full_ag_sequence`:

```python
def deploy_teardown(self, task_id: str) -> None:
    self._run_task(task_id, lambda: self.ansible.run_playbook("teardown.yml", extra_vars=self._build_extra_vars()))

def deploy_reset_baseline(self, task_id: str) -> None:
    self._run_task(task_id, lambda: self.ansible.run_playbook("uninstall.yml", extra_vars=self._build_extra_vars()))

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
            "playbook": "uninstall.yml",
            "endpoint": "POST /api/v1/deploy/reset-baseline",
            "leaves_mssql_installed": False,
            "steps": [
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

Add four routes (same try/except/logging shape as the existing ones):

```python
@router.post("/teardown")
async def deploy_teardown(background_tasks: BackgroundTasks):
    """Tear down the Always On AG, AdventureWorks, and backup artifacts.

    Leaves MSSQL installed and configured. Safe to re-run.
    """
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
    logger.info("Received deployment request - Reset baseline")
    try:
        task_id = deployer.start_task("reset-baseline")
        background_tasks.add_task(deployer.deploy_reset_baseline, task_id)
        return {
            "status": "initiated",
            "task_id": task_id,
            "message": "Reset to bare-VM baseline started",
            "engine": "ansible",
            "playbook": "uninstall.yml",
            "estimated_duration_minutes": 5,
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

**7. Practice a mid-cycle rewind** (tear down AG only, keep MSSQL installed, retry from a clean AdventureWorks on vm1):
```bash
curl -X POST http://localhost:8000/api/v1/deploy/rewind
tail -f logs/ansible.log
curl -X POST http://localhost:8000/api/v1/deploy/backup
curl -X POST http://localhost:8000/api/v1/deploy/alwayson
```

## Verification checklist

- [ ] `--syntax-check` passes on both new playbooks
- [ ] New pytest cases pass, no real `ansible-playbook` subprocess triggered by them
- [ ] `GET /rewind-plan` returns the three sections with no side effects
- [ ] `POST /teardown` on a host with an existing AG succeeds; re-running it immediately after (nothing left to tear down) also succeeds (idempotency)
- [ ] `POST /reset-baseline` leaves `systemctl status mssql-server` reporting the unit as not-found/inactive and `/var/opt/mssql` gone on both VMs
- [ ] `POST /full-ag` after `reset-baseline` reaches `SYNCHRONIZED`/`HEALTHY` on both replicas with no manual SSH intervention
- [ ] `POST /rewind` after a working AG leaves vm1 with a clean `AdventureWorks` and no AG, confirmed via `sqlcmd -Q "SELECT name FROM sys.availability_groups"` returning empty
