"""
Xen Hypervisor Resource Management & Monitoring Service (Modular Architecture)
Project: Xen-Based Dynamic Resource Allocation for Scalable E-Learning Services

NOTE: This module defines the architectural contracts, telemetry data structures, 
and integration hooks for Phase 2 dynamic CPU and RAM resource allocation under XCP-ng / Xen.
In accordance with MVP requirements, actual hypervisor dynamic resizing is reserved 
for Phase 2 via Xen XAPI (xe-cli / XenAPI).
"""

import os
import platform
import logging
from backend.config import Config

logger = logging.getLogger(__name__)

def read_local_vm_telemetry() -> dict:
    """
    Read guest OS CPU and Memory metrics from standard Linux files (/proc/meminfo, /proc/loadavg)
    or return platform diagnostics.
    """
    mem_total_mb = 0
    mem_available_mb = 0
    mem_used_pct = 0.0
    cpu_load_1m = 0.0
    
    # Try reading Linux /proc/meminfo (standard on Alpine Linux)
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

    # Try reading Linux /proc/loadavg
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
    """
    Return virtualized infrastructure configuration and integration readiness.
    """
    local_telemetry = read_local_vm_telemetry()
    
    return {
        "phase": "Phase 1 MVP: E-Learning Web Application & Modular Xen Architecture",
        "next_phase": "Phase 2: XenAPI Daemon & Dynamic CPU/RAM Allocation Controller",
        "virtualization": {
            "hypervisor": "XCP-ng / Xen",
            "host_management_ip": Config.XCP_NG_HOST,
            "management_interface": "XO Lite (Xen Orchestra Lite)",
            "network_topology": "Internal Host-Only / Private Bridged Network"
        },
        "vms": [
            {
                "name": "Alpine-Linux-New",
                "role": "Application Server (Streamlit Frontend + Flask Backend)",
                "ip": Config.APP_VM_IP,
                "os": "Alpine Linux 3.24",
                "python": "3.14.x",
                "telemetry": local_telemetry,
                "dynamic_allocation_hooks": {
                    "vcpus_target_controllable": True,
                    "memory_dynamic_min_max_controllable": True,
                    "xen_ballooning_driver": "xen-balloon"
                }
            },
            {
                "name": "Alpine-DB",
                "role": "Database Server (MariaDB 11.8.9)",
                "ip": Config.DB_VM_IP,
                "port": Config.DB_PORT,
                "os": "Alpine Linux 3.24",
                "database": "MariaDB 11.8.9",
                "dynamic_allocation_hooks": {
                    "vcpus_target_controllable": True,
                    "memory_dynamic_min_max_controllable": True,
                    "xen_ballooning_driver": "xen-balloon"
                }
            }
        ],
        "future_xenapi_spec": {
            "cpu_command_format": "xe vm-param-set uuid=<VM_UUID> VCPUs-at-startup=<N>",
            "ram_command_format": "xe vm-memory-limits-set uuid=<VM_UUID> dynamic-min=<MIN> dynamic-max=<MAX>",
            "metrics_polling_interval_sec": 5,
            "scale_up_threshold_cpu_pct": 75,
            "scale_down_threshold_cpu_pct": 25
        }
    }
