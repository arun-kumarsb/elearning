"""
Xen Hypervisor Resource Management & Monitoring Service
Project: Xen-Based Dynamic Resource Allocation for Scalable E-Learning Services

Provides service functions interfacing the Flask API routes with the Xen Resource Monitoring Engine.
"""

import os
import time
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
        "phase": "Phase 3: Dynamic CPU and RAM Resource Allocation",
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
            "min_vcpus": Config.MIN_VCPUS,
            "max_vcpus": Config.MAX_VCPUS,
            "ram_scale_up_threshold_pct": Config.RAM_SCALE_UP_THRESHOLD,
            "ram_scale_down_threshold_pct": Config.RAM_SCALE_DOWN_THRESHOLD,
            "ram_increment_mb": Config.RAM_INCREMENT_MB,
            "ram_min_mb": Config.RAM_MIN_MB,
            "ram_max_mb": Config.RAM_MAX_MB,
            "cooldown_period_sec": Config.COOLDOWN_PERIOD,
            "consecutive_breaches": Config.CONSECUTIVE_BREACH_THRESHOLD,
            "polling_interval_sec": Config.MONITOR_INTERVAL,
            "mode": getattr(Config, "ALLOCATION_MODE", "manual")
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

# -------------------------------------------------------------
# Phase 3: Dynamic Resource Allocation Service Functions
# -------------------------------------------------------------
def get_allocation_controller_status() -> Dict[str, Any]:
    """Retrieve dynamic allocation controller state, limits, and active recommendations."""
    monitor = get_monitor_instance()
    return monitor.get_allocation_status()

def get_allocation_recommendations() -> Dict[str, Any]:
    """Retrieve latest scaling recommendations across all monitored VMs."""
    monitor = get_monitor_instance()
    return monitor.get_allocation_recommendations()

def get_allocation_history(vm_name: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve allocation audit trail from resource_allocation_history table."""
    monitor = get_monitor_instance()
    return monitor.get_allocation_history(vm_name=vm_name, limit=limit)

def set_automation_mode(mode: str) -> str:
    """Set automation mode to 'auto' or 'manual'."""
    monitor = get_monitor_instance()
    return monitor.set_allocation_mode(mode)

def set_emergency_stop_status(enabled: bool, reason: str = "Administrator emergency stop", initiated_by: str = "admin") -> bool:
    """Engage or disengage emergency stop."""
    monitor = get_monitor_instance()
    return monitor.set_emergency_stop(enabled, reason=reason, initiated_by=initiated_by)

def reset_emergency_stop_status(reason: str = "Administrator reset", initiated_by: str = "admin") -> bool:
    """Reset emergency stop status, return operational mode to manual, and record audit log."""
    monitor = get_monitor_instance()
    return monitor.reset_emergency_stop(reason=reason, initiated_by=initiated_by)

def reboot_vm_service(vm_name: str, reason: str = "Admin requested reboot", initiated_by: str = "admin") -> Dict[str, Any]:
    """Gracefully reboot VM via XenAPI with audit logging."""
    monitor = get_monitor_instance()
    return monitor.reboot_vm(vm_name, reason=reason, initiated_by=initiated_by)

def apply_manual_cpu_allocation(vm_name: str, vcpus: int, reason: str = "Admin manual override", initiated_by: str = "admin") -> Dict[str, Any]:
    """Perform administrator-initiated live vCPU allocation."""
    monitor = get_monitor_instance()
    return monitor.apply_manual_cpu(vm_name, vcpus, reason=reason, initiated_by=initiated_by)

def apply_manual_ram_allocation(vm_name: str, ram_mb: float, reason: str = "Admin manual override", initiated_by: str = "admin") -> Dict[str, Any]:
    """Perform administrator-initiated dynamic RAM ballooning."""
    monitor = get_monitor_instance()
    return monitor.apply_manual_ram(vm_name, ram_mb, reason=reason, initiated_by=initiated_by)

def apply_pending_recommendation(vm_name: str, initiated_by: str = "admin") -> Dict[str, Any]:
    """Apply current scaling recommendation for a specific VM."""
    monitor = get_monitor_instance()
    return monitor.apply_recommended_action(vm_name, initiated_by=initiated_by)

def transition_vm_to_baseline(vm_name: str, initiated_by: str = "admin") -> Dict[str, Any]:
    """Safely transitions a VM to the target baseline policy (1 vCPU, 1024 MB RAM)."""
    monitor = get_monitor_instance()
    return monitor.transition_to_baseline(vm_name, initiated_by=initiated_by)

def execute_baseline_maintenance_service(vm_name: str, initiated_by: str = "admin") -> Dict[str, Any]:
    """Execute controlled administrator-approved baseline maintenance procedure."""
    monitor = get_monitor_instance()
    return monitor.execute_baseline_maintenance(vm_name, initiated_by=initiated_by)

# -------------------------------------------------------------
# Workload Simulator Service Functions
# -------------------------------------------------------------
def get_workload_simulator_status() -> Dict[str, Any]:
    """Retrieve status of active CPU, RAM, and Database synthetic workloads."""
    from backend.services.workload_service import WorkloadSimulatorService
    return WorkloadSimulatorService.get_instance().get_status()

def start_cpu_workload_service(target_vm: str = "Alpine-Linux", intensity_percent: float = 75.0,
                               workers: int = 2, duration_sec: int = 60, initiated_by: str = "admin") -> Dict[str, Any]:
    """Start artificial CPU workload on target VM."""
    from backend.services.workload_service import WorkloadSimulatorService
    return WorkloadSimulatorService.get_instance().start_cpu_workload(
        target_vm=target_vm,
        intensity_percent=intensity_percent,
        workers=workers,
        duration_sec=duration_sec,
        initiated_by=initiated_by
    )

def start_ram_workload_service(target_vm: str = "Alpine-Linux", allocated_mb: float = 256.0,
                               duration_sec: int = 60, initiated_by: str = "admin") -> Dict[str, Any]:
    """Start artificial RAM memory consumption on target VM."""
    from backend.services.workload_service import WorkloadSimulatorService
    return WorkloadSimulatorService.get_instance().start_ram_workload(
        target_vm=target_vm,
        allocated_mb=allocated_mb,
        duration_sec=duration_sec,
        initiated_by=initiated_by
    )

def start_database_workload_service(target_vm: str = "Alpine-DB", intensity: str = "medium",
                                    workers: int = 2, duration_sec: int = 60, initiated_by: str = "admin") -> Dict[str, Any]:
    """Start safe transactional workload against MariaDB database."""
    from backend.services.workload_service import WorkloadSimulatorService
    return WorkloadSimulatorService.get_instance().start_database_workload(
        target_vm=target_vm,
        intensity=intensity,
        workers=workers,
        duration_sec=duration_sec,
        initiated_by=initiated_by
    )

def stop_workload_service(session_id: str) -> Dict[str, Any]:
    """Stop an individual workload session."""
    from backend.services.workload_service import WorkloadSimulatorService
    return WorkloadSimulatorService.get_instance().stop_workload(session_id)

def stop_all_workloads_service() -> Dict[str, Any]:
    """Stop all active workload sessions (Emergency Stop)."""
    from backend.services.workload_service import WorkloadSimulatorService
    return WorkloadSimulatorService.get_instance().stop_all_workloads()

# -------------------------------------------------------------
# Student Load Simulator Service Functions
# -------------------------------------------------------------
def get_student_load_status() -> Dict[str, Any]:
    """Retrieve real-time telemetry from active Student Load Simulator."""
    from backend.services.student_load_service import StudentLoadSimulatorService
    return StudentLoadSimulatorService.get_instance().get_status()

def start_student_load_service(
    target_vm: str = "app_vm",
    simulated_students: int = 10,
    ramp_up_duration: int = 10,
    test_duration: int = 60,
    requests_per_student: float = 2.0,
    workload_intensity: str = "medium",
    initiated_by: str = "admin"
) -> Dict[str, Any]:
    """Launch real student traffic generation against API & DB."""
    from backend.services.student_load_service import StudentLoadSimulatorService
    return StudentLoadSimulatorService.get_instance().start_load_test(
        target_vm=target_vm,
        simulated_students=simulated_students,
        ramp_up_duration=ramp_up_duration,
        test_duration=test_duration,
        requests_per_student=requests_per_student,
        workload_intensity=workload_intensity,
        initiated_by=initiated_by
    )

def stop_student_load_service(session_id: Optional[str] = None) -> Dict[str, Any]:
    """Stop active student load test."""
    from backend.services.student_load_service import StudentLoadSimulatorService
    return StudentLoadSimulatorService.get_instance().stop_load_test(session_id)

def emergency_stop_student_load_service() -> Dict[str, Any]:
    """Emergency stop all student traffic generators and scaling."""
    from backend.services.student_load_service import StudentLoadSimulatorService
    return StudentLoadSimulatorService.get_instance().emergency_stop_all()

def run_student_load_preflight() -> Dict[str, Any]:
    """Run authentication and connectivity preflight verification."""
    from backend.services.student_load_service import StudentLoadSimulatorService
    return StudentLoadSimulatorService.get_instance().run_preflight_check()

def execute_simulated_student_db_query(session_id: str, student_id: int) -> Dict[str, Any]:
    """
    Execute a safe transient read/write on the dedicated workload_simulation_test table
    to generate authentic MariaDB query workload without touching real student/course data.
    """
    from backend.database import execute_db, query_db
    try:
        payload = f"student_{student_id}_{int(time.time()*1000)}"
        execute_db(
            "INSERT INTO workload_simulation_test (session_id, payload) VALUES (%s, %s)",
            (session_id, payload)
        )
        # Immediate readback with filtering
        rows = query_db(
            "SELECT id, session_id, payload FROM workload_simulation_test WHERE session_id = %s ORDER BY id DESC LIMIT 5",
            (session_id,)
        )
        return {"success": True, "rows_read": len(rows)}
    except Exception as e:
        return {"success": False, "error": str(e)}



