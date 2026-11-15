"""
Dynamic Allocation Engine (Phase 3 Intelligent Resource Controller)
Evaluates real-time VM telemetry against elasticity thresholds and generates
actionable scaling decisions with independent per-VM resource policies,
per-resource cooldown tracking, consecutive breach confirmation (hysteresis),
host capacity safety checks, and emergency stop controls.

Architecture:
- Exactly one active CPU controller (evaluate_cpu) using CPU telemetry only.
- Exactly one active RAM controller (evaluate_ram) using guest memory telemetry only.
- Separate cooldowns, thresholds, breach counters, and decision histories.
- Controller Version: v2.0
"""

import time
import logging
from typing import Dict, Any, List, Optional
from xen_monitor.monitor_config import MonitorConfig

logger = logging.getLogger("AllocationEngine")

class AllocationEngine:
    CONTROLLER_VERSION = "v2.0"

    def __init__(self, config: Optional[MonitorConfig] = None):
        self.config = config or MonitorConfig()
        
        # Independent cooldown tracking per (vm_name, resource_type):
        # Key: "vm_name:cpu" or "vm_name:ram" -> timestamp of last action
        self._last_action_time: Dict[str, float] = {}
        
        # Consecutive breach tracking for hysteresis:
        # Key: "vm_name:cpu:scale_up", "vm_name:ram:scale_down", etc. -> int count
        self._consecutive_breaches: Dict[str, int] = {}
        
        # Emergency stop flag
        self.emergency_stop: bool = False
        
        # Separate in-memory histories for CPU and RAM decisions
        self.cpu_decision_history: List[Dict[str, Any]] = []
        self.ram_decision_history: List[Dict[str, Any]] = []
        self.decision_history: List[Dict[str, Any]] = []

    def set_emergency_stop(self, enabled: bool):
        """Toggle emergency stop status."""
        self.emergency_stop = bool(enabled)
        logger.warning(f"AllocationEngine emergency stop set to: {self.emergency_stop}")

    def record_action_applied(self, vm_name: str, resource_type: str, timestamp: Optional[float] = None):
        """Record timestamp of executed scaling action to engage cooldown for (vm, resource)."""
        ts = timestamp or time.time()
        key = f"{vm_name.lower().strip()}:{resource_type.lower().strip()}"
        self._last_action_time[key] = ts
        logger.info(f"Cooldown engaged for {key} until {ts + self.config.cooldown_period_sec}")

    def get_cooldown_status(self, vm_name: str, resource_type: str) -> Dict[str, Any]:
        """Check whether a specific VM and resource type is currently in cooldown."""
        now = time.time()
        key = f"{vm_name.lower().strip()}:{resource_type.lower().strip()}"
        last_action = self._last_action_time.get(key, 0.0)
        remaining = max(0, int(self.config.cooldown_period_sec - (now - last_action)))
        return {
            "cooldown_active": remaining > 0,
            "remaining_sec": remaining,
            "last_action_timestamp": last_action
        }

    # -------------------------------------------------------------------------
    # 1. INDEPENDENT CPU ELASTICITY CONTROLLER (Uses CPU telemetry only)
    # -------------------------------------------------------------------------
    def evaluate_cpu(self, vm_metrics: Dict[str, Any], host_metrics: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Independent CPU Elasticity Controller (v2.0).
        Evaluates CPU telemetry against configured CPU thresholds,
        enforces CPU-specific cooldowns, consecutive breaches, and boundaries.
        Uses ONLY CPU metrics.
        """
        now = time.time()
        vm_name = vm_metrics.get("name", "Unknown VM")
        clean_name = vm_name.lower().strip()
        current_vcpus = int(vm_metrics.get("vcpu_count", 1))
        cpu_pct = float(vm_metrics.get("cpu_percent", 0.0))

        policy = self.config.get_vm_policy(vm_name)
        min_vcpus = policy.get("min_vcpus", self.config.min_vcpus)
        max_vcpus = policy.get("max_vcpus", self.config.max_vcpus)
        cpu_scale_up_thresh = policy.get("cpu_scale_up_threshold", self.config.cpu_scale_up_threshold)
        cpu_scale_down_thresh = policy.get("cpu_scale_down_threshold", self.config.cpu_scale_down_threshold)
        preserve_initial = policy.get("preserve_initial", False)

        cpu_cd = self.get_cooldown_status(clean_name, "cpu")
        scale_up_intervals = getattr(self.config, "scale_up_consecutive_threshold", getattr(self.config, "consecutive_breach_threshold", 3))
        scale_down_intervals = getattr(self.config, "scale_down_consecutive_threshold", 6)

        cpu_action = "HOLD"
        recommended_vcpus = current_vcpus
        reasons = []

        if self.emergency_stop:
            cpu_action = "BLOCKED"
            reasons.append("EMERGENCY STOP ENGAGED: Automated scaling suspended by administrator.")
        elif vm_metrics.get("is_stale", False):
            cpu_action = "HOLD"
            reasons.append("VM telemetry is stale or offline. Scaling withheld until fresh metrics arrive.")
        elif preserve_initial:
            cpu_action = "HOLD"
            reasons.append(f"Preserving initial {vm_name} resource baseline as configured by policy ({min_vcpus}-{max_vcpus} vCPUs).")
        else:
            cpu_up_key = f"{clean_name}:cpu:scale_up"
            cpu_down_key = f"{clean_name}:cpu:scale_down"

            if cpu_pct > cpu_scale_up_thresh:
                self._consecutive_breaches[cpu_up_key] = self._consecutive_breaches.get(cpu_up_key, 0) + 1
                self._consecutive_breaches[cpu_down_key] = 0
                breach_count = self._consecutive_breaches[cpu_up_key]

                if current_vcpus >= max_vcpus:
                    cpu_action = "HOLD"
                    reasons.append(f"High CPU workload ({cpu_pct}% > {cpu_scale_up_thresh}%), but VM is already at maximum boundary ({max_vcpus} vCPUs).")
                elif cpu_cd["cooldown_active"]:
                    cpu_action = "HOLD"
                    reasons.append(f"High CPU workload ({cpu_pct}% > {cpu_scale_up_thresh}%), but CPU cooldown is active ({cpu_cd['remaining_sec']}s remaining).")
                elif breach_count < scale_up_intervals:
                    cpu_action = "HOLD"
                    reasons.append(f"High CPU workload ({cpu_pct}%). Breaches: {breach_count}/{scale_up_intervals} (awaiting consecutive confirmation).")
                else:
                    cpu_action = "SCALE_UP"
                    recommended_vcpus = min(max_vcpus, current_vcpus + 1)
                    reasons.append(f"Sustained high CPU workload ({cpu_pct}% > {cpu_scale_up_thresh}% over {breach_count} intervals). Scale vCPUs from {current_vcpus} to {recommended_vcpus}.")

            elif cpu_pct < cpu_scale_down_thresh:
                self._consecutive_breaches[cpu_down_key] = self._consecutive_breaches.get(cpu_down_key, 0) + 1
                self._consecutive_breaches[cpu_up_key] = 0
                breach_count = self._consecutive_breaches[cpu_down_key]

                if current_vcpus <= min_vcpus:
                    cpu_action = "HOLD"
                    reasons.append(f"Low CPU workload ({cpu_pct}% < {cpu_scale_down_thresh}%), but VM is already at minimum boundary ({min_vcpus} vCPU).")
                elif cpu_cd["cooldown_active"]:
                    cpu_action = "HOLD"
                    reasons.append(f"Low CPU workload ({cpu_pct}% < {cpu_scale_down_thresh}%), but CPU cooldown is active ({cpu_cd['remaining_sec']}s remaining).")
                elif breach_count < scale_down_intervals:
                    cpu_action = "HOLD"
                    reasons.append(f"Low CPU workload ({cpu_pct}%). Breaches: {breach_count}/{scale_down_intervals} (awaiting consecutive confirmation).")
                else:
                    supports_hotplug = vm_metrics.get("supports_vcpu_hotplug", True)
                    if not supports_hotplug:
                        cpu_action = "MAINTENANCE_REQUIRED"
                        recommended_vcpus = max(min_vcpus, current_vcpus - 1)
                        reasons.append(f"Low CPU workload ({cpu_pct}% < {cpu_scale_down_thresh}% over {breach_count} intervals). Live vCPU hot-unplug unsupported by guest kernel; requires scheduled VM restart to apply {recommended_vcpus} vCPUs.")
                    else:
                        cpu_action = "SCALE_DOWN"
                        recommended_vcpus = max(min_vcpus, current_vcpus - 1)
                        reasons.append(f"Sustained low CPU workload ({cpu_pct}% < {cpu_scale_down_thresh}% over {breach_count} intervals). Scale down vCPUs from {current_vcpus} to {recommended_vcpus}.")
            else:
                self._consecutive_breaches[cpu_up_key] = 0
                self._consecutive_breaches[cpu_down_key] = 0
                reasons.append(f"CPU utilization nominal ({cpu_pct}%).")

        rationale = " | ".join(reasons)
        decision = {
            "controller_version": self.CONTROLLER_VERSION,
            "resource_type": "cpu",
            "timestamp": now,
            "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            "vm_name": vm_name,
            "vm_uuid": vm_metrics.get("uuid"),
            "action": cpu_action,
            "current_vcpus": current_vcpus,
            "recommended_vcpus": recommended_vcpus,
            "cpu_percent": cpu_pct,
            "rationale": rationale,
            "cooldown": cpu_cd,
            "emergency_stop": self.emergency_stop,
            "boundaries": {"min_vcpus": min_vcpus, "max_vcpus": max_vcpus}
        }
        self.cpu_decision_history.append(decision)
        if len(self.cpu_decision_history) > 50:
            self.cpu_decision_history.pop(0)
        return decision

    # -------------------------------------------------------------------------
    # 2. INDEPENDENT RAM ELASTICITY CONTROLLER (Uses Guest Memory telemetry only)
    # -------------------------------------------------------------------------
    def evaluate_ram(self, vm_metrics: Dict[str, Any], host_metrics: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Independent RAM Elasticity Controller (v2.0).
        Evaluates guest memory telemetry against configured RAM thresholds,
        enforces RAM-specific cooldowns, consecutive breaches, boundaries, and host physical memory headroom.
        Uses ONLY guest RAM and host memory metrics.
        """
        now = time.time()
        vm_name = vm_metrics.get("name", "Unknown VM")
        clean_name = vm_name.lower().strip()
        allocated_ram = float(vm_metrics.get("allocated_ram_mb", 1024.0))
        ram_pct = float(vm_metrics.get("ram_percent", 0.0))

        policy = self.config.get_vm_policy(vm_name)
        min_ram_mb = policy.get("min_ram_mb", self.config.min_ram_mb)
        max_ram_mb = policy.get("max_ram_mb", self.config.max_ram_mb)
        ram_scale_up_thresh = policy.get("ram_scale_up_threshold", self.config.ram_scale_up_threshold)
        ram_scale_down_thresh = policy.get("ram_scale_down_threshold", self.config.ram_scale_down_threshold)
        ram_inc = policy.get("ram_increment_mb", self.config.ram_increment_mb)
        preserve_initial = policy.get("preserve_initial", False)

        ram_cd = self.get_cooldown_status(clean_name, "ram")
        scale_up_intervals = getattr(self.config, "scale_up_consecutive_threshold", getattr(self.config, "consecutive_breach_threshold", 3))
        scale_down_intervals = getattr(self.config, "scale_down_consecutive_threshold", 6)

        ram_action = "HOLD"
        recommended_ram_mb = allocated_ram
        reasons = []

        guest_metrics_unavailable = (
            vm_metrics.get("guest_ram_percent") is None and 
            vm_metrics.get("memory_status") == "guest_metrics_unavailable"
        )

        if self.emergency_stop:
            ram_action = "BLOCKED"
            reasons.append("EMERGENCY STOP ENGAGED: Automated scaling suspended by administrator.")
        elif vm_metrics.get("is_stale", False):
            ram_action = "HOLD"
            reasons.append("VM telemetry is stale or offline. Scaling withheld until fresh metrics arrive.")
        elif preserve_initial:
            ram_action = "HOLD"
            reasons.append(f"Preserving initial {vm_name} resource baseline as configured by policy ({min_ram_mb}-{max_ram_mb} MB RAM).")
        elif guest_metrics_unavailable:
            ram_action = "HOLD"
            reasons.append(f"Guest memory telemetry unavailable for {vm_name}. Dynamic RAM scaling withheld to prevent unsafe guest kernel OOM.")
        else:
            ram_up_key = f"{clean_name}:ram:scale_up"
            ram_down_key = f"{clean_name}:ram:scale_down"

            if ram_pct > ram_scale_up_thresh:
                self._consecutive_breaches[ram_up_key] = self._consecutive_breaches.get(ram_up_key, 0) + 1
                self._consecutive_breaches[ram_down_key] = 0
                breach_count = self._consecutive_breaches[ram_up_key]

                if allocated_ram >= max_ram_mb:
                    ram_action = "HOLD"
                    reasons.append(f"High RAM pressure ({ram_pct}% > {ram_scale_up_thresh}%), but VM is already at maximum boundary ({max_ram_mb} MB).")
                elif ram_cd["cooldown_active"]:
                    ram_action = "HOLD"
                    reasons.append(f"High RAM pressure ({ram_pct}% > {ram_scale_up_thresh}%), but RAM cooldown is active ({ram_cd['remaining_sec']}s remaining).")
                elif breach_count < scale_up_intervals:
                    ram_action = "HOLD"
                    reasons.append(f"High RAM pressure ({ram_pct}%). Breaches: {breach_count}/{scale_up_intervals} (awaiting consecutive confirmation).")
                else:
                    target_ram = min(max_ram_mb, allocated_ram + ram_inc)
                    needed_mb = (target_ram - allocated_ram) + 256.0
                    host_avail = host_metrics.get("available_ram_mb") if host_metrics else None
                    if host_avail is not None and host_avail < needed_mb:
                        ram_action = "BLOCKED"
                        reasons.append(f"RAM scale-up blocked by hypervisor host capacity: available {host_avail} MB < required {needed_mb} MB (with cushion).")
                    else:
                        ram_action = "SCALE_UP"
                        recommended_ram_mb = target_ram
                        reasons.append(f"Sustained elevated memory pressure ({ram_pct}% > {ram_scale_up_thresh}% over {breach_count} intervals). Expand dynamic memory ceiling from {allocated_ram} MB to {recommended_ram_mb} MB.")

            elif ram_pct < ram_scale_down_thresh:
                self._consecutive_breaches[ram_down_key] = self._consecutive_breaches.get(ram_down_key, 0) + 1
                self._consecutive_breaches[ram_up_key] = 0
                breach_count = self._consecutive_breaches[ram_down_key]

                if allocated_ram <= min_ram_mb:
                    ram_action = "HOLD"
                    reasons.append(f"Low RAM workload ({ram_pct}% < {ram_scale_down_thresh}%), but VM is already at minimum boundary ({min_ram_mb} MB).")
                elif ram_cd["cooldown_active"]:
                    ram_action = "HOLD"
                    reasons.append(f"Low RAM workload ({ram_pct}% < {ram_scale_down_thresh}%), but RAM cooldown is active ({ram_cd['remaining_sec']}s remaining).")
                elif breach_count < scale_down_intervals:
                    ram_action = "HOLD"
                    reasons.append(f"Low RAM workload ({ram_pct}%). Breaches: {breach_count}/{scale_down_intervals} (awaiting consecutive confirmation).")
                else:
                    target_ram = max(min_ram_mb, allocated_ram - ram_inc)
                    used_ram = float(vm_metrics.get("used_ram_mb", 0.0))
                    min_safe_headroom = used_ram + 256.0
                    supports_ballooning = vm_metrics.get("supports_ballooning", True)
                    if not supports_ballooning:
                        ram_action = "MAINTENANCE_REQUIRED"
                        recommended_ram_mb = target_ram
                        reasons.append(f"Low RAM workload ({ram_pct}% < {ram_scale_down_thresh}% over {breach_count} intervals). Live memory ballooning unsupported; requires VM maintenance.")
                    elif used_ram > 0 and target_ram < min_safe_headroom:
                        ram_action = "HOLD"
                        reasons.append(f"RAM scale-down withheld: active guest consumption ({used_ram} MB) requires at least {min_safe_headroom} MB safe headroom (target {target_ram} MB risks guest OOM).")
                    else:
                        ram_action = "SCALE_DOWN"
                        recommended_ram_mb = target_ram
                        reasons.append(f"Sustained low memory workload ({ram_pct}% < {ram_scale_down_thresh}% over {breach_count} intervals). Reclaim hypervisor dynamic memory from {allocated_ram} MB to {recommended_ram_mb} MB.")
            else:
                self._consecutive_breaches[ram_up_key] = 0
                self._consecutive_breaches[ram_down_key] = 0
                reasons.append(f"Memory utilization nominal ({ram_pct}%).")

        rationale = " | ".join(reasons)
        decision = {
            "controller_version": self.CONTROLLER_VERSION,
            "resource_type": "ram",
            "timestamp": now,
            "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            "vm_name": vm_name,
            "vm_uuid": vm_metrics.get("uuid"),
            "action": ram_action,
            "current_ram_mb": allocated_ram,
            "recommended_ram_mb": recommended_ram_mb,
            "ram_percent": ram_pct,
            "rationale": rationale,
            "cooldown": ram_cd,
            "emergency_stop": self.emergency_stop,
            "boundaries": {"min_ram_mb": min_ram_mb, "max_ram_mb": max_ram_mb}
        }
        self.ram_decision_history.append(decision)
        if len(self.ram_decision_history) > 50:
            self.ram_decision_history.pop(0)
        return decision

    # -------------------------------------------------------------------------
    # 3. UNIFIED EVALUATION (Backward-Compatible Aggregate Decision)
    # -------------------------------------------------------------------------
    def evaluate_vm(self, vm_metrics: Dict[str, Any], host_metrics: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Evaluate VM telemetry by delegating to independent CPU and RAM controllers,
        aggregating their outputs for backwards compatibility with existing UI and API callers.
        """
        cpu_dec = self.evaluate_cpu(vm_metrics, host_metrics)
        ram_dec = self.evaluate_ram(vm_metrics, host_metrics)

        now = time.time()
        vm_name = vm_metrics.get("name", "Unknown VM")
        policy = self.config.get_vm_policy(vm_name)

        cpu_cd = cpu_dec.get("cooldown", {})
        ram_cd = ram_dec.get("cooldown", {})
        is_cooldown_active = cpu_cd.get("cooldown_active", False) or ram_cd.get("cooldown_active", False)
        max_cd_remaining = max(cpu_cd.get("remaining_sec", 0), ram_cd.get("remaining_sec", 0))

        reasons = [cpu_dec.get("rationale", ""), ram_dec.get("rationale", "")]
        rationale = " | ".join(r for r in reasons if r)

        min_v = policy.get("min_vcpus", self.config.min_vcpus) if policy else self.config.min_vcpus
        max_v = policy.get("max_vcpus", self.config.max_vcpus) if policy else self.config.max_vcpus
        min_r = policy.get("min_ram_mb", self.config.min_ram_mb) if policy else self.config.min_ram_mb
        max_r = policy.get("max_ram_mb", self.config.max_ram_mb) if policy else self.config.max_ram_mb

        decision = {
            "controller_version": self.CONTROLLER_VERSION,
            "timestamp": now,
            "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            "vm_name": vm_name,
            "vm_uuid": vm_metrics.get("uuid"),
            "cpu_action": cpu_dec["action"],
            "ram_action": ram_dec["action"],
            "current_vcpus": cpu_dec["current_vcpus"],
            "recommended_vcpus": cpu_dec["recommended_vcpus"],
            "current_ram_mb": ram_dec["current_ram_mb"],
            "recommended_ram_mb": ram_dec["recommended_ram_mb"],
            "rationale": rationale,
            "cpu_rationale": cpu_dec["rationale"],
            "ram_rationale": ram_dec["rationale"],
            "cpu_decision": cpu_dec,
            "ram_decision": ram_dec,
            "cooldown_active": is_cooldown_active,
            "cooldown_remaining_sec": max_cd_remaining,
            "cpu_cooldown": cpu_cd,
            "ram_cooldown": ram_cd,
            "emergency_stop": self.emergency_stop,
            "boundaries": {
                "min_vcpus": min_v,
                "max_vcpus": max_v,
                "min_ram_mb": min_r,
                "max_ram_mb": max_r
            }
        }
        self.decision_history.append(decision)
        if len(self.decision_history) > 50:
            self.decision_history.pop(0)
        return decision
