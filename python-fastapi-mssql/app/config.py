"""Configuration module"""
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import os


class Settings(BaseSettings):
    """Application settings"""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)
    
    # Application
    APP_NAME: str = "MSSQL Deployment API"
    VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    
    # MSSQL Configuration
    MSSQL_SA_PASSWORD: str = os.getenv("MSSQL_SA_PASSWORD", "YourStr0ng!Passw0rd")
    MSSQL_VERSION: str = os.getenv("MSSQL_VERSION", "2019")
    MSSQL_EDITION: str = os.getenv("MSSQL_EDITION", "Developer")
    MSSQL_PORT: int = int(os.getenv("MSSQL_PORT", "1433"))
    
    # VMware target hostnames. These should resolve from the machine/container
    # running the API, or be mapped through DNS/hosts entries.
    VM1_HOST: str = os.getenv("VM1_HOST", os.getenv("VM1_IP", "devops_VM1"))
    VM2_HOST: str = os.getenv("VM2_HOST", os.getenv("VM2_IP", "devops_VM2"))
    VM1_USER: str = os.getenv("VM1_USER", "root")
    VM2_USER: str = os.getenv("VM2_USER", "root")

    # SSH Configuration
    SSH_PORT: int = int(os.getenv("SSH_PORT", "22"))
    SSH_KEY_PATH: str = os.getenv("SSH_KEY_PATH", "~/.ssh/id_rsa")
    SSH_PASSWORD: str = os.getenv("SSH_PASSWORD", "")
    SSH_TIMEOUT: int = int(os.getenv("SSH_TIMEOUT", "30"))
    
    # Backup Configuration
    BACKUP_DIR: str = os.getenv("BACKUP_DIR", "/backup")
    BACKUP_STRIPES: int = int(os.getenv("BACKUP_STRIPES", "10"))
    LOCAL_BACKUP_DIR: str = os.getenv("LOCAL_BACKUP_DIR", "./backups/vm1_striped")
    DATA_DIR: str = os.getenv("DATA_DIR", "/var/opt/mssql/data")
    MSSQL_LOG_DIR: str = os.getenv("MSSQL_LOG_DIR", "/var/opt/mssql/log")
    
    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_DIR: str = os.getenv("LOG_DIR", "./logs")
    
    # API
    API_TIMEOUT: int = int(os.getenv("API_TIMEOUT", "3600"))  # 1 hour

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value):
        """Handle common non-boolean DEBUG values from host environments."""
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        return str(value).lower() in {"1", "true", "yes", "on", "debug", "development"}

settings = Settings()
