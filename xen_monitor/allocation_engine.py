"""
Dynamic Allocation Engine (Phase 3 Intelligent Resource Controller)
Evaluates real-time VM telemetry against elasticity thresholds and generates
actionable scaling decisions with independent cooldown tracking, consecutive breach
confirmation (hysteresis), host capacity safety checks, and emergency stop controls.
"""

import time
import logging
from typing import Dict, Any, List, Optional
from xen_monitor.monitor_config import MonitorConfig

logger = logging.getLogger("AllocationEngine")

class AllocationEngine:
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
        
        # In-memory history of recent recommendations
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

    def evaluate_vm(self, vm_metrics: Dict[str, Any], host_metrics: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Evaluate a single VM's CPU and RAM telemetry against configured thresholds.
        Enforces:
          - Minimum and maximum boundaries
          - Independent per-resource cooldown
          - Hysteresis via consecutive breach counts
          - Hypervisor physical memory headroom
          - Emergency stop override
        """
        vm_name = vm_metrics.get("name", "Unknown VM")
        clean_name = vm_name.lower().strip()
        current_vcpus = int(vm_metrics.get("vcpu_count", 1))
        allocated_ram = float(vm_metrics.get("allocated_ram_mb", 1024.0))
        cpu_pct = float(vm_metrics.get("cpu_percent", 0.0))
        ram_pct = float(vm_metrics.get("ram_percent", 0.0))

        now = time.time()

        # Cooldown check per resource
        cpu_cd = self.get_cooldown_status(clean_name, "cpu")
        ram_cd = self.get_cooldown_status(clean_name, "ram")

        cpu_action = "HOLD"
        ram_action = "HOLD"
        recommended_vcpus = current_vcpus
        recommended_ram_mb = allocated_ram
        reasons = []

        # Emergency stop check
        if self.emergency_stop:
            reasons.append("EMERGENCY STOP ENGAGED: Automated scaling suspended by administrator.")
            cpu_action = "BLOCKED"
            ram_action = "BLOCKED"
            decision = self._format_decision(
                now, vm_name, vm_metrics.get("uuid"),
                cpu_action, ram_action,
                current_vcpus, recommended_vcpus,
                allocated_ram, recommended_ram_mb,
                reasons, cpu_cd, ram_cd
            )
            self._save_decision(decision)
            return decision

        # -------------------------------------------------------------
        # 1. CPU ELASTICITY EVALUATION
        # -------------------------------------------------------------
        cpu_up_key = f"{clean_name}:cpu:scale_up"
        cpu_down_key = f"{clean_name}:cpu:scale_down"

        if cpu_pct > self.config.cpu_scale_up_threshold:
            self._consecutive_breaches[cpu_up_key] = self._consecutive_breaches.get(cpu_up_key, 0) + 1
            self._consecutive_breaches[cpu_down_key] = 0
            breach_count = self._consecutive_breaches[cpu_up_key]

            if current_vcpus >= self.config.max_vcpus:
                cpu_action = "HOLD"
                reasons.append(
                    f"High CPU workload ({cpu_pct}% > {self.config.cpu_scale_up_threshold}%), "
                    f"but VM is already at maximum boundary ({self.config.max_vcpus} vCPUs)."
                )
            elif cpu_cd["cooldown_active"]:
                cpu_action = "HOLD"
                reasons.append(
                    f"High CPU workload ({cpu_pct}% > {self.config.cpu_scale_up_threshold}%), "
                    f"but CPU cooldown is active ({cpu_cd['remaining_sec']}s remaining)."
                )
            elif breach_count < self.config.consecutive_breach_threshold:
                cpu_action = "HOLD"
                reasons.append(
                    f"High CPU workload ({cpu_pct}%). Breaches: {breach_count}/{self.config.consecutive_breach_threshold} "
                    f"(awaiting consecutive confirmation to prevent flapping)."
                )
            else:
                cpu_action = "SCALE_UP"
                recommended_vcpus = min(self.config.max_vcpus, current_vcpus + 1)
                reasons.append(
                    f"Sustained high CPU workload ({cpu_pct}% > {self.config.cpu_scale_up_threshold}% over {breach_count} intervals). "
                    f"Scale vCPUs from {current_vcpus} to {recommended_vcpus}."
                )

        elif cpu_pct < self.config.cpu_scale_down_threshold:
            self._consecutive_breaches[cpu_down_key] = self._consecutive_breaches.get(cpu_down_key, 0) + 1
            self._consecutive_breaches[cpu_up_key] = 0
            breach_count = self._consecutive_breaches[cpu_down_key]

            if current_vcpus <= self.config.min_vcpus:
                cpu_action = "HOLD"
                reasons.append(
                    f"Low CPU workload ({cpu_pct}% < {self.config.cpu_scale_down_threshold}%), "
                    f"but VM is already at minimum boundary ({self.config.min_vcpus} vCPU)."
                )
            elif cpu_cd["cooldown_active"]:
                cpu_action = "HOLD"
                reasons.append(
                    f"Low CPU workload ({cpu_pct}% < {self.config.cpu_scale_down_threshold}%), "
                    f"but CPU cooldown is active ({cpu_cd['remaining_sec']}s remaining)."
                )
            elif breach_count < self.config.consecutive_breach_threshold:
                cpu_action = "HOLD"
                reasons.append(
                    f"Low CPU workload ({cpu_pct}%). Breaches: {breach_count}/{self.config.consecutive_breach_threshold} "
                    f"(awaiting consecutive confirmation to prevent flapping)."
                )
            else:
                cpu_action = "SCALE_DOWN"
                recommended_vcpus = max(self.config.min_vcpus, current_vcpus - 1)
                reasons.append(
                    f"Sustained low CPU workload ({cpu_pct}% < {self.config.cpu_scale_down_threshold}% over {breach_count} intervals). "
                    f"Scale down vCPUs from {current_vcpus} to {recommended_vcpus} to optimize hypervisor cores."
                )
        else:
            # Nominal CPU utilization
            self._consecutive_breaches[cpu_up_key] = 0
            self._consecutive_breaches[cpu_down_key] = 0

        # -------------------------------------------------------------
        # 2. RAM ELASTICITY EVALUATION
        # -------------------------------------------------------------
        ram_up_key = f"{clean_name}:ram:scale_up"
        ram_down_key = f"{clean_name}:ram:scale_down"

        if ram_pct > self.config.ram_scale_up_threshold:
            self._consecutive_breaches[ram_up_key] = self._consecutive_breaches.get(ram_up_key, 0) + 1
            self._consecutive_breaches[ram_down_key] = 0
            breach_count = self._consecutive_breaches[ram_up_key]

            if allocated_ram >= self.config.max_ram_mb:
                ram_action = "HOLD"
                reasons.append(
                    f"High RAM pressure ({ram_pct}% > {self.config.ram_scale_up_threshold}%), "
                    f"but VM is already at maximum boundary ({self.config.max_ram_mb} MB)."
                )
            elif ram_cd["cooldown_active"]:
                ram_action = "HOLD"
                reasons.append(
                    f"High RAM pressure ({ram_pct}% > {self.config.ram_scale_up_threshold}%), "
                    f"but RAM cooldown is active ({ram_cd['remaining_sec']}s remaining)."
                )
            elif breach_count < self.config.consecutive_breach_threshold:
                ram_action = "HOLD"
                reasons.append(
                    f"High RAM pressure ({ram_pct}%). Breaches: {breach_count}/{self.config.consecutive_breach_threshold} "
                    f"(awaiting consecutive confirmation to prevent flapping)."
                )
            else:
                # Check hypervisor physical RAM capacity
                target_ram = min(self.config.max_ram_mb, allocated_ram + self.config.ram_increment_mb)
                needed_mb = (target_ram - allocated_ram) + 256.0  # 256MB safety cushion
                host_avail = host_metrics.get("available_ram_mb") if host_metrics else None

                if host_avail is not None and host_avail < needed_mb:
                    ram_action = "BLOCKED"
                    reasons.append(
                        f"RAM scale-up blocked by hypervisor host capacity: available {host_avail} MB < required {needed_mb} MB (with cushion)."
                    )
                else:
                    ram_action = "SCALE_UP"
                    recommended_ram_mb = target_ram
                    reasons.append(
                        f"Sustained elevated memory pressure ({ram_pct}% > {self.config.ram_scale_up_threshold}% over {breach_count} intervals). "
                        f"Expand dynamic memory ceiling from {allocated_ram} MB to {recommended_ram_mb} MB."
                    )

        elif ram_pct < self.config.ram_scale_down_threshold:
            self._consecutive_breaches[ram_down_key] = self._consecutive_breaches.get(ram_down_key, 0) + 1
            self._consecutive_breaches[ram_up_key] = 0
            breach_count = self._consecutive_breaches[ram_down_key]

            if allocated_ram <= self.config.min_ram_mb:
                ram_action = "HOLD"
                reasons.append(
                    f"Low RAM workload ({ram_pct}% < {self.config.ram_scale_down_threshold}%), "
                    f"but VM is already at minimum boundary ({self.config.min_ram_mb} MB)."
                )
            elif ram_cd["cooldown_active"]:
                ram_action = "HOLD"
                reasons.append(
                    f"Low RAM workload ({ram_pct}% < {self.config.ram_scale_down_threshold}%), "
                    f"but RAM cooldown is active ({ram_cd['remaining_sec']}s remaining)."
                )
            elif breach_count < self.config.consecutive_breach_threshold:
                ram_action = "HOLD"
                reasons.append(
                    f"Low RAM workload ({ram_pct}%). Breaches: {breach_count}/{self.config.consecutive_breach_threshold} "
                    f"(awaiting consecutive confirmation to prevent flapping)."
                )
            else:
                ram_action = "SCALE_DOWN"
                recommended_ram_mb = max(self.config.min_ram_mb, allocated_ram - self.config.ram_increment_mb)
                reasons.append(
                    f"Sustained low memory workload ({ram_pct}% < {self.config.ram_scale_down_threshold}% over {breach_count} intervals). "
                    f"Reclaim hypervisor dynamic memory from {allocated_ram} MB to {recommended_ram_mb} MB."
                )
        else:
            # Nominal RAM utilization
            self._consecutive_breaches[ram_up_key] = 0
            self._consecutive_breaches[ram_down_key] = 0

        if not reasons:
            reasons.append("Resource utilization within nominal operational boundaries. No scaling action required.")

        decision = self._format_decision(
            now, vm_name, vm_metrics.get("uuid"),
            cpu_action, ram_action,
            current_vcpus, recommended_vcpus,
            allocated_ram, recommended_ram_mb,
            reasons, cpu_cd, ram_cd
        )
        self._save_decision(decision)
        return decision

    def _format_decision(
        self, now: float, vm_name: str, vm_uuid: Optional[str],
        cpu_action: str, ram_action: str,
        current_vcpus: int, recommended_vcpus: int,
        current_ram_mb: float, recommended_ram_mb: float,
        reasons: List[str],
        cpu_cd: Dict[str, Any], ram_cd: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Construct structured decision record."""
        rationale = " | ".join(reasons)
        is_cooldown_active = cpu_cd.get("cooldown_active", False) or ram_cd.get("cooldown_active", False)
        max_cd_remaining = max(cpu_cd.get("remaining_sec", 0), ram_cd.get("remaining_sec", 0))

        return {
            "timestamp": now,
            "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            "vm_name": vm_name,
            "vm_uuid": vm_uuid,
            "cpu_action": cpu_action,
            "ram_action": ram_action,
            "current_vcpus": current_vcpus,
            "recommended_vcpus": recommended_vcpus,
            "current_ram_mb": current_ram_mb,
            "recommended_ram_mb": recommended_ram_mb,
            "rationale": rationale,
            "cooldown_active": is_cooldown_active,
            "cooldown_remaining_sec": max_cd_remaining,
            "cpu_cooldown": cpu_cd,
            "ram_cooldown": ram_cd,
            "emergency_stop": self.emergency_stop,
            "boundaries": {
                "min_vcpus": self.config.min_vcpus,
                "max_vcpus": self.config.max_vcpus,
                "min_ram_mb": self.config.min_ram_mb,
                "max_ram_mb": self.config.max_ram_mb
            }
        }

    def _save_decision(self, decision: Dict[str, Any]):
        """Maintain latest 50 decisions in memory."""
        self.decision_history.append(decision)
        if len(self.decision_history) > 50:
            self.decision_history.pop(0)
