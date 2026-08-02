# FastAPI + Ansible MSSQL Lab Runbook

## Goal
Run the FastAPI service locally on this PC, target the VMware SQL VMs (`devops_VM1` and `devops_VM2`), and test the full workflow end to end.

## Prerequisites
- VMware Workstation Pro running with two Linux VMs
- `devops_VM1` at `192.168.70.129`
- `devops_VM2` at `192.168.70.130`
- Git Bash available
- Python available in Git Bash
- SSH access from this host to both VMs
- Internet access from the VMs

## 1. Verify VMware Networking
From Git Bash:

```bash
ping -c 2 192.168.70.129
ping -c 2 192.168.70.130
ssh devops@192.168.70.129 'hostname'
ssh devops@192.168.70.130 'hostname'
```

If names are needed, add them to `/etc/hosts` on the VMs or your workstation host file.

## 2. Configure SSH Keys
If you do not already have a key:

```bash
ssh-keygen -t rsa -b 4096 -C "mssql-lab"
```

Copy the key to both VMs using the existing `devops` account:

```bash
ssh-copy-id -i ~/.ssh/id_rsa.pub devops@192.168.70.129
ssh-copy-id -i ~/.ssh/id_rsa.pub devops@192.168.70.130
```

Verify the login:

```bash
ssh -i ~/.ssh/id_rsa devops@192.168.70.129 'hostname'
ssh -i ~/.ssh/id_rsa devops@192.168.70.130 'hostname'
```

## 3. Create or Update Local Environment File
From the project root:

```bash
cd python-fastapi-mssql
cp .env.example .env
```

Edit `.env` and set at least:

```env
MSSQL_SA_PASSWORD=YourStr0ng!Passw0rd
VM1_HOST=192.168.70.129
VM2_HOST=192.168.70.130
VM1_USER=devops
VM2_USER=devops
SSH_KEY_PATH=~/.ssh/id_rsa
ANSIBLE_INVENTORY=./ansible/inventory/hosts.ini
ANSIBLE_PLAYBOOK_DIR=./ansible/playbooks
ANSIBLE_CMD=ansible-playbook
```

## 4. Install Python Dependencies
In Git Bash:

```bash
cd python-fastapi-mssql
python -m venv venv
source venv/Scripts/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If you are in Git Bash on Windows, `source venv/Scripts/activate` should work. If not, use:

```bash
source venv/Scripts/activate
```

## 5. Start the FastAPI Service
```bash
cd python-fastapi-mssql
source venv/Scripts/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open:
- http://localhost:8000/api/docs

## 6. Test the Workflow
### Install MSSQL and restore AdventureWorks
```bash
curl -X POST http://localhost:8000/api/v1/deploy/install
```

### Create backup on VM1 and restore on VM2
```bash
curl -X POST http://localhost:8000/api/v1/deploy/backup
```

### Run the full AdventureWorks + AG workflow
```bash
curl -X POST http://localhost:8000/api/v1/deploy/full-ag
```

### Configure Always On Availability Group
```bash
curl -X POST http://localhost:8000/api/v1/deploy/alwayson
```

### Check status
```bash
curl http://localhost:8000/api/v1/deploy/status
```

## 7. Reset and Start Over for Testing
Use this when you want to tear down and replay the lab from scratch.

### Stop the API
Press `Ctrl+C` in the terminal running Uvicorn.

### Remove local artifacts
```bash
cd python-fastapi-mssql
rm -rf backups logs
mkdir -p backups logs
```

### Optional: clean the target VMs before redeployment
On the VMs, remove prior SQL artifacts if needed:

```bash
systemctl stop mssql-server
rm -rf /var/opt/mssql/data/* /var/opt/mssql/log/* /backup/*
yum remove -y mssql-server mssql-tools || true
systemctl reset-failed mssql-server || true
```

### Restart the API
```bash
source venv/Scripts/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 8. Useful Commands
```bash
curl http://localhost:8000/api/v1/health/check
curl http://localhost:8000/api/v1/deploy/history
curl http://localhost:8000/api/v1/deploy/hosts
```

## 9. Checking Logs

Ansible is agentless -- it doesn't write a persistent log file on VM1/VM2
itself. The `ansible-playbook` output lives on the **controller** (wherever
`uvicorn` is running), and only a couple of small artifacts land on the VMs.

### Controller side (the actual "Ansible logs")
- **Per-run history via the API** -- the full `stdout`/`stderr` of every
  `ansible-playbook` invocation is captured and returned here:
  ```bash
  curl http://localhost:8000/api/v1/deploy/history | jq
  ```
  Each entry includes the exact command line run, return code, and complete
  stdout/stderr for that playbook.
- **The FastAPI application log file**, which also records request-level
  events:
  ```bash
  tail -f python-fastapi-mssql/logs/app.log
  ```
- For more verbose Ansible output on future runs, raise `ANSIBLE_VERBOSE` in
  `.env` (e.g. to `3` for `-vvv`).

### On VM1 (and VM2)
- **SQL Server's own error log** is the most useful thing to check for
  install/restore/Always On issues -- this is where SQL Server itself
  reports what happened (HADR state changes, endpoint/certificate errors,
  AG join attempts, etc.):
  ```bash
  ssh devops@192.168.70.129 'sudo tail -100 /var/opt/mssql/log/errorlog'
  ```
  Older logs roll to `errorlog.1`, `errorlog.2`, etc. in the same directory.
- **The one-off deployment summary** written by `site.yml`'s `post_tasks`
  after each install run:
  ```bash
  ssh devops@192.168.70.129 'cat /tmp/mssql_deployment_vm1.txt'
  ```

## 10. Push to GitLab and GitHub
From the workspace root:

```bash
cd /c/Users/mozy/devops
git status
git add .
git commit -m "Add FastAPI Ansible integration and lab runbook"
git push gitlab main
git push github main
```

If the remotes are not set yet:

```bash
git remote add gitlab https://gitlab.com/mozahidhossaingitlab-group/my-devops-project.git
git remote add github https://github.com/Mozahid84/my-devops-project.git
```
