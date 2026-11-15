"""
VM & Hypervisor Metrics Normalization Module
Standardizes metrics collected from XCP-ng host and guest virtual machines into
unified data structures ready for API responses, database persistence, and UI display.
"""

import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from xen_monitor.network_monitor import NetworkMonitor

class MetricsNormalizer:
    def __init__(self, network_monitor: Optional[NetworkMonitor] = None):
        self.network_monitor = network_monitor or NetworkMonitor()

    def normalize_host_metrics(self, raw_host: Dict[str, Any], timestamp: Optional[float] = None) -> Dict[str, Any]:
        """Normalize physical XCP-ng hypervisor host metrics."""
        now = timestamp or time.time()
        iso_time = datetime.fromtimestamp(now, tz=timezone.utc).isoformat()

        return {
            "entity_type": "hypervisor",
            "name": raw_host.get("host_name", "XCP-ng Hypervisor"),
            "uuid": raw_host.get("host_uuid", "unknown-host-uuid"),
            "ip": raw_host.get("host_ip"),
            "timestamp": now,
            "timestamp_iso": iso_time,
            "total_cpu_cores": int(raw_host.get("total_cpu_cores", 0)),
            "cpu_percent": float(raw_host.get("host_cpu_percent", 0.0)),
            "total_ram_mb": float(raw_host.get("total_ram_mb", 0.0)),
            "available_ram_mb": float(raw_host.get("available_ram_mb", 0.0)),
            "used_ram_mb": float(raw_host.get("used_ram_mb", 0.0)),
            "ram_percent": float(raw_host.get("ram_percent", 0.0)),
            "running_vms": int(raw_host.get("running_vms", 0)),
            "total_vms": int(raw_host.get("total_vms", 0)),
            "status": "online"
        }

    def normalize_vm_metrics(
        self,
        raw_vm: Dict[str, Any],
        role_label: str = "vm",
        expected_ip: Optional[str] = None,
        timestamp: Optional[float] = None
    ) -> Dict[str, Any]:
        """Normalize guest virtual machine telemetry (Application VM or Database VM)."""
        now = timestamp or time.time()
        iso_time = datetime.fromtimestamp(now, tz=timezone.utc).isoformat()
        vm_id = raw_vm.get("uuid") or raw_vm.get("name") or "unknown"

        rx_bytes = int(raw_vm.get("network_rx_bytes", 0))
        tx_bytes = int(raw_vm.get("network_tx_bytes", 0))

        # Compute dynamic network throughput
        net_stats = self.network_monitor.compute_network_rates(vm_id, rx_bytes, tx_bytes, now)

        allocated_ram = float(raw_vm.get("allocated_ram_mb", 0.0))
        used_ram = float(raw_vm.get("used_ram_mb", 0.0))
        ram_pct = float(raw_vm.get("ram_percent", 0.0))
        
        if ram_pct == 0.0 and allocated_ram > 0 and used_ram > 0:
            ram_pct = round((used_ram / allocated_ram * 100), 1)

        return {
            "entity_type": role_label,
            "name": raw_vm.get("name", "Unknown VM"),
            "uuid": raw_vm.get("uuid", "unknown-uuid"),
            "ip": expected_ip,
            "power_state": raw_vm.get("power_state", "Unknown"),
            "timestamp": now,
            "timestamp_iso": iso_time,
            "vcpu_count": int(raw_vm.get("vcpu_count", 1)),
            "cpu_percent": round(float(raw_vm.get("cpu_percent", 0.0)), 1),
            "allocated_ram_mb": allocated_ram,
            "used_ram_mb": used_ram,
            "ram_percent": round(ram_pct, 1),
            "network_rx_bytes": rx_bytes,
            "network_tx_bytes": tx_bytes,
            "network_rx_kbs": net_stats["network_rx_kbs"],
            "network_tx_kbs": net_stats["network_tx_kbs"],
            "network_rate_human": net_stats["network_rate_human"],
            "status": "online" if raw_vm.get("power_state") == "Running" else "offline"
        }
