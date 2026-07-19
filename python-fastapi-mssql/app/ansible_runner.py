"""Ansible integration helper for FastAPI deployment."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from app.config import settings


class AnsibleRunner:
    """Execute Ansible playbooks from the FastAPI application."""

    def __init__(self) -> None:
        self.inventory = Path(settings.ANSIBLE_INVENTORY)
        self.playbook_dir = Path(settings.ANSIBLE_PLAYBOOK_DIR)
        self.command = settings.ANSIBLE_CMD

    def run_playbook(
        self,
        playbook_name: str,
        tags: Optional[Iterable[str]] = None,
        limit: Optional[str] = None,
        extra_vars: Optional[Dict[str, object]] = None,
        skip_tags: Optional[Iterable[str]] = None,
    ) -> Dict[str, object]:
        """Run an Ansible playbook and return structured execution details."""
        playbook_path = self.playbook_dir / playbook_name
        if not playbook_path.exists():
            raise FileNotFoundError(f"Playbook not found: {playbook_path}")

        command = [self.command, "-i", str(self.inventory), str(playbook_path)]
        if tags:
            command.extend(["-t", ",".join(tags)])
        if skip_tags:
            command.extend(["--skip-tags", ",".join(skip_tags)])
        if limit:
            command.extend(["-l", limit])
        if settings.ANSIBLE_PRIVATE_KEY_FILE:
            command.extend(["--private-key", os.path.expanduser(settings.ANSIBLE_PRIVATE_KEY_FILE)])
        if extra_vars:
            command.extend(["-e", json.dumps(extra_vars)])
        if settings.ANSIBLE_VERBOSE and settings.ANSIBLE_VERBOSE > 0:
            command.append("-" + "v" * settings.ANSIBLE_VERBOSE)

        env = os.environ.copy()
        env["ANSIBLE_FORCE_COLOR"] = "false"
        env["ANSIBLE_HOST_KEY_CHECKING"] = "false"
        env["ANSIBLE_DEPRECATION_WARNINGS"] = "False"
        if settings.ANSIBLE_PRIVATE_KEY_FILE:
            env["ANSIBLE_PRIVATE_KEY_FILE"] = os.path.expanduser(settings.ANSIBLE_PRIVATE_KEY_FILE)

        start_time = datetime.utcnow()
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            env=env,
            timeout=settings.API_TIMEOUT,
        )
        end_time = datetime.utcnow()

        return {
            "playbook": str(playbook_path),
            "command": " ".join(shlex.quote(part) for part in command),
            "return_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "started_at": start_time.isoformat() + "Z",
            "completed_at": end_time.isoformat() + "Z",
            "duration_seconds": (end_time - start_time).total_seconds(),
            "success": result.returncode == 0,
        }

    def validate_inventory(self) -> Dict[str, object]:
        """Validate the configured inventory file exists."""
        return {
            "inventory_path": str(self.inventory),
            "exists": self.inventory.exists(),
            "playbook_dir": str(self.playbook_dir),
            "playbook_dir_exists": self.playbook_dir.exists(),
        }
