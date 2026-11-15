import os
from dotenv import load_dotenv

# Load variables from .env file if present
load_dotenv()

class Config:
    """Application configuration for Xen-based E-Learning Backend."""
    
    # Flask Settings
    SECRET_KEY = os.getenv("SECRET_KEY", "xen-elearning-secret-key-2026-secure")
    DEBUG = os.getenv("FLASK_DEBUG", "False").lower() in ("true", "1", "t")
    FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
    FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
    
    # MariaDB VM 1 Configuration (Alpine-DB)
    # Default private IP: 10.240.109.248
    DB_HOST = os.getenv("DB_HOST", "10.240.109.248")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_NAME = os.getenv("DB_NAME", "elearning")
    DB_USER = os.getenv("DB_USER", "elearning")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "elearning123")
    
    # Xen Virtualization & Infrastructure Metadata
    XCP_NG_HOST = os.getenv("XCP_NG_HOST", "10.240.109.196")
    XCP_NG_USERNAME = os.getenv("XCP_NG_USERNAME", "root")
    XCP_NG_PASSWORD = os.getenv("XCP_NG_PASSWORD", "")
    XCP_NG_VERIFY_SSL = os.getenv("XCP_NG_VERIFY_SSL", "False").lower() in ("true", "1", "t")
    APP_VM_NAME = os.getenv("APP_VM_NAME", "Alpine-Linux-New")
    DB_VM_NAME = os.getenv("DB_VM_NAME", "Alpine-DB")
    APP_VM_IP = os.getenv("APP_VM_IP", "10.240.109.51")
    DB_VM_IP = os.getenv("DB_VM_IP", "10.240.109.248")
    XEN_ENVIRONMENT = os.getenv("XEN_ENVIRONMENT", "XCP-ng Virtualized Infrastructure")
    
    # Phase 2 Monitoring Engine Configuration
    MONITOR_INTERVAL = int(os.getenv("MONITOR_INTERVAL", "5"))
    CPU_SCALE_UP_THRESHOLD = float(os.getenv("CPU_SCALE_UP_THRESHOLD", "75.0"))
    CPU_SCALE_DOWN_THRESHOLD = float(os.getenv("CPU_SCALE_DOWN_THRESHOLD", "25.0"))
    RAM_SCALE_UP_THRESHOLD = float(os.getenv("RAM_SCALE_UP_THRESHOLD", "80.0"))
    MONITOR_MODE = os.getenv("MONITOR_MODE", "read_only")

    # Optional Mock DB for local offline UI unit testing
    USE_MOCK_DB = os.getenv("USE_MOCK_DB", "False").lower() in ("true", "1", "t")

