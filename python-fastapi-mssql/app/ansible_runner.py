"""Ansible deployment utilities"""
import subprocess
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class AnsibleRunner:
    """Run Ansible playbooks programmatically"""
    
    def __init__(self, inventory_path: str, playbook_dir: str):
        """Initialize Ansible runner
        
        Args:
            inventory_path: Path to Ansible inventory file
            playbook_dir: Directory containing playbooks
        """
        self.inventory_path = inventory_path
        self.playbook_dir = playbook_dir
        self.execution_history = []
    
    def run_playbook(
        self,
        playbook_name: str,
        tags: Optional[List[str]] = None,
        limit: Optional[str] = None,
        extra_vars: Optional[Dict] = None,
        verbose: int = 1
    ) -> Dict:
        """Run an Ansible playbook
        
        Args:
            playbook_name: Name of the playbook (e.g., 'site.yml')
            tags: List of tags to run
            limit: Limit to specific hosts
            extra_vars: Extra variables to pass
            verbose: Verbosity level (1-4)
        
        Returns:
            Dict with execution results
        """
        
        playbook_path = os.path.join(self.playbook_dir, playbook_name)
        
        if not os.path.exists(playbook_path):
            raise FileNotFoundError(f"Playbook not found: {playbook_path}")
        
        # Build ansible-playbook command
        cmd = [
            "ansible-playbook",
            "-i", self.inventory_path,
            "-v" * verbose,
            playbook_path
        ]
        
        # Add tags
        if tags:
            cmd.extend(["-t", ",".join(tags)])
        
        # Add limit
        if limit:
            cmd.extend(["-l", limit])
        
        # Add extra vars
        if extra_vars:
            cmd.extend(["-e", json.dumps(extra_vars)])
        
        # Execute playbook
        logger.info(f"Running playbook: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )
            
            execution = {
                "playbook": playbook_name,
                "status": "success" if result.returncode == 0 else "failed",
                "return_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "timestamp": datetime.now().isoformat(),
                "command": " ".join(cmd)
            }
            
            self.execution_history.append(execution)
            
            logger.info(f"Playbook execution completed with code {result.returncode}")
            
            return execution
            
        except subprocess.TimeoutExpired:
            logger.error(f"Playbook execution timed out after 1 hour")
            return {
                "playbook": playbook_name,
                "status": "timeout",
                "error": "Playbook execution exceeded 1 hour timeout",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error running playbook: {str(e)}")
            return {
                "playbook": playbook_name,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def validate_inventory(self) -> Dict:
        """Validate Ansible inventory
        
        Returns:
            Dict with validation results
        """
        
        cmd = ["ansible-inventory", "-i", self.inventory_path, "--list"]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                inventory_data = json.loads(result.stdout)
                return {
                    "valid": True,
                    "hosts": list(inventory_data.get("_meta", {}).get("hostvars", {}).keys()),
                    "groups": list(inventory_data.keys())
                }
            else:
                return {
                    "valid": False,
                    "error": result.stderr
                }
        except Exception as e:
            return {
                "valid": False,
                "error": str(e)
            }
    
    def get_inventory(self) -> Dict:
        """Get inventory details
        
        Returns:
            Dict with inventory information
        """
        
        cmd = ["ansible-inventory", "-i", self.inventory_path, "--list"]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                return json.loads(result.stdout)
            else:
                raise Exception(f"Failed to get inventory: {result.stderr}")
        except Exception as e:
            logger.error(f"Error getting inventory: {str(e)}")
            raise
    
    def ping_hosts(self) -> Dict:
        """Ping all hosts in inventory
        
        Returns:
            Dict with ping results
        """
        
        cmd = ["ansible", "all", "-i", self.inventory_path, "-m", "ping"]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            return {
                "status": "success" if result.returncode == 0 else "failed",
                "return_code": result.returncode,
                "output": result.stdout,
                "errors": result.stderr if result.returncode != 0 else None
            }
        except Exception as e:
            logger.error(f"Error pinging hosts: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def get_execution_history(self) -> List[Dict]:
        """Get execution history
        
        Returns:
            List of execution records
        """
        return self.execution_history
