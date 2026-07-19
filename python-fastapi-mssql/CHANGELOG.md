# FastAPI MSSQL Ansible Integration Change Log

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
4. Update `README.md` to document new Ansible endpoint and workflow
