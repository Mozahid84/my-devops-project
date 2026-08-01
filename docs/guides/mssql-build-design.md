# MSSQL Build Design

## Purpose

This document defines a simple build design for the current MSSQL lab so it can be deployed, tested, and later extended with failover and DR workflows.

The goal is to keep the MSSQL path consistent with the Oracle and MySQL design documents so the overall lab can be understood and expanded in a uniform way.

---

## High-level goal

Build a repeatable MSSQL environment with:
- a primary SQL Server instance
- a secondary host for DR or failover learning
- base configuration and database setup
- a clear teardown and rewind path
- a FastAPI + Ansible orchestration layer for execution

---

## Proposed topology

```mermaid
flowchart LR
    A[Operator / API] --> B[Primary MSSQL Host]
    B --> C[Secondary MSSQL Host]
    B -.Backup / Sync / AG state.-> C
```

---

## Core components

- SQL Server host for the primary node
- Secondary host for replica or standby role
- FastAPI control plane
- Ansible playbooks for provisioning and orchestration
- Shared storage or backup location for restore and recovery exercises

---

## Build sequence

1. Prepare hosts and networking
2. Install SQL Server engine and required features
3. Configure authentication, service accounts, and ports
4. Create the baseline database and sample objects
5. Configure backup paths and restore locations
6. Prepare the secondary host for future DR and failover testing
7. Validate installation and basic connectivity

---

## Suggested automation split

### Provisioning phase
- install SQL Server components
- create service accounts and folders
- configure basic OS and SQL settings

### Database phase
- create the baseline database
- apply sample data or AdventureWorks-style content
- verify availability and accessibility

### DR preparation phase
- prepare backup paths
- configure secondary host readiness
- make the environment ready for failover exercises

---

## Reverse and teardown flow

The build design should also support:
- teardown of test objects and databases
- rollback to a clean lab state
- rebuild from a known baseline
- rerun of the installation flow without manual cleanup

---

## Learning outcomes

This design teaches:
- MSSQL deployment fundamentals
- how the lab can be built repeatedly
- how to prepare the environment for failover and standby DR exercises
- how to align MSSQL automation with the same FastAPI + Ansible model used elsewhere
