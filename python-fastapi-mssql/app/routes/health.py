"""Health check routes"""
from fastapi import APIRouter, status
from datetime import datetime
import psutil
import os

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
        "ansible": verify_ansible(),
        "inventory": verify_inventory(),
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


def verify_ansible() -> dict:
    """Verify Ansible is installed"""
    try:
        import ansible
        return {
            "ready": True,
            "component": "Ansible",
            "version": ansible.__version__
        }
    except ImportError:
        return {
            "ready": False,
            "component": "Ansible",
            "error": "Ansible not found"
        }


def verify_inventory() -> dict:
    """Verify Ansible inventory exists"""
    from app.config import settings
    
    if os.path.exists(settings.ANSIBLE_INVENTORY):
        return {
            "ready": True,
            "component": "Inventory",
            "path": settings.ANSIBLE_INVENTORY
        }
    else:
        return {
            "ready": False,
            "component": "Inventory",
            "error": f"Inventory not found at {settings.ANSIBLE_INVENTORY}"
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
