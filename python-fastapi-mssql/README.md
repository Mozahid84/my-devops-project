# MSSQL Server Deployment - Python FastAPI

This service uses native Python SSH execution through Paramiko. It does not call
Ansible. Keep Ansible/AWX for the GitLab-driven infrastructure path, and use
this API when you want lightweight REST operations directly from Python.

## Quick Start

```bash
# Clone the full repository
git clone https://gitlab.com/mozahidhossaingitlab-group/my-devops-project.git
cd my-devops-project/python-fastapi-mssql

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export VM1_HOST="192.168.70.129"
export VM2_HOST="192.168.70.130"
export SSH_KEY_PATH="~/.ssh/id_rsa"
export MSSQL_SA_PASSWORD="YourStr0ng!Passw0rd"

# Run FastAPI server
uvicorn app.main:app --reload
```

Server runs at `http://localhost:8000`
API docs at `http://localhost:8000/api/docs`

## Alternative: Docker

```bash
# Build and run with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f mssql-api

# Stop
docker-compose down
```

## Project Structure

```
python-fastapi-mssql/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── config.py            # Configuration settings
│   ├── python_deployer.py   # Native Python SSH deployment workflow
│   └── routes/
│       ├── __init__.py
│       ├── deploy.py        # Deployment endpoints
│       ├── health.py        # Health check endpoints
│       └── logs.py          # Logging endpoints
│
├── tests/
│   ├── __init__.py
│   └── test_api.py          # API tests
│
├── requirements.txt         # Python dependencies
├── docker-compose.yml       # Docker Compose config
├── Dockerfile              # Docker image config
├── run.sh                  # Startup script
├── .env.example           # Environment template
└── README.md              # This file
```

## API Endpoints

### Deployment (POST)

#### `/api/v1/deploy/install`
Install and configure MSSQL on all servers. Long-running operation.

```bash
curl -X POST http://localhost:8000/api/v1/deploy/install
```

Response:
```json
{
  "status": "initiated",
  "message": "MSSQL installation started",
  "playbook": "site.yml",
  "estimated_duration_minutes": 45
}
```

#### `/api/v1/deploy/backup`
Create 10-stripe backup on VM1 and transfer to VM2.

```bash
curl -X POST http://localhost:8000/api/v1/deploy/backup
```

#### `/api/v1/deploy/install-tools`
Install MSSQL tools (sqlcmd) only.

```bash
curl -X POST http://localhost:8000/api/v1/deploy/install-tools
```

#### `/api/v1/deploy/restore-db`
Restore AdventureWorks database only.

```bash
curl -X POST http://localhost:8000/api/v1/deploy/restore-db
```

### Deployment Status (GET)

#### `/api/v1/deploy/status`
Get current deployment status and configuration.

```bash
curl http://localhost:8000/api/v1/deploy/status
```

#### `/api/v1/deploy/hosts`
Get target host information from inventory.

```bash
curl http://localhost:8000/api/v1/deploy/hosts
```

#### `/api/v1/deploy/history`
Get deployment execution history.

```bash
curl http://localhost:8000/api/v1/deploy/history
```

#### `/api/v1/deploy/ping`
Ping all target hosts to verify connectivity.

```bash
curl -X POST http://localhost:8000/api/v1/deploy/ping
```

### Health Checks (GET)

#### `/api/v1/health/check`
Basic health check - API is running.

```bash
curl http://localhost:8000/api/v1/health/check
```

#### `/api/v1/health/ready`
Readiness check - all dependencies are ready.

```bash
curl http://localhost:8000/api/v1/health/ready
```

#### `/api/v1/health/live`
Liveness check - API is alive.

```bash
curl http://localhost:8000/api/v1/health/live
```

### Logs (GET/POST)

#### `/api/v1/logs/latest`
Get latest log entries (last 100 lines).

```bash
curl "http://localhost:8000/api/v1/logs/latest?lines=100"
```

#### `/api/v1/logs/level/{level}`
Get logs filtered by level (DEBUG, INFO, WARNING, ERROR, CRITICAL).

```bash
curl http://localhost:8000/api/v1/logs/level/ERROR
```

#### `/api/v1/logs/since`
Get logs from last N minutes.

```bash
curl "http://localhost:8000/api/v1/logs/since?minutes=30"
```

#### `/api/v1/logs/info`
Get log file information.

```bash
curl http://localhost:8000/api/v1/logs/info
```

#### `/api/v1/logs/clear`
Clear all logs.

```bash
curl -X POST http://localhost:8000/api/v1/logs/clear
```

## Configuration

### Environment Variables

Create `.env` file from `.env.example`:

```bash
# MSSQL
MSSQL_SA_PASSWORD=YourStr0ng!Passw0rd
MSSQL_VERSION=2019
MSSQL_EDITION=Developer

# VMs
VM1_HOST=192.168.70.129
VM2_HOST=192.168.70.130
VM1_USER=root
VM2_USER=root
SSH_KEY_PATH=~/.ssh/id_rsa
SSH_PASSWORD=

# Backup
BACKUP_DIR=/backup
BACKUP_STRIPES=10

# Logging
LOG_LEVEL=INFO
LOG_DIR=./logs

# API
API_TIMEOUT=3600
DEBUG=False
```

### Configuration File

Settings are loaded from `app/config.py`:
- Environment variables (highest priority)
- `.env` file
- Defaults

## Usage Examples

### Complete Installation

```bash
# 1. Start the API server
uvicorn app.main:app --reload

# 2. Verify health
curl http://localhost:8000/api/v1/health/check

# 3. Verify hosts are reachable
curl -X POST http://localhost:8000/api/v1/deploy/ping

# 4. Initiate installation
curl -X POST http://localhost:8000/api/v1/deploy/install

# 5. Monitor progress (check logs)
curl http://localhost:8000/api/v1/logs/latest
```

### Backup and Restore

```bash
# 1. Create backup
curl -X POST http://localhost:8000/api/v1/deploy/backup

# 2. Check progress
curl http://localhost:8000/api/v1/logs/since?minutes=5

# 3. Verify completion
curl http://localhost:8000/api/v1/deploy/history
```

### Troubleshooting

```bash
# Check health
curl http://localhost:8000/api/v1/health/ready

# View errors
curl http://localhost:8000/api/v1/logs/level/ERROR

# View full history
curl http://localhost:8000/api/v1/deploy/history
```

## Development

### Running Tests

```bash
# Install test dependencies (included in requirements.txt)
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=app
```

### Code Quality

```bash
# Format code
black app/

# Lint
flake8 app/

# Type checking
mypy app/
```

## Docker

### Build Image

```bash
docker build -t mssql-api:1.0 .
```

### Run Container

```bash
docker run -p 8000:8000 \
  -e VM1_HOST=192.168.70.129 \
  -e VM2_HOST=192.168.70.130 \
  -e SSH_KEY_PATH=/root/.ssh/id_rsa \
  -e MSSQL_SA_PASSWORD="YourStr0ng!Passw0rd" \
  -v ~/.ssh:/root/.ssh:ro \
  mssql-api:1.0
```

### Docker Compose

```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f mssql-api

# Stop services
docker-compose down
```

## API Integration

### Python Client Example

```python
import requests

API_URL = "http://localhost:8000"

# Check health
response = requests.get(f"{API_URL}/api/v1/health/check")
print(response.json())

# Initiate deployment
response = requests.post(f"{API_URL}/api/v1/deploy/install")
print(response.json())

# Get history
response = requests.get(f"{API_URL}/api/v1/deploy/history")
for execution in response.json()["executions"]:
    print(f"{execution['playbook']}: {execution['status']}")
```

### cURL Examples

```bash
# Test health
curl -i http://localhost:8000/api/v1/health/check

# Deploy
curl -i -X POST http://localhost:8000/api/v1/deploy/install

# Get logs in JSON
curl -s http://localhost:8000/api/v1/logs/latest | jq '.logs'

# Ping hosts
curl -X POST http://localhost:8000/api/v1/deploy/ping | jq
```

## Deployment Workflow

```
1. API Receives Request
   └─ POST /api/v1/deploy/install

2. Request Handler
   └─ Create background task
   └─ Return immediately (201 Accepted)

3. Background Task
   ├─ Initialize Python SSH deployer
   ├─ Connect to 192.168.70.129 and 192.168.70.130
   ├─ Execute MSSQL workflow commands
   ├─ Log output
   └─ Complete

4. User Can Monitor Progress
   └─ GET /api/v1/logs/latest
   └─ GET /api/v1/deploy/history
   └─ GET /api/v1/deploy/status
```

## Performance Tuning

### Workers (Production)

```bash
# Run with multiple workers for concurrency
uvicorn app.main:app --workers 4 --host 0.0.0.0 --port 8000
```

### Background Tasks

Long-running deployments run in background tasks:
- API responds immediately
- User can poll for status
- No timeout waiting for execution

## Monitoring

### Access Logs

```bash
tail -f logs/app.log
```

### Deployment Metrics

```bash
curl http://localhost:8000/api/v1/deploy/history | jq '
  .executions | group_by(.status) | map({status: .[0].status, count: length})
'
```

## Security

### SSH Keys

Required for Python SSH connectivity:
```bash
ssh-keygen -t rsa -b 4096
ssh-copy-id -i ~/.ssh/id_rsa root@192.168.70.129
ssh-copy-id -i ~/.ssh/id_rsa root@192.168.70.130
```

Mount in Docker:
```bash
docker run ... -v ~/.ssh:/root/.ssh:ro ...
```

### Environment Secrets

Use `.env` file (NOT in version control):
```bash
# .gitignore
.env
logs/
```

### API Security (Optional Enhancements)

- Add API key authentication
- Use HTTPS/TLS
- Rate limiting
- CORS configuration

## Troubleshooting

### "Host not reachable"

```bash
ping 192.168.70.129
ping 192.168.70.130
```

### "Paramiko not found"

```bash
pip install -r requirements.txt
```

### SSH Connection Fails

```bash
# Test SSH connectivity
ssh -i ~/.ssh/id_rsa root@192.168.70.129

# Verify keys are mounted in Docker
docker exec mssql-api ls -la /root/.ssh/
```

### No Logs

```bash
# Check log directory
ls -la logs/

# Create if missing
mkdir -p logs

# Check permissions
chmod 755 logs
```

## Support

For issues:
1. Check `/api/v1/logs/latest`
2. Run `/api/v1/health/ready`
3. Verify SSH connectivity
4. Review Ansible playbook logs

## Version

- **Version**: 1.0.0
- **Last Updated**: 2026-04-19
- **Python**: 3.9+
- **FastAPI**: 0.109.0
- **Ansible**: 2.10.7+
