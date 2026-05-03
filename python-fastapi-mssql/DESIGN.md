# MSSQL FastAPI Deployment - Design Document

> Note: The implementation has been refactored so FastAPI uses native Python SSH
> via Paramiko instead of Ansible. This generated design document still contains
> historical Ansible-runner detail and should be refreshed before relying on it
> as the source of truth.

## Overview

This document describes the architecture, design patterns, and implementation details of the Python FastAPI-based MSSQL Server deployment automation service.

## Business Objectives

1. **API-First Architecture**: Provide RESTful API for MSSQL deployment automation
2. **Lightweight Alternative**: Python-based alternative to AWX for smaller deployments
3. **Asynchronous Execution**: Support long-running deployments without blocking
4. **Monitoring & Logging**: Real-time logs and execution history
5. **Easy Integration**: Simple HTTP interface for custom workflows

## System Architecture

```
┌────────────────────────────────────────────────────────┐
│           Client Layer                                  │
├──────────────────────────────────────────────────────┤
│  curl / Postman / Custom App / CI/CD Pipeline         │
└────────────────────────────────────────────────────────┘
                        │
                        ↓ HTTP/REST
┌────────────────────────────────────────────────────────┐
│         FastAPI Web Server (uvicorn)                    │
│                                                         │
│  ┌──────────────────────────────────────────────────┐ │
│  │  API Routes                                      │ │
│  │  ├─ /deploy        (Deployment operations)      │ │
│  │  ├─ /health        (Health checks)              │ │
│  │  └─ /logs          (Logging & monitoring)       │ │
│  └──────────────────────────────────────────────────┘ │
│                       │                                │
│  ┌──────────────────────────────────────────────────┐ │
│  │  Background Task Queue (asyncio)                 │ │
│  │  └─ Long-running deployments run here           │ │
│  └──────────────────────────────────────────────────┘ │
│                       │                                │
└─────────────────────┬─────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        ↓             ↓             ↓
┌─────────────────┐ ┌──────────────────┐ ┌──────────────┐
│  AnsibleRunner  │ │  Log Handler     │ │ Config Mgr   │
│                 │ │                  │ │              │
│ - Run playbooks │ │ - File logging   │ │ - Settings   │
│ - Ping hosts    │ │ - Log filtering  │ │ - Inventory  │
│ - Get inventory │ │ - Log retrieval  │ │ - Secrets    │
└────────┬────────┘ └──────────────────┘ └──────────────┘
         │
         ↓
┌─────────────────────────────────────────────────────┐
│    Ansible (Orchestrator)                           │
│                                                     │
│  ansible-playbook / ansible-inventory /            │
│  ansible module execution                          │
└────────────┬────────────────────────────────────────┘
             │
    ┌────────┴────────┐
    ↓                 ↓
┌─────────────────┐ ┌──────────────────┐
│      VM1        │ │       VM2        │
│   (Primary)     │ │   (Secondary)    │
│                 │ │                  │
│  MSSQL 2019     │ │  MSSQL 2019      │
│  Instance 1     │ │  Instance 2      │
│                 │ │                  │
│  Backup 10x ════╩══ Restore 10x      │
│  Striped        │  Striped          │
│  AdventureWorks │  AdventureWorks   │
└─────────────────┘ └──────────────────┘
```

## Core Components

### 1. FastAPI Application (main.py)

```python
# Application initialization
app = FastAPI(
    title="MSSQL Deployment API",
    version="1.0.0",
    docs_url="/api/docs"
)

# Router includes
app.include_router(deploy.router)  # Deployment endpoints
app.include_router(health.router)  # Health endpoints
app.include_router(logs.router)    # Logging endpoints
```

**Key Features:**
- OpenAPI documentation at `/api/docs`
- Exception handling middleware
- Request/response logging
- CORS support ready (future enhancement)

### 2. Configuration (config.py)

```python
class Settings(BaseSettings):
    # Application
    APP_NAME: str = "MSSQL Deployment API"
    DEBUG: bool = False
    
    # Deployment
    ANSIBLE_INVENTORY: str = "../ansible-mssql-deploy/inventory/hosts.ini"
    ANSIBLE_PLAYBOOK_DIR: str = "../ansible-mssql-deploy/playbooks"
    
    # MSSQL
    MSSQL_SA_PASSWORD: str = "YourStr0ng!Passw0rd"
    MSSQL_VERSION: str = "2019"
    
    # VMs
    VM1_IP: str = "192.168.56.101"
    VM2_IP: str = "192.168.56.102"
    
    # API
    API_TIMEOUT: int = 3600  # 1 hour
```

**Loading Order:**
1. Environment variables (highest priority)
2. `.env` file
3. Default values in Settings class (lowest priority)

### 3. Ansible Integration (ansible_runner.py)

```python
class AnsibleRunner:
    def run_playbook(
        self,
        playbook_name: str,
        tags: Optional[List[str]] = None,
        limit: Optional[str] = None,
        extra_vars: Optional[Dict] = None,
        verbose: int = 1
    ) -> Dict:
        """Execute Ansible playbook"""
        # Build command
        # Execute subprocess
        # Capture output
        # Return results
```

**Methods:**
- `run_playbook()` - Execute playbook with options
- `validate_inventory()` - Verify inventory configuration
- `get_inventory()` - Retrieve inventory details
- `ping_hosts()` - Test connectivity to hosts

**Command Building:**
```bash
# Generated command example
ansible-playbook \
  -i ../ansible-mssql-deploy/inventory/hosts.ini \
  -vv \
  -t install,configure \
  -l vm1 \
  -e '{"sa_password":"..."}' \
  ../ansible-mssql-deploy/playbooks/site.yml
```

**Process Flow:**
1. Build command from parameters
2. Execute with subprocess.run()
3. Capture stdout/stderr
4. Parse results
5. Store in execution history
6. Return to caller

### 4. Deployment Routes (routes/deploy.py)

```python
@app.post("/deploy/install")
async def deploy_install(background_tasks: BackgroundTasks):
    """Install MSSQL - runs in background"""
    
    def run_deployment():
        result = ansible_runner.run_playbook("site.yml")
    
    background_tasks.add_task(run_deployment)
    return {"status": "initiated", ...}
```

**Endpoints:**
- `POST /deploy/install` - Full MSSQL deployment
- `POST /deploy/backup` - Backup and restore
- `POST /deploy/install-tools` - Tools only
- `POST /deploy/restore-db` - Database restore only
- `GET /deploy/status` - Current status
- `GET /deploy/hosts` - Inventory hosts
- `GET /deploy/history` - Execution history
- `POST /deploy/ping` - Test connectivity

**Key Pattern: Background Tasks**
```python
# API returns immediately
background_tasks.add_task(long_running_function)
return {"status": "initiated"}  # 202 Accepted

# Client polls for status
GET /deploy/history  # Check progress
GET /logs/latest     # View logs
```

### 5. Health Checks (routes/health.py)

```python
@app.get("/health/check")
async def health_check():
    """Basic health - API is running"""

@app.get("/health/ready")
async def readiness_check():
    """Readiness - dependencies configured"""
    # Check Ansible installed
    # Check inventory accessible
    # Check disk space (>5GB)
    # Check system resources

@app.get("/health/live")
async def liveness_check():
    """Liveness - API is alive"""
```

**Dependency Checks:**
1. **Ansible**: Verify installation and version
2. **Inventory**: File exists and readable
3. **Disk Space**: Minimum 5GB available
4. **System Resources**: CPU <90%, Memory <90%

### 6. Logging (routes/logs.py)

```python
@app.get("/logs/latest")
async def get_latest_logs(lines: int = 100):
    """Last N log lines"""

@app.get("/logs/level/{level}")
async def get_logs_by_level(level: str = "ERROR"):
    """Filter by log level"""

@app.get("/logs/since")
async def get_logs_since(minutes: int = 30):
    """Logs from last N minutes"""

@app.post("/logs/clear")
async def clear_logs():
    """Clear all logs"""
```

**Log Management:**
- Real-time file-based logging
- Filtering by level or time
- Access from API endpoints
- Log information retrieval

## Request/Response Flow

### Example: Full Deployment

```
1. Client Request
   ↓
   POST /api/v1/deploy/install
   
2. API Route Handler (deploy.py)
   ├─ Receive request
   ├─ Validate parameters
   ├─ Create background task
   └─ Return 202 Accepted
   
   Response: {
     "status": "initiated",
     "message": "MSSQL installation started",
     "playbook": "site.yml",
     "estimated_duration_minutes": 45
   }

3. Background Task Execution
   ├─ Prepare variables
   ├─ Call ansible_runner.run_playbook()
   │  ├─ Build ansible-playbook command
   │  ├─ Execute subprocess
   │  ├─ Capture output
   │  └─ Store execution record
   └─ Complete (execution continues after client disconnect)

4. Client Monitoring
   ├─ GET /api/v1/logs/latest
   │  ↓ Get latest 100 log lines
   │  ✓ View real-time progress
   │
   ├─ GET /api/v1/deploy/status
   │  ↓ Get deployment status
   │  ✓ View configuration
   │
   └─ GET /api/v1/deploy/history
      ↓ Get execution history
      ✓ View past executions
```

## Data Structures

### Execution Record

```python
{
    "playbook": "site.yml",
    "status": "success|failed|timeout|error",
    "return_code": 0,
    "stdout": "ansible output",
    "stderr": "error output (if any)",
    "timestamp": "2026-04-19T15:30:00.000000",
    "command": "ansible-playbook -i ... playbooks/site.yml"
}
```

### Inventory Structure

```python
{
    "_meta": {
        "hostvars": {
            "vm1": {
                "ansible_host": "192.168.56.101",
                "instance_name": "instance1"
            },
            "vm2": {
                "ansible_host": "192.168.56.102",
                "instance_name": "instance2"
            }
        }
    },
    "mssql_servers": {
        "hosts": ["vm1", "vm2"]
    }
}
```

### Health Status

```python
{
    "ready": True,
    "timestamp": "2026-04-19T15:30:00",
    "checks": {
        "ansible": {
            "ready": True,
            "version": "2.10.7"
        },
        "inventory": {
            "ready": True,
            "path": "/path/to/inventory"
        },
        "disk_space": {
            "ready": True,
            "available_gb": 50.5,
            "total_gb": 100
        },
        "system_resources": {
            "ready": True,
            "cpu_percent": 25,
            "memory_percent": 45
        }
    }
}
```

## Async/Background Task Pattern

### Why Background Tasks?

MSSQL deployment takes 30-60 minutes. Without background tasks:
- HTTP request would timeout
- Client connection would hang
- Server resources blocked

**Solution: Background Tasks**

```python
@app.post("/deploy/install")
async def deploy_install(background_tasks: BackgroundTasks):
    # Define long-running task
    def run_deployment():
        result = ansible_runner.run_playbook("site.yml")
        # Task completes asynchronously
    
    # Schedule task
    background_tasks.add_task(run_deployment)
    
    # Return immediately to client
    return {"status": "initiated"}  # HTTP 202 Accepted
```

### Client Monitoring

```python
# Client polls for status
while True:
    response = requests.get("/api/v1/logs/latest")
    print(response.json()["logs"])
    
    response = requests.get("/api/v1/deploy/history")
    latest = response.json()["executions"][-1]
    
    if latest["status"] in ["success", "failed", "error"]:
        break
    
    time.sleep(10)  # Poll every 10 seconds
```

## Deployment Phases

### Phase 1: Install MSSQL

```
POST /deploy/install
  ↓
run_playbook("site.yml")
  ├─ install.yml
  │  ├─ Install dependencies
  │  ├─ Add repositories
  │  ├─ Install mssql-server
  │  ├─ Install mssql-tools
  │  ├─ Configure MSSQL
  │  ├─ Start service
  │  └─ Verify installation
  │
  ├─ configure.yml
  │  ├─ Create directories
  │  ├─ Set paths
  │  ├─ Configure network
  │  └─ Enable SQL Agent
  │
  ├─ adventureworks.yml
  │  ├─ Download backup
  │  ├─ Restore database
  │  └─ Verify DB
  │
  ├─ backup.yml (VM1 only)
  │  ├─ Create /backup/striped
  │  └─ Create 10-stripe backup
  │
  └─ restore.yml (VM2 only)
     ├─ Fetch backups from VM1
     ├─ Copy to VM2
     └─ Restore on VM2
```

### Phase 2: Backup & Restore

```
POST /deploy/backup
  ↓
run_playbook("backup.yml")
  ├─ On VM1:
  │  └─ fetch module
  │     └─ Pull /backup/striped/* to control machine
  │
  └─ On VM2:
     ├─ copy module
     │  └─ Push fetched files to /backup/striped/
     │
     └─ RESTORE DATABASE
        └─ Restore from 10-stripe backup
```

## Error Handling

### Retry Logic

```python
result = subprocess.run(
    cmd,
    capture_output=True,
    text=True,
    timeout=3600  # 1 hour
)
```

### Timeout Handling

```python
try:
    result = subprocess.run(cmd, timeout=3600)
except subprocess.TimeoutExpired:
    return {
        "status": "timeout",
        "error": "Playbook execution exceeded 1 hour"
    }
```

### Execution History

All executions stored regardless of outcome:
- Success ✓
- Failure ✗
- Timeout ⏱
- Error 💥

Clients can query history to diagnose issues.

## Security Considerations

### 1. SSH Authentication

```python
# Ansible uses SSH keys
inventory_vars = {
    "ansible_ssh_private_key_file": "~/.ssh/id_rsa",
    "ansible_user": "root"
}
```

**Setup:**
```bash
ssh-keygen -t rsa -b 4096
ssh-copy-id -i ~/.ssh/id_rsa root@192.168.56.101
```

### 2. Password Management

```python
# Sensitive variables from environment
sa_password = os.getenv("MSSQL_SA_PASSWORD")

# Pass to Ansible
extra_vars = {
    "sa_password": sa_password
}
```

**Best Practice:**
- Never commit `.env` file
- Use `.env.example` as template
- Store secrets in environment or vault

### 3. Input Validation

```python
# Validate log level parameter
valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
if level.upper() not in valid_levels:
    raise HTTPException(status_code=400)
```

### 4. Rate Limiting (Future)

```python
# Add rate limiting to prevent abuse
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/deploy/install")
@limiter.limit("1/minute")
async def deploy_install():
    pass
```

## Performance Optimization

### 1. Concurrent Requests

```python
# FastAPI handles concurrent requests with asyncio
# Multiple clients can call API simultaneously

# Each long-running task is in background
# Doesn't block other requests
```

### 2. Background Task Queue

```python
# Could be enhanced with Celery/RabbitMQ
# Current implementation uses asyncio

# For large scale:
from celery import Celery

celery_app = Celery('tasks')

@celery_app.task
def run_deployment():
    pass
```

### 3. Caching (Future)

```python
# Cache inventory data
from functools import lru_cache

@lru_cache(maxsize=1)
def get_inventory_cached():
    return ansible_runner.get_inventory()
```

## Deployment

### Development

```bash
# With auto-reload
uvicorn app.main:app --reload --port 8000

# Logs in console
# Auto-reloads on file changes
```

### Production

```bash
# Multiple workers
uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 4 \
  --loop uvloop \
  --log-level info
```

### Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y ansible openssh-client
RUN pip install -r requirements.txt

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Monitoring & Observability

### Application Logs

```python
# Logging configuration
import logging

logger = logging.getLogger(__name__)
logger.info("Deployment started")
logger.error("Error occurred")
```

### Metrics

```python
# Execution history provides metrics
GET /api/v1/deploy/history
{
    "total_executions": 5,
    "executions": [
        {"status": "success", ...},
        {"status": "failed", ...}
    ]
}
```

### Health Dashboard

```bash
# Create simple dashboard
GET /api/v1/health/ready
GET /api/v1/deploy/status
GET /api/v1/logs/latest
```

## Testing

### Unit Tests

```python
# tests/test_api.py
def test_health_check(client):
    response = client.get("/api/v1/health/check")
    assert response.status_code == 200

def test_deployment_status(client):
    response = client.get("/api/v1/deploy/status")
    assert "mssql_version" in response.json()
```

### Integration Tests

```python
# Test full flow
def test_full_deployment(client):
    # 1. Check health
    r = client.get("/api/v1/health/ready")
    assert r.json()["ready"] == True
    
    # 2. Initiate deployment
    r = client.post("/api/v1/deploy/install")
    assert r.status_code == 202
    
    # 3. Check history
    r = client.get("/api/v1/deploy/history")
    assert len(r.json()["executions"]) > 0
```

### Load Testing

```bash
# Using wrk tool
wrk -t4 -c100 -d30s http://localhost:8000/api/v1/health/check
```

## Scaling Considerations

### Single Server (Current)

- Handles 10-20 concurrent deployments
- Background tasks queued in memory
- Suitable for small teams

### Multiple Servers (Future)

```python
# Add distributed task queue
from celery import Celery

app = Celery('mssql')
app.conf.broker_url = 'redis://localhost:6379'

@app.task
def deploy_mssql():
    pass
```

- Redis/RabbitMQ message broker
- Celery workers on multiple servers
- Better for large deployments

## Future Enhancements

1. **Database**: Store execution history in database
2. **Webhooks**: Notify on deployment completion
3. **Authentication**: API key or OAuth2
4. **Rate Limiting**: Prevent abuse
5. **Scheduling**: Schedule deployments
6. **Workflows**: Define multi-step workflows
7. **Rollback**: Automatic rollback on failure
8. **Notifications**: Email/Slack alerts

## Architecture Comparison: FastAPI vs AWX

| Aspect | FastAPI | AWX |
|--------|---------|-----|
| Complexity | Simple | Complex |
| Learning Curve | Easy | Steep |
| Resources | Lightweight | Heavy |
| Setup Time | Minutes | Hours |
| UI | API only | Full UI |
| Scaling | Simple | Complex |
| Enterprise Features | Basic | Advanced |
| Use Case | Small teams | Enterprise |

---

**Document Version**: 1.0  
**Last Updated**: 2026-04-19  
**Author**: DevOps Team  
**Status**: Production Ready
