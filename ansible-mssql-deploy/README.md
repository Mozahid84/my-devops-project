# MSSQL Server Deployment - Ansible

> Current setup note: for your VMware environment, use the root
> `SETUP_GUIDE.md`. This Ansible project is driven from AWX on `devops_AWX`
> against `devops_VM1` and `devops_VM2`, with GitLab as the source repo.

## Quick Start

```bash
# Clone the full repository
git clone https://gitlab.com/mozahidhossaingitlab-group/my-devops-project.git
cd my-devops-project/ansible-mssql-deploy

# Inventory already uses devops_VM1 and devops_VM2
nano inventory/hosts.ini

# Update SA password in group_vars/mssql_servers.yml
nano group_vars/mssql_servers.yml

# Run the playbook
ansible-playbook -i inventory/hosts.ini playbooks/site.yml -v
```

## Prerequisites

- **Ansible**: >= 2.10
- **Target OS**: CentOS 8 / RHEL 8 compatible
- **SSH Access**: To both VMs with sudo privileges
- **Network**: VMs reachable from control host

## Project Structure

```
ansible-mssql-deploy/
├── roles/
│   └── mssql/
│       ├── tasks/
│       │   ├── main.yml           # Task orchestration
│       │   ├── install.yml        # MSSQL installation
│       │   ├── configure.yml      # MSSQL configuration
│       │   ├── adventureworks.yml # Database restore
│       │   ├── backup.yml         # 10-stripe backup creation
│       │   └── restore.yml        # Backup transfer & restore
│       ├── handlers/
│       │   └── main.yml           # Service handlers
│       ├── defaults/
│       │   └── main.yml           # Default variables
│       └── [templates, files, vars/]
│
├── playbooks/
│   ├── site.yml      # Main deployment playbook
│   └── backup.yml    # Backup & restore playbook
│
├── inventory/
│   └── hosts.ini     # Inventory file with VM details
│
├── group_vars/
│   └── mssql_servers.yml  # Group variables
│
├── host_vars/
│   ├── vm1.yml       # VM1 specific variables
│   └── vm2.yml       # VM2 specific variables
│
├── awx/              # AWX configuration files
│   ├── project.yml
│   ├── inventory.yml
│   ├── credentials.yml
│   └── job-template.yml
│
├── .gitlab-ci.yml    # CI/CD pipeline
└── README.md         # This file
```

## Configuration

### 1. Update Inventory

Edit `inventory/hosts.ini`:
```ini
[mssql_servers]
vm1 ansible_host=devops_VM1
vm2 ansible_host=devops_VM2

[mssql_servers:vars]
ansible_user=root                 # SSH user
ansible_ssh_private_key_file=~/.ssh/id_rsa
```

### 2. Update Password

Edit `group_vars/mssql_servers.yml`:
```yaml
sa_password: "YourVeryStrong!Passw0rd"  # Must be strong!
```

**Password Requirements:**
- Minimum 8 characters
- Must contain uppercase, lowercase, number, and special character
- Examples: `MyStr0ng!Pwd`, `P@ssw0rd123`

### 3. SSH Key Setup

```bash
# Generate SSH key if you don't have one
ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa

# Copy key to VMs
ssh-copy-id -i ~/.ssh/id_rsa root@devops_VM1
ssh-copy-id -i ~/.ssh/id_rsa root@devops_VM2
```

## Usage

### Complete Deployment

Installs MSSQL, configures, restores AdventureWorks, and creates backup:

```bash
ansible-playbook -i inventory/hosts.ini playbooks/site.yml -v
```

### Backup and Restore Only

After initial deployment, create backup on VM1 and restore on VM2:

```bash
ansible-playbook -i inventory/hosts.ini playbooks/backup.yml -v
```

### Run Specific Tasks with Tags

```bash
# Only install
ansible-playbook -i inventory/hosts.ini playbooks/site.yml -t install

# Only configure
ansible-playbook -i inventory/hosts.ini playbooks/site.yml -t configure

# Only restore AdventureWorks
ansible-playbook -i inventory/hosts.ini playbooks/site.yml -t adventureworks

# Only backup and restore
ansible-playbook -i inventory/hosts.ini playbooks/site.yml -t backup,restore
```

## Execution Flow

### Phase 1: Installation (site.yml)
1. **Install Dependencies**: curl, wget, gnupg, libsodium
2. **Add Repositories**: Microsoft SQL Server and Tools repos
3. **Install MSSQL Server**: Latest version specified
4. **Run MSSQL Setup**: Configure with SA password
5. **Start Service**: Enable and start mssql-server

### Phase 2: Configuration
1. Create backup, data, and log directories
2. Set MSSQL default paths
3. Configure network port (default 1433)
4. Enable SQL Server Agent

### Phase 3: Database
1. Download AdventureWorks 2019 backup
2. Restore to MSSQL instance
3. Verify database exists

### Phase 4: Backup (VM1 Only)
1. Create /backup/striped directory
2. Execute BACKUP DATABASE with 10 disk stripes
3. Verify all 10 files created

### Phase 5: Restore (VM2 Only)
1. Fetch backup files from VM1 to control machine
2. Copy files to VM2 /backup/striped/
3. Execute RESTORE DATABASE from all 10 stripes
4. Verify AdventureWorks restored

## Verification

### Check MSSQL Installation
```bash
ansible all -i inventory/hosts.ini -m shell -a "sqlcmd -S localhost -U SA -Q 'SELECT @@VERSION'"
```

### Check AdventureWorks Database
```bash
ansible all -i inventory/hosts.ini -m shell -a "sqlcmd -S localhost -U SA -Q 'SELECT DB_ID(\"AdventureWorks\")'"
```

### Check Backup Files
```bash
ansible mssql_servers -i inventory/hosts.ini -m find -a "path=/backup/striped patterns='*.bak'"
```

## AWX Integration

### Setup in AWX

1. **Create Project**
   - Name: `mssql-deploy`
   - SCM Type: Git
   - SCM URL: Your GitLab repo URL
   - Branch: main

2. **Create Inventory**
   - Import from `awx/inventory.yml`
   - Or use file-based inventory

3. **Create Credentials**
   - Type: Machine
   - Username: root
   - SSH Key: Your private key

4. **Create Job Templates**
   - `MSSQL-Deploy-Install`: playbooks/site.yml
   - `MSSQL-Backup-Striped`: playbooks/backup.yml

5. **Create Workflow Template**
   - Link: Install → Backup → Restore

### Launch from AWX

```bash
# In AWX UI
Projects → mssql-deploy → Launch

# Or via AWX API
curl -k -X POST https://awx.local/api/v2/job_templates/XX/launch/ \
  --user admin:password
```

## GitLab CI/CD

### Setup Pipeline

1. Add SSH key to GitLab CI/CD variables:
   - Settings → CI/CD → Variables
   - `SSH_PRIVATE_KEY`: Your private SSH key

2. Pipeline stages:
   - **lint**: Syntax check and ansible-lint
   - **deploy**: Run playbooks (manual trigger)

### Run Pipeline

```bash
# Push to main branch to trigger lint
git push origin main

# Manually trigger deploy in GitLab UI
# Or use GitLab API:
curl -X POST --header "PRIVATE-TOKEN: YOUR_TOKEN" \
  "https://gitlab.com/api/v4/projects/ID/pipeline" \
  --form ref=main
```

## Troubleshooting

### SSH Connection Fails
```bash
# Test SSH connectivity
ansible all -i inventory/hosts.ini -m ping

# Check SSH key permissions
ls -la ~/.ssh/id_rsa
# Should be 600
```

### MSSQL Service Won't Start
```bash
# Check service status on VM
systemctl status mssql-server

# View service logs
journalctl -u mssql-server -n 50

# Check password strength
# SA password must contain: uppercase, lowercase, number, special char
```

### Backup/Restore Fails
```bash
# Verify sqlcmd connectivity
sqlcmd -S localhost -U SA -Q "SELECT @@VERSION"

# Check file permissions
ls -la /backup/striped/

# View SQL error log
tail -f /var/opt/mssql/log/errorlog
```

### Run with Increased Verbosity
```bash
# Verbose mode
ansible-playbook -i inventory/hosts.ini playbooks/site.yml -vv

# Very verbose (debug mode)
ansible-playbook -i inventory/hosts.ini playbooks/site.yml -vvv
```

## Security Considerations

### Use Ansible Vault for Passwords

```bash
# Create vault password file
echo "vault_password_here" > ~/.vault_pass

# Encrypt variables
ansible-vault encrypt group_vars/mssql_servers.yml --vault-password-file ~/.vault_pass

# Run playbook with vault
ansible-playbook -i inventory/hosts.ini playbooks/site.yml \
  --vault-password-file ~/.vault_pass
```

### Use SSH Keys Instead of Passwords
Always configure SSH key authentication (already recommended in inventory).

### Restrict File Permissions
```bash
# Backup files should be restricted
chmod 600 /backup/striped/*.bak
```

## Performance Optimization

### Parallel Execution
Ansible runs tasks in parallel by default (forks=5). Increase if needed:
```bash
ansible-playbook -i inventory/hosts.ini playbooks/site.yml -f 10
```

### Faster Backup/Restore with Synchronize
Edit `tasks/restore.yml` to use `synchronize` instead of `fetch/copy`:
```yaml
- name: Sync backup files (faster)
  synchronize:
    src: "{{ backup_dir }}/striped/"
    dest: "{{ backup_dir }}/striped/"
    mode: pull
  when: inventory_hostname == "vm2"
```

## Maintenance

### Scheduled Backups
Add to crontab:
```bash
0 2 * * * ansible-playbook -i /path/to/inventory/hosts.ini /path/to/playbooks/backup.yml
```

### Log Rotation
Configure logrotate for MSSQL error logs:
```bash
/var/opt/mssql/log/errorlog {
  daily
  rotate 7
  compress
  delaycompress
  missingok
}
```

## Advanced Topics

### Custom Database Restore
Edit `tasks/adventureworks.yml` to restore different databases:
```yaml
- name: Restore custom database
  shell: |
    sqlcmd -S localhost -U SA -P "{{ sa_password }}" << EOF
    RESTORE DATABASE YourDatabase
    FROM DISK = '/path/to/backup.bak'
    WITH MOVE 'LogicalName' TO '{{ data_dir }}/physical.mdf'
    EOF
```

### High Availability Setup
Extend playbooks for Always-On or Mirroring:
```yaml
# tasks/ha.yml
- name: Configure Availability Groups
  shell: |
    sqlcmd -S localhost -U SA -Q "
    CREATE AVAILABILITY GROUP AG1
    WITH (AUTOMATED_BACKUP_PREFERENCE = SECONDARY)
    "
```

### Database Encryption (TDE)
```yaml
- name: Enable TDE
  shell: |
    sqlcmd -S localhost -U SA -Q "
    CREATE MASTER KEY ENCRYPTION BY PASSWORD = 'MasterKey123'
    "
```

## Contributing

1. Create feature branch: `git checkout -b feature/xyz`
2. Make changes and test
3. Run lint: `ansible-lint playbooks/`
4. Push and create merge request

## Support

For issues and questions:
- Check Troubleshooting section above
- Review Ansible logs: `ansible-playbook ... -vvv`
- Review MSSQL error log on VMs

## License

MIT License - See LICENSE file

## Version

- **Version**: 1.0.0
- **Last Updated**: 2026-04-19
- **Ansible**: >= 2.10
- **MSSQL**: 2019
- **OS**: CentOS 8 / RHEL 8
