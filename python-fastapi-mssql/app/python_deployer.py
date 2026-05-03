"""Native Python MSSQL deployment workflow.

This module intentionally does not call Ansible. It uses SSH/SFTP from Python so
the FastAPI service can be operated as a lightweight API path while GitLab/AWX
remain the Ansible-driven path.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import socket
import threading
import uuid
from typing import Dict, Iterable, List, Optional

from app.config import settings


@dataclass(frozen=True)
class TargetHost:
    """A target Linux VM that will receive MSSQL commands."""

    name: str
    host: str
    instance_name: str
    backup_role: str
    user: str
    port: int = 22


class PythonMssqlDeployer:
    """Deploy and operate MSSQL on Linux targets over SSH."""

    def __init__(self) -> None:
        self.targets = [
            TargetHost(
                name="vm1",
                host=settings.VM1_HOST,
                instance_name="instance1",
                backup_role="primary",
                user=settings.VM1_USER,
                port=settings.SSH_PORT,
            ),
            TargetHost(
                name="vm2",
                host=settings.VM2_HOST,
                instance_name="instance2",
                backup_role="secondary",
                user=settings.VM2_USER,
                port=settings.SSH_PORT,
            ),
        ]
        self._history: List[Dict] = []
        self._lock = threading.Lock()

    def start_task(self, operation: str) -> str:
        task_id = str(uuid.uuid4())
        self._record(
            {
                "task_id": task_id,
                "operation": operation,
                "status": "queued",
                "started_at": datetime.now().isoformat(),
                "completed_at": None,
                "results": [],
                "error": None,
            }
        )
        return task_id

    def get_history(self) -> List[Dict]:
        with self._lock:
            return list(self._history)

    def get_task(self, task_id: str) -> Optional[Dict]:
        with self._lock:
            return next((item for item in self._history if item["task_id"] == task_id), None)

    def get_hosts(self) -> Dict:
        return {
            "hosts": [
                {
                    "name": target.name,
                    "host": target.host,
                    "user": target.user,
                    "port": target.port,
                    "instance_name": target.instance_name,
                    "backup_role": target.backup_role,
                }
                for target in self.targets
            ]
        }

    def resolve_hosts(self) -> Dict:
        results = {}
        for target in self.targets:
            try:
                results[target.name] = {
                    "host": target.host,
                    "address": socket.gethostbyname(target.host),
                    "resolved": True,
                }
            except OSError as exc:
                results[target.name] = {
                    "host": target.host,
                    "resolved": False,
                    "error": str(exc),
                }
        return results

    def ping_hosts(self) -> Dict:
        results = []
        for target in self.targets:
            try:
                with closing(self._connect(target)) as ssh:
                    command = self._run(ssh, "hostname && whoami", timeout=30)
                results.append({"host": target.name, "status": "success", "result": command})
            except Exception as exc:
                results.append({"host": target.name, "status": "failed", "error": str(exc)})

        return {
            "status": "success" if all(item["status"] == "success" for item in results) else "failed",
            "results": results,
        }

    def deploy_install(self, task_id: str) -> None:
        self._run_task(task_id, lambda: self._install_all())

    def deploy_backup_restore(self, task_id: str) -> None:
        self._run_task(task_id, lambda: self._backup_restore())

    def install_tools(self, task_id: str) -> None:
        self._run_task(task_id, lambda: self._run_on_all(self._install_tools_commands()))

    def restore_adventureworks(self, task_id: str) -> None:
        self._run_task(task_id, lambda: self._run_on_all(self._adventureworks_commands()))

    def _install_all(self) -> List[Dict]:
        results = self._run_on_all(
            [
                *self._install_server_commands(),
                *self._configure_commands(),
                *self._adventureworks_commands(),
            ]
        )
        results.extend(self._backup_restore())
        return results

    def _backup_restore(self) -> List[Dict]:
        vm1 = self.targets[0]
        vm2 = self.targets[1]
        local_dir = Path(settings.LOCAL_BACKUP_DIR)
        local_dir.mkdir(parents=True, exist_ok=True)

        results = []
        with closing(self._connect(vm1)) as ssh1:
            results.extend(self._run_commands(ssh1, vm1, self._backup_commands()))
            with closing(self._connect(vm2)) as ssh2:
                self._transfer_stripes(ssh1, ssh2, local_dir)
                results.extend(self._run_commands(ssh2, vm2, self._restore_commands()))
        return results

    def _run_on_all(self, commands: Iterable[str]) -> List[Dict]:
        results = []
        for target in self.targets:
            with closing(self._connect(target)) as ssh:
                results.extend(self._run_commands(ssh, target, commands))
        return results

    def _run_commands(self, ssh, target: TargetHost, commands: Iterable[str]) -> List[Dict]:
        results = []
        for command in commands:
            results.append(
                {
                    "host": target.name,
                    "command": self._redact(command),
                    "result": self._run(ssh, command, timeout=settings.API_TIMEOUT),
                }
            )
        return results

    def _connect(self, target: TargetHost):
        import paramiko

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs = {
            "hostname": target.host,
            "port": target.port,
            "username": target.user,
            "timeout": settings.SSH_TIMEOUT,
            "banner_timeout": settings.SSH_TIMEOUT,
            "auth_timeout": settings.SSH_TIMEOUT,
        }
        if settings.SSH_PASSWORD:
            kwargs["password"] = settings.SSH_PASSWORD
        else:
            kwargs["key_filename"] = os.path.expanduser(settings.SSH_KEY_PATH)
        ssh.connect(**kwargs)
        return ssh

    def _run(self, ssh, command: str, timeout: int) -> Dict:
        stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        if exit_code != 0:
            raise RuntimeError(f"Command failed ({exit_code}): {self._redact(command)}\n{err or out}")
        return {"exit_code": exit_code, "stdout": out[-4000:], "stderr": err[-4000:]}

    def _transfer_stripes(self, ssh1, ssh2, local_dir: Path) -> None:
        sftp1 = ssh1.open_sftp()
        sftp2 = ssh2.open_sftp()
        try:
            remote_dir = f"{settings.BACKUP_DIR}/striped"
            self._run(ssh2, f"mkdir -p {remote_dir}", timeout=60)
            for index in range(1, settings.BACKUP_STRIPES + 1):
                filename = f"adv_stripe_{index:02d}.bak"
                local_path = local_dir / filename
                sftp1.get(f"{remote_dir}/{filename}", str(local_path))
                sftp2.put(str(local_path), f"{remote_dir}/{filename}")
        finally:
            sftp1.close()
            sftp2.close()

    def _install_server_commands(self) -> List[str]:
        return [
            "yum install -y curl wget gnupg libsodium",
            "rpm --import https://packages.microsoft.com/keys/microsoft.asc",
            (
                "curl -o /etc/yum.repos.d/mssql-server.repo "
                f"https://packages.microsoft.com/config/rhel/8/mssql-server-{settings.MSSQL_VERSION}.repo"
            ),
            (
                "curl -o /etc/yum.repos.d/msprod.repo "
                "https://packages.microsoft.com/config/rhel/8/prod.repo"
            ),
            "yum install -y mssql-server",
            *self._install_tools_commands(),
            (
                "if test -f /var/opt/mssql/mssql.conf; then "
                "echo 'MSSQL already configured'; "
                "else "
                f"MSSQL_SA_PASSWORD='{settings.MSSQL_SA_PASSWORD}' "
                f"MSSQL_PID='{settings.MSSQL_EDITION}' "
                "ACCEPT_EULA=Y /opt/mssql/bin/mssql-conf -n setup accept-eula; "
                "fi"
            ),
            "systemctl enable --now mssql-server",
            f"timeout 90 bash -c 'until /opt/mssql-tools/bin/sqlcmd -S localhost -U SA -P \"{settings.MSSQL_SA_PASSWORD}\" -Q \"SELECT 1\"; do sleep 5; done'",
        ]

    def _install_tools_commands(self) -> List[str]:
        return [
            "ACCEPT_EULA=Y yum install -y mssql-tools unixODBC-devel",
            "ln -sf /opt/mssql-tools/bin/sqlcmd /usr/local/bin/sqlcmd",
        ]

    def _configure_commands(self) -> List[str]:
        return [
            f"mkdir -p {settings.BACKUP_DIR} {settings.DATA_DIR} {settings.MSSQL_LOG_DIR}",
            f"/opt/mssql/bin/mssql-conf set filelocation.defaultdatadir {settings.DATA_DIR}",
            f"/opt/mssql/bin/mssql-conf set filelocation.defaultlogdir {settings.MSSQL_LOG_DIR}",
            f"/opt/mssql/bin/mssql-conf set network.tcpport {settings.MSSQL_PORT}",
            "/opt/mssql/bin/mssql-conf set sqlagent.enabled true",
            "systemctl restart mssql-server",
        ]

    def _adventureworks_commands(self) -> List[str]:
        return [
            (
                f"curl -L --retry 3 -o {settings.DATA_DIR}/AdventureWorks2019.bak "
                "https://github.com/microsoft/sql-server-samples/releases/download/adventureworks/AdventureWorks2019.bak"
            ),
            self._sql(
                "RESTORE DATABASE AdventureWorks "
                f"FROM DISK = '{settings.DATA_DIR}/AdventureWorks2019.bak' "
                f"WITH MOVE 'AdventureWorks2019' TO '{settings.DATA_DIR}/AdventureWorks.mdf', "
                f"MOVE 'AdventureWorks2019_log' TO '{settings.DATA_DIR}/AdventureWorks.ldf', REPLACE"
            ),
            self._sql("IF DB_ID('AdventureWorks') IS NULL THROW 50000, 'AdventureWorks restore failed', 1"),
        ]

    def _backup_commands(self) -> List[str]:
        stripes = ", ".join(
            f"DISK='{settings.BACKUP_DIR}/striped/adv_stripe_{index:02d}.bak'"
            for index in range(1, settings.BACKUP_STRIPES + 1)
        )
        return [
            f"mkdir -p {settings.BACKUP_DIR}/striped",
            self._sql(f"BACKUP DATABASE AdventureWorks TO {stripes} WITH FORMAT, COMPRESSION"),
            f"test $(ls {settings.BACKUP_DIR}/striped/adv_stripe_*.bak | wc -l) -eq {settings.BACKUP_STRIPES}",
        ]

    def _restore_commands(self) -> List[str]:
        stripes = ", ".join(
            f"DISK='{settings.BACKUP_DIR}/striped/adv_stripe_{index:02d}.bak'"
            for index in range(1, settings.BACKUP_STRIPES + 1)
        )
        return [
            f"test $(ls {settings.BACKUP_DIR}/striped/adv_stripe_*.bak | wc -l) -eq {settings.BACKUP_STRIPES}",
            self._sql(f"RESTORE DATABASE AdventureWorks FROM {stripes} WITH REPLACE"),
            self._sql("IF DB_ID('AdventureWorks') IS NULL THROW 50000, 'AdventureWorks restore failed on VM2', 1"),
        ]

    def _sql(self, query: str) -> str:
        return f"/opt/mssql-tools/bin/sqlcmd -S localhost -U SA -P '{settings.MSSQL_SA_PASSWORD}' -Q \"{query}\""

    def _run_task(self, task_id: str, action) -> None:
        self._update(task_id, status="running")
        try:
            results = action()
            self._update(
                task_id,
                status="success",
                completed_at=datetime.now().isoformat(),
                results=results,
            )
        except Exception as exc:
            self._update(
                task_id,
                status="failed",
                completed_at=datetime.now().isoformat(),
                error=str(exc),
            )

    def _record(self, record: Dict) -> None:
        with self._lock:
            self._history.insert(0, record)

    def _update(self, task_id: str, **changes) -> None:
        with self._lock:
            task = next(item for item in self._history if item["task_id"] == task_id)
            task.update(changes)

    def _redact(self, value: str) -> str:
        if settings.MSSQL_SA_PASSWORD:
            return value.replace(settings.MSSQL_SA_PASSWORD, "********")
        return value
