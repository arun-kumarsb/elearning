"""
Xen Hypervisor Resource Management & Monitoring Service
Project: Xen-Based Dynamic Resource Allocation for Scalable E-Learning Services

Provides service functions interfacing the Flask API routes with the Xen Resource Monitoring Engine.
"""

import os
import platform
import logging
from typing import Dict, Any, List, Optional
from backend.config import Config
from xen_monitor.resource_monitor import XenResourceMonitor
from xen_monitor.monitor_config import MonitorConfig

logger = logging.getLogger(__name__)

def get_monitor_instance() -> XenResourceMonitor:
    """Return the application-wide XenResourceMonitor singleton instance."""
    cfg = MonitorConfig()
    return XenResourceMonitor.get_instance(cfg)

def read_local_vm_telemetry() -> dict:
    """
    Read guest OS CPU and Memory metrics from standard Linux files (/proc/meminfo, /proc/loadavg)
    or return platform diagnostics.
    """
    mem_total_mb = 0
    mem_available_mb = 0
    mem_used_pct = 0.0
    cpu_load_1m = 0.0
    
    if os.path.exists("/proc/meminfo"):
        try:
            meminfo = {}
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        key = parts[0].strip()
                        val = parts[1].strip().split()[0]
                        meminfo[key] = int(val)
            total_kb = meminfo.get("MemTotal", 0)
            avail_kb = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
            mem_total_mb = round(total_kb / 1024, 1)
            mem_available_mb = round(avail_kb / 1024, 1)
            used_kb = total_kb - avail_kb
            mem_used_pct = round((used_kb / total_kb * 100), 1) if total_kb > 0 else 0.0
        except Exception as e:
            logger.debug(f"Could not parse /proc/meminfo: {e}")

    if os.path.exists("/proc/loadavg"):
        try:
            with open("/proc/loadavg", "r") as f:
                load_parts = f.read().split()
                cpu_load_1m = float(load_parts[0])
        except Exception as e:
            logger.debug(f"Could not parse /proc/loadavg: {e}")

    return {
        "os": platform.system(),
        "release": platform.release(),
        "arch": platform.machine(),
        "mem_total_mb": mem_total_mb,
        "mem_available_mb": mem_available_mb,
        "mem_used_percent": mem_used_pct,
        "cpu_load_1m": cpu_load_1m
    }

def get_xen_cluster_metadata() -> dict:
    """Return virtualization infrastructure configuration and integration status."""
    local_telemetry = read_local_vm_telemetry()
    monitor = get_monitor_instance()
    status = monitor.get_status()

    return {
        "phase": "Phase 2: Real-Time Xen/XCP-ng Resource Monitoring & Elasticity Engine",
        "next_phase": "Phase 3: Automated Dynamic Actuation & Closed-Loop Hypervisor Scaling",
        "monitoring_status": status["status"],
        "monitoring_connected": status["connected"],
        "virtualization": {
            "hypervisor": "XCP-ng / Xen",
            "host_management_ip": Config.XCP_NG_HOST,
            "management_interface": "XO Lite (Xen Orchestra Lite)",
            "network_topology": "Internal Host-Only / Private Bridged Network"
        },
        "vms": [
            {
                "name": Config.APP_VM_NAME,
                "role": "Application Server (Streamlit Frontend + Flask Backend)",
                "ip": Config.APP_VM_IP,
                "os": "Alpine Linux 3.24",
                "python": "3.14.x",
                "telemetry": local_telemetry
            },
            {
                "name": Config.DB_VM_NAME,
                "role": "Database Server (MariaDB 11.8.9)",
                "ip": Config.DB_VM_IP,
                "port": Config.DB_PORT,
                "os": "Alpine Linux 3.24",
                "database": "MariaDB 11.8.9"
            }
        ],
        "elasticity_thresholds": {
            "cpu_scale_up_threshold_pct": Config.CPU_SCALE_UP_THRESHOLD,
            "cpu_scale_down_threshold_pct": Config.CPU_SCALE_DOWN_THRESHOLD,
            "ram_scale_up_threshold_pct": Config.RAM_SCALE_UP_THRESHOLD,
            "polling_interval_sec": Config.MONITOR_INTERVAL,
            "mode": Config.MONITOR_MODE
        }
    }

def get_realtime_metrics() -> Dict[str, Any]:
    """Retrieve consolidated real-time hypervisor, App VM, and DB VM metrics."""
    monitor = get_monitor_instance()
    return monitor.get_latest_metrics()

def get_host_resource_metrics() -> Dict[str, Any]:
    """Retrieve physical host CPU cores, RAM, and running VM metrics."""
    monitor = get_monitor_instance()
    return monitor.get_host_metrics()

def get_discovered_vms() -> List[Dict[str, Any]]:
    """Retrieve list of discovered VMs from XCP-ng hypervisor."""
    monitor = get_monitor_instance()
    return monitor.get_vms()

def get_single_vm_metrics(vm_identifier: str) -> Optional[Dict[str, Any]]:
    """Retrieve telemetry for a specific VM by UUID or name."""
    monitor = get_monitor_instance()
    return monitor.get_vm_metrics(vm_identifier)

def get_monitor_health() -> Dict[str, Any]:
    """Retrieve monitoring engine status and health."""
    monitor = get_monitor_instance()
    return monitor.get_status()

def get_metrics_history(vm_name: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve persistent historical telemetry from database."""
    monitor = get_monitor_instance()
    return monitor.get_history(vm_name=vm_name, limit=limit)
