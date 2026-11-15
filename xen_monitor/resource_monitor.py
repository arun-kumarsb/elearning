"""
Xen Resource Monitoring Scheduler & Dynamic Allocation Controller
Coordinates XAPI communication, metric normalization, historical storage,
intelligent elasticity evaluation, and safe dynamic resource actuation.
"""

import time
import os
import sys
import uuid
import threading
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from xen_monitor.monitor_config import MonitorConfig
from xen_monitor.xen_api_client import XenAPIClient
from xen_monitor.network_monitor import NetworkMonitor
from xen_monitor.vm_metrics import MetricsNormalizer
from xen_monitor.allocation_engine import AllocationEngine
from backend.database import execute_db, query_db

logger = logging.getLogger("ResourceMonitor")

class XenResourceMonitor:
    _instance = None
    _allocation_lock = threading.Lock()

    def __init__(self, config: Optional[MonitorConfig] = None):
        self.config = config or MonitorConfig()
        self.client = XenAPIClient(self.config)
        self.network_monitor = NetworkMonitor()
        self.normalizer = MetricsNormalizer(self.network_monitor)
        self.allocation_engine = AllocationEngine(self.config)

        # Independent allocation locks for CPU and RAM
        self._cpu_allocation_lock = threading.Lock()
        self._ram_allocation_lock = threading.Lock()

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()

        self.last_poll_time: Optional[float] = None
        self.last_successful_update: Optional[float] = None
        self.consecutive_failures: int = 0
        self.last_error: Optional[str] = None
        self.last_xen_operation: Optional[Dict[str, Any]] = None

        # Check persisted emergency stop status from DB
        self._check_persisted_emergency_stop()

        # Cached latest snapshot
        self._latest_state: Dict[str, Any] = {
            "status": "initializing",
            "connected": False,
            "hypervisor": None,
            "vms": {},
            "all_discovered_vms": [],
            "recommendations": {},
            "last_successful_update": None,
            "last_xen_operation": None,
            "error": None
        }

    def _check_persisted_emergency_stop(self):
        """Check if emergency stop was engaged in a previous run and restore it."""
        try:
            rows = query_db(
                """
                SELECT action_type, execution_status FROM resource_allocation_history
                WHERE action_type IN ('emergency_stop', 'emergency_stop_reset')
                ORDER BY created_at DESC, id DESC LIMIT 1
                """
            )
            if rows and rows[0]["action_type"] == "emergency_stop" and rows[0]["execution_status"] in ("engaged", "ENGAGED"):
                self.allocation_engine.set_emergency_stop(True)
                logger.warning("Restored active EMERGENCY STOP state from database audit history.")
        except Exception as e:
            logger.debug(f"Could not restore emergency stop state from DB: {e}")

    @classmethod
    def get_instance(cls, config: Optional[MonitorConfig] = None):
        """Singleton accessor for application-wide resource monitor."""
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance

    def set_allocation_mode(self, mode: str) -> str:
        """Switch allocation mode between 'manual' and 'auto'."""
        clean_mode = mode.lower().strip()
        if clean_mode in ("manual", "auto"):
            self.config.allocation_mode = clean_mode
            logger.info(f"Allocation mode updated to: {clean_mode}")
            return clean_mode
        raise ValueError(f"Invalid allocation mode '{mode}'. Must be 'manual' or 'auto'.")

    def set_emergency_stop(self, enabled: bool, reason: str = "Administrator emergency stop", initiated_by: str = "admin") -> bool:
        """Toggle emergency stop status and halt any active synthetic workloads and student load simulations."""
        if enabled:
            self.allocation_engine.set_emergency_stop(True)
            self.config.allocation_mode = "manual"
            try:
                from backend.services.workload_service import WorkloadSimulatorService
                WorkloadSimulatorService.get_instance().stop_all_workloads()
            except Exception as e:
                logger.warning(f"Failed to stop active workloads during emergency stop: {e}")
            try:
                from backend.services.student_load_service import StudentLoadSimulatorService
                StudentLoadSimulatorService.get_instance().emergency_stop_all()
            except Exception as e:
                logger.warning(f"Failed to stop student load simulations during emergency stop: {e}")
            self._persist_allocation_action({
                "vm_name": "Hypervisor",
                "vm_uuid": None,
                "resource_type": "all",
                "previous_value": 0.0,
                "requested_value": 0.0,
                "actual_value": 0.0,
                "trigger_reason": reason,
                "action_type": "emergency_stop",
                "execution_status": "engaged",
                "initiated_by": initiated_by,
                "verification_status": "verified"
            })
            return True
        else:
            return self.reset_emergency_stop(reason=reason, initiated_by=initiated_by)

    def reset_emergency_stop(self, reason: str = "Administrator reset", initiated_by: str = "admin") -> bool:
        """Explicitly reset emergency stop, return operational mode to manual, and record audit log."""
        self.allocation_engine.set_emergency_stop(False)
        self.config.allocation_mode = "manual"
        self._persist_allocation_action({
            "vm_name": "Hypervisor",
            "vm_uuid": None,
            "resource_type": "all",
            "previous_value": 0.0,
            "requested_value": 0.0,
            "actual_value": 0.0,
            "trigger_reason": f"Emergency stop cleared by administrator. Reason: {reason}",
            "action_type": "emergency_stop_reset",
            "execution_status": "success",
            "initiated_by": initiated_by,
            "verification_status": "verified"
        })
        logger.warning(f"EMERGENCY STOP explicitly reset by {initiated_by}. Mode returned to MANUAL.")
        return False

    def start(self):
        """Start the background monitoring thread."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._run_loop, daemon=True, name="XenMonitorThread")
            self._thread.start()
            logger.info(f"Xen Resource Monitoring Engine started (Interval: {self.config.poll_interval_sec}s)")

    def stop(self):
        """Stop the background monitoring thread."""
        with self._lock:
            self._running = False
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=2.0)
            self.client.close()
            logger.info("Xen Resource Monitoring Engine stopped.")

    def _run_loop(self):
        """Periodic polling loop."""
        while self._running:
            try:
                self.poll_once()
            except Exception as e:
                logger.error(f"Unexpected error in monitoring cycle: {e}")
            time.sleep(self.config.poll_interval_sec)

    def poll_once(self) -> Dict[str, Any]:
        """Execute a single polling iteration against XCP-ng hypervisor."""
        self.last_poll_time = time.time()
        now = self.last_poll_time
        iso_time = datetime.fromtimestamp(now, tz=timezone.utc).isoformat()

        # Connect if not connected
        if not self.client.is_connected:
            connected = self.client.connect()
            if not connected:
                self.consecutive_failures += 1
                self.last_error = self.client.last_error
                with self._lock:
                    self._latest_state = {
                        "status": "offline",
                        "connected": False,
                        "hypervisor": None,
                        "vms": {},
                        "all_discovered_vms": [],
                        "recommendations": {},
                        "last_poll_time": now,
                        "last_successful_update": self.last_successful_update,
                        "last_successful_update_iso": datetime.fromtimestamp(
                            self.last_successful_update, tz=timezone.utc
                        ).isoformat() if self.last_successful_update else None,
                        "consecutive_failures": self.consecutive_failures,
                        "error": self.last_error,
                        "diagnostics": {
                            "xcp_host": self.config.xcp_host,
                            "xcp_user": self.config.xcp_username,
                            "reason": self.last_error or "Connection to XCP-ng host failed."
                        }
                    }
                return self._latest_state

        # We are connected, retrieve live metrics
        try:
            # 1. Host Metrics
            raw_host = self.client.get_host_metrics()
            norm_host = self.normalizer.normalize_host_metrics(raw_host, now)

            # 2. Discover all VMs
            all_vms = self.client.get_all_vms()

            # 3. Target Specific VMs (Alpine-Linux and Alpine-DB)
            app_vm_rec = self.client.get_vm_by_name(self.config.app_vm_name)
            db_vm_rec = self.client.get_vm_by_name(self.config.db_vm_name)

            norm_vms: Dict[str, Any] = {}
            recommendations: Dict[str, Any] = {}

            # Process Application VM
            if app_vm_rec:
                actual_app_name = app_vm_rec.get("name", self.config.app_vm_name)
                logger.info(f"Processing metrics for Application VM: {actual_app_name} (UUID: {app_vm_rec.get('uuid')})")
                raw_app_metrics = self.client.get_vm_runtime_metrics(app_vm_rec)
                norm_app = self.normalizer.normalize_vm_metrics(
                    raw_app_metrics, role_label="app_vm", expected_ip=self.config.app_vm_ip, timestamp=now
                )
                norm_vms[self.config.app_vm_name] = norm_app
                if actual_app_name != self.config.app_vm_name:
                    norm_vms[actual_app_name] = norm_app

                # Elasticity recommendation
                recommendations[actual_app_name] = self.allocation_engine.evaluate_vm(norm_app, host_metrics=norm_host)
                # Store historical metric
                self._persist_metric(norm_app)
            else:
                logger.warning(f"Application VM named '{self.config.app_vm_name}' not found on XCP-ng host.")
                norm_vms[self.config.app_vm_name] = {
                    "name": self.config.app_vm_name,
                    "status": "not_discovered",
                    "reason": f"VM named '{self.config.app_vm_name}' not found on XCP-ng host."
                }

            # Process Database VM
            if db_vm_rec:
                actual_db_name = db_vm_rec.get("name", self.config.db_vm_name)
                logger.info(f"Processing metrics for Database VM: {actual_db_name} (UUID: {db_vm_rec.get('uuid')})")
                raw_db_metrics = self.client.get_vm_runtime_metrics(db_vm_rec)
                norm_db = self.normalizer.normalize_vm_metrics(
                    raw_db_metrics, role_label="db_vm", expected_ip=self.config.db_vm_ip, timestamp=now
                )
                norm_vms[self.config.db_vm_name] = norm_db
                if actual_db_name != self.config.db_vm_name:
                    norm_vms[actual_db_name] = norm_db

                # Elasticity recommendation
                recommendations[actual_db_name] = self.allocation_engine.evaluate_vm(norm_db, host_metrics=norm_host)
                # Store historical metric
                self._persist_metric(norm_db)
            else:
                logger.warning(f"Database VM named '{self.config.db_vm_name}' not found on XCP-ng host.")
                norm_vms[self.config.db_vm_name] = {
                    "name": self.config.db_vm_name,
                    "status": "not_discovered",
                    "reason": f"VM named '{self.config.db_vm_name}' not found on XCP-ng host."
                }

            # Persist host metric
            self._persist_host_metric(norm_host)

            # Persist recommendations history
            for rec in recommendations.values():
                self._persist_recommendation(rec)

            # ---------------------------------------------------------
            # AUTOMATED ACTUATION (Phase 3 Closed-Loop Execution)
            # Only executes if ALLOCATION_MODE is 'auto' and emergency stop is NOT engaged
            # ---------------------------------------------------------
            if self.config.allocation_mode.lower() == "auto" and not self.allocation_engine.emergency_stop:
                if self._allocation_lock.acquire(blocking=False):
                    try:
                        for target_vm_name, rec in recommendations.items():
                            # Check CPU automated scaling
                            if rec.get("cpu_action") in ("SCALE_UP", "SCALE_DOWN"):
                                target_vcpus = rec.get("recommended_vcpus")
                                if target_vcpus and target_vcpus != rec.get("current_vcpus"):
                                    logger.info(f"Auto-actuating CPU scaling for '{target_vm_name}': {rec.get('current_vcpus')} -> {target_vcpus}")
                                    res = self.client.set_vm_vcpus(target_vm_name, target_vcpus)
                                    status = "success" if res.get("success") else "failed"
                                    err = res.get("error")
                                    act_val = res.get("actual_value", rec.get("current_vcpus")) if status == "success" else None
                                    if status == "success":
                                        self.allocation_engine.record_action_applied(target_vm_name, "cpu")
                                    self._persist_allocation_action({
                                        "vm_name": target_vm_name,
                                        "vm_uuid": rec.get("vm_uuid"),
                                        "resource_type": "cpu",
                                        "previous_value": rec.get("current_vcpus"),
                                        "requested_value": target_vcpus,
                                        "actual_value": act_val,
                                        "trigger_reason": rec.get("rationale"),
                                        "action_type": "auto_scale",
                                        "execution_status": status,
                                        "error_message": err,
                                        "initiated_by": "auto"
                                    })
                                    if status == "success":
                                        self.last_xen_operation = {
                                            "timestamp": now,
                                            "timestamp_iso": iso_time,
                                            "operation": "auto_scale_cpu",
                                            "vm_name": target_vm_name,
                                            "resource_type": "cpu",
                                            "requested_value": target_vcpus,
                                            "actual_value": act_val,
                                            "status": "verified"
                                        }

                            # Check RAM automated scaling
                            if rec.get("ram_action") in ("SCALE_UP", "SCALE_DOWN"):
                                target_ram = rec.get("recommended_ram_mb")
                                if target_ram and target_ram != rec.get("current_ram_mb"):
                                    logger.info(f"Auto-actuating RAM ballooning for '{target_vm_name}': {rec.get('current_ram_mb')} -> {target_ram} MB")
                                    res = self.client.set_vm_dynamic_memory(target_vm_name, target_ram)
                                    status = "success" if res.get("success") else "failed"
                                    err = res.get("error")
                                    act_val = res.get("actual_value", rec.get("current_ram_mb")) if status == "success" else None
                                    if status == "success":
                                        self.allocation_engine.record_action_applied(target_vm_name, "ram")
                                        self.last_xen_operation = {
                                            "timestamp": now,
                                            "timestamp_iso": iso_time,
                                            "operation": "auto_scale_ram",
                                            "vm_name": target_vm_name,
                                            "resource_type": "ram",
                                            "requested_value": target_ram,
                                            "actual_value": act_val,
                                            "status": "verified"
                                        }
                                    self._persist_allocation_action({
                                        "vm_name": target_vm_name,
                                        "vm_uuid": rec.get("vm_uuid"),
                                        "resource_type": "ram",
                                        "previous_value": rec.get("current_ram_mb"),
                                        "requested_value": target_ram,
                                        "actual_value": act_val,
                                        "trigger_reason": rec.get("rationale"),
                                        "action_type": "auto_scale",
                                        "execution_status": status,
                                        "error_message": err,
                                        "initiated_by": "auto"
                                    })
                    finally:
                        self._allocation_lock.release()
                else:
                    logger.debug("Allocation lock active; skipping automated scaling check this cycle.")

            self.last_successful_update = now
            self.consecutive_failures = 0
            self.last_error = None

            with self._lock:
                self._latest_state = {
                    "status": "online",
                    "connected": True,
                    "timestamp": now,
                    "timestamp_iso": iso_time,
                    "last_successful_update": self.last_successful_update,
                    "last_successful_update_iso": iso_time,
                    "hypervisor": norm_host,
                    "vms": norm_vms,
                    "all_discovered_vms": [
                        {"name": v["name"], "uuid": v["uuid"], "power_state": v["power_state"], "vcpus": v["vcpus"]}
                        for v in all_vms
                    ],
                    "recommendations": recommendations,
                    "allocation_mode": self.config.allocation_mode,
                    "emergency_stop": self.allocation_engine.emergency_stop,
                    "error": None
                }

            return self._latest_state

        except Exception as e:
            self.consecutive_failures += 1
            self.last_error = str(e)
            logger.error(f"Error querying XAPI metrics: {e}")
            self.client.close()  # Reset session for next retry

            with self._lock:
                self._latest_state = {
                    "status": "error",
                    "connected": False,
                    "hypervisor": None,
                    "vms": {},
                    "all_discovered_vms": [],
                    "recommendations": {},
                    "last_poll_time": now,
                    "last_successful_update": self.last_successful_update,
                    "consecutive_failures": self.consecutive_failures,
                    "error": self.last_error
                }
            return self._latest_state

    # -----------------------------------------------------------------
    # MANUAL AND RECOMMENDED SCALING ACTUATION METHODS
    # -----------------------------------------------------------------
    def apply_manual_cpu(self, vm_identifier: str, target_vcpus: int, reason: str = "Admin manual override", initiated_by: str = "admin") -> Dict[str, Any]:
        """Manually actuate vCPU modification via XenAPI and record audit log."""
        if self.allocation_engine.emergency_stop:
            return {"success": False, "error": "Emergency Stop is active. Manual scaling blocked."}

        with self._allocation_lock:
            res = self.client.set_vm_vcpus(vm_identifier, target_vcpus)
            vm_name = res.get("vm_name") or vm_identifier
            vm_uuid = res.get("vm_uuid")
            res_status = res.get("status", "SUCCESS" if res.get("success") else "FAILED")
            status = "maintenance_required" if res_status == "MAINTENANCE_REQUIRED" else ("success" if res.get("success") else "failed")

            if status == "success":
                self.allocation_engine.record_action_applied(vm_name, "cpu")
                self.last_xen_operation = {
                    "timestamp": time.time(),
                    "timestamp_iso": datetime.now(timezone.utc).isoformat(),
                    "operation": "manual_cpu",
                    "vm_name": vm_name,
                    "resource_type": "cpu",
                    "requested_value": target_vcpus,
                    "actual_value": res.get("actual_value"),
                    "status": "verified"
                }

            self._persist_allocation_action({
                "vm_name": vm_name,
                "vm_uuid": vm_uuid,
                "resource_type": "cpu",
                "previous_value": res.get("previous_value"),
                "requested_value": target_vcpus,
                "actual_value": res.get("actual_value"),
                "trigger_reason": reason,
                "action_type": "manual_cpu",
                "execution_status": status,
                "error_message": res.get("error"),
                "initiated_by": initiated_by,
                "controller_version": "v2.0",
                "verification_status": "verified" if status == "success" else ("maintenance_required" if status == "maintenance_required" else "failed")
            })
            return res

    def apply_manual_ram(self, vm_identifier: str, target_ram_mb: float, reason: str = "Admin manual override", initiated_by: str = "admin") -> Dict[str, Any]:
        """Manually actuate dynamic memory ballooning via XenAPI and record audit log."""
        if self.allocation_engine.emergency_stop:
            return {"success": False, "error": "Emergency Stop is active. Manual scaling blocked."}

        with self._allocation_lock:
            res = self.client.set_vm_dynamic_memory(vm_identifier, target_ram_mb)
            vm_name = res.get("vm_name") or vm_identifier
            vm_uuid = res.get("vm_uuid")
            status = "success" if res.get("success") else "failed"

            if status == "success":
                self.allocation_engine.record_action_applied(vm_name, "ram")
                self.last_xen_operation = {
                    "timestamp": time.time(),
                    "timestamp_iso": datetime.now(timezone.utc).isoformat(),
                    "operation": "manual_ram",
                    "vm_name": vm_name,
                    "resource_type": "ram",
                    "requested_value": target_ram_mb,
                    "actual_value": res.get("actual_value"),
                    "status": "verified"
                }

            self._persist_allocation_action({
                "vm_name": vm_name,
                "vm_uuid": vm_uuid,
                "resource_type": "ram",
                "previous_value": res.get("previous_value"),
                "requested_value": target_ram_mb,
                "actual_value": res.get("actual_value"),
                "trigger_reason": reason,
                "action_type": "manual_ram",
                "execution_status": status,
                "error_message": res.get("error"),
                "initiated_by": initiated_by,
                "controller_version": "v2.0",
                "verification_status": "verified" if status == "success" else "failed"
            })
            return res

    def reboot_vm(self, vm_identifier: str, reason: str = "Admin requested reboot", initiated_by: str = "admin") -> Dict[str, Any]:
        """Perform graceful VM reboot via XenAPI with audit logging."""
        res = self.client.clean_reboot_vm(vm_identifier)
        status = "success" if res.get("success") else "failed"
        self._persist_allocation_action({
            "vm_name": res.get("vm_name") or vm_identifier,
            "resource_type": "vm",
            "previous_value": 0.0,
            "requested_value": 0.0,
            "actual_value": 0.0,
            "trigger_reason": reason,
            "action_type": "vm_reboot",
            "execution_status": status,
            "error_message": res.get("error"),
            "initiated_by": initiated_by,
            "controller_version": "v2.0",
            "verification_status": "verified" if status == "success" else "failed"
        })
        return res

    def transition_to_baseline(self, vm_identifier: str, initiated_by: str = "admin") -> Dict[str, Any]:
        """
        Safely transitions a VM from current configuration to baseline policy (1 vCPU, 1024 MB RAM)
        with host verification, MariaDB buffer pool safety check, and audit logging.
        """
        if self.allocation_engine.emergency_stop:
            return {
                "success": False,
                "status": "BLOCKED",
                "vm_name": vm_identifier,
                "error": "Emergency Stop is active. Baseline transition blocked."
            }

        with self._allocation_lock:
            policy = self.config.get_vm_policy(vm_identifier)
            target_vcpus = policy.get("initial_vcpus", 1)
            target_ram_mb = policy.get("initial_ram_mb", 1024.0)

            # Check MariaDB buffer pool safety for database VM before scaling RAM
            if "db" in vm_identifier.lower():
                safety = self.client.verify_mariadb_baseline_safety(target_ram_mb)
                if not safety.get("safe", True):
                    err = safety.get("error", "MariaDB buffer pool size unsafe for 1024 MB baseline.")
                    logger.warning(f"MariaDB safety check blocked baseline transition on {vm_identifier}: {err}")
                    self._persist_allocation_action({
                        "vm_name": vm_identifier,
                        "resource_type": "ram",
                        "previous_value": target_ram_mb,
                        "requested_value": target_ram_mb,
                        "actual_value": target_ram_mb,
                        "trigger_reason": f"MariaDB safety check blocked baseline: {err}",
                        "action_type": "baseline_transition",
                        "execution_status": "blocked",
                        "error_message": err,
                        "initiated_by": initiated_by,
                        "controller_version": "v2.0",
                        "verification_status": "blocked"
                    })
                    return {
                        "success": False,
                        "status": "BLOCKED",
                        "vm_name": vm_identifier,
                        "target_baseline": {"vcpus": target_vcpus, "ram_mb": target_ram_mb},
                        "error": err,
                        "mariadb_safety": safety,
                        "message": f"Baseline transition blocked by MariaDB safety check: {err}"
                    }

            # 1. vCPU Transition
            cpu_res = self.client.set_vm_vcpus(vm_identifier, target_vcpus)
            cpu_ok = cpu_res.get("success", False)
            cpu_status = cpu_res.get("status", "SUCCESS" if cpu_ok else "FAILED")
            if cpu_ok:
                self.allocation_engine.record_action_applied(vm_identifier, "cpu")

            self._persist_allocation_action({
                "vm_name": vm_identifier,
                "vm_uuid": cpu_res.get("vm_uuid"),
                "resource_type": "cpu",
                "previous_value": cpu_res.get("previous_value"),
                "requested_value": target_vcpus,
                "actual_value": cpu_res.get("actual_value"),
                "trigger_reason": "Baseline transition approved by administrator",
                "action_type": "baseline_transition",
                "execution_status": cpu_status.lower(),
                "error_message": cpu_res.get("error"),
                "initiated_by": initiated_by,
                "controller_version": "v2.0",
                "verification_status": "verified" if cpu_ok else ("maintenance_required" if cpu_status == "MAINTENANCE_REQUIRED" else "failed")
            })

            # 2. RAM Transition
            ram_res = self.client.set_vm_dynamic_memory(vm_identifier, target_ram_mb)
            ram_ok = ram_res.get("success", False)
            if ram_ok:
                self.allocation_engine.record_action_applied(vm_identifier, "ram")
            self._persist_allocation_action({
                "vm_name": vm_identifier,
                "vm_uuid": ram_res.get("vm_uuid"),
                "resource_type": "ram",
                "previous_value": ram_res.get("previous_value"),
                "requested_value": target_ram_mb,
                "actual_value": ram_res.get("actual_value"),
                "trigger_reason": "Baseline transition approved by administrator",
                "action_type": "baseline_transition",
                "execution_status": "success" if ram_ok else "failed",
                "error_message": ram_res.get("error"),
                "initiated_by": initiated_by,
                "controller_version": "v2.0",
                "verification_status": "verified" if ram_ok else "failed"
            })

            if cpu_status == "MAINTENANCE_REQUIRED":
                overall_status = "MAINTENANCE_REQUIRED"
                all_ok = False
                msg = (
                    f"Baseline transition for '{vm_identifier}' requires maintenance: "
                    f"Startup vCPUs configured to {target_vcpus}, RAM set to {target_ram_mb} MB. "
                    f"Live CPU hot-unplug is unsupported by running guest kernel (online: {cpu_res.get('actual_value')}). "
                    f"A controlled VM restart is required to achieve {target_vcpus} online vCPU."
                )
            elif cpu_ok and ram_ok:
                overall_status = "SUCCESS"
                all_ok = True
                msg = f"Successfully transitioned '{vm_identifier}' to baseline ({target_vcpus} vCPU, {target_ram_mb} MB RAM)!"
            else:
                overall_status = "FAILED"
                all_ok = False
                msg = f"Baseline transition incomplete: CPU ({cpu_res.get('error') or 'OK'}), RAM ({ram_res.get('error') or 'OK'})."

            if all_ok:
                self.last_xen_operation = {
                    "timestamp": time.time(),
                    "timestamp_iso": datetime.now(timezone.utc).isoformat(),
                    "operation": "baseline_transition",
                    "vm_name": vm_identifier,
                    "resource_type": "cpu_and_ram",
                    "requested_value": f"{target_vcpus} vCPU / {target_ram_mb} MB",
                    "actual_value": f"{cpu_res.get('actual_value')} vCPU / {ram_res.get('actual_value')} MB",
                    "status": "verified"
                }

            return {
                "success": all_ok,
                "status": overall_status,
                "vm_name": vm_identifier,
                "target_baseline": {"vcpus": target_vcpus, "ram_mb": target_ram_mb},
                "cpu_result": cpu_res,
                "ram_result": ram_res,
                "message": msg
            }

    def execute_baseline_maintenance(self, vm_identifier: str, initiated_by: str = "admin") -> Dict[str, Any]:
        """
        Execute administrator-approved controlled baseline maintenance procedure:
        clean shutdown -> configure startup 1 vCPU & 1024 MB RAM -> restart VM -> verify.
        """
        if self.allocation_engine.emergency_stop:
            return {"success": False, "status": "BLOCKED", "error": "Emergency Stop is active."}

        with self._allocation_lock:
            policy = self.config.get_vm_policy(vm_identifier)
            target_vcpus = policy.get("initial_vcpus", 1)
            target_ram_mb = policy.get("initial_ram_mb", 1024.0)

            res = self.client.execute_baseline_maintenance(vm_identifier, target_vcpus=target_vcpus, target_ram_mb=target_ram_mb)
            vm_name = res.get("vm_name", vm_identifier)
            status = "success" if res.get("success") else ("blocked" if res.get("status") == "BLOCKED" else "failed")

            if res.get("success"):
                self.allocation_engine.record_action_applied(vm_name, "cpu")
                self.allocation_engine.record_action_applied(vm_name, "ram")
                self.last_xen_operation = {
                    "timestamp": time.time(),
                    "timestamp_iso": datetime.now(timezone.utc).isoformat(),
                    "operation": "baseline_maintenance",
                    "vm_name": vm_name,
                    "resource_type": "cpu_and_ram",
                    "requested_value": f"{target_vcpus} vCPU / {target_ram_mb} MB",
                    "actual_value": res.get("actual_value"),
                    "status": "verified"
                }

            self._persist_allocation_action({
                "vm_name": vm_name,
                "vm_uuid": res.get("vm_uuid"),
                "resource_type": "cpu_and_ram",
                "previous_value": 0.0,
                "requested_value": target_vcpus,
                "actual_value": target_vcpus if res.get("success") else 0.0,
                "trigger_reason": "Controlled VM baseline maintenance procedure executed by administrator",
                "action_type": "baseline_maintenance",
                "execution_status": status,
                "error_message": res.get("error"),
                "initiated_by": initiated_by,
                "controller_version": "v2.0",
                "verification_status": "verified" if res.get("success") else "failed"
            })
            return res

    def apply_recommended_action(self, vm_identifier: str, initiated_by: str = "admin") -> Dict[str, Any]:
        """Apply pending recommendation for a specific VM."""
        state = self.get_latest_metrics()
        recs = state.get("recommendations", {})

        target_rec = None
        for k, r in recs.items():
            if k.lower() == vm_identifier.lower() or r.get("vm_uuid") == vm_identifier:
                target_rec = r
                break

        if not target_rec:
            return {"success": False, "error": f"No active recommendations found for VM '{vm_identifier}'."}

        actions_performed = []
        # CPU
        if target_rec.get("cpu_action") in ("SCALE_UP", "SCALE_DOWN"):
            cpu_res = self.apply_manual_cpu(
                vm_identifier=target_rec.get("vm_name", vm_identifier),
                target_vcpus=target_rec["recommended_vcpus"],
                reason=f"Applied recommendation: {target_rec.get('rationale')}",
                initiated_by=initiated_by
            )
            actions_performed.append({"resource": "cpu", "result": cpu_res})

        # RAM
        if target_rec.get("ram_action") in ("SCALE_UP", "SCALE_DOWN"):
            ram_res = self.apply_manual_ram(
                vm_identifier=target_rec.get("vm_name", vm_identifier),
                target_ram_mb=target_rec["recommended_ram_mb"],
                reason=f"Applied recommendation: {target_rec.get('rationale')}",
                initiated_by=initiated_by
            )
            actions_performed.append({"resource": "ram", "result": ram_res})

        if not actions_performed:
            return {"success": True, "message": "No actionable scaling recommendations pending for this VM.", "actions": []}

        all_ok = all(a["result"].get("success") for a in actions_performed)
        return {
            "success": all_ok,
            "message": f"Applied {len(actions_performed)} recommended scaling action(s).",
            "actions": actions_performed
        }

    def configure_startup_vcpus(self, vm_identifier: str, target_startup_vcpus: int = 1, initiated_by: str = "admin") -> Dict[str, Any]:
        """Configure VM startup vCPU count (VCPUs_at_startup) using XenAPI with audit logging."""
        with self._allocation_lock:
            res = self.client.configure_startup_vcpus(vm_identifier, target_startup_vcpus=target_startup_vcpus)
            vm_name = res.get("vm_name") or vm_identifier
            vm_uuid = res.get("vm_uuid")
            res_status = res.get("status", "SUCCESS" if res.get("success") else "FAILED")
            status = "maintenance_required" if res_status == "MAINTENANCE_REQUIRED" else ("success" if res.get("success") else "failed")

            self._persist_allocation_action({
                "vm_name": vm_name,
                "vm_uuid": vm_uuid,
                "resource_type": "cpu",
                "previous_value": res.get("previous_value"),
                "requested_value": target_startup_vcpus,
                "actual_value": res.get("actual_value"),
                "trigger_reason": f"Administrator configured startup vCPUs to {target_startup_vcpus}",
                "action_type": "configure_startup_vcpus",
                "execution_status": status,
                "error_message": res.get("error"),
                "initiated_by": initiated_by,
                "controller_version": "v2.0",
                "verification_status": "verified" if status == "success" else ("maintenance_required" if status == "maintenance_required" else "failed")
            })
            return res

    # -----------------------------------------------------------------
    # PERSISTENCE METHODS
    # -----------------------------------------------------------------
    def _persist_allocation_action(self, action: Dict[str, Any]):
        """Persist scaling action audit record into resource_allocation_history table."""
        try:
            sql = """
                INSERT INTO resource_allocation_history
                (vm_name, vm_uuid, resource_type, previous_value, requested_value, actual_value,
                 trigger_reason, action_type, execution_status, error_message, initiated_by,
                 controller_version, xen_operation_id, verification_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            prev_val = float(action.get("previous_value") if action.get("previous_value") is not None else 0.0)
            req_val = float(action.get("requested_value") if action.get("requested_value") is not None else 0.0)

            # Never default actual_value to 0.0 when failed! Fallback to previous_value
            if action.get("actual_value") is not None:
                act_val = float(action.get("actual_value"))
            elif action.get("previous_value") is not None:
                act_val = float(action.get("previous_value"))
            else:
                act_val = 0.0

            err_msg = action.get("error_message") or action.get("error")
            raw_status = action.get("execution_status")
            if raw_status:
                exec_status = raw_status.lower() if str(raw_status).lower() in ("success", "failed") else raw_status
            else:
                exec_status = "success"

            # If error message exists and status was SUCCESS/success, fix to failed
            if err_msg and str(exec_status).lower() == "success":
                exec_status = "failed"

            # If status claimed as SUCCESS but value didn't change when a change was requested
            if str(exec_status).lower() == "success" and abs(req_val - prev_val) > 0.001 and abs(act_val - req_val) > 0.001:
                exec_status = "failed"
                err_msg = err_msg or f"Verification failed: actual allocation ({act_val}) did not reach requested ({req_val})"

            controller_ver = action.get("controller_version", "v2.0")
            xen_op_id = action.get("xen_operation_id") or f"xen-op-{uuid.uuid4().hex[:10]}"
            verif_status = action.get("verification_status")
            if not verif_status:
                verif_status = "verified" if str(exec_status).lower() == "success" else ("maintenance_required" if str(exec_status).upper() == "MAINTENANCE_REQUIRED" else "failed")

            execute_db(sql, (
                action.get("vm_name"),
                action.get("vm_uuid"),
                action.get("resource_type"),
                prev_val,
                req_val,
                act_val,
                action.get("trigger_reason"),
                action.get("action_type", "auto_scale"),
                exec_status,
                err_msg,
                action.get("initiated_by", "system"),
                controller_ver,
                xen_op_id,
                verif_status
            ))
            logger.info(f"Persisted allocation audit log: {action.get('action_type')} on {action.get('vm_name')} ({exec_status})")
        except Exception as e:
            logger.warning(f"Failed to persist allocation action audit log: {e}")

    def _persist_metric(self, vm_norm: Dict[str, Any]):
        """Save a single normalized VM telemetry record into MariaDB/SQLite."""
        try:
            sql = """
                INSERT INTO vm_metrics_history 
                (vm_name, vm_uuid, entity_type, cpu_percent, ram_percent, allocated_ram_mb, used_ram_mb, vcpu_count, network_rx_bytes, network_tx_bytes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            execute_db(sql, (
                vm_norm["name"],
                vm_norm.get("uuid"),
                vm_norm.get("entity_type", "vm"),
                vm_norm.get("cpu_percent", 0.0),
                vm_norm.get("ram_percent", 0.0),
                vm_norm.get("allocated_ram_mb", 0.0),
                vm_norm.get("used_ram_mb", 0.0),
                vm_norm.get("vcpu_count", 1),
                vm_norm.get("network_rx_bytes", 0),
                vm_norm.get("network_tx_bytes", 0)
            ))
            logger.debug(f"Persisted VM metric history for {vm_norm.get('name')}")
        except Exception as e:
            logger.warning(f"Failed to persist VM metric history for {vm_norm.get('name')}: {e}")

    def _persist_host_metric(self, host_norm: Dict[str, Any]):
        """Save host hypervisor metric record."""
        try:
            sql = """
                INSERT INTO vm_metrics_history 
                (vm_name, vm_uuid, entity_type, cpu_percent, ram_percent, allocated_ram_mb, used_ram_mb, vcpu_count, network_rx_bytes, network_tx_bytes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            execute_db(sql, (
                host_norm["name"],
                host_norm.get("uuid"),
                "hypervisor",
                host_norm.get("cpu_percent", 0.0),
                host_norm.get("ram_percent", 0.0),
                host_norm.get("total_ram_mb", 0.0),
                host_norm.get("used_ram_mb", 0.0),
                host_norm.get("total_cpu_cores", 0),
                0,
                0
            ))
            logger.debug("Persisted Host hypervisor metric history")
        except Exception as e:
            logger.warning(f"Failed to persist Host metric history: {e}")

    def _persist_recommendation(self, rec: Dict[str, Any]):
        """Save allocation decision history."""
        try:
            sql = """
                INSERT INTO allocation_decisions_history
                (vm_name, cpu_action, ram_action, current_vcpus, recommended_vcpus, current_ram_mb, recommended_ram_mb, rationale, cooldown_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            execute_db(sql, (
                rec["vm_name"],
                rec["cpu_action"],
                rec["ram_action"],
                rec["current_vcpus"],
                rec["recommended_vcpus"],
                rec["current_ram_mb"],
                rec["recommended_ram_mb"],
                rec["rationale"],
                1 if rec["cooldown_active"] else 0
            ))
            logger.debug(f"Persisted elasticity recommendation for {rec.get('vm_name')}")
        except Exception as e:
            logger.warning(f"Failed to persist allocation decision: {e}")

    # -----------------------------------------------------------------
    # QUERY METHODS FOR FLASK API
    # -----------------------------------------------------------------
    def get_latest_metrics(self) -> Dict[str, Any]:
        """Return cached snapshot of latest live metrics."""
        with self._lock:
            needs_poll = (self._latest_state.get("status") == "initializing")
            if not needs_poll:
                return dict(self._latest_state)
        return self.poll_once()

    def get_host_metrics(self) -> Dict[str, Any]:
        state = self.get_latest_metrics()
        return state.get("hypervisor") or {"status": state.get("status"), "error": state.get("error")}

    def get_vms(self) -> List[Dict[str, Any]]:
        state = self.get_latest_metrics()
        return state.get("all_discovered_vms", [])

    def get_vm_metrics(self, vm_identifier: str) -> Optional[Dict[str, Any]]:
        state = self.get_latest_metrics()
        vms = state.get("vms", {})
        if vm_identifier in vms:
            return vms[vm_identifier]
        for k, v in vms.items():
            if isinstance(v, dict):
                if v.get("uuid") == vm_identifier or k.lower() == vm_identifier.lower():
                    return v
        return None

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "engine": "XenResourceMonitor",
                "status": self._latest_state.get("status", "unknown"),
                "connected": self._latest_state.get("connected", False),
                "poll_interval_sec": self.config.poll_interval_sec,
                "last_poll_time": self.last_poll_time,
                "last_successful_update": self.last_successful_update,
                "consecutive_failures": self.consecutive_failures,
                "error": self.last_error,
                "config": self.config.to_dict()
            }

    def get_history(self, vm_name: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Query persistent metric history from database with robust error handling."""
        try:
            safe_limit = min(200, max(1, int(limit)))
            if vm_name:
                sql = f"""
                    SELECT id, timestamp, vm_name, vm_uuid, entity_type, cpu_percent, ram_percent,
                           allocated_ram_mb, used_ram_mb, vcpu_count, network_rx_bytes, network_tx_bytes
                    FROM vm_metrics_history
                    WHERE LOWER(vm_name) = LOWER(%s)
                    ORDER BY timestamp DESC
                    LIMIT {safe_limit}
                """
                rows = query_db(sql, (vm_name,))
            else:
                sql = f"""
                    SELECT id, timestamp, vm_name, vm_uuid, entity_type, cpu_percent, ram_percent,
                           allocated_ram_mb, used_ram_mb, vcpu_count, network_rx_bytes, network_tx_bytes
                    FROM vm_metrics_history
                    ORDER BY timestamp DESC
                    LIMIT {safe_limit}
                """
                rows = query_db(sql)

            if not rows:
                return []

            formatted = []
            for r in rows:
                row_dict = dict(r)
                if row_dict.get("timestamp"):
                    row_dict["timestamp"] = str(row_dict["timestamp"])
                formatted.append(row_dict)
            return formatted
        except Exception as e:
            logger.warning(f"Database query error in get_history: {e}")
            return []

    def get_allocation_status(self) -> Dict[str, Any]:
        """Return dynamic allocation controller configuration and state."""
        with self._lock:
            state = dict(self._latest_state)

        recs = state.get("recommendations", {})
        return {
            "allocation_mode": self.config.allocation_mode,
            "emergency_stop": self.allocation_engine.emergency_stop,
            "poll_interval_sec": self.config.poll_interval_sec,
            "cooldown_period_sec": self.config.cooldown_period_sec,
            "consecutive_breach_threshold": self.config.consecutive_breach_threshold,
            "last_xen_operation": self.last_xen_operation,
            "app_vm_policy": self.config.get_vm_policy(self.config.app_vm_name),
            "db_vm_policy": self.config.get_vm_policy(self.config.db_vm_name),
            "thresholds": {
                "cpu_scale_up_threshold": self.config.cpu_scale_up_threshold,
                "cpu_scale_down_threshold": self.config.cpu_scale_down_threshold,
                "min_vcpus": self.config.min_vcpus,
                "max_vcpus": self.config.max_vcpus,
                "ram_scale_up_threshold": self.config.ram_scale_up_threshold,
                "ram_scale_down_threshold": self.config.ram_scale_down_threshold,
                "ram_increment_mb": self.config.ram_increment_mb,
                "min_ram_mb": self.config.min_ram_mb,
                "max_ram_mb": self.config.max_ram_mb
            },
            "recommendations_count": len(recs),
            "recommendations": recs
        }

    def get_allocation_recommendations(self) -> Dict[str, Any]:
        """Return latest recommendations for all monitored VMs."""
        state = self.get_latest_metrics()
        return state.get("recommendations", {})

    def get_allocation_history(self, vm_name: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Query allocation history from resource_allocation_history table with controller versioning."""
        try:
            safe_limit = min(200, max(1, int(limit)))
            cols = """id, vm_name, vm_uuid, resource_type, previous_value, requested_value,
                   actual_value, trigger_reason, action_type, execution_status,
                   error_message, initiated_by, created_at,
                   controller_version, xen_operation_id, verification_status"""
            if vm_name:
                sql = f"""
                    SELECT {cols}
                    FROM resource_allocation_history
                    WHERE LOWER(vm_name) = LOWER(%s)
                    ORDER BY created_at DESC, id DESC
                    LIMIT {safe_limit}
                """
                rows = query_db(sql, (vm_name,))
            else:
                sql = f"""
                    SELECT {cols}
                    FROM resource_allocation_history
                    ORDER BY created_at DESC, id DESC
                    LIMIT {safe_limit}
                """
                rows = query_db(sql)

            if not rows:
                return []

            formatted = []
            for r in rows:
                row_dict = dict(r)
                if row_dict.get("created_at"):
                    row_dict["created_at"] = str(row_dict["created_at"])
                if not row_dict.get("controller_version"):
                    row_dict["controller_version"] = "legacy"
                formatted.append(row_dict)
            return formatted
        except Exception as e:
            logger.warning(f"Database query error in get_allocation_history: {e}")
            return []


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing Xen Resource Monitor standalone...")
    monitor = XenResourceMonitor()
    result = monitor.poll_once()
    print("Poll Result:")
    import json
    print(json.dumps(result, indent=2, default=str))
