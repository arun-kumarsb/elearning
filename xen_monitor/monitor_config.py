"""
Xen Resource Monitoring Configuration Module
Reads hypervisor connection parameters, VM discovery names, and elasticity thresholds
dynamically from environment variables, supporting independent per-VM resource policies.
"""

import os
from typing import Dict, Any, Optional
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

        # Global Elasticity Thresholds
        self.cpu_scale_up_threshold = float(os.getenv("CPU_SCALE_UP_THRESHOLD", "80.0"))
        self.cpu_scale_down_threshold = float(os.getenv("CPU_SCALE_DOWN_THRESHOLD", "25.0"))
        self.ram_scale_up_threshold = float(os.getenv("RAM_SCALE_UP_THRESHOLD", "85.0"))
        self.ram_scale_down_threshold = float(os.getenv("RAM_SCALE_DOWN_THRESHOLD", "30.0"))
        self.ram_increment_mb = float(os.getenv("RAM_INCREMENT_MB", "512.0"))

        # Global / Default Boundaries
        self.min_vcpus = int(os.getenv("MIN_VCPUS", "1"))
        self.max_vcpus = int(os.getenv("MAX_VCPUS", "4"))
        self.min_ram_mb = float(os.getenv("RAM_MIN_MB", os.getenv("MIN_RAM_MB", "1024.0")))
        self.max_ram_mb = float(os.getenv("RAM_MAX_MB", os.getenv("MAX_RAM_MB", "6144.0")))

        # Application VM Specific Policy (Alpine-Linux)
        self.app_vm_initial_ram_mb = float(os.getenv("APP_VM_INITIAL_RAM_MB", "4096.0"))
        self.app_vm_min_ram_mb = float(os.getenv("APP_VM_MIN_RAM_MB", "2048.0"))
        self.app_vm_max_ram_mb = float(os.getenv("APP_VM_MAX_RAM_MB", "6144.0"))
        self.app_vm_initial_vcpus = int(os.getenv("APP_VM_INITIAL_VCPUS", "2"))
        self.app_vm_min_vcpus = int(os.getenv("APP_VM_MIN_VCPUS", "1"))
        self.app_vm_max_vcpus = int(os.getenv("APP_VM_MAX_VCPUS", "4"))

        # Database VM Specific Policy (Alpine-DB - Independently Configurable)
        self.db_vm_min_ram_mb = float(os.getenv("DB_VM_MIN_RAM_MB", "1024.0"))
        self.db_vm_max_ram_mb = float(os.getenv("DB_VM_MAX_RAM_MB", "4096.0"))
        self.db_vm_min_vcpus = int(os.getenv("DB_VM_MIN_VCPUS", "1"))
        self.db_vm_max_vcpus = int(os.getenv("DB_VM_MAX_VCPUS", "4"))
        self.db_vm_preserve_initial = os.getenv("DB_VM_PRESERVE_INITIAL", "True").lower() in ("true", "1", "t")

        # Boundaries & Cooldown Hysteresis
        self.cooldown_period_sec = int(os.getenv("COOLDOWN_PERIOD", os.getenv("SCALE_COOLDOWN_SEC", "60")))
        self.consecutive_breach_threshold = int(os.getenv("CONSECUTIVE_BREACH_THRESHOLD", "2"))

        # Operational Mode
        self.monitor_mode = os.getenv("MONITOR_MODE", "active")

    def get_vm_policy(self, vm_name: Optional[str] = None) -> Dict[str, Any]:
        """Return the independently configured resource policy for a specific VM."""
        name_clean = (vm_name or "").lower().strip()
        app_name_clean = self.app_vm_name.lower().strip()
        db_name_clean = self.db_vm_name.lower().strip()

        if name_clean in (app_name_clean, "alpine-linux", "alpine-linux-new") or "alpine-linux" in name_clean:
            return {
                "vm_name": self.app_vm_name,
                "role": "application_server",
                "min_vcpus": self.app_vm_min_vcpus,
                "max_vcpus": self.app_vm_max_vcpus,
                "initial_vcpus": self.app_vm_initial_vcpus,
                "min_ram_mb": self.app_vm_min_ram_mb,
                "max_ram_mb": self.app_vm_max_ram_mb,
                "initial_ram_mb": self.app_vm_initial_ram_mb,
                "cpu_scale_up_threshold": self.cpu_scale_up_threshold,
                "cpu_scale_down_threshold": self.cpu_scale_down_threshold,
                "ram_scale_up_threshold": self.ram_scale_up_threshold,
                "ram_scale_down_threshold": self.ram_scale_down_threshold,
                "ram_increment_mb": self.ram_increment_mb,
                "preserve_initial": False
            }
        elif name_clean in (db_name_clean, "alpine-db") or "alpine-db" in name_clean or "db" in name_clean:
            return {
                "vm_name": self.db_vm_name,
                "role": "database_server",
                "min_vcpus": self.db_vm_min_vcpus,
                "max_vcpus": self.db_vm_max_vcpus,
                "min_ram_mb": self.db_vm_min_ram_mb,
                "max_ram_mb": self.db_vm_max_ram_mb,
                "cpu_scale_up_threshold": self.cpu_scale_up_threshold,
                "cpu_scale_down_threshold": self.cpu_scale_down_threshold,
                "ram_scale_up_threshold": self.ram_scale_up_threshold,
                "ram_scale_down_threshold": self.ram_scale_down_threshold,
                "ram_increment_mb": self.ram_increment_mb,
                "preserve_initial": self.db_vm_preserve_initial
            }
        else:
            return {
                "vm_name": vm_name or "Generic-VM",
                "role": "generic_vm",
                "min_vcpus": self.min_vcpus,
                "max_vcpus": self.max_vcpus,
                "min_ram_mb": self.min_ram_mb,
                "max_ram_mb": self.max_ram_mb,
                "cpu_scale_up_threshold": self.cpu_scale_up_threshold,
                "cpu_scale_down_threshold": self.cpu_scale_down_threshold,
                "ram_scale_up_threshold": self.ram_scale_up_threshold,
                "ram_scale_down_threshold": self.ram_scale_down_threshold,
                "ram_increment_mb": self.ram_increment_mb,
                "preserve_initial": False
            }

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
            "app_vm_policy": self.get_vm_policy(self.app_vm_name),
            "db_vm_policy": self.get_vm_policy(self.db_vm_name),
            "cooldown_period_sec": self.cooldown_period_sec,
            "consecutive_breach_threshold": self.consecutive_breach_threshold,
            "monitor_mode": self.monitor_mode
        }
