# MSSQL Deployment Projects - Complete Setup Guide

## Project Overview

Two production-ready projects for MSSQL Server deployment automation on Linux:

1. **ansible-mssql-deploy** - Ansible-based orchestration
2. **python-fastapi-mssql** - Python FastAPI RESTful service

## Directory Structure

```
devops/
├── ansible-mssql-deploy/           # Ansible project
│   ├── roles/mssql/                # Main Ansible role
│   ├── playbooks/                  # site.yml, backup.yml
│   ├── inventory/                  # hosts.ini
│   ├── group_vars/                 # mssql_servers.yml
│   ├── host_vars/                  # vm1.yml, vm2.yml
│   ├── awx/                        # AWX configuration
│   ├── .gitlab-ci.yml              # GitLab CI/CD pipeline
│   ├── README.md                   # Quick start guide
│   ├── DESIGN.md                   # Design documentation
│   └── .gitignore
│
├── python-fastapi-mssql/           # FastAPI project
│   ├── app/                        # FastAPI application
│   │   ├── main.py                 # Entry point
│   │   ├── config.py               # Configuration
│   │   ├── ansible_runner.py       # Ansible integration
│   │   └── routes/                 # API endpoints
│   ├── tests/                      # Unit tests
│   ├── requirements.txt            # Python dependencies
│   ├── Dockerfile                  # Container image
│   ├── docker-compose.yml          # Docker Compose config
│   ├── run.sh                      # Startup script
│   ├── README.md                   # Quick start guide
│   ├── DESIGN.md                   # Design documentation
│   └── .gitignore
│
├── ARCHITECTURE.md                 # Architecture diagrams (this file)
└── SETUP_GUIDE.md                  # Setup instructions (this file)
```

## Quick Comparison

| Feature | Ansible | FastAPI |
|---------|---------|---------|
| **Approach** | Declarative IaC | Imperative API |
| **Setup Time** | 5 minutes | 5 minutes |
| **Learning Curve** | Moderate | Easy (Python) |
| **Enterprise** | Yes (AWX) | No (SMB) |
| **UI** | AWX web UI | API only |
| **Scaling** | Complex | Simple |
| **Best For** | Large orgs | Startups/small teams |
| **Cost** | Free (open source) | Free |

## Prerequisites

### System Requirements

- **OS**: Windows 10 with WSL2 or native Windows (Git Bash)
- **Tools**:
  - Git
  - Python 3.9+ (for FastAPI)
  - Ansible 2.10+ (for both)
  - SSH client
  - Docker (optional)

### Network Requirements

- Two Linux VMs (CentOS 8 or compatible)
  - VM1: 192.168.56.101 (Primary)
  - VM2: 192.168.56.102 (Secondary)
- SSH access to both VMs
- 5GB+ free disk space on each VM

### Credentials Required

- Linux user account with sudo privileges (default: root)
- SSH key pair for authentication

## Installation Steps

### Step 1: Clone or Create Local Repositories

```bash
cd ~/devops

# Create Ansible project
git clone <your-gitlab-ansible-repo> ansible-mssql-deploy
# OR
mkdir -p ansible-mssql-deploy
# ... copy files from created structure

# Create FastAPI project
git clone <your-gitlab-fastapi-repo> python-fastapi-mssql
# OR
mkdir -p python-fastapi-mssql
# ... copy files from created structure
```

### Step 2: Setup SSH Keys

```bash
# Generate SSH key if you don't have one
ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa

# Add public key to both VMs
ssh-copy-id -i ~/.ssh/id_rsa root@192.168.56.101
ssh-copy-id -i ~/.ssh/id_rsa root@192.168.56.102

# Test connectivity
ssh -i ~/.ssh/id_rsa root@192.168.56.101 "echo Connected!"
ssh -i ~/.ssh/id_rsa root@192.168.56.102 "echo Connected!"
```

### Step 3: Configure Ansible Project

```bash
cd ansible-mssql-deploy

# Update inventory with your VM IPs
nano inventory/hosts.ini
# Change IPs if needed:
# vm1 ansible_host=<YOUR_VM1_IP>
# vm2 ansible_host=<YOUR_VM2_IP>

# Update SA password
nano group_vars/mssql_servers.yml
# Change: sa_password: "YourStrongPassword"
# Requirements: 8+ chars, uppercase, lowercase, digit, special char

# Test connectivity
ansible all -i inventory/hosts.ini -m ping
```

### Step 4: Setup FastAPI Project

```bash
cd ../python-fastapi-mssql

# Create Python virtual environment
python -m venv venv

# Activate virtual environment
# On Windows (Git Bash):
source venv/Scripts/activate
# On Windows (PowerShell):
venv\Scripts\Activate.ps1
# On Mac/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
nano .env
# Update paths and credentials

# Create logs directory
mkdir -p logs
```

## Usage

### Option A: Ansible with AWX (Enterprise)

Best for: Large organizations, complex workflows, team collaboration

```bash
cd ansible-mssql-deploy

# 1. Test playbook syntax
ansible-playbook --syntax-check playbooks/site.yml

# 2. Run with dry-run
ansible-playbook -i inventory/hosts.ini playbooks/site.yml -C

# 3. Execute deployment
ansible-playbook -i inventory/hosts.ini playbooks/site.yml -v

# 4. Create backup and restore
ansible-playbook -i inventory/hosts.ini playbooks/backup.yml -v

# 5. Setup in AWX
# See awx/ directory for project, inventory, and job template configs
```

**Setup in AWX:**
1. Create project pointing to your GitLab repo
2. Create inventory from awx/inventory.yml
3. Create credentials with SSH key
4. Create job templates for each playbook
5. Create workflow template combining all job templates
6. Launch from AWX UI or API

### Option B: FastAPI (Lightweight)

Best for: Startups, rapid prototyping, REST API integration

```bash
cd python-fastapi-mssql

# 1. Ensure virtual environment is activated
source venv/Scripts/activate  # Windows Git Bash

# 2. Start FastAPI server
uvicorn app.main:app --reload --port 8000

# 3. Access API documentation
# Open browser: http://localhost:8000/api/docs

# 4. Deploy via API
# In another terminal:
curl -X POST http://localhost:8000/api/v1/deploy/install

# 5. Monitor progress
curl http://localhost:8000/api/v1/logs/latest

# 6. Check history
curl http://localhost:8000/api/v1/deploy/history
```

**Or use Docker:**

```bash
# Build and run with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f mssql-api

# Access at http://localhost:8000

# Stop
docker-compose down
```

## Deployment Workflow

### Full Deployment (Both VMs)

#### Using Ansible:
```bash
cd ansible-mssql-deploy

# Phase 1: Install MSSQL on both VMs
ansible-playbook -i inventory/hosts.ini playbooks/site.yml

# Estimated time: 30-45 minutes
# This includes:
#  - MSSQL Server installation
#  - Configuration
#  - AdventureWorks database restore
#  - 10-stripe backup creation (VM1)
#  - Backup transfer and restore (VM2)
```

#### Using FastAPI:
```bash
# Terminal 1: Start API server
cd python-fastapi-mssql
source venv/Scripts/activate
uvicorn app.main:app --reload

# Terminal 2: Trigger deployment
curl -X POST http://localhost:8000/api/v1/deploy/install

# Terminal 3: Monitor progress
watch -n 5 'curl http://localhost:8000/api/v1/logs/latest | tail -20'
```

### Backup and Restore Only

#### Using Ansible:
```bash
cd ansible-mssql-deploy

ansible-playbook -i inventory/hosts.ini playbooks/backup.yml

# Estimated time: 10-20 minutes
# Creates 10-stripe backup on VM1 and restores on VM2
```

#### Using FastAPI:
```bash
curl -X POST http://localhost:8000/api/v1/deploy/backup

# Monitor progress
curl http://localhost:8000/api/v1/logs/latest?lines=50
```

## Verification

### Verify Installation

```bash
# SSH into VM1
ssh root@192.168.56.101

# Check MSSQL service
systemctl status mssql-server

# Check database
sqlcmd -S localhost -U SA -Q "SELECT DB_ID('AdventureWorks')"

# Check backup files
ls -lah /backup/striped/adv_stripe_*.bak
```

### Verify from API

```bash
# Health check
curl http://localhost:8000/api/v1/health/check

# Deployment status
curl http://localhost:8000/api/v1/deploy/status

# Host connectivity
curl -X POST http://localhost:8000/api/v1/deploy/ping

# Execution history
curl http://localhost:8000/api/v1/deploy/history | jq
```

## GitLab CI/CD Integration

### Setup Pipeline

1. **Create GitLab repository**
   ```bash
   cd ansible-mssql-deploy
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://gitlab.com/YOUR_USERNAME/ansible-mssql-deploy.git
   git push -u origin main
   ```

2. **Add SSH key to CI/CD**
   - Settings → CI/CD → Variables
   - Add `SSH_PRIVATE_KEY` variable with your private SSH key

3. **Pipeline runs automatically**
   - On push: Runs lint and syntax checks
   - Manual trigger: Deploys to production

4. **View pipeline status**
   - CI/CD → Pipelines → Click on pipeline

## Troubleshooting

### SSH Connection Issues

```bash
# Test SSH directly
ssh -v -i ~/.ssh/id_rsa root@192.168.56.101

# Check permissions
chmod 600 ~/.ssh/id_rsa
chmod 644 ~/.ssh/id_rsa.pub

# Verify key on target
ssh root@192.168.56.101 "cat ~/.ssh/authorized_keys | grep $(cat ~/.ssh/id_rsa.pub)"
```

### Ansible Issues

```bash
# Test connectivity
ansible all -i inventory/hosts.ini -m ping

# Run with verbose output
ansible-playbook -i inventory/hosts.ini playbooks/site.yml -vvv

# Check playbook syntax
ansible-playbook --syntax-check playbooks/site.yml

# Validate inventory
ansible-inventory -i inventory/hosts.ini --list
```

### FastAPI Issues

```bash
# Check if Ansible is installed
python -c "import ansible; print(ansible.__version__)"

# Verify inventory path
ls -la ../ansible-mssql-deploy/inventory/hosts.ini

# Check logs
tail -f logs/app.log

# Test health
curl http://localhost:8000/api/v1/health/ready

# Verify system resources
curl http://localhost:8000/api/v1/health/ready | jq '.checks'
```

### MSSQL Issues

```bash
# On target VM
ssh root@192.168.56.101

# Check service status
systemctl status mssql-server

# View error log
tail -100 /var/opt/mssql/log/errorlog

# Check port 1433 is listening
netstat -tlnp | grep 1433

# Test connectivity
sqlcmd -S localhost -U SA -Q "SELECT @@VERSION"
```

## Best Practices

### Security

1. **Use SSH keys** - Never use passwords for Ansible
2. **Rotate credentials** - Change SA password regularly
3. **Use Ansible Vault** - Encrypt sensitive variables
4. **Restrict access** - Firewall rules on VMs
5. **Monitor logs** - Regular audit of deployment logs

### Operations

1. **Test first** - Use `-C` flag for dry-run
2. **Backup before changes** - Create snapshots of VMs
3. **Monitor deployment** - Watch logs in real-time
4. **Document changes** - Keep changelog of deployments
5. **Schedule maintenance** - Run deployments during maintenance window

### Development

1. **Version control** - Keep all code in Git
2. **Test in staging** - Deploy to test VMs first
3. **Code review** - Have playbooks reviewed before production
4. **CI/CD pipeline** - Automate testing and linting
5. **Document changes** - Update README for new features

## Scaling Considerations

### Small Team (Current Setup)
- Single control machine
- Manual deployment triggers
- Suitable for 1-10 deployments/month

### Medium Team (Add AWX)
- AWX instance for orchestration
- Scheduled deployments
- RBAC and audit logs
- Suitable for 10-50 deployments/month

### Large Organization (Enterprise)
- Multiple AWX instances
- Distributed ansible-runner nodes
- Centralized logging and monitoring
- Suitable for 50+ deployments/month

## Support & Resources

### Documentation
- [Ansible Documentation](https://docs.ansible.com/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Microsoft MSSQL on Linux](https://docs.microsoft.com/en-us/sql/linux/sql-server-linux-setup)
- [Project README files](./ansible-mssql-deploy/README.md)

### Community
- Ansible: https://github.com/ansible/ansible
- FastAPI: https://github.com/tiangolo/fastapi
- MSSQL: https://github.com/microsoft/mssql-docker

### Troubleshooting
1. Check project README.md for common issues
2. Check DESIGN.md for architecture understanding
3. Review logs: `/var/opt/mssql/log/errorlog`
4. Test connectivity: `ansible all -i inventory -m ping`
5. Run with verbose: `-vvv` flag

## Next Steps

1. ✅ Setup SSH keys and test connectivity
2. ✅ Configure Ansible inventory and variables
3. ✅ Run playbook on test VMs
4. ✅ Verify MSSQL installation
5. ✅ Test backup and restore
6. ✅ Deploy via AWX or FastAPI
7. ✅ Setup GitLab CI/CD pipeline
8. ✅ Document custom changes
9. ✅ Train team on deployment process
10. ✅ Schedule regular testing and maintenance

---

**Version**: 1.0  
**Last Updated**: 2026-04-19  
**Status**: Production Ready
