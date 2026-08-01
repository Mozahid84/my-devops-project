# MSSQL Build Implementation Changelog

Date: 2026-08-01

## Summary

This changelog records the work performed to implement the `mssql` build design: an Ansible playbook and role skeleton, a FastAPI endpoint to trigger the build, and supporting documentation.

## What was added

- `ansible-mssql-deploy/playbooks/build.yml` — a lightweight playbook that includes the `mssql_build` role.
- `ansible-mssql-deploy/roles/mssql_build/` — role skeleton with idempotent directory and user creation tasks and a placeholder for package installation.
- `python-fastapi-mssql/app/deployer.py` — added `deploy_build()` to run `build.yml` through the `AnsibleRunner`.
- `python-fastapi-mssql/app/routes/deploy.py` — added `POST /api/v1/deploy/build` endpoint to trigger the build as a background task.
- `docs/changelog/mssql-build-changelog.md` — this changelog file.

## How it was implemented

1. Created a focused playbook (`build.yml`) that targets `mssql_servers` and delegates to a role. This keeps the playbook simple and readable.
2. Implemented `mssql_build` role defaults and safe tasks:
   - create backup, data, and log directories (idempotent)
   - create a service account placeholder
   - include a `debug` placeholder where platform-specific package installation should be added
3. Hooked the orchestration into the FastAPI control plane by adding `deploy_build()` in the `AnsibleMssqlDeployer` class and exposing a `/build` route that runs the task in the background.

## Why these choices

- Keep initial implementation safe: avoid executing destructive or platform-specific installs until validated.
- Use a role-based layout to allow later expansion (OS-specific tasks can be added under `roles/mssql_build/tasks/` or split into multiple roles).
- Integrate with existing `AnsibleRunner` and `deployer` patterns to keep orchestration consistent across endpoints.

## Problems encountered and resolutions

- Problem: No existing `build.yml` or `mssql_build` role in the repo.
  - Resolution: Added a minimal playbook and role skeleton; kept installation placeholder to avoid accidental destructive runs.

- Problem: `AnsibleMssqlDeployer` had no `deploy_build()` helper.
  - Resolution: Added `deploy_build()` to call `run_playbook("build.yml")` and wired it into the new FastAPI endpoint.

- Problem: Need to keep the API surface consistent and non-blocking.
  - Resolution: The endpoint returns immediately and schedules the build as a FastAPI background task, consistent with other deployment endpoints.

## Next steps / Recommendations

- Replace the placeholder installation task in `roles/mssql_build/tasks/main.yml` with platform-specific package installation (YUM/APT/DNF) or call a more complete role. [In progress: the CentOS/RHEL install path is now wired into the build role.]
- Add tests or a dry-run mode to validate playbook execution without changing host state.
- Consider adding inventory group `mssql_servers` to the project-level inventory if not present.
- Add more detailed logging and result parsing in `AnsibleRunner` if you need structured outputs for UI or audit.

## Current implementation status (2026-08-01)

- The build role now performs real SQL Server package installation steps for CentOS/RHEL hosts: repository key/repo setup, `mssql-server` and `mssql-tools` package installation, service configuration, and basic verification with `sqlcmd`.
- The role now also configures a conservative SQL Server memory limit for the lab VM so the service can start under the available RAM budget.
- The next verification step is to execute the FastAPI build endpoint again and confirm that `mssql-server` starts and `sqlcmd` can connect locally on each VM.

---

## Practical execution log (2026-08-01)

I ran the newly-added `/api/v1/deploy/build` endpoint from the FastAPI service to execute `ansible-playbook` against the lab VMs. Steps performed:

1. Started the FastAPI server locally:

```bash
cd python-fastapi-mssql
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level info
```

2. Verified API and endpoints:

```
GET /api/v1/deploy/hosts  -> returned inventory and DNS resolution for 192.168.70.129 and 192.168.70.130
POST /api/v1/deploy/ping  -> returned reachable for both hosts (TCP connect to SSH port)
```

3. Triggered the build via the API:

```
POST /api/v1/deploy/build  -> task queued and executed by background worker
```

4. Observed Ansible execution (summary):

- `vm2 (192.168.70.130)`: tasks applied successfully (created `/backup`, `/var/opt/mssql/data`, `/var/opt/mssql/log`, and created `mssql` user). The placeholder debug task ran as `ok`.
- `vm1 (192.168.70.129)`: unreachable during play (SSH permission denied). Ansible logs show `Permission denied (publickey,gssapi-keyex,gssapi-with-mic,password)`.

Key evidence from the Ansible run (abridged):

```
fatal: [vm1]: UNREACHABLE! => {"changed": false, "msg": "Failed to connect to the host via ssh: devops@192.168.70.129: Permission denied (publickey,gssapi-keyex,gssapi-with-mic,password).", "unreachable": true}

changed: [vm2] => {"changed": true, "path": "/var/opt/mssql/data", "state": "directory"}
```

Root cause

- `vm1` does not accept the control host's SSH key for the `devops` account. The project's inventory initially pointed at a Windows-style key path (`/c/Users/mozy/.ssh/id_rsa`) which I corrected to `/home/devops/.ssh/id_rsa` for the control host; after fixing that, Ansible used the correct key but `vm1` still denied access.

Resolution / recommended next steps

1. Add the control host public key to `devops` user's `~/.ssh/authorized_keys` on `vm1`.

  From your workstation or the control host run:

  ```bash
  ssh-copy-id -i ~/.ssh/id_rsa.pub devops@192.168.70.129
  ```

  If `ssh-copy-id` is not available, copy the contents of `~/.ssh/id_rsa.pub` into `/home/devops/.ssh/authorized_keys` on `vm1`.

2. Alternatively, if VM1 uses a different account or key, update `python-fastapi-mssql/ansible/inventory/hosts.ini` with the correct `ansible_user` or `ansible_ssh_private_key_file` for `vm1`.

3. After resolving SSH access, re-run the build endpoint:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/deploy/build
curl http://127.0.0.1:8000/api/v1/deploy/history
```

Notes

- The role remains a safe skeleton — it intentionally does not install SQL Server packages until you confirm target OS and package sources.
- Once SSH access to `vm1` is fixed, the same build run should apply the identical idempotent tasks there and leave both VMs prepared for further installation steps.
