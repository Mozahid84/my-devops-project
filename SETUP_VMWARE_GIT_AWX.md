# VMware, GitLab, GitHub, and AWX Setup Guide

This repo has two deployment paths:

- GitLab to AWX to Ansible for the main infrastructure workflow.
- FastAPI to native Python SSH for lightweight API-driven operations.

The FastAPI app no longer calls Ansible. It connects directly to the target VMs with Python SSH.

## 1. VMware Names

Use these hostnames throughout the project:

| VM | Purpose | Hostname |
| --- | --- | --- |
| AWX | Runs AWX and pulls from GitLab | `devops_AWX` |
| VM1 | Primary SQL Server | `devops_VM1` |
| VM2 | Secondary SQL Server | `devops_VM2` |

From `devops_AWX`, confirm DNS/name resolution:

```bash
ping -c 2 devops_VM1
ping -c 2 devops_VM2
```

If the names do not resolve, add them to `/etc/hosts` on `devops_AWX` and on the PC/container that runs FastAPI.

## 2. Push To GitLab And GitHub

The repo already has both remotes:

```bash
git remote -v
```

Expected names:

```text
gitlab  https://gitlab.com/mozahidhossaingitlab-group/my-devops-project.git
github  https://github.com/Mozahid84/my-devops-project.git
```

Push the same branch to both:

```bash
git add .
git commit -m "Harden MSSQL deployment and refactor FastAPI to Python SSH"
git push gitlab main
git push github main
```

GitLab should be treated as the deployment source of truth because AWX will sync from GitLab.

## 3. AWX Project

In AWX on `devops_AWX`, create or update the project:

| Field | Value |
| --- | --- |
| Name | `mssql-deploy` |
| Source Control Type | Git |
| Source Control URL | `https://gitlab.com/mozahidhossaingitlab-group/my-devops-project.git` |
| Branch | `main` |
| Update Revision on Launch | enabled |

The AWX config files are in `ansible-mssql-deploy/awx/`.

Because the Ansible project lives in a subdirectory of the repo, the job templates use:

```text
ansible-mssql-deploy/playbooks/site.yml
ansible-mssql-deploy/playbooks/backup.yml
```

## 4. AWX Inventory

Create an inventory named `mssql-deployment-inventory` with:

```ini
[mssql_servers]
vm1 ansible_host=devops_VM1 instance_name=instance1
vm2 ansible_host=devops_VM2 instance_name=instance2

[mssql_servers:vars]
ansible_user=root
ansible_connection=ssh
ansible_port=22
```

Use an AWX Machine Credential named `mssql-ssh-credential` with SSH access to both target hosts.

## 5. AWX Job Templates

Create these templates:

| Template | Playbook | Purpose |
| --- | --- | --- |
| `MSSQL-Deploy-Install` | `ansible-mssql-deploy/playbooks/site.yml` | Install SQL Server, restore AdventureWorks, backup, restore |
| `MSSQL-Backup-Striped` | `ansible-mssql-deploy/playbooks/backup.yml` | Run backup and restore only |

Set `Become enabled` to true.

Before running the full job, run a quick connectivity check from AWX:

```bash
ansible mssql_servers -i ansible-mssql-deploy/inventory/hosts.ini -m ping
```

## 6. FastAPI Native Python Path

FastAPI now uses Python SSH, not Ansible. Configure it with:

```bash
cd python-fastapi-mssql
cp .env.example .env
```

Important values:

```text
VM1_HOST=devops_VM1
VM2_HOST=devops_VM2
VM1_USER=root
VM2_USER=root
SSH_KEY_PATH=~/.ssh/id_rsa
MSSQL_SA_PASSWORD=YourStr0ng!Passw0rd
```

Run locally:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Useful checks:

```bash
curl http://localhost:8000/api/v1/health/ready
curl http://localhost:8000/api/v1/deploy/hosts
curl -X POST http://localhost:8000/api/v1/deploy/ping
```

## 7. Recommended Flow

Use GitLab and AWX for repeatable infrastructure deployments.

Use FastAPI when you want a small REST service that can run install, backup, restore, health checks, and host checks through Python SSH without AWX.
