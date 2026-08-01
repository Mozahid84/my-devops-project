MSSQL Build role
================

This role provides a minimal, safe skeleton for building a SQL Server host in
the lab. It contains idempotent directory and user creation tasks and a
placeholder where platform-specific package installation should be added.

Usage:

- Include role in `playbooks/build.yml` for an idempotent prepare+install flow.
- Replace the placeholder task with real package installation steps for your
  target OS (yum/apt/dnf) or call out to a more detailed role.
