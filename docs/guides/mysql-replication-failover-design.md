# MySQL Replication Failover Design

## Purpose

This design adds a disaster-recovery failover workflow for MySQL Community Edition 8.4.10 so the FastAPI control plane can promote the replica to primary and reverse replication for a lab-based DR exercise.

The purpose is to make replication failover visible, repeatable, and easy to test.

---

## Goal

Enable an automated DR path where:
- the primary is evaluated for health
- the replica is validated for readiness
- the replica is promoted to primary
- replication direction is reversed
- the new topology is verified

---

## Proposed FastAPI orchestration

The FastAPI service can expose:
- POST /api/v1/dr/failover/mysql
- GET /api/v1/dr/status/mysql
- POST /api/v1/dr/failback/mysql

The implementation should use the existing Ansible runner layer to execute the failover playbook.

---

## Suggested workflow

1. Precheck
   - verify both MySQL servers are reachable
   - confirm replication health and GTID state
   - confirm the replica has applied all required transactions

2. Failover execution
   - pause writes or switch to maintenance mode
   - stop replica threads on the current replica
   - promote the replica to primary
   - reconfigure replication direction to the new primary

3. Postcheck
   - verify the new primary accepts writes
   - confirm the old primary is now configured as replica
   - record logs and status

---

## Simple flow diagram

```mermaid
flowchart LR
    A[FastAPI API] --> B[Ansible Runner]
    B --> C[Precheck]
    C --> D[Promote Replica to Primary]
    D --> E[Reverse Replication]
    E --> F[Validate New Topology]
    F --> G[Return DR Result]
```

---

## Ansible playbook phases

### 1. Precheck phase
- confirm connectivity
- confirm GTID and replica lag state
- ensure the standby is healthy enough to take over

### 2. Failover phase
- stop replica threads
- promote replica to primary
- create or update the replication user and configuration

### 3. Validation phase
- confirm write access on the new primary
- confirm the old primary is following the new primary as replica

---

## Reverse role design

After failover, the old primary can be reconfigured as the standby by resetting replication settings and joining it to the new primary.

This supports:
- failover rehearsal
- replication rollback testing
- manual recovery drills
- deeper understanding of MySQL HA behavior

---

## Learning value

This design teaches:
- MySQL replication failover behavior
- GTID-based role reversal
- how to automate DR steps through a control plane
- how to practice standby recovery without losing the lab workflow
