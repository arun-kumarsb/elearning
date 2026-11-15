"""
Xen Resource Monitoring Scheduler & Engine
Coordinates XAPI communication, metric normalization, historical storage,
and dynamic allocation recommendation evaluations.
"""

import time
import os
import sys
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

    def __init__(self, config: Optional[MonitorConfig] = None):
        self.config = config or MonitorConfig()
        self.client = XenAPIClient(self.config)
        self.network_monitor = NetworkMonitor()
        self.normalizer = MetricsNormalizer(self.network_monitor)
        self.allocation_engine = AllocationEngine(self.config)

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()

        self.last_poll_time: Optional[float] = None
        self.last_successful_update: Optional[float] = None
        self.consecutive_failures: int = 0
        self.last_error: Optional[str] = None

        # Cached latest snapshot
        self._latest_state: Dict[str, Any] = {
            "status": "initializing",
            "connected": False,
            "hypervisor": None,
            "vms": {},
            "all_discovered_vms": [],
            "recommendations": {},
            "last_successful_update": None,
            "error": None
        }

    @classmethod
    def get_instance(cls, config: Optional[MonitorConfig] = None):
        """Singleton accessor for application-wide resource monitor."""
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance

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

            # 3. Target Specific VMs (Alpine-Linux-New and Alpine-DB)
            app_vm_rec = self.client.get_vm_by_name(self.config.app_vm_name)
            db_vm_rec = self.client.get_vm_by_name(self.config.db_vm_name)

            norm_vms: Dict[str, Any] = {}
            recommendations: Dict[str, Any] = {}

            # Process Application VM
            if app_vm_rec:
                raw_app_metrics = self.client.get_vm_runtime_metrics(app_vm_rec)
                norm_app = self.normalizer.normalize_vm_metrics(
                    raw_app_metrics, role_label="app_vm", expected_ip=self.config.app_vm_ip, timestamp=now
                )
                norm_vms[self.config.app_vm_name] = norm_app
                # Elasticity recommendation
                recommendations[self.config.app_vm_name] = self.allocation_engine.evaluate_vm(norm_app)
                # Store historical metric
                self._persist_metric(norm_app)
            else:
                norm_vms[self.config.app_vm_name] = {
                    "name": self.config.app_vm_name,
                    "status": "not_discovered",
                    "reason": f"VM named '{self.config.app_vm_name}' not found on XCP-ng host."
                }

            # Process Database VM
            if db_vm_rec:
                raw_db_metrics = self.client.get_vm_runtime_metrics(db_vm_rec)
                norm_db = self.normalizer.normalize_vm_metrics(
                    raw_db_metrics, role_label="db_vm", expected_ip=self.config.db_vm_ip, timestamp=now
                )
                norm_vms[self.config.db_vm_name] = norm_db
                # Elasticity recommendation
                recommendations[self.config.db_vm_name] = self.allocation_engine.evaluate_vm(norm_db)
                # Store historical metric
                self._persist_metric(norm_db)
            else:
                norm_vms[self.config.db_vm_name] = {
                    "name": self.config.db_vm_name,
                    "status": "not_discovered",
                    "reason": f"VM named '{self.config.db_vm_name}' not found on XCP-ng host."
                }

            # Persist host metric
            self._persist_host_metric(norm_host)

            # Persist recommendations
            for rec in recommendations.values():
                self._persist_recommendation(rec)

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
        except Exception as e:
            logger.debug(f"Failed to persist VM metric history: {e}")

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
        except Exception as e:
            logger.debug(f"Failed to persist Host metric history: {e}")

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
        except Exception as e:
            logger.debug(f"Failed to persist allocation decision: {e}")

    # Query methods for Flask API
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
        # Search by exact name
        if vm_identifier in vms:
            return vms[vm_identifier]
        # Search by uuid or lowercase
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
        """Query persistent metric history from database."""
        limit = min(200, max(1, int(limit)))
        if vm_name:
            sql = """
                SELECT id, timestamp, vm_name, vm_uuid, entity_type, cpu_percent, ram_percent,
                       allocated_ram_mb, used_ram_mb, vcpu_count, network_rx_bytes, network_tx_bytes
                FROM vm_metrics_history
                WHERE LOWER(vm_name) = LOWER(%s)
                ORDER BY timestamp DESC
                LIMIT %s
            """
            rows = query_db(sql, (vm_name, limit))
        else:
            sql = """
                SELECT id, timestamp, vm_name, vm_uuid, entity_type, cpu_percent, ram_percent,
                       allocated_ram_mb, used_ram_mb, vcpu_count, network_rx_bytes, network_tx_bytes
                FROM vm_metrics_history
                ORDER BY timestamp DESC
                LIMIT %s
            """
            rows = query_db(sql, (limit,))

        # Format datetimes
        for r in rows:
            if r.get("timestamp"):
                r["timestamp"] = str(r["timestamp"])
        return rows


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing Xen Resource Monitor standalone...")
    monitor = XenResourceMonitor()
    result = monitor.poll_once()
    print("Poll Result:")
    import json
    print(json.dumps(result, indent=2, default=str))
