"""
Xen Resource Monitoring Configuration Module
Reads hypervisor connection parameters, VM discovery names, and elasticity thresholds
dynamically from environment variables.
"""

import os
from dotenv import load_dotenv

load_dotenv()

class MonitorConfig:
    def __init__(self):
        # Hypervisor XAPI Credentials & Endpoints
        self.xcp_host = os.getenv("XCP_NG_HOST", "10.189.191.175")
        self.xcp_username = os.getenv("XCP_NG_USERNAME", "root")
        self.xcp_password = os.getenv("XCP_NG_PASSWORD", "")
        self.verify_ssl = os.getenv("XCP_NG_VERIFY_SSL", "False").lower() in ("true", "1", "t")

        # Dynamic VM Target Discovery Names
        self.app_vm_name = os.getenv("APP_VM_NAME", "Alpine-Linux")
        self.db_vm_name = os.getenv("DB_VM_NAME", "Alpine-DB")

        # Infrastructure IPs
        self.app_vm_ip = os.getenv("APP_VM_IP", "10.189.191.51")
        self.db_vm_ip = os.getenv("DB_VM_IP", "10.189.191.248")

        # Polling & Scheduling
        self.poll_interval_sec = int(os.getenv("MONITOR_INTERVAL", "5"))
        self.allocation_mode = os.getenv("ALLOCATION_MODE", "manual")  # 'manual' (default) or 'auto'

        # CPU Elasticity Thresholds (Phase 3)
        self.cpu_scale_up_threshold = float(os.getenv("CPU_SCALE_UP_THRESHOLD", "80.0"))
        self.cpu_scale_down_threshold = float(os.getenv("CPU_SCALE_DOWN_THRESHOLD", "25.0"))
        self.min_vcpus = int(os.getenv("MIN_VCPUS", "1"))
        self.max_vcpus = int(os.getenv("MAX_VCPUS", "4"))

        # RAM Ballooning Thresholds (Phase 3)
        self.ram_scale_up_threshold = float(os.getenv("RAM_SCALE_UP_THRESHOLD", "85.0"))
        self.ram_scale_down_threshold = float(os.getenv("RAM_SCALE_DOWN_THRESHOLD", "30.0"))
        self.ram_increment_mb = float(os.getenv("RAM_INCREMENT_MB", "512.0"))
        self.min_ram_mb = float(os.getenv("RAM_MIN_MB", os.getenv("MIN_RAM_MB", "1024.0")))
        self.max_ram_mb = float(os.getenv("RAM_MAX_MB", os.getenv("MAX_RAM_MB", "4096.0")))

        # Boundaries & Cooldown Hysteresis
        self.cooldown_period_sec = int(os.getenv("COOLDOWN_PERIOD", os.getenv("SCALE_COOLDOWN_SEC", "60")))
        self.consecutive_breach_threshold = int(os.getenv("CONSECUTIVE_BREACH_THRESHOLD", "2"))

        # Operational Mode
        self.monitor_mode = os.getenv("MONITOR_MODE", "active")

    def to_dict(self):
        return {
            "xcp_host": self.xcp_host,
            "xcp_username": self.xcp_username,
            "verify_ssl": self.verify_ssl,
            "app_vm_name": self.app_vm_name,
            "db_vm_name": self.db_vm_name,
            "app_vm_ip": self.app_vm_ip,
            "db_vm_ip": self.db_vm_ip,
            "poll_interval_sec": self.poll_interval_sec,
            "allocation_mode": self.allocation_mode,
            "cpu_scale_up_threshold": self.cpu_scale_up_threshold,
            "cpu_scale_down_threshold": self.cpu_scale_down_threshold,
            "min_vcpus": self.min_vcpus,
            "max_vcpus": self.max_vcpus,
            "ram_scale_up_threshold": self.ram_scale_up_threshold,
            "ram_scale_down_threshold": self.ram_scale_down_threshold,
            "ram_increment_mb": self.ram_increment_mb,
            "min_ram_mb": self.min_ram_mb,
            "max_ram_mb": self.max_ram_mb,
            "cooldown_period_sec": self.cooldown_period_sec,
            "consecutive_breach_threshold": self.consecutive_breach_threshold,
            "monitor_mode": self.monitor_mode
        }
