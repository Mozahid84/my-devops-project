"""Deployment orchestration wrapper for FastAPI."""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from app.ansible_runner import AnsibleRunner
from app.config import settings


logger = logging.getLogger(__name__)


class AnsibleMssqlDeployer:
    """Deploy MSSQL using Ansible playbooks."""

    def __init__(self) -> None:
        self.ansible = AnsibleRunner()
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
                "results": None,
                "error": None,
            }
        )
        return task_id

    def get_history(self) -> List[Dict]:
        with self._lock:
            return list(self._history)

    def _record(self, record: Dict) -> None:
        with self._lock:
            self._history.insert(0, record)

    def _update(self, task_id: str, **changes) -> None:
        with self._lock:
            task = next(item for item in self._history if item["task_id"] == task_id)
            task.update(changes)

    def _run_task(self, task_id: str, action) -> None:
        self._update(task_id, status="running")
        try:
            result = action()
            self._update(
                task_id,
                status="success",
                completed_at=datetime.now().isoformat(),
                results=result,
            )
        except Exception as exc:
            logger.exception("Deployment task failed")
            self._update(
                task_id,
                status="failed",
                completed_at=datetime.now().isoformat(),
                error=str(exc),
            )

    def deploy_install(self, task_id: str) -> None:
        self._run_task(task_id, lambda: self.ansible.run_playbook("site.yml", extra_vars=self._build_extra_vars()))

    def deploy_backup_restore(self, task_id: str) -> None:
        self._run_task(task_id, lambda: self.ansible.run_playbook("backup.yml", extra_vars=self._build_extra_vars()))

    def deploy_alwayson(self, task_id: str) -> None:
        self._run_task(task_id, lambda: self.ansible.run_playbook("alwayson.yml", extra_vars=self._build_extra_vars()))

    def deploy_full_ag(self, task_id: str) -> None:
        self._run_task(task_id, self._run_full_ag_sequence)

    def _run_full_ag_sequence(self) -> Dict[str, object]:
        results: Dict[str, object] = {}
        results["restore_vm1"] = self.ansible.run_playbook(
            "site.yml",
            tags=["adventureworks"],
            limit="vm1",
            extra_vars=self._build_extra_vars(),
        )
        results["backup_restore_vm2"] = self.ansible.run_playbook(
            "backup.yml",
            extra_vars=self._build_extra_vars(),
        )
        results["alwayson"] = self.ansible.run_playbook(
            "alwayson.yml",
            extra_vars=self._build_extra_vars(),
        )
        return results

    def deploy_build(self, task_id: str) -> None:
        """Run the MSSQL build playbook which prepares hosts and runs the mssql_build role."""
        self._run_task(task_id, lambda: self.ansible.run_playbook("build.yml", extra_vars=self._build_extra_vars()))

    def get_hosts(self) -> Dict:
        return {
            "hosts": [
                {"name": "vm1", "host": settings.VM1_HOST, "user": settings.VM1_USER, "port": settings.SSH_PORT},
                {"name": "vm2", "host": settings.VM2_HOST, "user": settings.VM2_USER, "port": settings.SSH_PORT},
            ]
        }

    def resolve_hosts(self) -> Dict:
        import socket

        results = {}
        for hostname in [settings.VM1_HOST, settings.VM2_HOST]:
            try:
                results[hostname] = {
                    "address": socket.gethostbyname(hostname),
                    "resolved": True,
                }
            except OSError as exc:
                results[hostname] = {
                    "resolved": False,
                    "error": str(exc),
                }
        return results

    def ping_hosts(self) -> Dict:
        import socket

        results = []
        for host in [settings.VM1_HOST, settings.VM2_HOST]:
            try:
                with socket.create_connection((host, settings.SSH_PORT), timeout=settings.SSH_TIMEOUT):
                    results.append({"host": host, "status": "reachable"})
            except Exception as exc:
                results.append({"host": host, "status": "unreachable", "error": str(exc)})
        return {
            "status": "success" if all(r["status"] == "reachable" for r in results) else "failed",
            "results": results,
        }

    def install_tools(self, task_id: str) -> None:
        self._run_task(task_id, lambda: self.ansible.run_playbook("site.yml", tags=["install", "tools"], extra_vars=self._build_extra_vars()))

    def restore_adventureworks(self, task_id: str) -> None:
        self._run_task(
            task_id,
            lambda: self.ansible.run_playbook(
                "site.yml",
                tags=["adventureworks"],
                limit="vm1",
                extra_vars=self._build_extra_vars(),
            ),
        )

    def _build_extra_vars(self) -> Dict[str, object]:
        return {
            "sa_password": settings.MSSQL_SA_PASSWORD,
            "mssql_version": settings.MSSQL_VERSION,
            "mssql_edition": settings.MSSQL_EDITION,
            "backup_dir": settings.BACKUP_DIR,
            "data_dir": settings.DATA_DIR,
            "log_dir": settings.MSSQL_LOG_DIR,
            "mssql_port": settings.MSSQL_PORT,
            "ansible_private_key_file": settings.ANSIBLE_PRIVATE_KEY_FILE,
        }
