# FastAPI MSSQL Ansible Integration Change Log

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
- The Always On task is a first-pass implementation and assumes Linux SQL Server HADR support is available.
- The router still provides lightweight status and history endpoints for asynchronous task tracking.
- A local lab runbook was added for VMware Workstation Pro testing against `devops_VM1` and `devops_VM2`.
- A reset workflow was documented for tearing down and replaying the lab from scratch.

## Testing
- Existing API endpoint tests remain unchanged.
- New Ansible execution behavior should be validated in the target deployment environment.
- Verify Docker build includes Ansible artifacts and the API can locate `ansible/inventory/hosts.ini`.

## Next Steps
1. Add validation for `ansible-playbook` availability in `routes/health.py`
2. Add unit tests or mocks for `AnsibleRunner`
3. Validate the Always On playbook on actual CentOS 8/RHEL 8 hosts
4. Remove the unused `app/python_deployer.py` and the now-dead `paramiko`
   dependency, or otherwise decide their fate (currently unimported dead code)
5. Reconcile the SSH user/key path shown in `RUNBOOK.md`/`.env.example`
   (`root@`, `id_ed25519`) with `ansible/inventory/hosts.ini`
   (`ansible_user=devops`, `id_rsa`)
