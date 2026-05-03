"""Deployment routes"""
from fastapi import APIRouter, HTTPException, status, BackgroundTasks
import logging
from app.config import settings
from app.python_deployer import PythonMssqlDeployer

router = APIRouter()
logger = logging.getLogger(__name__)

deployer = PythonMssqlDeployer()


@router.get("/status")
async def get_deployment_status():
    """Get current deployment status"""
    history = deployer.get_history()
    latest = history[0] if history else None
    return {
        "status": latest["status"] if latest else "ready",
        "latest_task": latest,
        "engine": "python-ssh",
        "mssql_version": settings.MSSQL_VERSION,
        "mssql_edition": settings.MSSQL_EDITION,
        "vm1": settings.VM1_HOST,
        "vm2": settings.VM2_HOST
    }


@router.post("/install")
async def deploy_install(background_tasks: BackgroundTasks):
    """Deploy and install MSSQL on all servers
    
    This is a long-running operation (30-60 minutes).
    Returns immediately with a status ID.
    """
    
    logger.info("Received deployment request - Install MSSQL")
    
    try:
        task_id = deployer.start_task("install")
        background_tasks.add_task(deployer.deploy_install, task_id)
        
        return {
            "status": "initiated",
            "task_id": task_id,
            "message": "MSSQL installation started",
            "engine": "python-ssh",
            "estimated_duration_minutes": 45,
            "instructions": "Check /api/v1/deploy/status or /api/v1/deploy/history for progress"
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
        task_id = deployer.start_task("backup-restore")
        background_tasks.add_task(deployer.deploy_backup_restore, task_id)
        
        return {
            "status": "initiated",
            "task_id": task_id,
            "message": "Backup and restore process started",
            "engine": "python-ssh",
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
        task_id = deployer.start_task("install-tools")
        background_tasks.add_task(deployer.install_tools, task_id)
        
        return {
            "status": "initiated",
            "task_id": task_id,
            "message": "MSSQL tools installation started",
            "engine": "python-ssh",
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
        task_id = deployer.start_task("restore-adventureworks")
        background_tasks.add_task(deployer.restore_adventureworks, task_id)
        
        return {
            "status": "initiated",
            "task_id": task_id,
            "message": "Database restore started",
            "engine": "python-ssh",
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
        history = deployer.get_history()
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
        inventory = deployer.get_hosts()
        return {
            "status": "success",
            "inventory": inventory,
            "dns": deployer.resolve_hosts()
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
        result = deployer.ping_hosts()
        return result
    except Exception as e:
        logger.error(f"Error pinging hosts: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to ping hosts: {str(e)}"
        )
