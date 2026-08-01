# MSSQL Lab Rewind and Teardown Design

## Purpose

This design extends the current MSSQL FastAPI + Ansible lab with a safe reverse path so the environment can be reset, rewound, or torn down for learning and experimentation.

The goal is to make it easy to:
- run a deployment flow
- observe the result
- rewind to a known baseline
- try the same workflow again with a fresh state

---

## Why this matters

A learning lab becomes much more useful when it supports:
- repeatable experiments
- clean rollback steps
- quick reset to a known starting point
- deep troubleshooting without manual cleanup

---

## Proposed learning flow

1. Install or configure MSSQL
2. Run a sample workload or backup/restore flow
3. Capture the current state
4. Trigger a teardown or rewind action
5. Return to the baseline state and try again

---

## Proposed API endpoints

The FastAPI layer can expose these actions:

- POST /api/v1/deploy/teardown
  - Stops services
  - Removes database objects or test data
  - Cleans temporary files and logs

- POST /api/v1/deploy/rewind
  - Reverts the environment to a known baseline
  - Re-runs the install path if needed

- POST /api/v1/deploy/reset-baseline
  - Restores the lab to the original starting state

- GET /api/v1/deploy/rewind-plan
  - Returns the step-by-step plan before execution

---

## Suggested reverse sequence

### Safe teardown path

1. Stop MSSQL services
2. Stop related agents or listeners
3. Remove created databases or test schemas
4. Remove temporary backup artifacts
5. Uninstall or disable optional features used by the flow
6. Leave the host in a clean, reusable state

### Baseline rewind path

1. Restore a known baseline snapshot or prebuilt image
2. Re-run the initial install workflow
3. Reapply the base configuration
4. Validate the environment again

---

## Simple flow diagram

```mermaid
flowchart LR
    A[Operator] --> B[FastAPI endpoint]
    B --> C[Deployer / playbook]
    C --> D[Stop services]
    D --> E[Remove test state]
    E --> F[Restore baseline]
    F --> G[Ready for retry]
```

---

## Suggested playbook structure

A simple Ansible design could be split into three phases:

- prepare
  - gather host state
  - confirm current configuration

- reverse
  - stop services
  - remove objects and artifacts
  - clear temporary configuration

- restore-baseline
  - apply baseline role state
  - re-run install or configuration tasks

---

## Design notes

- Keep this workflow lab-only and clearly separate from production behavior.
- Prefer a baseline snapshot or restore point over destructive actions when possible.
- Record each rewind action in the API history and logs.
- Make each step idempotent so retries are safe.

---

## Example learning scenarios

- Install MSSQL, then rewind to the starting point
- Backup and restore, then teardown the restored database
- Run Always On setup, then remove the cluster state and retry

This gives the lab a true “build, test, rewind, repeat” cycle.
