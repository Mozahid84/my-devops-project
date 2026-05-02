"""Logging and output routes"""
from fastapi import APIRouter, HTTPException, status
from datetime import datetime, timedelta
import os
import logging
from pathlib import Path

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/latest")
async def get_latest_logs(lines: int = 100):
    """Get latest log entries
    
    Args:
        lines: Number of lines to return (default 100)
    """
    from app.config import settings
    
    try:
        log_dir = settings.LOG_DIR
        log_file = os.path.join(log_dir, "app.log")
        
        if not os.path.exists(log_file):
            return {
                "status": "no logs",
                "message": "No log file found yet",
                "log_path": log_file
            }
        
        with open(log_file, "r") as f:
            all_lines = f.readlines()
        
        # Get last N lines
        recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
        
        return {
            "status": "success",
            "total_lines": len(all_lines),
            "returned_lines": len(recent_lines),
            "log_path": log_file,
            "logs": "".join(recent_lines)
        }
    
    except Exception as e:
        logger.error(f"Error retrieving logs: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve logs: {str(e)}"
        )


@router.get("/level/{level}")
async def get_logs_by_level(level: str = "ERROR", lines: int = 50):
    """Get logs filtered by level
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        lines: Number of lines to return
    """
    from app.config import settings
    
    valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    
    if level.upper() not in valid_levels:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid log level. Must be one of: {', '.join(valid_levels)}"
        )
    
    try:
        log_dir = settings.LOG_DIR
        log_file = os.path.join(log_dir, "app.log")
        
        if not os.path.exists(log_file):
            return {"status": "no logs", "message": "No log file found yet"}
        
        with open(log_file, "r") as f:
            all_lines = f.readlines()
        
        # Filter by level
        filtered_lines = [line for line in all_lines if level.upper() in line]
        
        # Get last N lines
        recent_lines = filtered_lines[-lines:] if len(filtered_lines) > lines else filtered_lines
        
        return {
            "status": "success",
            "level": level.upper(),
            "total_entries": len(filtered_lines),
            "returned_entries": len(recent_lines),
            "logs": "".join(recent_lines)
        }
    
    except Exception as e:
        logger.error(f"Error retrieving logs: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve logs: {str(e)}"
        )


@router.get("/since")
async def get_logs_since(minutes: int = 30):
    """Get logs from the last N minutes
    
    Args:
        minutes: Number of minutes to look back
    """
    from app.config import settings
    
    try:
        log_dir = settings.LOG_DIR
        log_file = os.path.join(log_dir, "app.log")
        
        if not os.path.exists(log_file):
            return {"status": "no logs", "message": "No log file found yet"}
        
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        
        with open(log_file, "r") as f:
            all_lines = f.readlines()
        
        # Parse and filter by time (assumes ISO format timestamps)
        recent_lines = []
        for line in all_lines:
            try:
                # Try to extract timestamp from log line
                if "ISO" in line or "-" in line[:20]:
                    # This is a heuristic - adjust based on your log format
                    recent_lines.append(line)
            except:
                recent_lines.append(line)
        
        return {
            "status": "success",
            "minutes_back": minutes,
            "cutoff_time": cutoff_time.isoformat(),
            "entries": len(recent_lines),
            "logs": "".join(recent_lines[-100:])  # Return last 100 lines
        }
    
    except Exception as e:
        logger.error(f"Error retrieving logs: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve logs: {str(e)}"
        )


@router.post("/clear")
async def clear_logs():
    """Clear all log files (use with caution)"""
    from app.config import settings
    
    try:
        log_dir = settings.LOG_DIR
        log_file = os.path.join(log_dir, "app.log")
        
        if os.path.exists(log_file):
            with open(log_file, "w") as f:
                f.write("")
            
            return {
                "status": "success",
                "message": "Logs cleared",
                "log_path": log_file
            }
        else:
            return {
                "status": "info",
                "message": "No log file to clear"
            }
    
    except Exception as e:
        logger.error(f"Error clearing logs: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear logs: {str(e)}"
        )


@router.get("/info")
async def get_log_info():
    """Get log file information"""
    from app.config import settings
    
    try:
        log_dir = settings.LOG_DIR
        log_file = os.path.join(log_dir, "app.log")
        
        if os.path.exists(log_file):
            stat_info = os.stat(log_file)
            
            return {
                "status": "success",
                "log_path": log_file,
                "size_bytes": stat_info.st_size,
                "size_mb": round(stat_info.st_size / (1024 * 1024), 2),
                "created": datetime.fromtimestamp(stat_info.st_ctime).isoformat(),
                "modified": datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
                "accessible": True
            }
        else:
            return {
                "status": "no logs",
                "log_path": log_file,
                "message": "No log file exists yet"
            }
    
    except Exception as e:
        logger.error(f"Error getting log info: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get log info: {str(e)}"
        )
