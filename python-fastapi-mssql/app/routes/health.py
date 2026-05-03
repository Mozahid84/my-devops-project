"""Health check routes"""
from fastapi import APIRouter, status
from datetime import datetime
import psutil
import os
from pathlib import Path

router = APIRouter()


@router.get("/check")
async def health_check():
    """Basic health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "MSSQL Deployment API",
        "version": "1.0.0"
    }


@router.get("/ready")
async def readiness_check():
    """Readiness check - verifies all dependencies"""
    
    checks = {
        "python_ssh": verify_python_ssh(),
        "ssh_key": verify_ssh_credentials(),
        "vmware_dns": verify_vmware_dns(),
        "disk_space": check_disk_space(),
        "system_resources": check_system_resources()
    }
    
    all_ready = all(check.get("ready", False) for check in checks.values())
    
    return {
        "ready": all_ready,
        "timestamp": datetime.now().isoformat(),
        "checks": checks
    }


@router.get("/live")
async def liveness_check():
    """Liveness check - verifies API is running"""
    return {
        "alive": True,
        "timestamp": datetime.now().isoformat()
    }


def verify_python_ssh() -> dict:
    """Verify Paramiko is installed for Python SSH execution."""
    try:
        import paramiko
        return {
            "ready": True,
            "component": "Python SSH",
            "library": "paramiko",
            "version": paramiko.__version__
        }
    except ImportError:
        return {
            "ready": False,
            "component": "Python SSH",
            "error": "paramiko not found"
        }


def verify_ssh_credentials() -> dict:
    """Verify either an SSH key or password is configured."""
    from app.config import settings

    if settings.SSH_PASSWORD:
        return {
            "ready": True,
            "component": "SSH credentials",
            "method": "password"
        }

    key_path = Path(os.path.expanduser(settings.SSH_KEY_PATH))
    if key_path.exists():
        return {
            "ready": True,
            "component": "SSH credentials",
            "method": "key",
            "path": str(key_path)
        }

    return {
        "ready": False,
        "component": "SSH credentials",
        "error": f"SSH key not found at {key_path}; set SSH_KEY_PATH or SSH_PASSWORD"
    }


def verify_vmware_dns() -> dict:
    """Verify VMware hostnames resolve from this API runtime."""
    from app.routes.deploy import deployer

    results = deployer.resolve_hosts()
    return {
        "ready": all(item["resolved"] for item in results.values()),
        "component": "VMware DNS",
        "hosts": results
    }


def check_disk_space() -> dict:
    """Check available disk space"""
    try:
        disk = psutil.disk_usage("/")
        available_gb = disk.free / (1024 ** 3)
        
        return {
            "ready": available_gb > 5,  # Need at least 5GB
            "component": "Disk Space",
            "available_gb": round(available_gb, 2),
            "total_gb": round(disk.total / (1024 ** 3), 2),
            "used_percent": disk.percent
        }
    except Exception as e:
        return {
            "ready": False,
            "component": "Disk Space",
            "error": str(e)
        }


def check_system_resources() -> dict:
    """Check system resources"""
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        
        return {
            "ready": cpu_percent < 90 and memory.percent < 90,
            "component": "System Resources",
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "available_memory_gb": round(memory.available / (1024 ** 3), 2)
        }
    except Exception as e:
        return {
            "ready": False,
            "component": "System Resources",
            "error": str(e)
        }
