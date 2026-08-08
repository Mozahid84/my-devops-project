# FastAPI MSSQL Ansible Integration Change Log

## Teardown, Rewind, and Reset-Baseline
Added a reverse path to complement the forward `install`/`backup`/`alwayson`/
`full-ag` flow, so the lab can be reset without SSHing in by hand: `POST
/api/v1/deploy/teardown`, `/rewind`, `/reset-baseline`, and `GET
/api/v1/deploy/rewind-plan`. Design and full code walkthrough in
`docs/guides/mssql-rewind-and-teardown-implementation.md`.

- `roles/mssql/tasks/teardown.yml` + `playbooks/teardown.yml`: drops the
  Availability Group independently on both replicas (`CLUSTER_TYPE=NONE` has
  no shared cluster state, so each node needs its own `DROP AVAILABILITY
  GROUP`), takes `AdventureWorks` out of HADR as a safety net, drops the
  database, drops the Always On endpoint/certificate/master key, removes the
  AG certificate files/striped backups/seed backups/downloaded
  `AdventureWorks2019.bak`, and clears the controller-side backup/cert relay
  directories. Every step is `IF EXISTS`/`state: absent`, so it's safe to
  call repeatedly or on a host with nothing to tear down. Leaves MSSQL
  installed and configured.
- `roles/mssql/tasks/uninstall.yml` + `playbooks/uninstall.yml`: deep wipe --
  stops `mssql-server`, removes the `mssql-server`/`mssql-tools` packages and
  their yum repos, deletes `/var/opt/mssql`, `data_dir`, `log_dir`,
  `backup_dir`, and clears the controller-side relay directories. Automates
  what `RUNBOOK.md` section 7 previously documented as manual SSH steps.
- `deployer.py`: added `deploy_teardown`, `deploy_reset_baseline`,
  `deploy_rewind` (chains `teardown.yml` then `site.yml -l vm1`, reusing the
  `SequenceStepError` pattern from `_run_full_ag_sequence` so a failed
  teardown stops the sequence instead of continuing into a reinstall), and
  `get_rewind_plan` (a static description of what each destructive playbook
  does -- not a live check-mode run, since these are `shell`/`sqlcmd` tasks
  Ansible `--check` can't safely simulate).
- Added `test_rewind_plan_endpoint` (GET-only, no side effects) and
  `test_deploy_rewind_sequence_stops_on_teardown_failure` (monkeypatches
  `AnsibleRunner.run_playbook` so it never shells out for real -- the
  existing suite deliberately never calls the other `POST` endpoints
  directly either, since Starlette's `TestClient` runs `BackgroundTasks`
  synchronously inside the request).
- Implemented and syntax-checked; not yet live-tested end-to-end against the
  lab VMs this session (no `teardown`/`uninstall` runs in `logs/ansible.log`
  yet). Next real verification step: `reset-baseline` -> `full-ag` from a
  bare VM and confirm it reaches `SYNCHRONIZED`/`HEALTHY` with no manual
  intervention, the same discipline used to verify the AG build below.

## Working Always On Availability Group (vm1 primary, vm2 secondary)
Completed and live-tested the full `full-ag` workflow end to end against the
lab VMs: download AdventureWorks -> restore on vm1 -> 10-stripe backup ->
transfer to vm2 -> restore on vm2 -> Always On AG pairing vm2 to vm1. The AG
now reaches `devops_VM1 PRIMARY HEALTHY` / `devops_VM2 SECONDARY HEALTHY`
with `AdventureWorks` `SYNCHRONIZED` on both replicas, verified independently
via direct `sqlcmd` queries (not just the playbook's own output).

Built as `CLUSTER_TYPE = NONE`, `FAILOVER_MODE = MANUAL` (Microsoft's
documented no-cluster-manager pattern for a 2-node AG) rather than
`CLUSTER_TYPE = EXTERNAL`/Pacemaker, since no cluster manager exists in this
lab. `roles/mssql/tasks/alwayson.yml` was rewritten to add: HADR enablement
at the engine level, a firewalld rule for the 5022 mirroring endpoint,
certificate-based endpoint authentication (generated once on vm1, relayed to
vm2 via the same fetch/copy controller-relay pattern `restore.yml` already
used for backups), a `CREATE AVAILABILITY GROUP` that actually declares
*both* replicas (the original only ever declared itself), automatic-seeding
grants, and a poll for synchronized state.

Getting this working end-to-end (not just passing `--syntax-check`) surfaced
several real bugs that static review had missed:
- `data_dir`/`log_dir`/`backup_dir` were owned `root:root`, so the `mssql`
  service account couldn't create new files there -- `RESTORE DATABASE` and
  `BACKUP DATABASE` both failed with OS error 5 (access denied). Fixed
  ownership in `configure.yml`/`backup.yml`/`restore.yml`.
- The `BACKUP DATABASE`/`RESTORE DATABASE` heredocs sent to `sqlcmd` were
  missing a `GO` batch terminator, so `sqlcmd` silently accepted the input
  and executed nothing (rc=0, no output, no error). Added `GO` to both.
- `tags: always` on `include_tasks` does not reliably force child tasks to
  run under a `--tags` filter on this Ansible version -- `deployer.py`'s
  `tags=["adventureworks"]` fast path silently skipped `configure.yml`
  entirely. Removed tag filtering from `restore_adventureworks`/
  `_run_full_ag_sequence`; they now run the full `site.yml` against vm1.
- `_run_full_ag_sequence` continued to the next playbook even when a prior
  one failed, and the outer task status always reported "success" regardless
  of playbook exit codes. Added `SequenceStepError` (carries partial results)
  so a failed step now stops the sequence and the task history reports
  `failed` with the real stdout/stderr attached.
- The certificate files copied to vm2 were owned `root:root` mode `0600`,
  unreadable by the `mssql` service account -- fixed ownership on copy.
- `ALTER DATABASE ... SET RECOVERY FULL` requires a fresh **full** backup
  before a log backup will succeed across the recovery-model switch; added
  one before the log backup.
- Two DMV queries referenced columns that don't exist on those views
  (`database_name` on `dm_hadr_database_replica_states`,
  `replica_server_name`/`synchronization_state_desc` on
  `dm_hadr_availability_replica_states`) -- fixed with joins to
  `sys.databases`/`sys.availability_replicas`.
- `CREATE AVAILABILITY GROUP ... REPLICA ON N'vm1'` used the Ansible
  inventory hostname, but SQL Server matches replicas by `@@SERVERNAME`
  (`devops_VM1`/`devops_VM2` here) -- switched to the `vmware_name` hostvar
  already defined in `inventory/hosts.ini`.

## MSSQL Build Workflow & Role De-duplication
- Added the `mssql_build` role and `playbooks/build.yml` playbook: a full
  idempotent SQL Server install flow (dirs, service account, repos,
  packages, `mssql-conf setup`, verification), exposed via the new
  `POST /api/v1/deploy/build` endpoint (`deployer.deploy_build`).
- Fixed an accidental role duplication: because Ansible resolves roles
  relative to the playbook's own directory and this project has no
  `ansible.cfg` `roles_path` override, `ansible/playbooks/roles/` had become
  a second physical copy of `ansible/roles/`. Replaced it with a symlink
  (`ansible/playbooks/roles -> ../roles`) so there is a single source of
  truth; verified with `ansible-playbook --syntax-check` against all four
  playbooks (`build.yml`, `site.yml`, `alwayson.yml`, `backup.yml`).
- Added `tags: always` to each `include_tasks` step in
  `roles/mssql/tasks/main.yml` so sub-task files aren't skipped when the
  role is invoked with tag filters from `alwayson.yml`/`backup.yml`.
- Reconciled stale docs: `roles/mssql_build/README.md` no longer describes
  the role as a placeholder skeleton, `DESIGN.md`'s stale
  "refactored to Paramiko" banner was removed, and `main.py`/`README.md`
  no longer describe the service as native-Python-SSH-based.

## Summary
This update converts the `python-fastapi-mssql` project from native SSH-based MSSQL deployment to an Ansible-driven workflow. The FastAPI service now orchestrates embedded Ansible playbooks and roles for:
- MSSQL installation on VM1 and VM2
- AdventureWorks restore on VM1
- 10-stripe backup creation on VM1
- Backup transfer and restore on VM2
- Always On Availability Group setup

## Files Added
- `app/ansible_runner.py`
  - Executes `ansible-playbook` commands via subprocess
  - Builds command line with inventory, tags, limit, extra vars, and private key support
  - Captures stdout/stderr, return code, duration, and result metadata

- `app/deployer.py`
  - New Ansible-based deployment orchestration class
  - Tracks task history and status for background operations
  - Supports install, backup/restore, tool installation, restore only, and Always On operations

- `ansible/` directory
  - `inventory/hosts.ini`
  - `playbooks/site.yml`
  - `playbooks/backup.yml`
  - `playbooks/alwayson.yml`
  - `roles/mssql/` with tasks and defaults for install/configure/db/backup/restore/alwayson

## Files Updated
- `app/config.py`
  - Added Ansible configuration settings: `ANSIBLE_INVENTORY`, `ANSIBLE_PLAYBOOK_DIR`, `ANSIBLE_CMD`, `ANSIBLE_VERBOSE`, `ANSIBLE_PRIVATE_KEY_FILE`

- `app/routes/deploy.py`
  - Switched router to use `AnsibleMssqlDeployer`
  - Updated endpoint responses to reflect Ansible playbooks
  - Added `/api/v1/deploy/alwayson` endpoint
  - Added Ansible inventory/playbook metadata to `/hosts`

- `requirements.txt`
  - Added `ansible-core==2.16.1`

- `.env.example`
  - Documented Ansible settings and inventory paths

- `Dockerfile`
  - Copied embedded Ansible content into container image

## Notes
- The new embedded Ansible role is based on the existing `ansible-mssql-deploy` structure.
- The Always On task is now a working, live-tested `CLUSTER_TYPE=NONE` two-node
  AG (see above) -- no longer a first-pass stub.
- The router still provides lightweight status and history endpoints for asynchronous task tracking.
- A local lab runbook was added for VMware Workstation Pro testing against `devops_VM1` and `devops_VM2`.
- A reset workflow was documented for tearing down and replaying the lab from scratch.

## Testing
- Existing API endpoint tests remain unchanged.
- The full `full-ag` sequence (download, restore, backup, transfer, restore,
  AG pairing) has been executed and independently verified against the live
  CentOS 8 lab VMs (see "Working Always On Availability Group" above).
- Verify Docker build includes Ansible artifacts and the API can locate `ansible/inventory/hosts.ini`.

## Next Steps
1. Add validation for `ansible-playbook` availability in `routes/health.py`
2. Add unit tests or mocks for `AnsibleRunner`
3. Remove the unused `app/python_deployer.py` and the now-dead `paramiko`
   dependency, or otherwise decide their fate (currently unimported dead code)
4. Consider an AG listener and/or a real cluster manager (Pacemaker) if
   automatic failover is ever needed -- current setup is manual-failover only
5. `mssql_build` role's directory-creation tasks have the same
   root-ownership issue that was fixed in the `mssql` role's `configure.yml`
   -- not yet fixed since `build.yml` wasn't exercised this session

~~Reconcile the SSH user/key path shown in `RUNBOOK.md`/`.env.example`~~ --
done: all `root@`/`id_ed25519` references in `README.md`/`RUNBOOK.md` now
match `ansible/inventory/hosts.ini`'s `ansible_user=devops`/`id_rsa`. Also
documented that VM1 doubles as the Ansible controller in this lab (see
`RUNBOOK.md` section 9 and `README.md`'s Access Logs), and added
`ansible.cfg` with `log_path` so `logs/ansible.log` now persists full
Ansible run output independent of the API process's lifetime.
