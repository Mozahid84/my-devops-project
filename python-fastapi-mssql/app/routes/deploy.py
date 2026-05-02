"""Deployment routes"""
from fastapi import APIRouter, HTTPException, status, BackgroundTasks
from typing import Optional, List
import logging
from app.ansible_runner import AnsibleRunner
from app.config import settings
import os

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize Ansible runner
ansible_runner = AnsibleRunner(
    inventory_path=settings.ANSIBLE_INVENTORY,
    playbook_dir=settings.ANSIBLE_PLAYBOOK_DIR
)


class DeploymentRequest:
    """Deployment request model"""
    pass


@router.get("/status")
async def get_deployment_status():
    """Get current deployment status"""
    return {
        "status": "ready",
        "inventory": settings.ANSIBLE_INVENTORY,
        "playbook_dir": settings.ANSIBLE_PLAYBOOK_DIR,
        "mssql_version": settings.MSSQL_VERSION,
        "mssql_edition": settings.MSSQL_EDITION,
        "vm1": settings.VM1_IP,
        "vm2": settings.VM2_IP
    }


@router.post("/install")
async def deploy_install(background_tasks: BackgroundTasks):
    """Deploy and install MSSQL on all servers
    
    This is a long-running operation (30-60 minutes).
    Returns immediately with a status ID.
    """
    
    logger.info("Received deployment request - Install MSSQL")
    
    try:
        # Run playbook in background
        def run_deployment():
            extra_vars = {
                "sa_password": settings.MSSQL_SA_PASSWORD,
                "mssql_version": settings.MSSQL_VERSION,
                "mssql_edition": settings.MSSQL_EDITION
            }
            
            result = ansible_runner.run_playbook(
                playbook_name="site.yml",
                extra_vars=extra_vars,
                verbose=2
            )
            logger.info(f"Deployment completed: {result['status']}")
        
        background_tasks.add_task(run_deployment)
        
        return {
            "status": "initiated",
            "message": "MSSQL installation started",
            "playbook": "site.yml",
            "estimated_duration_minutes": 45,
            "instructions": "Check deployment status at /api/v1/deploy/status and logs at /api/v1/logs/latest"
        }
    
    except Exception as e:
        logger.error(f"Error initiating deployment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate deployment: {str(e)}"
        )


@router.post("/backup")
async def deploy_backup(background_tasks: BackgroundTasks):
    """Create 10-stripe backup on VM1 and transfer to VM2
    
    Prerequisites: MSSQL must be installed and AdventureWorks DB must exist
    This operation takes 10-20 minutes depending on database size.
    """
    
    logger.info("Received deployment request - Backup and Restore")
    
    try:
        def run_backup():
            result = ansible_runner.run_playbook(
                playbook_name="backup.yml",
                verbose=2
            )
            logger.info(f"Backup completed: {result['status']}")
        
        background_tasks.add_task(run_backup)
        
        return {
            "status": "initiated",
            "message": "Backup and restore process started",
            "playbook": "backup.yml",
            "operations": [
                "Create 10-stripe backup on VM1",
                "Transfer backup files to VM2",
                "Restore AdventureWorks on VM2"
            ],
            "estimated_duration_minutes": 15
        }
    
    except Exception as e:
        logger.error(f"Error initiating backup: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate backup: {str(e)}"
        )


@router.post("/install-tools")
async def deploy_install_tools(background_tasks: BackgroundTasks):
    """Install MSSQL tools only (sqlcmd) without database"""
    
    logger.info("Received deployment request - Install tools only")
    
    try:
        def run_tools():
            result = ansible_runner.run_playbook(
                playbook_name="site.yml",
                tags=["install", "tools"],
                verbose=2
            )
            logger.info(f"Tools installation completed: {result['status']}")
        
        background_tasks.add_task(run_tools)
        
        return {
            "status": "initiated",
            "message": "MSSQL tools installation started",
            "components": ["mssql-tools", "sqlcmd"],
            "estimated_duration_minutes": 10
        }
    
    except Exception as e:
        logger.error(f"Error initiating tools installation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate tools installation: {str(e)}"
        )


@router.post("/restore-db")
async def deploy_restore_db(background_tasks: BackgroundTasks):
    """Restore AdventureWorks database only"""
    
    logger.info("Received deployment request - Restore database")
    
    try:
        def run_restore():
            result = ansible_runner.run_playbook(
                playbook_name="site.yml",
                tags=["adventureworks"],
                verbose=2
            )
            logger.info(f"Database restore completed: {result['status']}")
        
        background_tasks.add_task(run_restore)
        
        return {
            "status": "initiated",
            "message": "Database restore started",
            "database": "AdventureWorks",
            "operations": [
                "Download AdventureWorks2019.bak",
                "Restore to MSSQL instance"
            ],
            "estimated_duration_minutes": 10
        }
    
    except Exception as e:
        logger.error(f"Error initiating database restore: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate database restore: {str(e)}"
        )


@router.get("/history")
async def get_deployment_history():
    """Get deployment execution history"""
    try:
        history = ansible_runner.get_execution_history()
        return {
            "total_executions": len(history),
            "executions": history
        }
    except Exception as e:
        logger.error(f"Error retrieving history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve history: {str(e)}"
        )


@router.get("/hosts")
async def get_target_hosts():
    """Get target host information"""
    try:
        inventory = ansible_runner.get_inventory()
        return {
            "status": "success",
            "inventory": inventory
        }
    except Exception as e:
        logger.error(f"Error retrieving hosts: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve hosts: {str(e)}"
        )


@router.post("/ping")
async def ping_hosts():
    """Ping all target hosts to verify connectivity"""
    try:
        result = ansible_runner.ping_hosts()
        return result
    except Exception as e:
        logger.error(f"Error pinging hosts: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to ping hosts: {str(e)}"
        )
