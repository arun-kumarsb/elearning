"""
XCP-ng / XenAPI Client Module
Handles authenticated XML-RPC communication with XCP-ng hypervisor (XAPI).
Dynamically discovers VM UUIDs, retrieves host hardware statistics, VM allocations,
and guest telemetry without hardcoding or fabrications.
"""

import ssl
import socket
import logging
import xmlrpc.client
from typing import Dict, Any, List, Optional
from xen_monitor.monitor_config import MonitorConfig

logger = logging.getLogger("XenAPIClient")

class TimeoutTransport(xmlrpc.client.Transport):
    """XML-RPC transport with configurable socket timeout."""
    def __init__(self, timeout: float = 3.0, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timeout = timeout

    def make_connection(self, host):
        conn = super().make_connection(host)
        conn.timeout = self.timeout
        return conn

class TimeoutSafeTransport(xmlrpc.client.SafeTransport):
    """HTTPS XML-RPC transport with configurable socket timeout."""
    def __init__(self, timeout: float = 3.0, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timeout = timeout

    def make_connection(self, host):
        conn = super().make_connection(host)
        conn.timeout = self.timeout
        return conn

class XenAPIClient:
    def __init__(self, config: Optional[MonitorConfig] = None):
        self.config = config or MonitorConfig()
        self.session_id: Optional[str] = None
        self.proxy: Optional[xmlrpc.client.ServerProxy] = None
        self.is_connected: bool = False
        self.last_error: Optional[str] = None
        self.host_ref: Optional[str] = None

    def connect(self) -> bool:
        """
        Authenticate with XCP-ng XAPI over XML-RPC.
        Supports both HTTP and HTTPS with configurable SSL verification.
        """
        self.last_error = None
        host = self.config.xcp_host
        username = self.config.xcp_username
        password = self.config.xcp_password

        if not host:
            self.last_error = "XCP_NG_HOST is not configured in environment."
            self.is_connected = False
            return False

        # Build endpoints (try HTTPS first, fallback to HTTP if standard port)
        protocols = ["https", "http"] if not self.config.verify_ssl else ["https"]
        
        for proto in protocols:
            url = f"{proto}://{host}"
            try:
                # Test connectivity with short socket timeout before XML-RPC handshake
                port = 443 if proto == "https" else 80
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1.0)
                res = sock.connect_ex((host, port))
                sock.close()
                if res != 0:
                    continue

                ssl_ctx = ssl._create_unverified_context() if not self.config.verify_ssl else ssl.create_default_context()
                transport = TimeoutSafeTransport(timeout=3.0, context=ssl_ctx) if proto == "https" else TimeoutTransport(timeout=3.0)
                
                proxy = xmlrpc.client.ServerProxy(
                    url,
                    transport=transport,
                    allow_none=True,
                    use_datetime=True
                )

                login_res = proxy.session.login_with_password(username, password, "1.0", "XenLearnMonitoring")
                if isinstance(login_res, dict) and login_res.get("Status") == "Success":
                    self.session_id = login_res.get("Value")
                    self.proxy = proxy
                    self.is_connected = True
                    logger.info(f"Successfully authenticated with XCP-ng at {url} (Session: {self.session_id[:8]}...)")
                    return True
                elif isinstance(login_res, dict) and login_res.get("Status") == "Failure":
                    err_details = login_res.get("ErrorDescription", ["Authentication failed"])
                    self.last_error = f"XAPI Authentication Failed: {err_details}"
                    self.is_connected = False
                    return False
            except Exception as e:
                self.last_error = f"XAPI connection failed ({url}): {str(e)}"
                logger.debug(f"Connection attempt to {url} failed: {e}")

        self.is_connected = False
        if not self.last_error:
            self.last_error = f"Could not establish connection to XCP-ng host at {host}:80/443. Host unreachable."
        return False

    def close(self):
        """Cleanly logout and close session."""
        if self.proxy and self.session_id:
            try:
                self.proxy.session.logout(self.session_id)
            except Exception:
                pass
        self.session_id = None
        self.proxy = None
        self.is_connected = False

    def get_host_metrics(self) -> Dict[str, Any]:
        """
        Retrieve physical host hardware, CPU cores, RAM, and running VM count.
        """
        if not self.is_connected or not self.proxy or not self.session_id:
            raise ConnectionError(self.last_error or "XAPI client not connected")

        # Query all hosts in the pool
        hosts_res = self.proxy.host.get_all_records(self.session_id)
        if hosts_res.get("Status") != "Success":
            raise RuntimeError(f"host.get_all_records failed: {hosts_res.get('ErrorDescription')}")
        
        hosts = hosts_res.get("Value", {})
        if not hosts:
            raise RuntimeError("No host records found on XCP-ng server")

        # Pick primary host
        host_ref, host_rec = next(iter(hosts.items()))
        self.host_ref = host_ref
        host_uuid = host_rec.get("uuid")
        host_name = host_rec.get("name_label", "XCP-ng Host")
        
        # Query host metrics
        metrics_ref = host_rec.get("metrics")
        host_metrics = {}
        if metrics_ref and metrics_ref != "OpaqueRef:NULL":
            hm_res = self.proxy.host_metrics.get_record(self.session_id, metrics_ref)
            if hm_res.get("Status") == "Success":
                host_metrics = hm_res.get("Value", {})

        total_memory_bytes = int(host_metrics.get("memory_total", 0))
        free_memory_bytes = int(host_metrics.get("memory_free", 0))
        used_memory_bytes = max(0, total_memory_bytes - free_memory_bytes)
        
        total_ram_mb = round(total_memory_bytes / (1024 * 1024), 1)
        free_ram_mb = round(free_memory_bytes / (1024 * 1024), 1)
        used_ram_mb = round(used_memory_bytes / (1024 * 1024), 1)
        ram_percent = round((used_memory_bytes / total_memory_bytes * 100), 1) if total_memory_bytes > 0 else 0.0

        # Query Host CPUs
        cpus_res = self.proxy.host_cpu.get_all_records(self.session_id)
        host_cpus = cpus_res.get("Value", {}) if cpus_res.get("Status") == "Success" else {}
        cpu_cores = len(host_cpus) or int(host_rec.get("cpu_info", {}).get("cpu_count", 0))

        # Calculate average host CPU utilization across cores
        cpu_utils = []
        for cpu in host_cpus.values():
            util = float(cpu.get("utilisation", 0.0))
            # Utilisation is typically 0.0 to 1.0 in XenAPI
            cpu_utils.append(util * 100.0 if util <= 1.0 else util)
        host_cpu_pct = round(sum(cpu_utils) / len(cpu_utils), 1) if cpu_utils else 0.0

        # Running VMs count
        vms_res = self.proxy.VM.get_all_records(self.session_id)
        vms = vms_res.get("Value", {}) if vms_res.get("Status") == "Success" else {}
        running_vms = sum(
            1 for v in vms.values() 
            if not v.get("is_a_template") and not v.get("is_control_domain") and v.get("power_state") == "Running"
        )

        return {
            "host_uuid": host_uuid,
            "host_name": host_name,
            "host_ip": self.config.xcp_host,
            "total_cpu_cores": cpu_cores,
            "host_cpu_percent": host_cpu_pct,
            "total_ram_mb": total_ram_mb,
            "available_ram_mb": free_ram_mb,
            "used_ram_mb": used_ram_mb,
            "ram_percent": ram_percent,
            "running_vms": running_vms,
            "total_vms": len(vms)
        }

    def get_all_vms(self) -> List[Dict[str, Any]]:
        """
        Discover and return all guest virtual machines with power states, vCPUs, and memory limits.
        """
        if not self.is_connected or not self.proxy or not self.session_id:
            raise ConnectionError(self.last_error or "XAPI client not connected")

        vms_res = self.proxy.VM.get_all_records(self.session_id)
        if vms_res.get("Status") != "Success":
            raise RuntimeError(f"VM.get_all_records failed: {vms_res.get('ErrorDescription')}")

        vms_raw = vms_res.get("Value", {})
        result = []

        for ref, rec in vms_raw.items():
            # Skip templates, snapshots, and Dom0
            if rec.get("is_a_template") or rec.get("is_control_domain") or rec.get("is_a_snapshot"):
                continue

            vcpus = int(rec.get("VCPUs_max") or rec.get("VCPUs_at_startup") or 1)
            static_max_mb = round(int(rec.get("memory_static_max", 0)) / (1024 * 1024), 1)
            dynamic_max_mb = round(int(rec.get("memory_dynamic_max", 0)) / (1024 * 1024), 1)
            dynamic_min_mb = round(int(rec.get("memory_dynamic_min", 0)) / (1024 * 1024), 1)
            target_mb = round(int(rec.get("memory_target", 0)) / (1024 * 1024), 1)

            result.append({
                "vm_ref": ref,
                "uuid": rec.get("uuid"),
                "name": rec.get("name_label"),
                "power_state": rec.get("power_state"),
                "vcpus": vcpus,
                "memory_static_max_mb": static_max_mb,
                "memory_dynamic_max_mb": dynamic_max_mb,
                "memory_dynamic_min_mb": dynamic_min_mb,
                "memory_target_mb": target_mb,
                "metrics_ref": rec.get("metrics"),
                "guest_metrics_ref": rec.get("guest_metrics"),
                "vifs": rec.get("VIFs", [])
            })

        return result

    def get_vm_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Find a VM dynamically by its exact or partial name_label."""
        vms = self.get_all_vms()
        for vm in vms:
            if vm["name"].lower() == name.lower():
                return vm
        # Try substring match
        for vm in vms:
            if name.lower() in vm["name"].lower():
                return vm
        return None

    def get_vm_runtime_metrics(self, vm_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Query runtime metrics (CPU utilization %, Memory utilization %, Network RX/TX)
        for a discovered VM using VM_metrics, VM_guest_metrics, and VIFs.
        """
        if not self.is_connected or not self.proxy or not self.session_id:
            raise ConnectionError(self.last_error or "XAPI client not connected")

        cpu_percent = 0.0
        used_ram_mb = 0.0
        ram_percent = 0.0
        net_rx_bytes = 0
        net_tx_bytes = 0

        allocated_ram_mb = vm_info.get("memory_dynamic_max_mb") or vm_info.get("memory_static_max_mb") or 0.0

        # 1. Read VM_metrics (Hypervisor level)
        metrics_ref = vm_info.get("metrics_ref")
        if metrics_ref and metrics_ref != "OpaqueRef:NULL":
            m_res = self.proxy.VM_metrics.get_record(self.session_id, metrics_ref)
            if m_res.get("Status") == "Success":
                m_data = m_res.get("Value", {})
                # CPU utilization map: {0: 0.15, 1: 0.25}
                vcpu_utils = m_data.get("VCPUs_utilisation", {})
                if vcpu_utils:
                    vals = [float(v) * 100.0 if float(v) <= 1.0 else float(v) for v in vcpu_utils.values()]
                    cpu_percent = round(sum(vals) / len(vals), 1)

                mem_actual = int(m_data.get("memory_actual", 0))
                if mem_actual > 0:
                    allocated_ram_mb = round(mem_actual / (1024 * 1024), 1)

        # 2. Read VM_guest_metrics (Guest OS level if xen-tools/balloon active)
        guest_ref = vm_info.get("guest_metrics_ref")
        if guest_ref and guest_ref != "OpaqueRef:NULL":
            gm_res = self.proxy.VM_guest_metrics.get_record(self.session_id, guest_ref)
            if gm_res.get("Status") == "Success":
                gm_data = gm_res.get("Value", {})
                mem_map = gm_data.get("memory", {})
                # memory map may have 'free' and 'total'
                if "free" in mem_map and "total" in mem_map:
                    g_total = float(mem_map["total"])
                    g_free = float(mem_map["free"])
                    g_used = max(0.0, g_total - g_free)
                    used_ram_mb = round(g_used / (1024 * 1024), 1)
                    ram_percent = round((g_used / g_total * 100), 1) if g_total > 0 else 0.0

        # If guest metrics are not reporting exact free RAM, estimate from dynamic target vs memory_actual
        if ram_percent == 0.0 and allocated_ram_mb > 0:
            target_mb = vm_info.get("memory_target_mb", 0)
            if target_mb > 0:
                used_ram_mb = target_mb
                ram_percent = round((used_ram_mb / allocated_ram_mb * 100), 1)

        # 3. Read Network Virtual Interfaces (VIF metrics)
        vif_refs = vm_info.get("vifs", [])
        for vif_ref in vif_refs:
            vif_res = self.proxy.VIF.get_record(self.session_id, vif_ref)
            if vif_res.get("Status") == "Success":
                vif_data = vif_res.get("Value", {})
                vm_m_ref = vif_data.get("metrics")
                if vm_m_ref and vm_m_ref != "OpaqueRef:NULL":
                    vifm_res = self.proxy.VIF_metrics.get_record(self.session_id, vm_m_ref)
                    if vifm_res.get("Status") == "Success":
                        vif_metrics = vifm_res.get("Value", {})
                        net_rx_bytes += int(float(vif_metrics.get("io_read_kbs", 0.0)) * 1024)
                        net_tx_bytes += int(float(vif_metrics.get("io_write_kbs", 0.0)) * 1024)

        return {
            "uuid": vm_info["uuid"],
            "name": vm_info["name"],
            "power_state": vm_info["power_state"],
            "vcpu_count": vm_info["vcpus"],
            "cpu_percent": cpu_percent,
            "ram_percent": ram_percent,
            "allocated_ram_mb": allocated_ram_mb,
            "used_ram_mb": used_ram_mb,
            "network_rx_bytes": net_rx_bytes,
            "network_tx_bytes": net_tx_bytes
        }
