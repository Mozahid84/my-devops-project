# Simple Setup Guide: GitLab, AWX, VMware, MSSQL

This is the current implementation guide for your project.

Use this file as the source of truth. Some older generated docs are still present for background reading, but this guide matches the current repo layout and your VMware VM names.

## What You Have

One Git repo:

```text
https://gitlab.com/mozahidhossaingitlab-group/my-devops-project.git
https://github.com/Mozahid84/my-devops-project.git
```

Three VMware Workstation Pro VMs:

| VM | Role | Hostname |
| --- | --- | --- |
| AWX server | Runs AWX and pulls from GitLab | `devops_AWX` |
| SQL VM 1 | Primary SQL Server target | `devops_VM1` |
| SQL VM 2 | Secondary SQL Server target | `devops_VM2` |

Two deployment paths:

| Path | Purpose |
| --- | --- |
| GitLab -> AWX -> Ansible | Main repeatable deployment path |
| FastAPI -> Python SSH | Lightweight API path, no Ansible inside FastAPI |

## Step 1: Check VMware Networking

All three VMs should be on VMware NAT and have internet access.

From `devops_AWX`, test name resolution:

```bash
ping -c 2 devops_VM1
ping -c 2 devops_VM2
```

If those names do not resolve, add them to `/etc/hosts` on `devops_AWX`:

```bash
sudo nano /etc/hosts
```

Add lines like this, using the actual VM IP addresses:

```text
192.168.x.x devops_VM1
192.168.x.x devops_VM2
```

Then test SSH:

```bash
ssh root@devops_VM1 "hostname"
ssh root@devops_VM2 "hostname"
```

## Step 2: Configure SSH Access

On `devops_AWX`, create or reuse an SSH key:

```bash
ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa
```

Copy the key to both target VMs:

```bash
ssh-copy-id -i ~/.ssh/id_rsa.pub root@devops_VM1
ssh-copy-id -i ~/.ssh/id_rsa.pub root@devops_VM2
```

Test:

```bash
ssh -i ~/.ssh/id_rsa root@devops_VM1 "echo VM1 OK"
ssh -i ~/.ssh/id_rsa root@devops_VM2 "echo VM2 OK"
```

## Step 3: Push Code To GitLab And GitHub

From your PC in `C:\Users\mozy\devops`:

```powershell
git status
git add .
git commit -m "Update setup guide"
git push gitlab main
git push github main
```

GitLab is the deployment source for AWX. GitHub is a mirror/copy.

## Step 4: Configure AWX Project

In AWX on `devops_AWX`, create or update the project:

| Field | Value |
| --- | --- |
| Name | `mssql-deploy` |
| Organization | `Default` |
| Source Control Type | `Git` |
| Source Control URL | `https://gitlab.com/mozahidhossaingitlab-group/my-devops-project.git` |
| Source Control Branch | `main` |
| Update Revision on Launch | enabled |

After saving, click **Sync**.

## Step 5: Configure AWX Credential

Create a Machine credential:

| Field | Value |
| --- | --- |
| Name | `mssql-ssh-credential` |
| Credential Type | `Machine` |
| Username | `root` |
| SSH Private Key | paste the private key from `devops_AWX:/root/.ssh/id_rsa` or your chosen AWX SSH key |
| Privilege Escalation Method | `sudo` |

If you use a non-root account, make sure it has passwordless sudo or configure the become password in AWX.

## Step 6: Configure AWX Inventory

Create an inventory:

| Field | Value |
| --- | --- |
| Name | `mssql-deployment-inventory` |
| Organization | `Default` |

Add group:

```text
mssql_servers
```

Add hosts:

```ini
vm1 ansible_host=devops_VM1 instance_name=instance1
vm2 ansible_host=devops_VM2 instance_name=instance2
```

Group variables for `mssql_servers`:

```yaml
ansible_user: root
ansible_connection: ssh
ansible_port: 22
mssql_version: "2019"
mssql_port: 1433
sa_password: "YourStr0ng!Passw0rd"
backup_dir: "/backup"
data_dir: "/var/opt/mssql/data"
log_dir: "/var/opt/mssql/log"
```

Change `sa_password` before real use.

## Step 7: Configure AWX Job Templates

Create the install job:

| Field | Value |
| --- | --- |
| Name | `MSSQL-Deploy-Install` |
| Job Type | `Run` |
| Inventory | `mssql-deployment-inventory` |
| Project | `mssql-deploy` |
| Playbook | `ansible-mssql-deploy/playbooks/site.yml` |
| Credentials | `mssql-ssh-credential` |
| Become Enabled | yes |

Create the backup job:

| Field | Value |
| --- | --- |
| Name | `MSSQL-Backup-Striped` |
| Job Type | `Run` |
| Inventory | `mssql-deployment-inventory` |
| Project | `mssql-deploy` |
| Playbook | `ansible-mssql-deploy/playbooks/backup.yml` |
| Credentials | `mssql-ssh-credential` |
| Become Enabled | yes |

## Step 8: Run In AWX

Run this first:

```text
MSSQL-Deploy-Install
```

This installs SQL Server, restores AdventureWorks, creates a 10-stripe backup on VM1, copies it to VM2, and restores it.

For later backup/restore only, run:

```text
MSSQL-Backup-Striped
```

## Step 9: FastAPI Optional Path

FastAPI now uses Python SSH directly. It does not use Ansible.

Configure:

```powershell
cd C:\Users\mozy\devops\python-fastapi-mssql
copy .env.example .env
```

Edit `.env`:

```text
VM1_HOST=devops_VM1
VM2_HOST=devops_VM2
VM1_USER=root
VM2_USER=root
SSH_KEY_PATH=~/.ssh/id_rsa
MSSQL_SA_PASSWORD=YourStr0ng!Passw0rd
```

Run:

```powershell
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open:

```text
http://localhost:8000/api/docs
```

Useful checks:

```powershell
curl http://localhost:8000/api/v1/health/ready
curl http://localhost:8000/api/v1/deploy/hosts
curl -X POST http://localhost:8000/api/v1/deploy/ping
```

## Step 10: Current Important Files

| File | Purpose |
| --- | --- |
| `SETUP_GUIDE.md` | Main simple setup guide |
| `SETUP_VMWARE_GIT_AWX.md` | Extra GitLab/GitHub/AWX notes |
| `ansible-mssql-deploy/inventory/hosts.ini` | Local Ansible inventory using `devops_VM1` and `devops_VM2` |
| `ansible-mssql-deploy/awx/` | AWX reference config files |
| `python-fastapi-mssql/app/python_deployer.py` | FastAPI native Python SSH deployment code |
| `python-fastapi-mssql/.env.example` | FastAPI environment template |

## Quick Troubleshooting

If AWX cannot sync:

```text
Check GitLab project URL, credentials, and internet access from devops_AWX.
```

If AWX cannot SSH:

```text
Check the AWX Machine credential and SSH from devops_AWX to devops_VM1/devops_VM2.
```

If hostnames do not resolve:

```text
Add devops_VM1 and devops_VM2 to /etc/hosts on devops_AWX.
```

If SQL install fails:

```text
Check internet access from devops_VM1/devops_VM2 and confirm the SA password is strong.
```
