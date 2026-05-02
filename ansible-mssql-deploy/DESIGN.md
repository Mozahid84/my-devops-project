# MSSQL Ansible Deployment - Design Document

## Overview

This document describes the architecture, design decisions, and implementation details of the Ansible-based MSSQL Server deployment solution.

## Business Objectives

1. **Automation**: Automate MSSQL installation and configuration on multiple Linux VMs
2. **Consistency**: Ensure identical configurations across all instances
3. **Backup & Recovery**: Implement striped backup strategy for performance and reliability
4. **Orchestration**: Enable deployment via AWX for enterprise management
5. **CI/CD Integration**: Integrate with GitLab for automated testing and deployment

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    DevOps Workflow                            │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Developer  →  GitLab Repo  →  GitLab CI/CD  →  AWX         │
│              (ansible-mssql-                                 │
│               deploy)                                        │
│                                                               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ↓
                    ┌──────────────────┐
                    │   AWX Instance   │
                    │  (Orchestrator)  │
                    └──────────────────┘
                              │
                ┌─────────────┴─────────────┐
                ↓                           ↓
        ┌────────────────┐        ┌────────────────┐
        │      VM1       │        │      VM2       │
        │   (Primary)    │        │  (Secondary)   │
        │                │        │                │
        │  MSSQL 2019    │        │  MSSQL 2019    │
        │  Instance 1    │        │  Instance 2    │
        │                │        │                │
        │  Backup 10x    │  ════  │  Restore 10x   │
        │  Striped       │        │  Striped       │
        │  AdventureWorks│        │  AdventureWorks│
        └────────────────┘        └────────────────┘
```

## Role Structure

### Mssql Role - Task Breakdown

```
roles/mssql/
├── tasks/
│   ├── install.yml        [Phase 1] Install MSSQL + Tools
│   ├── configure.yml      [Phase 2] Setup directories & paths
│   ├── adventureworks.yml [Phase 3] Download & restore DB
│   ├── backup.yml         [Phase 4] Create 10-stripe backup (VM1)
│   └── restore.yml        [Phase 5] Transfer & restore (VM2)
│
├── handlers/
│   └── main.yml           Service restart handlers
│
├── defaults/
│   └── main.yml           Default variables (passwords, paths)
│
├── vars/
│   └── main.yml           Fixed variables
│
└── templates/ & files/    Configuration templates (if needed)
```

### Task Execution Flow

```
1. INSTALL PHASE (install.yml)
   └─ Install dependencies (curl, wget, gnupg, libsodium)
   └─ Add Microsoft repositories (mssql-server, mssql-tools)
   └─ Install mssql-server package
   └─ Install mssql-tools (sqlcmd utility)
   └─ Run /opt/mssql/bin/mssql-conf setup
   └─ Start mssql-server service
   └─ Wait for port 1433 ready (10-60 second retry loop)
   └─ Verify installation with @@VERSION query

2. CONFIGURE PHASE (configure.yml)
   └─ Create /backup directory
   └─ Create /var/opt/mssql/data directory
   └─ Create /var/opt/mssql/log directory
   └─ Set default data directory path
   └─ Set default log directory path
   └─ Configure network TCP port (1433)
   └─ Enable SQL Server Agent
   └─ Restart service to apply config

3. DATABASE PHASE (adventureworks.yml)
   └─ Create backup subdirectory
   └─ Download AdventureWorks2019.bak from GitHub (300s timeout)
   └─ Verify MSSQL connectivity
   └─ RESTORE DATABASE from .bak file
   └─ Move MDF/LDF to correct paths
   └─ Enable REPLACE option (if DB exists)
   └─ Verify restoration with DB_ID check

4. BACKUP PHASE (backup.yml) - VM1 ONLY
   └─ Create /backup/striped directory
   └─ Execute BACKUP DATABASE with 10 disk stripes
   └─ Write to: adv_stripe_01.bak through adv_stripe_10.bak
   └─ Enable FORMAT and COMPRESSION options
   └─ Verify all 10 files created
   └─ Log file counts

5. RESTORE PHASE (restore.yml)
   ├─ On VM1:
   │  └─ Fetch /backup/striped/* to local ./backups/vm1_striped/
   │
   └─ On VM2:
      └─ Create /backup/striped directory
      └─ Copy fetched files to local /backup/striped/
      └─ RESTORE DATABASE from 10 striped backup files
      └─ Enable REPLACE option
      └─ Verify restoration with DB_ID check
      └─ Log restoration status
```

## Variables and Configuration

### Hierarchy (Priority Order)

1. **Command-line vars** (highest priority)
   ```bash
   ansible-playbook ... -e "sa_password=Override123"
   ```

2. **Host-specific vars** (`host_vars/vm1.yml`, `host_vars/vm2.yml`)
   ```yaml
   instance_name: instance1
   backup_location: primary
   ```

3. **Group vars** (`group_vars/mssql_servers.yml`)
   ```yaml
   mssql_version: "2019"
   sa_password: "YourStr0ng!Passw0rd"
   backup_dir: "/backup"
   ```

4. **Role defaults** (`roles/mssql/defaults/main.yml`) (lowest priority)
   ```yaml
   mssql_port: 1433
   ```

### Critical Variables

| Variable | Default | Example | Notes |
|----------|---------|---------|-------|
| `sa_password` | YourStr0ng!Passw0rd | MyStrong!Pass123 | **MUST change** - min 8 chars, uppercase, lowercase, digit, special char |
| `mssql_version` | 2019 | 2019, 2022 | SQL Server version |
| `mssql_edition` | Developer | Developer, Express, Standard, Enterprise | For licensing |
| `backup_dir` | /backup | /mnt/backup | Where backups are stored |
| `data_dir` | /var/opt/mssql/data | /mnt/data | Where MDF files go |
| `log_dir` | /var/opt/mssql/log | /mnt/log | Where LDF files go |
| `mssql_port` | 1433 | 1433, 1434 | TCP listening port |

## Backup Strategy

### 10-Stripe Backup Approach

**Why striping?**
- **Parallel I/O**: 10 parallel writes → faster backup speed
- **Reliability**: Single file corruption doesn't affect entire backup
- **Performance**: Reduced single-disk bottleneck

**Stripe File Naming**
```
/backup/striped/adv_stripe_01.bak
/backup/striped/adv_stripe_02.bak
...
/backup/striped/adv_stripe_10.bak
```

**Backup Command (SQL)**
```sql
BACKUP DATABASE AdventureWorks
TO
  DISK='/backup/striped/adv_stripe_01.bak',
  DISK='/backup/striped/adv_stripe_02.bak',
  ...
  DISK='/backup/striped/adv_stripe_10.bak'
WITH FORMAT, COMPRESSION
```

**Restore Command (SQL)**
```sql
RESTORE DATABASE AdventureWorks
FROM
  DISK='/backup/striped/adv_stripe_01.bak',
  DISK='/backup/striped/adv_stripe_02.bak',
  ...
  DISK='/backup/striped/adv_stripe_10.bak'
WITH REPLACE
```

## Cross-VM Data Transfer

```
Step 1: Fetch from VM1
┌─────────────────────────────────────┐
│ Ansible Control Machine             │
│ ./backups/vm1_striped/vm1/backup/   │
│ striped/adv_stripe_*.bak            │
└─────────────────────────────────────┘

Step 2: Copy to VM2
            │
            ↓
┌─────────────────────────────────────┐
│ VM2: /backup/striped/               │
│ adv_stripe_*.bak                    │
└─────────────────────────────────────┘
```

**Transfer Mechanism:**
1. `fetch` module: Pulls files from VM1 to control machine
   - Source: `/backup/striped/` on VM1
   - Dest: `./backups/vm1_striped/` on control machine

2. `copy` module: Pushes files to VM2
   - Source: `./backups/vm1_striped/vm1/backup/striped/` on control machine
   - Dest: `/backup/striped/` on VM2

## Playbook Execution

### Main Playbook (site.yml)

```yaml
- hosts: mssql_servers
  become: yes              # Run with sudo
  gather_facts: yes        # Collect system info
  
  pre_tasks:              # Run before roles
    - Validate OS is CentOS 8
    - Display deployment info
  
  roles:
    - mssql               # Execute role
  
  post_tasks:             # Run after roles
    - Create summary report
    - Display success message
```

### Backup Playbook (backup.yml)

```yaml
- hosts: mssql_servers
  become: yes
  
  tasks:
    - Include backup.yml when inventory_hostname == "vm1"
    - Include restore.yml when inventory_hostname == "vm2"
```

## Idempotency

### Idempotent Tasks

Tasks that can be run multiple times safely:

- ✅ `yum install` - Won't re-install if already present
- ✅ `file` - Creates directory if missing, no error if exists
- ✅ `systemd` - Idempotent service management

### Non-Idempotent Tasks (Requires Guards)

- ❌ `shell` commands - Always runs
- ❌ `RESTORE DATABASE` - Will fail if DB already exists

**Solution: Use when conditions**
```yaml
- name: Run MSSQL setup
  shell: /opt/mssql/bin/mssql-conf setup
  args:
    creates: /var/opt/mssql/.setup_done  # Only runs if file doesn't exist
```

## Error Handling

### Retry Logic

```yaml
- name: Download backup (with retries)
  get_url:
    url: https://...
    dest: /path/to/file
  retries: 3              # Try 3 times
  delay: 5                # Wait 5 seconds between retries
  until: download_result is succeeded
```

### Conditional Failures

```yaml
- name: Restore database
  shell: sqlcmd ...
  register: restore_output
  failed_when: false                    # Don't fail on error
  changed_when: "'restored' in output"  # Only report change on success
```

### Service Readiness

```yaml
- name: Wait for SQL Server
  wait_for:
    port: 1433
    delay: 10              # Wait 10 seconds before checking
    timeout: 60            # Timeout after 60 seconds
```

## Security Considerations

### 1. Password Management

**Problem:** Plaintext passwords in files

**Solution: Use Ansible Vault**
```bash
# Encrypt file
ansible-vault encrypt group_vars/mssql_servers.yml

# Run with vault
ansible-playbook ... --vault-password-file ~/.vault_pass
```

### 2. SSH Key Authentication

**Configured in inventory:**
```ini
[mssql_servers:vars]
ansible_ssh_private_key_file=~/.ssh/id_rsa
```

**Setup:**
```bash
ssh-keygen -t rsa -b 4096
ssh-copy-id -i ~/.ssh/id_rsa root@vm1
```

### 3. Privilege Escalation

```yaml
become: yes              # Equivalent to sudo
become_method: sudo      # Use sudo (default)
become_user: root        # Become root user
```

### 4. Firewall Rules

**Recommended:**
```bash
# Open MSSQL port on each VM
firewall-cmd --permanent --add-port=1433/tcp
firewall-cmd --reload
```

## AWX Integration

### AWX Architecture

```
GitLab Repo ──→ AWX Project
                    │
                    ├─→ Inventory (vm1, vm2)
                    ├─→ Credentials (SSH)
                    ├─→ Job Templates
                    │   ├─ Install
                    │   ├─ Backup
                    │   └─ Restore
                    │
                    └─→ Workflow Template
                        [Install] → [Backup] → [Restore]
```

### Workflow Execution

```
1. Launch Workflow Template "MSSQL-Complete-Workflow"
   │
   ├─→ Job: MSSQL-Deploy-Install
   │   └─ Runs playbooks/site.yml
   │   └─ Status: Success ✓
   │
   ├─→ Job: MSSQL-Backup-Striped
   │   └─ Runs playbooks/backup.yml
   │   └─ Only if Install succeeded
   │   └─ Status: Success ✓
   │
   └─→ Workflow Status: SUCCESS ✓
```

### AWX Configuration Files

- `awx/project.yml` - Project definition with GitLab URL
- `awx/inventory.yml` - Host and group definitions
- `awx/credentials.yml` - SSH credentials
- `awx/job-template.yml` - Job template configurations

## GitLab CI/CD Pipeline

### Pipeline Stages

```
Lint Stage          Deploy Stage        
     │                  │
     ├─ Syntax Check    ├─ Deploy MSSQL (manual)
     └─ Ansible Lint    └─ Deploy Backup (manual)
```

### CI/CD Variables (Required)

Set in GitLab Settings → CI/CD → Variables:

| Variable | Value |
|----------|-------|
| `SSH_PRIVATE_KEY` | Your private SSH key (full content) |
| `ANSIBLE_USER` | root |
| `ANSIBLE_PASSWORD` | (optional if using SSH key) |

### Pipeline Definition

```yaml
# .gitlab-ci.yml
stages:
  - lint      # Validate syntax
  - deploy    # Execute playbooks

lint:
  stage: lint
  before_script:
    - Setup SSH key from CI variable
    - Install Ansible

deploy:
  stage: deploy
  when: manual  # Require manual trigger
  only:
    - main    # Only on main branch
```

## Performance Considerations

### Parallel Execution

**Default:** Ansible forks=5 (5 parallel tasks)

**Increase for larger deployments:**
```bash
ansible-playbook ... -f 20
```

### Backup/Restore Performance

**Compression:**
```sql
BACKUP DATABASE ...
WITH FORMAT, COMPRESSION  -- Reduces backup size ~60%
```

**Faster Transfer (Optional Enhancement):**
```yaml
- name: Sync backups (parallel)
  synchronize:
    src: /backup/striped/
    dest: /backup/striped/
    mode: pull
    delete: yes
    rsync_opts:
      - "--compress"
      - "--parallel=10"
```

## Monitoring and Logging

### Ansible Logging

**Enable logging:**
```bash
export ANSIBLE_LOG_PATH=./ansible.log
ansible-playbook playbooks/site.yml
```

**Verbosity levels:**
```bash
-v      # 1 verbose
-vv     # 2 verbose (detailed execution)
-vvv    # 3 verbose (connection debug)
-vvvv   # 4 verbose (script debug)
```

### MSSQL Logs

**View error log:**
```bash
tail -f /var/opt/mssql/log/errorlog
```

**Check service status:**
```bash
systemctl status mssql-server
journalctl -u mssql-server -n 50
```

### Generated Reports

After execution, check:
```
/tmp/mssql_deployment_vm1.txt
/tmp/mssql_deployment_vm2.txt
```

## Disaster Recovery

### Backup Recovery Procedure

**If AdventureWorks is corrupted:**

1. Restore from striped backup on same server:
```bash
ansible vm1 -i inventory/hosts.ini -m shell -a "
  sqlcmd -S localhost -U SA -Q '
  RESTORE DATABASE AdventureWorks FROM DISK=... WITH REPLACE
  '"
```

2. Or re-run full playbook:
```bash
ansible-playbook playbooks/site.yml
```

### VM Recovery

**If VM1 fails:**
1. Restore backups still exist on control machine: `./backups/vm1_striped/`
2. Restore to new VM2 (or replacement VM1)
3. Re-run playbook with new VM IP

**If VM2 fails:**
1. Restore from VM1 backups (kept in /backup/striped/)
2. Provision new VM2
3. Re-run restore playbook

## Maintenance Schedule

### Weekly
- Monitor /var/opt/mssql/log/errorlog
- Verify backup file permissions

### Monthly
- Test restore procedures
- Review and update SA password

### Quarterly
- Review MSSQL security patches
- Test full disaster recovery

## Future Enhancements

1. **High Availability**: Configure Always-On Availability Groups
2. **Database Encryption**: Implement Transparent Data Encryption (TDE)
3. **Monitoring**: Add monitoring with Prometheus/Grafana
4. **Scaling**: Multi-instance deployments
5. **Backup Rotation**: Implement backup lifecycle management
6. **Change Management**: Add change tracking and audit logs

## Testing Strategy

### Pre-Deployment
1. Syntax check: `ansible-playbook --syntax-check`
2. Lint: `ansible-lint playbooks/`
3. Dry-run: `ansible-playbook -C` (check mode)

### Post-Deployment
1. Verify service: `systemctl status mssql-server`
2. Verify database: `sqlcmd -Q "SELECT DB_ID('AdventureWorks')"`
3. Verify backups: `ls -la /backup/striped/`
4. Test restore: Restore backup to test server

### Continuous Testing
- GitLab CI/CD pipeline runs on every commit
- Manual deployment trigger in AWX
- Regular restore drills

## Documentation

- **README.md**: User guide and quick start
- **DESIGN.md**: This document - architecture and design details
- **Code comments**: Inline YAML documentation for each task
- **AWX help**: Built-in AWX documentation for job templates

---

**Document Version**: 1.0  
**Last Updated**: 2026-04-19  
**Author**: DevOps Team  
**Status**: Production Ready
