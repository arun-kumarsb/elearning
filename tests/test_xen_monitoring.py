"""
Unit & Integration Tests for Phase 2 Xen/XCP-ng Resource Monitoring
Tests the 14 required capabilities:
1. XenAPI connection
2. VM discovery for Alpine-Linux
3. VM discovery for Alpine-DB
4. VM name matching
5. VM UUID lookup
6. CPU metrics
7. RAM metrics
8. Network metrics
9. Monitoring history endpoint
10. Empty history response
11. Database migration idempotency
12. Missing VM handling
13. Missing XCP-ng credentials
14. Frontend display of actual VM names
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
from backend.database import ensure_schema, get_sqlite_connection, init_sqlite_schema, query_db
from backend.app import create_app

class TestXenMonitoring(unittest.TestCase):

    def setUp(self):
        self.config = MonitorConfig()
        self.config.xcp_host = "10.189.191.175"
        self.config.app_vm_name = "Alpine-Linux"
        self.config.db_vm_name = "Alpine-DB"
        self.client = XenAPIClient(self.config)
        self.net_monitor = NetworkMonitor()
        self.normalizer = MetricsNormalizer(self.net_monitor)
        self.allocation_engine = AllocationEngine(self.config)

    # 1. XenAPI connection
    @patch("xen_monitor.xen_api_client.xmlrpc.client.ServerProxy")
    @patch("xen_monitor.xen_api_client.socket.socket")
    def test_01_xenapi_connection(self, mock_socket, mock_proxy_cls):
        """Test XenAPI authenticated connection and session management."""
        mock_sock_instance = MagicMock()
        mock_sock_instance.connect_ex.return_value = 0
        mock_socket.return_value = mock_sock_instance

        mock_proxy = MagicMock()
        mock_proxy.session.login_with_password.return_value = {
            "Status": "Success",
            "Value": "OpaqueRef:session-token-xyz-12345"
        }
        mock_proxy_cls.return_value = mock_proxy

        client = XenAPIClient(self.config)
        connected = client.connect()
        self.assertTrue(connected)
        self.assertTrue(client.is_connected)
        self.assertEqual(client.session_id, "OpaqueRef:session-token-xyz-12345")
        
        # Test clean close
        client.close()
        self.assertFalse(client.is_connected)
        self.assertIsNone(client.session_id)

    # Helper: mock standard XCP-ng VM inventory
    def _create_mock_client_with_vms(self):
        client = XenAPIClient(self.config)
        client.is_connected = True
        client.session_id = "test-session"
        client.proxy = MagicMock()
        client.proxy.VM.get_all_records.return_value = {
            "Status": "Success",
            "Value": {
                "ref_dom0": {
                    "uuid": "dom0-uuid-000",
                    "name_label": "Control domain on host",
                    "is_control_domain": True,
                    "is_a_template": False,
                    "is_a_snapshot": False,
                    "power_state": "Running"
                },
                "ref_tpl": {
                    "uuid": "template-uuid-111",
                    "name_label": "Alpine Linux 3.24 Template",
                    "is_control_domain": False,
                    "is_a_template": True,
                    "is_a_snapshot": False,
                    "power_state": "Halted"
                },
                "ref_app": {
                    "uuid": "alpine-linux-uuid-101",
                    "name_label": "Alpine-Linux",
                    "is_control_domain": False,
                    "is_a_template": False,
                    "is_a_snapshot": False,
                    "power_state": "Running",
                    "VCPUs_max": 2,
                    "VCPUs_at_startup": 2,
                    "memory_static_max": 2147483648,
                    "memory_dynamic_max": 2147483648,
                    "memory_dynamic_min": 1073741824,
                    "memory_target": 1073741824,
                    "metrics": "ref_metrics_app",
                    "guest_metrics": "ref_guest_app",
                    "VIFs": ["ref_vif_app"]
                },
                "ref_db": {
                    "uuid": "alpine-db-uuid-202",
                    "name_label": "Alpine-DB",
                    "is_control_domain": False,
                    "is_a_template": False,
                    "is_a_snapshot": False,
                    "power_state": "Running",
                    "VCPUs_max": 2,
                    "VCPUs_at_startup": 2,
                    "memory_static_max": 2147483648,
                    "memory_dynamic_max": 2147483648,
                    "memory_dynamic_min": 1073741824,
                    "memory_target": 1073741824,
                    "metrics": "ref_metrics_db",
                    "guest_metrics": "ref_guest_db",
                    "VIFs": ["ref_vif_db"]
                }
            }
        }
        return client

    # 2. VM discovery for Alpine-Linux
    def test_02_vm_discovery_alpine_linux(self):
        """Test dynamic discovery of actual VM Alpine-Linux from XCP-ng host."""
        client = self._create_mock_client_with_vms()
        vms = client.get_all_vms()
        discovered_names = [v["name"] for v in vms]
        self.assertIn("Alpine-Linux", discovered_names)
        self.assertNotIn("Control domain on host", discovered_names)
        self.assertNotIn("Alpine Linux 3.24 Template", discovered_names)

        app_vm = client.get_vm_by_name("Alpine-Linux")
        self.assertIsNotNone(app_vm)
        self.assertEqual(app_vm["name"], "Alpine-Linux")
        self.assertEqual(app_vm["power_state"], "Running")

    # 3. VM discovery for Alpine-DB
    def test_03_vm_discovery_alpine_db(self):
        """Test dynamic discovery of actual VM Alpine-DB from XCP-ng host."""
        client = self._create_mock_client_with_vms()
        db_vm = client.get_vm_by_name("Alpine-DB")
        self.assertIsNotNone(db_vm)
        self.assertEqual(db_vm["name"], "Alpine-DB")
        self.assertEqual(db_vm["power_state"], "Running")
        self.assertEqual(db_vm["vcpus"], 2)

    # 4. VM name matching
    def test_04_vm_name_matching(self):
        """Test exact, case-insensitive, and legacy alias name matching."""
        client = self._create_mock_client_with_vms()
        
        # Exact match
        exact = client.get_vm_by_name("Alpine-Linux")
        self.assertIsNotNone(exact)
        self.assertEqual(exact["name"], "Alpine-Linux")

        # Case-insensitive
        lower = client.get_vm_by_name("alpine-linux")
        self.assertIsNotNone(lower)
        self.assertEqual(lower["name"], "Alpine-Linux")

        # Legacy alias fallback (Alpine-Linux-New matches Alpine-Linux)
        alias = client.get_vm_by_name("Alpine-Linux-New")
        self.assertIsNotNone(alias)
        self.assertEqual(alias["name"], "Alpine-Linux")

    # 5. VM UUID lookup
    def test_05_vm_uuid_lookup(self):
        """Test dynamic retrieval of genuine UUIDs without hardcoded values."""
        client = self._create_mock_client_with_vms()
        app_vm = client.get_vm_by_name("Alpine-Linux")
        db_vm = client.get_vm_by_name("Alpine-DB")
        
        self.assertEqual(app_vm["uuid"], "alpine-linux-uuid-101")
        self.assertEqual(db_vm["uuid"], "alpine-db-uuid-202")

    # 6. CPU metrics
    def test_06_cpu_metrics(self):
        """Test retrieval and parsing of vCPUs and CPU utilization percentage."""
        client = self._create_mock_client_with_vms()
        client.proxy.VM_metrics.get_record.return_value = {
            "Status": "Success",
            "Value": {
                "VCPUs_utilisation": {0: 0.45, 1: 0.55},
                "memory_actual": 2147483648
            }
        }
        client.proxy.VM_guest_metrics.get_record.return_value = {"Status": "Failure"}
        client.proxy.VIF.get_record.return_value = {"Status": "Failure"}

        app_info = client.get_vm_by_name("Alpine-Linux")
        metrics = client.get_vm_runtime_metrics(app_info)
        
        self.assertEqual(metrics["vcpu_count"], 2)
        # Average of 45% and 55% = 50.0%
        self.assertEqual(metrics["cpu_percent"], 50.0)

    # 7. RAM metrics
    def test_07_ram_metrics(self):
        """Test retrieval and parsing of allocated RAM, used RAM, and RAM utilization percentage."""
        client = self._create_mock_client_with_vms()
        client.proxy.VM_metrics.get_record.return_value = {
            "Status": "Success",
            "Value": {
                "VCPUs_utilisation": {},
                "memory_actual": 2147483648  # 2048 MB
            }
        }
        client.proxy.VM_guest_metrics.get_record.return_value = {
            "Status": "Success",
            "Value": {
                "memory": {
                    "total": 2147483648,  # 2048 MB
                    "free": 1073741824   # 1024 MB
                }
            }
        }
        client.proxy.VIF.get_record.return_value = {"Status": "Failure"}

        app_info = client.get_vm_by_name("Alpine-Linux")
        metrics = client.get_vm_runtime_metrics(app_info)
        
        self.assertEqual(metrics["allocated_ram_mb"], 2048.0)
        self.assertEqual(metrics["used_ram_mb"], 1024.0)
        self.assertEqual(metrics["ram_percent"], 50.0)

    # 8. Network metrics
    def test_08_network_metrics(self):
        """Test retrieval and throughput delta calculation of VIF network RX/TX."""
        client = self._create_mock_client_with_vms()
        client.proxy.VM_metrics.get_record.return_value = {"Status": "Failure"}
        client.proxy.VM_guest_metrics.get_record.return_value = {"Status": "Failure"}
        client.proxy.VIF.get_record.return_value = {
            "Status": "Success",
            "Value": {"metrics": "ref_vifm_1"}
        }
        client.proxy.VIF_metrics.get_record.return_value = {
            "Status": "Success",
            "Value": {
                "io_read_kbs": 500.0,
                "io_write_kbs": 250.0
            }
        }

        app_info = client.get_vm_by_name("Alpine-Linux")
        metrics = client.get_vm_runtime_metrics(app_info)
        
        self.assertGreater(metrics["network_rx_bytes"], 0)
        self.assertGreater(metrics["network_tx_bytes"], 0)

        # Compute throughput with network monitor
        rates = self.net_monitor.compute_network_rates("test-vm", 5000000, 2500000, timestamp=1005.0)
        self.assertIn("network_rx_kbs", rates)
        self.assertIn("network_tx_kbs", rates)

    # 9. Monitoring history endpoint
    def test_09_monitoring_history_endpoint(self):
        """Test GET /api/xen/history?limit=50 returns HTTP 200 with valid JSON schema."""
        app = create_app()
        app.config["TESTING"] = True
        client = app.test_client()

        res = client.get("/api/xen/history?limit=50")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIsInstance(data["data"], list)

    # 10. Empty history response
    def test_10_empty_history_response(self):
        """Test GET /api/xen/history for a nonexistent VM returns empty list without HTTP 500."""
        app = create_app()
        app.config["TESTING"] = True
        client = app.test_client()

        res = client.get("/api/xen/history?vm_name=nonexistent-vm-xyz-999&limit=10")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["data"], [])

    # 11. Database migration idempotency
    def test_11_database_migration_idempotency(self):
        """Test database migration runs repeatedly without syntax errors or data loss."""
        conn = get_sqlite_connection()
        # Run schema initialization twice to verify idempotency
        init_sqlite_schema(conn)
        init_sqlite_schema(conn)

        # Check required monitoring tables exist
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r["name"] for r in cur.fetchall()]
        self.assertIn("vm_metrics_history", tables)
        self.assertIn("allocation_decisions_history", tables)
        self.assertIn("students", tables)
        self.assertIn("courses", tables)
        conn.close()

    # 12. Missing VM handling
    def test_12_missing_vm_handling(self):
        """Test graceful handling when a VM is not found on the hypervisor."""
        client = self._create_mock_client_with_vms()
        missing = client.get_vm_by_name("Unknown-Nonexistent-VM")
        self.assertIsNone(missing)

        # Verify monitor handles missing VM gracefully
        monitor = XenResourceMonitor(self.config)
        monitor.client = client
        norm_metrics = monitor.normalizer.normalize_vm_metrics(
            {"name": "Missing-VM", "power_state": "Halted"},
            role_label="app_vm"
        )
        self.assertEqual(norm_metrics["status"], "offline")
        self.assertEqual(norm_metrics["power_state"], "Halted")

    # 13. Missing XCP-ng credentials
    def test_13_missing_xcp_credentials(self):
        """Test missing host IP or unconfigured credentials fails fast with clean message."""
        empty_cfg = MonitorConfig()
        empty_cfg.xcp_host = ""
        client = XenAPIClient(empty_cfg)
        connected = client.connect()
        self.assertFalse(connected)
        self.assertFalse(client.is_connected)
        self.assertIn("not configured", client.last_error)

    # 14. Frontend display of actual VM names
    def test_14_frontend_display_of_actual_vm_names(self):
        """Test that configured/discovered VM name Alpine-Linux is used and not Alpine-Linux-New."""
        cfg = MonitorConfig()
        self.assertEqual(cfg.app_vm_name, "Alpine-Linux")
        self.assertEqual(cfg.db_vm_name, "Alpine-DB")

        # Verify alias resolver finds Alpine-Linux
        client = self._create_mock_client_with_vms()
        discovered = client.get_vm_by_name(cfg.app_vm_name)
        self.assertIsNotNone(discovered)
        self.assertEqual(discovered["name"], "Alpine-Linux")


if __name__ == "__main__":
    unittest.main()
