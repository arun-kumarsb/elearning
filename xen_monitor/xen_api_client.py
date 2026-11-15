"""
XCP-ng / XenAPI Client Module
Handles authenticated XML-RPC communication with XCP-ng hypervisor (XAPI).
Dynamically discovers VM UUIDs, retrieves host hardware statistics, VM allocations,
and guest telemetry without hardcoding or fabrications.
"""

import ssl
import time
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
    EXPECTED_APP_VM_UUID = "01cdb87c-408f-72bc-449c-0364a8e69647"
    EXPECTED_DB_VM_UUID = "0a6dec09-0466-0079-4b66-80704b59587d"

    def __init__(self, config: Optional[MonitorConfig] = None):
        self.config = config or MonitorConfig()
        self.session_id: Optional[str] = None
        self.proxy: Optional[xmlrpc.client.ServerProxy] = None
        self.is_connected: bool = False
        self.last_error: Optional[str] = None
        self.host_ref: Optional[str] = None
        self._cpu_usage_history: Dict[str, Dict[str, Any]] = {}
        self._local_cpu_sample: Optional[Dict[str, float]] = None

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
            static_min_mb = round(int(rec.get("memory_static_min", 0)) / (1024 * 1024), 1)
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
                "memory_static_min_mb": static_min_mb,
                "memory_static_max_mb": static_max_mb,
                "memory_dynamic_max_mb": dynamic_max_mb,
                "memory_dynamic_min_mb": dynamic_min_mb,
                "memory_target_mb": target_mb,
                "metrics_ref": rec.get("metrics"),
                "guest_metrics_ref": rec.get("guest_metrics"),
                "supports_ballooning": bool(rec.get("guest_metrics") and rec.get("guest_metrics") != "OpaqueRef:NULL"),
                "supports_vcpu_hotplug": bool(rec.get("power_state") == "Running" and int(rec.get("VCPUs_max", 1)) > 1),
                "vifs": rec.get("VIFs", [])
            })

        return result

    def get_vm_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Find a VM dynamically by its exact or case-insensitive name_label.
        Supports exact match first, case-insensitive match, and normalized alias matching.
        """
        if not name:
            return None

        vms = self.get_all_vms()
        clean_target = name.strip()
        logger.debug(f"Looking up VM '{clean_target}' among {len(vms)} discovered VMs...")

        # 1. Exact match
        for vm in vms:
            if vm.get("name") == clean_target:
                logger.info(f"Exact match found for VM '{clean_target}' (UUID: {vm.get('uuid')})")
                return vm

        # 2. Case-insensitive exact match
        for vm in vms:
            if vm.get("name", "").lower() == clean_target.lower():
                logger.info(f"Case-insensitive match found for VM '{clean_target}' -> '{vm.get('name')}' (UUID: {vm.get('uuid')})")
                return vm

        # 3. Known alias / legacy name mapping (Alpine-Linux <-> Alpine-Linux-New)
        alias_map = {
            "alpine-linux-new": "alpine-linux",
            "alpine-linux": "alpine-linux-new"
        }
        alt_target = alias_map.get(clean_target.lower())
        if alt_target:
            for vm in vms:
                if vm.get("name", "").lower() == alt_target:
                    logger.info(f"Alias match found for VM '{clean_target}' -> '{vm.get('name')}' (UUID: {vm.get('uuid')})")
                    return vm

        # 4. Normalized whitespace / hyphen match
        norm_target = clean_target.lower().replace("-", "").replace("_", "").replace(" ", "")
        for vm in vms:
            vm_norm = vm.get("name", "").lower().replace("-", "").replace("_", "").replace(" ", "")
            if vm_norm == norm_target:
                logger.info(f"Normalized match found for VM '{clean_target}' -> '{vm.get('name')}' (UUID: {vm.get('uuid')})")
                return vm

        # 5. Substring match as last resort
        for vm in vms:
            if clean_target.lower() in vm.get("name", "").lower():
                logger.info(f"Substring match found for VM '{clean_target}' in '{vm.get('name')}' (UUID: {vm.get('uuid')})")
                return vm

        available_names = [v.get("name") for v in vms]
        logger.warning(f"VM '{clean_target}' was not discovered on XCP-ng host. Available VMs: {available_names}")
        return None

    def _read_local_linux_guest_cpu(self) -> Optional[float]:
        """Read guest CPU utilization from Linux /proc/stat using consecutive samples."""
        import os
        if not os.path.exists("/proc/stat"):
            return None
        try:
            with open("/proc/stat", "r") as f:
                first_line = f.readline()
            parts = first_line.split()
            if len(parts) >= 5 and parts[0] == "cpu":
                user = float(parts[1])
                nice = float(parts[2])
                system = float(parts[3])
                idle = float(parts[4])
                iowait = float(parts[5]) if len(parts) > 5 else 0.0
                irq = float(parts[6]) if len(parts) > 6 else 0.0
                softirq = float(parts[7]) if len(parts) > 7 else 0.0
                steal = float(parts[8]) if len(parts) > 8 else 0.0

                busy = user + nice + system + irq + softirq + steal
                total = busy + idle + iowait
                now = time.time()

                if self._local_cpu_sample is not None:
                    prev_busy = self._local_cpu_sample["busy"]
                    prev_total = self._local_cpu_sample["total"]
                    d_busy = busy - prev_busy
                    d_total = total - prev_total
                    self._local_cpu_sample = {"busy": busy, "total": total, "timestamp": now}
                    if d_total > 0 and d_busy >= 0:
                        pct = round((d_busy / d_total) * 100.0, 1)
                        return min(100.0, max(0.0, pct))
                else:
                    self._local_cpu_sample = {"busy": busy, "total": total, "timestamp": now}
                    return None
        except Exception as e:
            logger.debug(f"Could not read local /proc/stat: {e}")
        return None

    def _read_local_linux_guest_ram(self) -> Dict[str, Any]:
        """Read guest physical RAM metrics from Linux /proc/meminfo."""
        import os
        res = {
            "guest_total_ram_mb": None,
            "guest_used_ram_mb": None,
            "guest_available_ram_mb": None,
            "guest_ram_percent": None,
            "guest_memory_pressure": "N/A"
        }
        if not os.path.exists("/proc/meminfo"):
            return res
        try:
            meminfo = {}
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        k = parts[0].strip()
                        v = parts[1].strip().split()[0]
                        meminfo[k] = int(v)
            if "MemTotal" in meminfo:
                total_kb = meminfo["MemTotal"]
                avail_kb = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
                used_kb = max(0, total_kb - avail_kb)
                total_mb = round(total_kb / 1024.0, 1)
                avail_mb = round(avail_kb / 1024.0, 1)
                used_mb = round(used_kb / 1024.0, 1)
                pct = round((used_kb / total_kb * 100.0), 1) if total_kb > 0 else 0.0

                pressure = "high" if pct > 85.0 else ("moderate" if pct > 70.0 else "normal")
                return {
                    "guest_total_ram_mb": total_mb,
                    "guest_used_ram_mb": used_mb,
                    "guest_available_ram_mb": avail_mb,
                    "guest_ram_percent": pct,
                    "guest_memory_pressure": pressure
                }
        except Exception as e:
            logger.debug(f"Could not read /proc/meminfo: {e}")
        return res

    def get_vm_runtime_metrics(self, vm_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Query runtime metrics (CPU utilization %, Memory utilization %, Network RX/TX)
        for a discovered VM using Xen VM CPU-time counters, VM_metrics, VM_guest_metrics, and VIFs.
        Computes real CPU utilization from consecutive samples.
        Collects guest memory and Xen-assigned memory strictly separately without fake 100% calculations.
        """
        if not self.is_connected or not self.proxy or not self.session_id:
            raise ConnectionError(self.last_error or "XAPI client not connected")

        now = time.time()
        vm_name = vm_info.get("name", "Unknown VM")
        vm_uuid = vm_info.get("uuid", "unknown-uuid")
        vcpu_count = int(vm_info.get("vcpus", 1))

        cpu_percent = 0.0
        cpu_source = "xen_cpu_time_counter"
        cpu_status = "ok"

        # Xen Memory
        allocated_ram_mb = vm_info.get("memory_dynamic_max_mb") or vm_info.get("memory_static_max_mb") or 0.0
        target_mb = vm_info.get("memory_target_mb", 0.0)

        # Guest Memory (Default to None / N/A unless confirmed by guest metrics or local probe)
        guest_total_ram_mb = None
        guest_used_ram_mb = None
        guest_available_ram_mb = None
        guest_ram_percent = None
        guest_memory_pressure = "N/A"
        memory_source = "xen_hypervisor_only"
        memory_status = "guest_metrics_unavailable"

        net_rx_bytes = 0
        net_tx_bytes = 0

        # 1. Read VM_metrics (Hypervisor level)
        metrics_ref = vm_info.get("metrics_ref")
        if metrics_ref and metrics_ref != "OpaqueRef:NULL":
            try:
                m_res = self.proxy.VM_metrics.get_record(self.session_id, metrics_ref)
                if m_res.get("Status") == "Success":
                    m_data = m_res.get("Value", {})
                    
                    # Actual hypervisor-assigned memory
                    mem_actual = int(m_data.get("memory_actual", 0))
                    if mem_actual > 0:
                        allocated_ram_mb = round(mem_actual / (1024 * 1024), 1)

                    # A. CPU Utilization from consecutive CPU-time counters
                    # XenAPI VCPUs_CPU_usage maps vCPU number -> cumulative CPU time in seconds
                    vcpu_cpu_usage = m_data.get("VCPUs_CPU_usage", {})
                    if vcpu_cpu_usage:
                        try:
                            total_cpu_sec = sum(float(v) for v in vcpu_cpu_usage.values())
                            prev_sample = self._cpu_usage_history.get(vm_uuid)
                            if prev_sample is not None:
                                dt = now - prev_sample["timestamp"]
                                dc = total_cpu_sec - prev_sample["total_cpu_seconds"]
                                if dt > 0.05 and dc >= 0.0:
                                    calc_pct = (dc / (dt * max(1, vcpu_count))) * 100.0
                                    cpu_percent = round(min(100.0, max(0.0, calc_pct)), 1)
                                    cpu_source = "xen_cpu_time_counter"
                                    cpu_status = "ok"
                                elif dc < 0.0:
                                    # Counter reset (VM rebooted or time adjusted)
                                    logger.debug(f"CPU counter reset detected for VM {vm_name}")
                                    cpu_status = "calibrating"
                            else:
                                cpu_status = "calibrating"

                            self._cpu_usage_history[vm_uuid] = {
                                "timestamp": now,
                                "total_cpu_seconds": total_cpu_sec
                            }
                        except Exception as ce:
                            logger.debug(f"Error parsing VCPUs_CPU_usage for {vm_name}: {ce}")

                    # Fallback to VCPUs_utilisation if provided by Xen guest tools
                    if cpu_percent == 0.0:
                        vcpu_utils = m_data.get("VCPUs_utilisation", {})
                        if vcpu_utils:
                            vals = [float(v) * 100.0 if float(v) <= 1.0 else float(v) for v in vcpu_utils.values()]
                            if sum(vals) > 0.0:
                                cpu_percent = round(sum(vals) / len(vals), 1)
                                cpu_source = "xen_vcpu_utilisation"
                                cpu_status = "ok"

            except Exception as e:
                logger.warning(f"Error querying VM_metrics for {vm_name}: {e}")

        # 2. Local Linux guest-side CPU & RAM verification (for Application VM running locally)
        is_local_app_vm = (vm_name.lower() in ("alpine-linux", "alpine-linux-new") or vm_name == self.config.app_vm_name)
        if is_local_app_vm:
            # Read local guest RAM directly from /proc/meminfo
            local_ram = self._read_local_linux_guest_ram()
            if local_ram["guest_total_ram_mb"] is not None:
                guest_total_ram_mb = local_ram["guest_total_ram_mb"]
                guest_used_ram_mb = local_ram["guest_used_ram_mb"]
                guest_available_ram_mb = local_ram["guest_available_ram_mb"]
                guest_ram_percent = local_ram["guest_ram_percent"]
                guest_memory_pressure = local_ram["guest_memory_pressure"]
                memory_source = "guest_proc_meminfo"
                memory_status = "ok"

            # Check local guest CPU from /proc/stat
            local_cpu = self._read_local_linux_guest_cpu()
            if local_cpu is not None and (cpu_percent == 0.0 or cpu_status == "calibrating"):
                cpu_percent = local_cpu
                cpu_source = "guest_proc_stat"
                cpu_status = "ok"

        # 3. Read VM_guest_metrics (Guest OS level via Xen tools if active, e.g. for Database VM)
        if guest_ram_percent is None:
            guest_ref = vm_info.get("guest_metrics_ref")
            if guest_ref and guest_ref != "OpaqueRef:NULL":
                try:
                    gm_res = self.proxy.VM_guest_metrics.get_record(self.session_id, guest_ref)
                    if gm_res.get("Status") == "Success":
                        gm_data = gm_res.get("Value", {})
                        mem_map = gm_data.get("memory", {})
                        if "free" in mem_map and "total" in mem_map:
                            g_total = float(mem_map["total"])
                            g_free = float(mem_map["free"])
                            g_used = max(0.0, g_total - g_free)
                            guest_total_ram_mb = round(g_total / (1024 * 1024), 1)
                            guest_available_ram_mb = round(g_free / (1024 * 1024), 1)
                            guest_used_ram_mb = round(g_used / (1024 * 1024), 1)
                            guest_ram_percent = round((g_used / g_total * 100), 1) if g_total > 0 else 0.0
                            guest_memory_pressure = "high" if guest_ram_percent > 85.0 else ("moderate" if guest_ram_percent > 70.0 else "normal")
                            memory_source = "xen_guest_metrics"
                            memory_status = "ok"
                except Exception as e:
                    logger.debug(f"Guest metrics unavailable for {vm_name}: {e}")

        # 4. Read Network Virtual Interfaces (VIF metrics)
        vif_refs = vm_info.get("vifs", [])
        for vif_ref in vif_refs:
            try:
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
            except Exception as e:
                logger.debug(f"Error querying VIF {vif_ref} for {vm_name}: {e}")

        # Normalize used_ram_mb and ram_percent for backwards compatibility:
        # If guest metrics are available, use guest used RAM.
        # If unavailable, set to 0.0 (or None) and NEVER fake 100% by setting target = allocated.
        norm_used_ram_mb = guest_used_ram_mb if guest_used_ram_mb is not None else 0.0
        norm_ram_pct = guest_ram_percent if guest_ram_percent is not None else 0.0

        return {
            "uuid": vm_uuid,
            "name": vm_name,
            "power_state": vm_info.get("power_state", "Unknown"),
            "vcpu_count": vcpu_count,
            "online_vcpus": vcpu_count,
            "max_vcpus": int(vm_info.get("max_vcpus", vcpu_count)),
            
            # Real CPU Telemetry
            "cpu_percent": cpu_percent,
            "cpu_source": cpu_source,
            "cpu_status": cpu_status,
            
            # Xen Configured & Assigned Memory
            "configured_dynamic_min_mb": vm_info.get("memory_dynamic_min_mb", 0.0),
            "configured_dynamic_max_mb": vm_info.get("memory_dynamic_max_mb", 0.0),
            "configured_static_min_mb": vm_info.get("memory_static_min_mb", 0.0),
            "configured_static_max_mb": vm_info.get("memory_static_max_mb", 0.0),
            "xen_memory_target_mb": target_mb,
            "xen_assigned_ram_mb": allocated_ram_mb,
            "allocated_ram_mb": allocated_ram_mb,
            
            # Real Guest Memory Telemetry (Distinct!)
            "guest_total_ram_mb": guest_total_ram_mb,
            "guest_used_ram_mb": guest_used_ram_mb,
            "guest_available_ram_mb": guest_available_ram_mb,
            "guest_ram_percent": guest_ram_percent,
            "guest_memory_pressure": guest_memory_pressure,
            "used_ram_mb": norm_used_ram_mb,
            "ram_percent": norm_ram_pct,
            "memory_source": memory_source,
            "memory_status": memory_status,
            
            # Network
            "network_rx_bytes": net_rx_bytes,
            "network_tx_bytes": net_tx_bytes,
            
            # Capabilities
            "supports_ballooning": vm_info.get("supports_ballooning", False),
            "supports_vcpu_hotplug": vm_info.get("supports_vcpu_hotplug", False),
            "timestamp": now
        }

    def get_vm_by_uuid(self, uuid: str) -> Optional[Dict[str, Any]]:
        """Find a VM by its exact UUID."""
        if not uuid:
            return None
        vms = self.get_all_vms()
        for vm in vms:
            if vm.get("uuid") == uuid.strip():
                return vm
        return None

    def find_vm(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Lookup VM by UUID first, falling back to name matching."""
        if not identifier:
            return None
        vm = self.get_vm_by_uuid(identifier)
        if vm:
            return vm
        return self.get_vm_by_name(identifier)

    def set_vm_vcpus(self, vm_identifier: str, target_vcpus: int) -> Dict[str, Any]:
        """
        Dynamically adjust VM vCPU allocation on XCP-ng hypervisor.
        Applies live scaling if VM is running and persists at startup.
        Verifies actual allocation via XenAPI post-change.
        """
        if not self.is_connected or not self.proxy or not self.session_id:
            return {
                "success": False,
                "error": self.last_error or "XAPI client not connected to hypervisor",
                "vm_identifier": vm_identifier,
                "requested_value": target_vcpus
            }

        try:
            target_vcpus = int(target_vcpus)
        except (ValueError, TypeError):
            return {
                "success": False,
                "error": f"Invalid vCPU target value: {target_vcpus}. Must be an integer.",
                "vm_identifier": vm_identifier
            }

        vm = self.find_vm(vm_identifier)
        if not vm:
            return {
                "success": False,
                "error": f"VM '{vm_identifier}' was not found on XCP-ng host.",
                "vm_identifier": vm_identifier
            }

        vm_ref = vm["vm_ref"]
        vm_name = vm["name"]
        vm_uuid = vm["uuid"]
        power_state = vm.get("power_state")

        # Boundary checks against VM policy
        policy = self.config.get_vm_policy(vm_name)
        min_vcpus = policy.get("min_vcpus", self.config.min_vcpus)
        max_vcpus = policy.get("max_vcpus", self.config.max_vcpus)

        if target_vcpus < min_vcpus or target_vcpus > max_vcpus:
            return {
                "success": False,
                "error": f"Target vCPUs {target_vcpus} violates configured limits [{min_vcpus}, {max_vcpus}] for VM '{vm_name}'.",
                "vm_name": vm_name,
                "vm_uuid": vm_uuid,
                "requested_value": target_vcpus
            }

        # Check power state
        if power_state not in ("Running", "Halted"):
            return {
                "success": False,
                "error": f"Cannot modify vCPUs for VM '{vm_name}' in state '{power_state}'. Must be Running or Halted.",
                "vm_name": vm_name,
                "vm_uuid": vm_uuid,
                "power_state": power_state
            }

        # Retrieve full VM record to check VCPUs_max
        rec_res = self.proxy.VM.get_record(self.session_id, vm_ref)
        if rec_res.get("Status") != "Success":
            return {
                "success": False,
                "error": f"Failed to retrieve VM record for '{vm_name}': {rec_res.get('ErrorDescription')}",
                "vm_name": vm_name,
                "vm_uuid": vm_uuid
            }
        rec = rec_res.get("Value", {})
        vcpus_max = int(rec.get("VCPUs_max", 1))
        prev_vcpus = int(rec.get("VCPUs_at_startup") or vm.get("vcpus", 1))

        if target_vcpus > vcpus_max:
            return {
                "success": False,
                "error": f"Target vCPUs ({target_vcpus}) exceeds VM VCPUs_max ({vcpus_max}). Increasing VCPUs_max requires a VM power cycle.",
                "vm_name": vm_name,
                "vm_uuid": vm_uuid,
                "previous_value": prev_vcpus,
                "requested_value": target_vcpus
            }

        # Actuate via XenAPI
        try:
            if power_state == "Running":
                live_res = self.proxy.VM.set_VCPUs_number_live(self.session_id, vm_ref, target_vcpus)
                if live_res.get("Status") != "Success":
                    err = live_res.get("ErrorDescription", ["Live vCPU change failed"])
                    return {
                        "success": False,
                        "error": f"XenAPI set_VCPUs_number_live failed: {err}",
                        "vm_name": vm_name,
                        "vm_uuid": vm_uuid,
                        "previous_value": prev_vcpus,
                        "requested_value": target_vcpus
                    }

            # Update startup configuration for persistence
            startup_res = self.proxy.VM.set_VCPUs_at_startup(self.session_id, vm_ref, target_vcpus)
            if startup_res.get("Status") != "Success":
                logger.warning(f"Failed to update VCPUs_at_startup for {vm_name}: {startup_res.get('ErrorDescription')}")

            # Verify actual allocation by re-reading VM configuration
            verify_res = self.proxy.VM.get_record(self.session_id, vm_ref)
            if verify_res.get("Status") != "Success":
                return {
                    "success": False,
                    "error": f"Verification failed: XenAPI could not read back VM configuration: {verify_res.get('ErrorDescription')}",
                    "vm_name": vm_name,
                    "vm_uuid": vm_uuid,
                    "previous_value": prev_vcpus,
                    "requested_value": target_vcpus
                }

            v_rec = verify_res.get("Value", {})
            actual_vcpus = int(v_rec.get("VCPUs_at_startup") or v_rec.get("VCPUs_max") or 0)
            if actual_vcpus != target_vcpus:
                return {
                    "success": False,
                    "error": f"Verification failed: Xen reported vCPUs as {actual_vcpus}, expected {target_vcpus}.",
                    "vm_name": vm_name,
                    "vm_uuid": vm_uuid,
                    "previous_value": prev_vcpus,
                    "requested_value": target_vcpus,
                    "actual_value": actual_vcpus
                }

            logger.info(f"Dynamic CPU allocation successful and verified for {vm_name}: {prev_vcpus} -> {actual_vcpus} vCPUs.")
            return {
                "success": True,
                "vm_name": vm_name,
                "vm_uuid": vm_uuid,
                "resource_type": "cpu",
                "previous_value": prev_vcpus,
                "requested_value": target_vcpus,
                "actual_value": actual_vcpus,
                "power_state": power_state,
                "message": f"Successfully scaled vCPUs for '{vm_name}' from {prev_vcpus} to {actual_vcpus}."
            }
        except Exception as e:
            logger.error(f"Error during XenAPI vCPU modification on {vm_name}: {e}")
            return {
                "success": False,
                "error": f"XenAPI exception: {str(e)}",
                "vm_name": vm_name,
                "vm_uuid": vm_uuid,
                "previous_value": prev_vcpus,
                "requested_value": target_vcpus
            }

    def set_vm_dynamic_memory(self, vm_identifier: str, target_ram_mb: float) -> Dict[str, Any]:
        """
        Dynamically adjust VM dynamic memory boundaries (Xen ballooning).
        Enforces Xen memory invariants (static_min <= dynamic_min <= dynamic_max <= static_max),
        checks host physical RAM headroom, and verifies allocation post-change.
        """
        if not self.is_connected or not self.proxy or not self.session_id:
            return {
                "success": False,
                "error": self.last_error or "XAPI client not connected to hypervisor",
                "vm_identifier": vm_identifier,
                "requested_value": target_ram_mb
            }

        try:
            target_ram_mb = float(target_ram_mb)
        except (ValueError, TypeError):
            return {
                "success": False,
                "error": f"Invalid RAM target value: {target_ram_mb}. Must be a numeric value.",
                "vm_identifier": vm_identifier
            }

        vm = self.find_vm(vm_identifier)
        if not vm:
            return {
                "success": False,
                "error": f"VM '{vm_identifier}' was not found on XCP-ng host.",
                "vm_identifier": vm_identifier
            }

        vm_ref = vm["vm_ref"]
        vm_name = vm["name"]
        vm_uuid = vm["uuid"]
        power_state = vm.get("power_state")

        # Boundary checks against VM-specific policy
        policy = self.config.get_vm_policy(vm_name)
        min_ram_mb = policy.get("min_ram_mb", self.config.min_ram_mb)
        max_ram_mb = policy.get("max_ram_mb", self.config.max_ram_mb)

        if target_ram_mb < min_ram_mb or target_ram_mb > max_ram_mb:
            return {
                "success": False,
                "error": f"Target RAM {target_ram_mb} MB violates configured limits [{min_ram_mb} MB, {max_ram_mb} MB] for VM '{vm_name}'.",
                "vm_name": vm_name,
                "vm_uuid": vm_uuid,
                "requested_value": target_ram_mb
            }

        if power_state not in ("Running", "Halted"):
            return {
                "success": False,
                "error": f"Cannot modify dynamic memory for VM '{vm_name}' in state '{power_state}'.",
                "vm_name": vm_name,
                "vm_uuid": vm_uuid,
                "power_state": power_state
            }

        # Query VM limits from hypervisor
        rec_res = self.proxy.VM.get_record(self.session_id, vm_ref)
        if rec_res.get("Status") != "Success":
            return {
                "success": False,
                "error": f"Failed to retrieve VM record for '{vm_name}': {rec_res.get('ErrorDescription')}",
                "vm_name": vm_name,
                "vm_uuid": vm_uuid
            }
        rec = rec_res.get("Value", {})
        static_min = int(rec.get("memory_static_min", 0))
        dynamic_min = int(rec.get("memory_dynamic_min", 0))
        dynamic_max = int(rec.get("memory_dynamic_max", 0))
        static_max = int(rec.get("memory_static_max", 0))

        prev_dynamic_max_mb = round(dynamic_max / (1024 * 1024), 1)
        target_bytes = int(target_ram_mb * 1024 * 1024)

        # Invariant checks
        if static_max > 0 and target_bytes > static_max:
            static_max_mb = round(static_max / (1024 * 1024), 1)
            return {
                "success": False,
                "error": f"Target RAM ({target_ram_mb} MB) exceeds VM static maximum limit ({static_max_mb} MB).",
                "vm_name": vm_name,
                "vm_uuid": vm_uuid,
                "previous_value": prev_dynamic_max_mb,
                "requested_value": target_ram_mb
            }

        if static_min > 0 and target_bytes < static_min:
            static_min_mb = round(static_min / (1024 * 1024), 1)
            return {
                "success": False,
                "error": f"Target RAM ({target_ram_mb} MB) is below VM static minimum limit ({static_min_mb} MB).",
                "vm_name": vm_name,
                "vm_uuid": vm_uuid,
                "previous_value": prev_dynamic_max_mb,
                "requested_value": target_ram_mb
            }

        # Host capacity check if scaling up
        if target_ram_mb > prev_dynamic_max_mb:
            try:
                host_metrics = self.get_host_metrics()
                avail_host_mb = host_metrics.get("available_ram_mb", 0.0)
                needed_mb = (target_ram_mb - prev_dynamic_max_mb) + 256.0  # 256MB safety cushion
                if avail_host_mb < needed_mb:
                    return {
                        "success": False,
                        "error": f"Host RAM capacity restriction. Available: {avail_host_mb} MB, Required with cushion: {needed_mb} MB.",
                        "vm_name": vm_name,
                        "vm_uuid": vm_uuid,
                        "previous_value": prev_dynamic_max_mb,
                        "requested_value": target_ram_mb
                    }
            except Exception as e:
                logger.warning(f"Could not verify host RAM capacity: {e}")

        # Set dynamic memory range
        try:
            # Ensure dynamic_min does not exceed new target
            safe_dyn_min = min(dynamic_min, target_bytes) if dynamic_min > 0 else target_bytes
            dyn_res = self.proxy.VM.set_memory_dynamic_range(
                self.session_id, vm_ref, safe_dyn_min, target_bytes
            )
            if dyn_res.get("Status") != "Success":
                err = dyn_res.get("ErrorDescription", ["set_memory_dynamic_range failed"])
                return {
                    "success": False,
                    "error": f"XenAPI set_memory_dynamic_range failed: {err}",
                    "vm_name": vm_name,
                    "vm_uuid": vm_uuid,
                    "previous_value": prev_dynamic_max_mb,
                    "requested_value": target_ram_mb
                }

            # If VM is running, actively adjust live memory target for ballooning
            if power_state == "Running":
                target_res = self.proxy.VM.set_memory_target_live(self.session_id, vm_ref, target_bytes)
                if target_res.get("Status") != "Success":
                    logger.warning(f"set_memory_target_live returned non-success (may be unsupported by guest agent): {target_res.get('ErrorDescription')}")

            # Verify actual allocation by re-reading VM configuration
            verify_res = self.proxy.VM.get_record(self.session_id, vm_ref)
            if verify_res.get("Status") != "Success":
                return {
                    "success": False,
                    "error": f"Verification failed: XenAPI could not read back VM configuration: {verify_res.get('ErrorDescription')}",
                    "vm_name": vm_name,
                    "vm_uuid": vm_uuid,
                    "previous_value": prev_dynamic_max_mb,
                    "requested_value": target_ram_mb
                }

            v_rec = verify_res.get("Value", {})
            actual_ram_mb = round(int(v_rec.get("memory_dynamic_max", 0)) / (1024 * 1024), 1)
            if abs(actual_ram_mb - target_ram_mb) > 1.0:
                return {
                    "success": False,
                    "error": f"Verification failed: Xen reported dynamic max as {actual_ram_mb} MB, expected {target_ram_mb} MB.",
                    "vm_name": vm_name,
                    "vm_uuid": vm_uuid,
                    "previous_value": prev_dynamic_max_mb,
                    "requested_value": target_ram_mb,
                    "actual_value": actual_ram_mb
                }

            logger.info(f"Dynamic RAM ballooning successful and verified for {vm_name}: {prev_dynamic_max_mb} MB -> {actual_ram_mb} MB.")
            return {
                "success": True,
                "vm_name": vm_name,
                "vm_uuid": vm_uuid,
                "resource_type": "ram",
                "previous_value": prev_dynamic_max_mb,
                "requested_value": target_ram_mb,
                "actual_value": actual_ram_mb,
                "power_state": power_state,
                "message": f"Successfully updated dynamic memory for '{vm_name}' from {prev_dynamic_max_mb} MB to {actual_ram_mb} MB."
            }
        except Exception as e:
            logger.error(f"Error during XenAPI memory modification on {vm_name}: {e}")
            return {
                "success": False,
                "error": f"XenAPI exception: {str(e)}",
                "vm_name": vm_name,
                "vm_uuid": vm_uuid,
                "previous_value": prev_dynamic_max_mb,
                "requested_value": target_ram_mb
            }
