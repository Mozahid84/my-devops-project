# MSSQL DR Sync Rebuild Design

## Purpose

This design covers the reverse of failover: rebuilding or resynchronizing the standby MSSQL environment when it has drifted out of sync or becomes stale after a DR event.

The aim is to make standby recovery an explicit, repeatable workflow rather than a manual cleanup task.

---

## Goal

Provide a simple rebuild path where:
- the current primary is verified
- a fresh backup or copy is taken
- the secondary is rebuilt or reinitialized
- the AG is rejoined and synchronized
- the environment returns to a healthy standby state

---

## Proposed FastAPI orchestration

The FastAPI service can expose:
- POST /api/v1/dr/sync-rebuild/mssql
- GET /api/v1/dr/sync-status/mssql

The workflow should run through Ansible playbooks using the existing runner interface.

---

## Suggested workflow

1. Precheck
   - confirm primary health
   - confirm backup location and disk space
   - verify the secondary is unhealthy or stale

2. Rebuild execution
   - prepare the secondary host
   - copy the latest backup or database state from the primary
   - restore or reinitialize the secondary database state
   - rejoin the AG and resume synchronization

3. Validation
   - verify the AG health
   - confirm synchronization and data freshness
   - record the recovery result

---

## Simple flow diagram

```mermaid
flowchart LR
    A[FastAPI API] --> B[Ansible Runner]
    B --> C[Precheck]
    C --> D[Restore Latest Backup]
    D --> E[Rejoin AG / Resync]
    E --> F[Validate Standby Health]
    F --> G[Standby Rebuilt]
```

---

## Ansible playbook phases

### 1. Prepare phase
- verify host state and storage
- confirm backup artifacts are available

### 2. Rebuild phase
- restore the required database state
- reconfigure the AG membership
- reinitialize synchronization

### 3. Validation phase
- confirm health and data flow
- log the recovery outcome

---

## Learning value

This design teaches:
- how to recover a stale standby
- how to automate rebuild steps
- how to re-establish a healthy DR posture after a failover or outage
