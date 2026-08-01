# MySQL Replication Sync Rebuild Design

## Purpose

This design covers the recovery path when a MySQL replica has fallen out of sync or needs to be rebuilt after a failover event or replication outage.

The goal is to make standby recovery a repeatable workflow for labs and future automation work.

---

## Goal

Provide a rebuild path where:
- the primary is verified
- the replica is reinitialized from a fresh backup or consistent snapshot
- replication is re-established
- GTID and binlog state are validated
- the environment is returned to a healthy DR posture

---

## Proposed FastAPI orchestration

The FastAPI service can expose:
- POST /api/v1/dr/sync-rebuild/mysql
- GET /api/v1/dr/sync-status/mysql

The workflow should use the existing Ansible runner integration to keep orchestration consistent with the rest of the lab design.

---

## Suggested workflow

1. Precheck
   - verify the primary is reachable
   - confirm the replica is stale or out of sync
   - check GTID and replication lag state

2. Rebuild execution
   - capture a fresh backup from the primary using XtraBackup
   - restore the backup on the replica
   - reconfigure replication settings
   - start the replica and rejoin the replication stream

3. Validation
   - verify replication is running
   - confirm the replica is applying transactions
   - record the recovery outcome in logs and history

---

## Simple flow diagram

```mermaid
flowchart LR
    A[FastAPI API] --> B[Ansible Runner]
    B --> C[Precheck]
    C --> D[Take Fresh Backup]
    D --> E[Restore on Replica]
    E --> F[Re-establish Replication]
    F --> G[Validate Replica Health]
```

---

## Ansible playbook phases

### 1. Prepare phase
- confirm storage and backup availability
- verify MySQL service state

### 2. Rebuild phase
- run XtraBackup on the primary
- restore the backup on the replica
- configure replication connection settings

### 3. Validation phase
- confirm replica status
- confirm GTID and relay log progress
- log the recovery result

---

## Learning value

This design teaches:
- how to rebuild a stale replica
- how to recover from replication drift
- how to automate recovery steps for experimentation and DR drills
- how to make MySQL replication recovery repeatable and observable
