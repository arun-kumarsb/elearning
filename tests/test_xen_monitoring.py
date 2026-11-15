"""
Unit & Integration Tests for Phase 2 Xen/XCP-ng Resource Monitoring
Tests XAPI connectivity, VM discovery, CPU/RAM/Network metric parsing,
elasticity recommendations, database persistence, and Flask REST API endpoints.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from xen_monitor.monitor_config import MonitorConfig
from xen_monitor.xen_api_client import XenAPIClient
from xen_monitor.network_monitor import NetworkMonitor
from xen_monitor.vm_metrics import MetricsNormalizer
from xen_monitor.allocation_engine import AllocationEngine
from xen_monitor.resource_monitor import XenResourceMonitor
from backend.app import create_app

class TestXenMonitoring(unittest.TestCase):

    def setUp(self):
        self.config = MonitorConfig()
        self.config.xcp_host = "10.240.109.196"
        self.config.app_vm_name = "Alpine-Linux-New"
        self.config.db_vm_name = "Alpine-DB"
        self.client = XenAPIClient(self.config)
        self.net_monitor = NetworkMonitor()
        self.normalizer = MetricsNormalizer(self.net_monitor)
        self.allocation_engine = AllocationEngine(self.config)

    def test_network_monitor_throughput_calculation(self):
        """Test delta rate computation and human formatting in NetworkMonitor."""
        net = NetworkMonitor()
        # Initial reading
        res1 = net.compute_network_rates("vm-1", 1000000, 500000, timestamp=1000.0)
        self.assertEqual(res1["network_rx_kbs"], 0.0)
        self.assertEqual(res1["network_tx_kbs"], 0.0)

        # 5 seconds later (+500,000 bytes RX, +250,000 bytes TX)
        res2 = net.compute_network_rates("vm-1", 1500000, 750000, timestamp=1005.0)
        # 500000 / 5 = 100000 bytes/s = ~97.66 KB/s
        self.assertGreater(res2["network_rx_kbs"], 90.0)
        self.assertGreater(res2["network_tx_kbs"], 45.0)
        self.assertIn("MB", res2["network_rx_human"])

    def test_allocation_engine_recommendations(self):
        """Test elasticity recommendations: scale-up on high load, scale-down on idle, cooldown dampening."""
        engine = AllocationEngine(self.config)

        # 1. High CPU Load -> Recommend scale-up
        high_cpu_vm = {
            "name": "Alpine-Linux-New",
            "uuid": "test-uuid-1",
            "vcpu_count": 2,
            "allocated_ram_mb": 2048.0,
            "cpu_percent": 88.5,
            "ram_percent": 65.0
        }
        dec1 = engine.evaluate_vm(high_cpu_vm)
        self.assertEqual(dec1["cpu_action"], "SCALE_UP_RECOMMENDED")
        self.assertEqual(dec1["recommended_vcpus"], 3)
        self.assertIn("High CPU workload", dec1["rationale"])

        # 2. Cooldown Active -> Subsequent check within cooldown window must flag cooldown_active
        dec2 = engine.evaluate_vm(high_cpu_vm)
        self.assertTrue(dec2["cooldown_active"])

        # 3. Low CPU Load on separate VM -> Recommend scale-down
        idle_vm = {
            "name": "Alpine-DB",
            "uuid": "test-uuid-2",
            "vcpu_count": 4,
            "allocated_ram_mb": 2048.0,
            "cpu_percent": 15.0,
            "ram_percent": 30.0
        }
        dec_idle = engine.evaluate_vm(idle_vm)
        self.assertEqual(dec_idle["cpu_action"], "SCALE_DOWN_RECOMMENDED")
        self.assertEqual(dec_idle["recommended_vcpus"], 3)

        # 4. High RAM Load -> Recommend memory evaluation
        high_ram_vm = {
            "name": "Alpine-DB-RAM",
            "uuid": "test-uuid-3",
            "vcpu_count": 2,
            "allocated_ram_mb": 2048.0,
            "cpu_percent": 40.0,
            "ram_percent": 92.0
        }
        dec_ram = engine.evaluate_vm(high_ram_vm)
        self.assertEqual(dec_ram["ram_action"], "SCALE_UP_RECOMMENDED")
        self.assertEqual(dec_ram["recommended_ram_mb"], 2560.0)

    @patch("xen_monitor.xen_api_client.xmlrpc.client.ServerProxy")
    @patch("xen_monitor.xen_api_client.socket.socket")
    def test_xapi_connection_success(self, mock_socket, mock_proxy_cls):
        """Test successful XAPI authentication and session acquisition."""
        mock_sock_instance = MagicMock()
        mock_sock_instance.connect_ex.return_value = 0
        mock_socket.return_value = mock_sock_instance

        mock_proxy = MagicMock()
        mock_proxy.session.login_with_password.return_value = {
            "Status": "Success",
            "Value": "OpaqueRef:session-test-token-12345"
        }
        mock_proxy_cls.return_value = mock_proxy

        client = XenAPIClient(self.config)
        connected = client.connect()
        self.assertTrue(connected)
        self.assertTrue(client.is_connected)
        self.assertEqual(client.session_id, "OpaqueRef:session-test-token-12345")

    def test_xapi_connection_failure_handling(self):
        """Test unreachable XCP-ng hypervisor handles error without crashing."""
        # Case 1: Empty host
        cfg_empty = MonitorConfig()
        cfg_empty.xcp_host = ""
        client_empty = XenAPIClient(cfg_empty)
        self.assertFalse(client_empty.connect())
        self.assertIn("not configured", client_empty.last_error)

        # Case 2: Unreachable / closed port (127.0.0.1 on closed port)
        cfg_offline = MonitorConfig()
        cfg_offline.xcp_host = "127.0.0.1"
        client_offline = XenAPIClient(cfg_offline)
        connected = client_offline.connect()
        self.assertFalse(connected)
        self.assertFalse(client_offline.is_connected)
        self.assertIsNotNone(client_offline.last_error)

    def test_vm_discovery_and_filtering(self):
        """Test discovering guest VMs while ignoring templates and Dom0."""
        client = XenAPIClient(self.config)
        client.is_connected = True
        client.session_id = "test-session"
        client.proxy = MagicMock()

        # Mock VM.get_all_records with a mix of template, Dom0, and actual VMs
        client.proxy.VM.get_all_records.return_value = {
            "Status": "Success",
            "Value": {
                "ref_dom0": {
                    "uuid": "dom0-uuid",
                    "name_label": "Control domain on host",
                    "is_control_domain": True,
                    "is_a_template": False,
                    "is_a_snapshot": False,
                    "power_state": "Running"
                },
                "ref_tpl": {
                    "uuid": "template-uuid",
                    "name_label": "Alpine Linux 3.24 Template",
                    "is_control_domain": False,
                    "is_a_template": True,
                    "is_a_snapshot": False,
                    "power_state": "Halted"
                },
                "ref_app": {
                    "uuid": "app-vm-uuid-9999",
                    "name_label": "Alpine-Linux-New",
                    "is_control_domain": False,
                    "is_a_template": False,
                    "is_a_snapshot": False,
                    "power_state": "Running",
                    "VCPUs_max": 2,
                    "memory_static_max": 2147483648,
                    "memory_dynamic_max": 2147483648,
                    "metrics": "ref_metrics_app",
                    "guest_metrics": "ref_guest_app",
                    "VIFs": []
                },
                "ref_db": {
                    "uuid": "db-vm-uuid-8888",
                    "name_label": "Alpine-DB",
                    "is_control_domain": False,
                    "is_a_template": False,
                    "is_a_snapshot": False,
                    "power_state": "Running",
                    "VCPUs_max": 2,
                    "memory_static_max": 2147483648,
                    "memory_dynamic_max": 2147483648,
                    "metrics": "ref_metrics_db",
                    "guest_metrics": "ref_guest_db",
                    "VIFs": []
                }
            }
        }

        vms = client.get_all_vms()
        self.assertEqual(len(vms), 2)
        names = [v["name"] for v in vms]
        self.assertIn("Alpine-Linux-New", names)
        self.assertIn("Alpine-DB", names)
        self.assertNotIn("Control domain on host", names)

        # Test finding by name
        app_found = client.get_vm_by_name("Alpine-Linux-New")
        self.assertIsNotNone(app_found)
        self.assertEqual(app_found["uuid"], "app-vm-uuid-9999")

        # Test missing VM handling
        missing = client.get_vm_by_name("Non-Existent-VM")
        self.assertIsNone(missing)

    def test_flask_xen_monitoring_endpoints(self):
        """Test Flask REST API routes for Xen monitoring."""
        app = create_app()
        app.config["TESTING"] = True
        client = app.test_client()

        # 1. GET /api/xen/status
        res_status = client.get("/api/xen/status")
        self.assertEqual(res_status.status_code, 200)
        self.assertTrue(res_status.get_json()["success"])

        # 2. GET /api/xen/monitor/status
        res_mon = client.get("/api/xen/monitor/status")
        self.assertEqual(res_mon.status_code, 200)
        mon_json = res_mon.get_json()
        self.assertTrue(mon_json["success"])
        self.assertEqual(mon_json["data"]["engine"], "XenResourceMonitor")

        # 3. GET /api/xen/metrics
        res_metrics = client.get("/api/xen/metrics")
        self.assertEqual(res_metrics.status_code, 200)
        self.assertTrue(res_metrics.get_json()["success"])

        # 4. GET /api/xen/host
        res_host = client.get("/api/xen/host")
        self.assertEqual(res_host.status_code, 200)

        # 5. GET /api/xen/vms
        res_vms = client.get("/api/xen/vms")
        self.assertEqual(res_vms.status_code, 200)

        # 6. GET /api/xen/vms/<vm_id>/metrics - 404 for unknown VM
        res_unknown = client.get("/api/xen/vms/unknown-id-xyz/metrics")
        self.assertEqual(res_unknown.status_code, 404)

        # 7. GET /api/xen/history
        res_hist = client.get("/api/xen/history?limit=10")
        self.assertEqual(res_hist.status_code, 200)
        self.assertTrue(res_hist.get_json()["success"])


if __name__ == "__main__":
    unittest.main()
