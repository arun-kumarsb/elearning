"""
Network Monitor Component
Tracks cumulative network traffic (bytes received/transmitted) and calculates
real-time network transfer rates (KB/s, MB/s) per VM and host across polling intervals.
"""

import time
from typing import Dict, Any, Optional

class NetworkMonitor:
    def __init__(self):
        # Store previous state for calculating delta rates:
        # { entity_id: { "rx_bytes": int, "tx_bytes": int, "timestamp": float } }
        self._previous_states: Dict[str, Dict[str, Any]] = {}

    def compute_network_rates(
        self,
        entity_id: str,
        current_rx_bytes: int,
        current_tx_bytes: int,
        timestamp: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Compute network transfer throughput (bytes/sec, KB/sec) given new cumulative counters.
        """
        now = timestamp or time.time()
        prev = self._previous_states.get(entity_id)

        rx_rate_kbs = 0.0
        tx_rate_kbs = 0.0

        if prev:
            dt = max(0.001, now - prev["timestamp"])
            d_rx = max(0, current_rx_bytes - prev["rx_bytes"])
            d_tx = max(0, current_tx_bytes - prev["tx_bytes"])

            rx_rate_kbs = round((d_rx / dt) / 1024.0, 2)
            tx_rate_kbs = round((d_tx / dt) / 1024.0, 2)

        # Update cache
        self._previous_states[entity_id] = {
            "rx_bytes": current_rx_bytes,
            "tx_bytes": current_tx_bytes,
            "timestamp": now
        }

        return {
            "entity_id": entity_id,
            "network_rx_bytes": current_rx_bytes,
            "network_tx_bytes": current_tx_bytes,
            "network_rx_kbs": rx_rate_kbs,
            "network_tx_kbs": tx_rate_kbs,
            "network_rx_human": self.format_bytes(current_rx_bytes),
            "network_tx_human": self.format_bytes(current_tx_bytes),
            "network_rate_human": f"↓ {rx_rate_kbs} KB/s | ↑ {tx_rate_kbs} KB/s"
        }

    @staticmethod
    def format_bytes(num_bytes: int) -> str:
        """Format raw byte counts to human-readable strings (KB, MB, GB)."""
        if num_bytes < 1024:
            return f"{num_bytes} B"
        elif num_bytes < 1024 * 1024:
            return f"{round(num_bytes / 1024, 1)} KB"
        elif num_bytes < 1024 * 1024 * 1024:
            return f"{round(num_bytes / (1024 * 1024), 2)} MB"
        else:
            return f"{round(num_bytes / (1024 * 1024 * 1024), 2)} GB"
