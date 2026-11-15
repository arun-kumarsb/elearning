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
        self.xcp_host = os.getenv("XCP_NG_HOST", "10.240.109.196")
        self.xcp_username = os.getenv("XCP_NG_USERNAME", "root")
        self.xcp_password = os.getenv("XCP_NG_PASSWORD", "")
        self.verify_ssl = os.getenv("XCP_NG_VERIFY_SSL", "False").lower() in ("true", "1", "t")

        # Dynamic VM Target Discovery Names
        self.app_vm_name = os.getenv("APP_VM_NAME", "Alpine-Linux-New")
        self.db_vm_name = os.getenv("DB_VM_NAME", "Alpine-DB")

        # Infrastructure IPs
        self.app_vm_ip = os.getenv("APP_VM_IP", "10.240.109.51")
        self.db_vm_ip = os.getenv("DB_VM_IP", "10.240.109.248")

        # Polling & Scheduling
        self.poll_interval_sec = int(os.getenv("MONITOR_INTERVAL", "5"))

        # Elasticity Thresholds (Phase 3 Prep)
        self.cpu_scale_up_threshold = float(os.getenv("CPU_SCALE_UP_THRESHOLD", "75.0"))
        self.cpu_scale_down_threshold = float(os.getenv("CPU_SCALE_DOWN_THRESHOLD", "25.0"))
        self.ram_scale_up_threshold = float(os.getenv("RAM_SCALE_UP_THRESHOLD", "80.0"))

        # Boundaries & Cooldown (Phase 3 Prep)
        self.cooldown_period_sec = int(os.getenv("SCALE_COOLDOWN_SEC", "60"))
        self.min_vcpus = int(os.getenv("MIN_VCPUS", "1"))
        self.max_vcpus = int(os.getenv("MAX_VCPUS", "8"))
        self.min_ram_mb = int(os.getenv("MIN_RAM_MB", "1024"))
        self.max_ram_mb = int(os.getenv("MAX_RAM_MB", "8192"))

        # Operational Mode: strictly read_only for Phase 2
        self.monitor_mode = os.getenv("MONITOR_MODE", "read_only")

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
            "cpu_scale_up_threshold": self.cpu_scale_up_threshold,
            "cpu_scale_down_threshold": self.cpu_scale_down_threshold,
            "ram_scale_up_threshold": self.ram_scale_up_threshold,
            "cooldown_period_sec": self.cooldown_period_sec,
            "min_vcpus": self.min_vcpus,
            "max_vcpus": self.max_vcpus,
            "min_ram_mb": self.min_ram_mb,
            "max_ram_mb": self.max_ram_mb,
            "monitor_mode": self.monitor_mode
        }
