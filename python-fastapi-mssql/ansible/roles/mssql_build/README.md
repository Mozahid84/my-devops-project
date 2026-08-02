MSSQL Build role
================

This role performs a full, idempotent SQL Server 2019 install on
CentOS/RHEL 8-based hosts: it creates the backup/data/log directories and the
`mssql` service account, installs required OS dependencies, adds the
Microsoft SQL Server and MSSQL-Tools yum repositories, installs
`mssql-server`/`mssql-tools`, runs `mssql-conf setup`, applies a lab memory
limit, starts the service, waits for it to listen on `mssql_port`, and
verifies the install with `sqlcmd -Q "SELECT @@VERSION"`.

Key variables (see `defaults/main.yml`): `mssql_version`, `mssql_edition`,
`mssql_service_user`, `sa_password`, `backup_dir`, `data_dir`, `log_dir`,
`mssql_port`, `mssql_tools_path`, `mssql_memory_limit_mb`.

Usage:

- Included by `playbooks/build.yml` as the sole role in an idempotent
  prepare+install flow, invoked via the FastAPI service's `build` deploy
  endpoint (see `app/deployer.py`).
- Override `sa_password` and other defaults via `-e` or a vars file rather
  than editing `defaults/main.yml` directly.
