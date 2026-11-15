"""
Dynamic Allocation Recommendation Engine (Phase 3 Architecture Preparation)
Evaluates real-time VM telemetry against elasticity thresholds and generates
actionable scaling recommendations with cooldown dampening and boundary enforcement.

NOTE: This phase implements recommendations and analysis ONLY.
No hypervisor commands (reboot, resize, migration) are executed automatically.
"""

import time
from typing import Dict, Any, List, Optional
from xen_monitor.monitor_config import MonitorConfig

class AllocationEngine:
    def __init__(self, config: Optional[MonitorConfig] = None):
        self.config = config or MonitorConfig()
        # Track last recommendation timestamp per VM to enforce cooldown:
        # { vm_identifier: timestamp }
        self._last_action_time: Dict[str, float] = {}
        # In-memory history of recent recommendations
        self.decision_history: List[Dict[str, Any]] = []

    def evaluate_vm(self, vm_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate a single VM's CPU and RAM telemetry against configured thresholds.
        Returns a structured recommendation dictionary.
        """
        vm_name = vm_metrics.get("name", "Unknown VM")
        current_vcpus = int(vm_metrics.get("vcpu_count", 1))
        allocated_ram = float(vm_metrics.get("allocated_ram_mb", 1024.0))
        cpu_pct = float(vm_metrics.get("cpu_percent", 0.0))
        ram_pct = float(vm_metrics.get("ram_percent", 0.0))

        now = time.time()
        last_action = self._last_action_time.get(vm_name, 0.0)
        cooldown_remaining = max(0, int(self.config.cooldown_period_sec - (now - last_action)))
        is_in_cooldown = cooldown_remaining > 0

        cpu_action = "HOLD"
        ram_action = "HOLD"
        recommended_vcpus = current_vcpus
        recommended_ram_mb = allocated_ram
        reasons = []

        # 1. CPU Elasticity Evaluation
        if cpu_pct > self.config.cpu_scale_up_threshold:
            if current_vcpus < self.config.max_vcpus:
                cpu_action = "SCALE_UP_RECOMMENDED"
                recommended_vcpus = min(self.config.max_vcpus, current_vcpus + 1)
                reasons.append(
                    f"High CPU workload ({cpu_pct}% > threshold {self.config.cpu_scale_up_threshold}%). "
                    f"Recommend scaling vCPUs from {current_vcpus} to {recommended_vcpus}."
                )
            else:
                reasons.append(
                    f"High CPU workload ({cpu_pct}%), but VM already at maximum configured boundary ({self.config.max_vcpus} vCPUs)."
                )
        elif cpu_pct < self.config.cpu_scale_down_threshold and current_vcpus > self.config.min_vcpus:
            cpu_action = "SCALE_DOWN_RECOMMENDED"
            recommended_vcpus = max(self.config.min_vcpus, current_vcpus - 1)
            reasons.append(
                f"Low CPU workload ({cpu_pct}% < threshold {self.config.cpu_scale_down_threshold}%). "
                f"Recommend optimizing vCPUs from {current_vcpus} to {recommended_vcpus} to reclaim hypervisor capacity."
            )

        # 2. RAM Elasticity Evaluation (Xen Ballooning Preparation)
        if ram_pct > self.config.ram_scale_up_threshold:
            if allocated_ram < self.config.max_ram_mb:
                ram_action = "SCALE_UP_RECOMMENDED"
                recommended_ram_mb = min(self.config.max_ram_mb, allocated_ram + 512.0)
                reasons.append(
                    f"Elevated memory pressure ({ram_pct}% > threshold {self.config.ram_scale_up_threshold}%). "
                    f"Recommend expanding Xen dynamic memory ceiling from {allocated_ram}MB to {recommended_ram_mb}MB."
                )
            else:
                reasons.append(
                    f"Memory pressure elevated ({ram_pct}%), but VM already at maximum boundary ({self.config.max_ram_mb}MB)."
                )

        if not reasons:
            reasons.append("Resource utilization within nominal operational boundaries. No scaling action required.")

        rationale = " | ".join(reasons)

        # If a scaling change is proposed and not in cooldown, record timestamp
        has_recommendation = cpu_action != "HOLD" or ram_action != "HOLD"
        if has_recommendation and not is_in_cooldown:
            self._last_action_time[vm_name] = now

        decision = {
            "timestamp": now,
            "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            "vm_name": vm_name,
            "vm_uuid": vm_metrics.get("uuid"),
            "cpu_action": cpu_action,
            "ram_action": ram_action,
            "current_vcpus": current_vcpus,
            "recommended_vcpus": recommended_vcpus,
            "current_ram_mb": allocated_ram,
            "recommended_ram_mb": recommended_ram_mb,
            "rationale": rationale,
            "cooldown_active": is_in_cooldown,
            "cooldown_remaining_sec": cooldown_remaining if is_in_cooldown else 0,
            "boundaries": {
                "min_vcpus": self.config.min_vcpus,
                "max_vcpus": self.config.max_vcpus,
                "min_ram_mb": self.config.min_ram_mb,
                "max_ram_mb": self.config.max_ram_mb
            }
        }

        # Keep last 50 decisions in memory
        self.decision_history.append(decision)
        if len(self.decision_history) > 50:
            self.decision_history.pop(0)

        return decision
