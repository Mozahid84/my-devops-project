"""Configuration module"""
from pydantic_settings import BaseSettings
import os


class Settings(BaseSettings):
    """Application settings"""
    
    # Application
    APP_NAME: str = "MSSQL Deployment API"
    VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    
    # Deployment
    ANSIBLE_INVENTORY: str = os.getenv("ANSIBLE_INVENTORY", "../ansible-mssql-deploy/inventory/hosts.ini")
    ANSIBLE_PLAYBOOK_DIR: str = os.getenv("ANSIBLE_PLAYBOOK_DIR", "../ansible-mssql-deploy/playbooks")
    ANSIBLE_VAULT_PASSWORD: str = os.getenv("ANSIBLE_VAULT_PASSWORD", "")
    
    # MSSQL Configuration
    MSSQL_SA_PASSWORD: str = os.getenv("MSSQL_SA_PASSWORD", "YourStr0ng!Passw0rd")
    MSSQL_VERSION: str = os.getenv("MSSQL_VERSION", "2019")
    MSSQL_EDITION: str = os.getenv("MSSQL_EDITION", "Developer")
    
    # VM Configuration
    VM1_IP: str = os.getenv("VM1_IP", "192.168.56.101")
    VM2_IP: str = os.getenv("VM2_IP", "192.168.56.102")
    VM1_USER: str = os.getenv("VM1_USER", "root")
    VM2_USER: str = os.getenv("VM2_USER", "root")
    
    # Backup Configuration
    BACKUP_DIR: str = os.getenv("BACKUP_DIR", "/backup")
    BACKUP_STRIPES: int = int(os.getenv("BACKUP_STRIPES", "10"))
    
    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_DIR: str = os.getenv("LOG_DIR", "./logs")
    
    # API
    API_TIMEOUT: int = int(os.getenv("API_TIMEOUT", "3600"))  # 1 hour
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
