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
        guest_used = raw_vm.get("guest_used_ram_mb")
        guest_avail = raw_vm.get("guest_available_ram_mb")
        guest_total = raw_vm.get("guest_total_ram_mb")
        guest_pct = raw_vm.get("guest_ram_percent")
        
        # Backward compatibility for legacy tests expecting used_ram_mb
        used_ram = float(raw_vm.get("used_ram_mb", 0.0))
        ram_pct = float(raw_vm.get("ram_percent", 0.0))

        return {
            "entity_type": role_label,
            "name": raw_vm.get("name", "Unknown VM"),
            "uuid": raw_vm.get("uuid", "unknown-uuid"),
            "ip": expected_ip,
            "power_state": raw_vm.get("power_state", "Unknown"),
            "timestamp": now,
            "timestamp_iso": iso_time,
            "freshness_seconds": round(time.time() - now, 2),
            "vcpu_count": int(raw_vm.get("vcpu_count", 1)),
            "cpu_percent": round(float(raw_vm.get("cpu_percent", 0.0)), 1),
            "cpu_source": raw_vm.get("cpu_source", "xen_cpu_time_counter"),
            "cpu_status": raw_vm.get("cpu_status", "ok"),
            
            # Xen Allocation
            "allocated_ram_mb": allocated_ram,
            "xen_assigned_ram_mb": float(raw_vm.get("xen_assigned_ram_mb", allocated_ram)),
            "xen_memory_target_mb": float(raw_vm.get("xen_memory_target_mb", 0.0)),
            "configured_dynamic_min_mb": raw_vm.get("configured_dynamic_min_mb", 0.0),
            "configured_dynamic_max_mb": raw_vm.get("configured_dynamic_max_mb", 0.0),
            "configured_static_min_mb": raw_vm.get("configured_static_min_mb", 0.0),
            "configured_static_max_mb": raw_vm.get("configured_static_max_mb", 0.0),
            
            # Guest Telemetry (Separated!)
            "guest_total_ram_mb": guest_total,
            "guest_used_ram_mb": guest_used,
            "guest_available_ram_mb": guest_avail,
            "guest_ram_percent": guest_pct,
            "guest_memory_pressure": raw_vm.get("guest_memory_pressure", "N/A"),
            "used_ram_mb": used_ram,
            "ram_percent": round(ram_pct, 1),
            "memory_source": raw_vm.get("memory_source", "xen_hypervisor_only"),
            "memory_status": raw_vm.get("memory_status", "ok"),
            
            # Network
            "network_rx_bytes": rx_bytes,
            "network_tx_bytes": tx_bytes,
            "network_rx_kbs": net_stats["network_rx_kbs"],
            "network_tx_kbs": net_stats["network_tx_kbs"],
            "network_rate_human": net_stats["network_rate_human"],
            "supports_ballooning": raw_vm.get("supports_ballooning", False),
            "supports_vcpu_hotplug": raw_vm.get("supports_vcpu_hotplug", False),
            "status": "online" if raw_vm.get("power_state") == "Running" else "offline"
        }
