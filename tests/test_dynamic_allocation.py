"""
Automated Unit & Integration Test Suite for Phase 3: Dynamic Resource Allocation
Project: Xen-Based Dynamic Resource Allocation for Scalable E-Learning Services

Covers all 18+ required verification scenarios from Section 13:
1. XenAPI connection failure handling
2. Successful authentication using mocked XenAPI
3. VM discovery
4. VM UUID lookup
5. CPU scale-up decision (>80%)
6. CPU scale-down decision (<25%)
7. RAM scale-up decision (>85%)
8. RAM scale-down decision (<30%)
9. Cooldown dampening behavior
10. Independent cooldowns (CPU cooldown does not block RAM)
11. Hysteresis & consecutive threshold confirmation
12. Maximum CPU boundary enforcement (4 vCPUs)
13. Minimum CPU boundary enforcement (1 vCPU)
14. Maximum RAM boundary enforcement (4096 MB)
15. Minimum RAM boundary enforcement (1024 MB)
16. Hypervisor host physical RAM capacity restrictions
17. Failed XenAPI allocation handling & error capture
18. Allocation history recording in database (resource_allocation_history)
19. Administrator authentication & authorization gating
20. Emergency stop safety interlock
21. Real XenAPI vCPU live actuation & post-change verification
22. Real XenAPI RAM dynamic ballooning actuation & invariant verification
"""

import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from xen_monitor.monitor_config import MonitorConfig
from xen_monitor.xen_api_client import XenAPIClient
from xen_monitor.allocation_engine import AllocationEngine
from xen_monitor.resource_monitor import XenResourceMonitor
from backend.services.auth_service import generate_session_token
from backend.database import ensure_schema, execute_db, query_db
from backend.app import create_app

class TestDynamicAllocation(unittest.TestCase):

    def setUp(self):
        """Set up test environment and mock client objects."""
        ensure_schema()
        self.config = MonitorConfig()
        self.config.xcp_host = "10.189.191.175"
        self.config.app_vm_name = "Alpine-Linux"
        self.config.db_vm_name = "Alpine-DB"
        self.config.cpu_scale_up_threshold = 80.0
        self.config.cpu_scale_down_threshold = 25.0
        self.config.min_vcpus = 1
        self.config.max_vcpus = 4
        self.config.ram_scale_up_threshold = 85.0
        self.config.ram_scale_down_threshold = 30.0
        self.config.ram_increment_mb = 512.0
        self.config.min_ram_mb = 1024.0
        self.config.max_ram_mb = 4096.0
        self.config.app_min_ram_mb = 1024.0
        self.config.app_max_ram_mb = 4096.0
        self.config.app_initial_ram_mb = 1024.0
        self.config.app_initial_vcpus = 1
        self.config.db_min_ram_mb = 1024.0
        self.config.db_max_ram_mb = 4096.0
        self.config.db_initial_ram_mb = 1024.0
        self.config.db_initial_vcpus = 1
        self.config.cooldown_period_sec = 60
        self.config.scale_up_consecutive_threshold = 3
        self.config.scale_down_consecutive_threshold = 6
        self.config.consecutive_breach_threshold = 3
        self.config.allocation_mode = "manual"

        self.engine = AllocationEngine(self.config)
        self.app = create_app()
        self.test_client = self.app.test_client()

        # Admin and Student auth tokens for endpoint testing
        self.admin_token = generate_session_token(1, "admin@elearning.local", "admin")
        self.student_token = generate_session_token(2, "student@example.com", "student")

    def _create_mock_client(self):
        """Helper to create a mocked XenAPIClient with standard test VMs."""
        client = XenAPIClient(self.config)
        client.is_connected = True
        client.session_id = "test-session-token-123"
        client.proxy = MagicMock()

        # Mock standard VM inventory
        client.proxy.VM.get_all_records.return_value = {
            "Status": "Success",
            "Value": {
                "ref_dom0": {
                    "uuid": "dom0-uuid",
                    "name_label": "Control domain",
                    "is_control_domain": True,
                    "is_a_template": False,
                    "is_a_snapshot": False,
                    "power_state": "Running"
                },
                "ref_app": {
                    "uuid": "app-vm-uuid-111",
                    "name_label": "Alpine-Linux",
                    "is_control_domain": False,
                    "is_a_template": False,
                    "is_a_snapshot": False,
                    "power_state": "Running",
                    "VCPUs_max": "4",
                    "VCPUs_at_startup": "2",
                    "memory_static_min": str(512 * 1024 * 1024),
                    "memory_dynamic_min": str(1024 * 1024 * 1024),
                    "memory_dynamic_max": str(2048 * 1024 * 1024),
                    "memory_static_max": str(4096 * 1024 * 1024),
                    "memory_target": str(2048 * 1024 * 1024),
                    "metrics": "OpaqueRef:app-metrics",
                    "guest_metrics": "OpaqueRef:app-guest-metrics",
                    "VIFs": []
                },
                "ref_db": {
                    "uuid": "db-vm-uuid-222",
                    "name_label": "Alpine-DB",
                    "is_control_domain": False,
                    "is_a_template": False,
                    "is_a_snapshot": False,
                    "power_state": "Running",
                    "VCPUs_max": "4",
                    "VCPUs_at_startup": "1",
                    "memory_static_min": str(512 * 1024 * 1024),
                    "memory_dynamic_min": str(1024 * 1024 * 1024),
                    "memory_dynamic_max": str(1536 * 1024 * 1024),
                    "memory_static_max": str(4096 * 1024 * 1024),
                    "memory_target": str(1536 * 1024 * 1024),
                    "metrics": "OpaqueRef:db-metrics",
                    "guest_metrics": "OpaqueRef:db-guest-metrics",
                    "VIFs": []
                }
            }
        }
        return client

    # 1. XenAPI Connection Failure Handling
    @patch("xen_monitor.xen_api_client.socket.socket")
    def test_01_xenapi_connection_failure(self, mock_socket):
        """Verify that hypervisor connection failures are handled gracefully without exceptions."""
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 111  # Connection refused
        mock_socket.return_value = mock_sock

        client = XenAPIClient(self.config)
        connected = client.connect()
        self.assertFalse(connected)
        self.assertFalse(client.is_connected)
        self.assertIsNotNone(client.last_error)

    # 2. Successful Authentication using Mocked XenAPI
    @patch("xen_monitor.xen_api_client.xmlrpc.client.ServerProxy")
    @patch("xen_monitor.xen_api_client.socket.socket")
    def test_02_xenapi_authentication_success(self, mock_socket, mock_proxy_cls):
        """Verify successful authenticated handshake with XCP-ng XAPI."""
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 0
        mock_socket.return_value = mock_sock

        mock_proxy = MagicMock()
        mock_proxy.session.login_with_password.return_value = {
            "Status": "Success",
            "Value": "OpaqueRef:valid-session-id"
        }
        mock_proxy_cls.return_value = mock_proxy

        client = XenAPIClient(self.config)
        connected = client.connect()
        self.assertTrue(connected)
        self.assertTrue(client.is_connected)
        self.assertEqual(client.session_id, "OpaqueRef:valid-session-id")

    # 3. VM Discovery
    def test_03_vm_discovery(self):
        """Verify VM discovery excludes Dom0 and templates, discovering Alpine-Linux and Alpine-DB."""
        client = self._create_mock_client()
        vms = client.get_all_vms()
        names = [v["name"] for v in vms]
        self.assertIn("Alpine-Linux", names)
        self.assertIn("Alpine-DB", names)
        self.assertNotIn("Control domain", names)

    # 4. VM UUID Lookup
    def test_04_vm_uuid_lookup(self):
        """Verify VM UUID lookup and dynamic resolution."""
        client = self._create_mock_client()
        vm = client.get_vm_by_uuid("app-vm-uuid-111")
        self.assertIsNotNone(vm)
        self.assertEqual(vm["name"], "Alpine-Linux")

        found = client.find_vm("Alpine-Linux")
        self.assertIsNotNone(found)
        self.assertEqual(found["uuid"], "app-vm-uuid-111")

    # 5. CPU Scale-Up Decision (>80% over 3 intervals)
    def test_05_cpu_scale_up_decision(self):
        """Verify CPU utilization >80% triggers SCALE_UP after 3 consecutive confirmations."""
        vm_metrics = {
            "name": "Alpine-Linux",
            "uuid": "app-vm-uuid-111",
            "vcpu_count": 2,
            "allocated_ram_mb": 2048.0,
            "cpu_percent": 90.0,
            "ram_percent": 50.0
        }
        # Intervals 1 and 2: Awaiting consecutive confirmations
        dec1 = self.engine.evaluate_vm(vm_metrics)
        self.assertEqual(dec1["cpu_action"], "HOLD")

        dec2 = self.engine.evaluate_vm(vm_metrics)
        self.assertEqual(dec2["cpu_action"], "HOLD")

        # Interval 3: 3rd consecutive breach triggers scale-up (+1 vCPU)
        dec3 = self.engine.evaluate_vm(vm_metrics)
        self.assertEqual(dec3["cpu_action"], "SCALE_UP")
        self.assertEqual(dec3["recommended_vcpus"], 3)

    # 6. CPU Scale-Down Decision (<25% over 6 intervals)
    def test_06_cpu_scale_down_decision(self):
        """Verify CPU utilization <25% triggers SCALE_DOWN after 6 consecutive confirmations."""
        vm_metrics = {
            "name": "Alpine-Linux",
            "uuid": "app-vm-uuid-111",
            "vcpu_count": 3,
            "allocated_ram_mb": 2048.0,
            "cpu_percent": 15.0,
            "ram_percent": 50.0
        }
        # Intervals 1-5: First breaches
        for _ in range(5):
            dec = self.engine.evaluate_vm(vm_metrics)
            self.assertEqual(dec["cpu_action"], "HOLD")

        # Interval 6: 6th consecutive breach triggers scale-down (-1 vCPU)
        dec6 = self.engine.evaluate_vm(vm_metrics)
        self.assertEqual(dec6["cpu_action"], "SCALE_DOWN")
        self.assertEqual(dec6["recommended_vcpus"], 2)

    # 7. RAM Scale-Up Decision (>85% over 3 intervals)
    def test_07_ram_scale_up_decision(self):
        """Verify RAM utilization >85% triggers SCALE_UP (+512 MB) after 3 intervals."""
        vm_metrics = {
            "name": "Alpine-Linux",
            "uuid": "app-vm-uuid-111",
            "vcpu_count": 2,
            "allocated_ram_mb": 2048.0,
            "cpu_percent": 50.0,
            "ram_percent": 92.0
        }
        host_metrics = {"available_ram_mb": 4096.0}

        dec1 = self.engine.evaluate_vm(vm_metrics, host_metrics=host_metrics)
        self.assertEqual(dec1["ram_action"], "HOLD")

        dec2 = self.engine.evaluate_vm(vm_metrics, host_metrics=host_metrics)
        self.assertEqual(dec2["ram_action"], "HOLD")

        dec3 = self.engine.evaluate_vm(vm_metrics, host_metrics=host_metrics)
        self.assertEqual(dec3["ram_action"], "SCALE_UP")
        self.assertEqual(dec3["recommended_ram_mb"], 2560.0)

    # 8. RAM Scale-Down Decision (<30% over 6 intervals)
    def test_08_ram_scale_down_decision(self):
        """Verify RAM utilization <30% triggers SCALE_DOWN (-512 MB) after 6 intervals."""
        vm_metrics = {
            "name": "Alpine-Linux",
            "uuid": "app-vm-uuid-111",
            "vcpu_count": 2,
            "allocated_ram_mb": 2560.0,
            "cpu_percent": 50.0,
            "ram_percent": 20.0
        }
        for _ in range(5):
            dec = self.engine.evaluate_vm(vm_metrics)
            self.assertEqual(dec["ram_action"], "HOLD")

        dec6 = self.engine.evaluate_vm(vm_metrics)
        self.assertEqual(dec6["ram_action"], "SCALE_DOWN")
        self.assertEqual(dec6["recommended_ram_mb"], 2048.0)

    # 9. Cooldown Dampening Behavior
    def test_09_cooldown_behavior(self):
        """Verify that executed action engages cooldown and suppresses subsequent scaling."""
        vm_name = "Alpine-Linux"
        self.engine.record_action_applied(vm_name, "cpu", timestamp=time.time())

        vm_metrics = {
            "name": vm_name,
            "uuid": "app-vm-uuid-111",
            "vcpu_count": 2,
            "allocated_ram_mb": 2048.0,
            "cpu_percent": 95.0,
            "ram_percent": 50.0
        }
        dec = self.engine.evaluate_vm(vm_metrics)
        self.assertEqual(dec["cpu_action"], "HOLD")
        self.assertTrue(dec["cpu_cooldown"]["cooldown_active"])
        self.assertGreater(dec["cpu_cooldown"]["remaining_sec"], 0)

    # 10. Independent Cooldowns (CPU cooldown does not block RAM)
    def test_10_independent_cooldowns(self):
        """Verify that CPU cooldown does NOT block RAM evaluation on the same VM."""
        vm_name = "Alpine-Linux"
        # Engage CPU cooldown only
        self.engine.record_action_applied(vm_name, "cpu", timestamp=time.time())

        vm_metrics = {
            "name": vm_name,
            "uuid": "app-vm-uuid-111",
            "vcpu_count": 2,
            "allocated_ram_mb": 2048.0,
            "cpu_percent": 95.0,  # in CPU cooldown -> HOLD
            "ram_percent": 92.0   # not in RAM cooldown -> evaluate RAM
        }
        host_metrics = {"available_ram_mb": 4096.0}

        # Interval 1
        dec1 = self.engine.evaluate_vm(vm_metrics, host_metrics=host_metrics)
        self.assertEqual(dec1["cpu_action"], "HOLD")
        self.assertTrue(dec1["cpu_cooldown"]["cooldown_active"])
        self.assertFalse(dec1["ram_cooldown"]["cooldown_active"])

        # Interval 2
        dec2 = self.engine.evaluate_vm(vm_metrics, host_metrics=host_metrics)
        self.assertEqual(dec2["cpu_action"], "HOLD")

        # Interval 3: RAM triggers SCALE_UP even while CPU is in cooldown
        dec3 = self.engine.evaluate_vm(vm_metrics, host_metrics=host_metrics)
        self.assertEqual(dec3["cpu_action"], "HOLD")
        self.assertEqual(dec3["ram_action"], "SCALE_UP")
        self.assertEqual(dec3["recommended_ram_mb"], 2560.0)

    # 11. Hysteresis & Consecutive Threshold Confirmation
    def test_11_hysteresis_consecutive_breaches(self):
        """Verify that isolated workload spikes do not trigger scaling (hysteresis protection)."""
        vm_metrics = {
            "name": "Alpine-Linux",
            "uuid": "app-vm-uuid-111",
            "vcpu_count": 2,
            "allocated_ram_mb": 2048.0,
            "cpu_percent": 95.0,
            "ram_percent": 50.0
        }
        # First spike
        dec1 = self.engine.evaluate_vm(vm_metrics)
        self.assertEqual(dec1["cpu_action"], "HOLD")

        # Load returns to normal before 2nd breach -> reset hysteresis
        vm_metrics["cpu_percent"] = 50.0
        dec2 = self.engine.evaluate_vm(vm_metrics)
        self.assertEqual(dec2["cpu_action"], "HOLD")

        # New isolated spike -> count starts fresh from 1
        vm_metrics["cpu_percent"] = 92.0
        dec3 = self.engine.evaluate_vm(vm_metrics)
        self.assertEqual(dec3["cpu_action"], "HOLD")

    # 12. Maximum CPU Boundary Enforcement (4 vCPUs)
    def test_12_maximum_cpu_enforcement(self):
        """Verify that at MAX_VCPUS (4), scale-up is blocked and held."""
        vm_metrics = {
            "name": "Alpine-Linux",
            "uuid": "app-vm-uuid-111",
            "vcpu_count": 4,
            "allocated_ram_mb": 2048.0,
            "cpu_percent": 95.0,
            "ram_percent": 50.0
        }
        # Even after 3 consecutive breaches, stays at max 4
        self.engine.evaluate_vm(vm_metrics)
        self.engine.evaluate_vm(vm_metrics)
        dec = self.engine.evaluate_vm(vm_metrics)
        self.assertEqual(dec["cpu_action"], "HOLD")
        self.assertEqual(dec["recommended_vcpus"], 4)
        self.assertIn("maximum boundary", dec["rationale"])

    # 13. Minimum CPU Boundary Enforcement (1 vCPU)
    def test_13_minimum_cpu_enforcement(self):
        """Verify that at MIN_VCPUS (1), scale-down is blocked and held."""
        vm_metrics = {
            "name": "Alpine-Linux",
            "uuid": "app-vm-uuid-111",
            "vcpu_count": 1,
            "allocated_ram_mb": 2048.0,
            "cpu_percent": 10.0,
            "ram_percent": 50.0
        }
        for _ in range(5):
            self.engine.evaluate_vm(vm_metrics)
        dec = self.engine.evaluate_vm(vm_metrics)
        self.assertEqual(dec["cpu_action"], "HOLD")
        self.assertEqual(dec["recommended_vcpus"], 1)
        self.assertIn("minimum boundary", dec["rationale"])

    # 14. Maximum RAM Boundary Enforcement (4096 MB)
    def test_14_maximum_ram_enforcement(self):
        """Verify that at MAX_RAM_MB (4096 MB), scale-up is blocked and held."""
        vm_metrics = {
            "name": "Alpine-Linux",
            "uuid": "app-vm-uuid-111",
            "vcpu_count": 2,
            "allocated_ram_mb": 4096.0,
            "cpu_percent": 50.0,
            "ram_percent": 95.0
        }
        self.engine.evaluate_vm(vm_metrics)
        self.engine.evaluate_vm(vm_metrics)
        dec = self.engine.evaluate_vm(vm_metrics)
        self.assertEqual(dec["ram_action"], "HOLD")
        self.assertEqual(dec["recommended_ram_mb"], 4096.0)
        self.assertIn("maximum boundary", dec["rationale"])

    # 15. Minimum RAM Boundary Enforcement (1024 MB)
    def test_15_minimum_ram_enforcement(self):
        """Verify that at MIN_RAM_MB (1024 MB), scale-down is blocked and held."""
        vm_metrics = {
            "name": "Alpine-Linux",
            "uuid": "app-vm-uuid-111",
            "vcpu_count": 2,
            "allocated_ram_mb": 1024.0,
            "cpu_percent": 50.0,
            "ram_percent": 15.0
        }
        for _ in range(5):
            self.engine.evaluate_vm(vm_metrics)
        dec = self.engine.evaluate_vm(vm_metrics)
        self.assertEqual(dec["ram_action"], "HOLD")
        self.assertEqual(dec["recommended_ram_mb"], 1024.0)
        self.assertIn("minimum boundary", dec["rationale"])

    # 16. Hypervisor Host Physical Capacity Restrictions
    def test_16_host_capacity_restrictions(self):
        """Verify that insufficient hypervisor free RAM blocks RAM scale-up (BLOCKED)."""
        vm_metrics = {
            "name": "Alpine-Linux",
            "uuid": "app-vm-uuid-111",
            "vcpu_count": 2,
            "allocated_ram_mb": 2048.0,
            "cpu_percent": 50.0,
            "ram_percent": 95.0
        }
        # Needed RAM = 512 + 256 cushion = 768 MB. Host only has 300 MB available.
        host_metrics = {"available_ram_mb": 300.0}

        self.engine.evaluate_vm(vm_metrics, host_metrics=host_metrics)
        self.engine.evaluate_vm(vm_metrics, host_metrics=host_metrics)
        dec = self.engine.evaluate_vm(vm_metrics, host_metrics=host_metrics)
        self.assertEqual(dec["ram_action"], "BLOCKED")
        self.assertIn("host capacity", dec["rationale"].lower())

    # 17. Failed XenAPI Allocation Handling & Error Capture
    def test_17_failed_allocation_handling(self):
        """Verify that XenAPI errors during actuation are cleanly captured and reported."""
        client = self._create_mock_client()
        client.proxy.VM.get_record.return_value = {
            "Status": "Success",
            "Value": {
                "VCPUs_max": "4",
                "VCPUs_at_startup": "2",
                "memory_static_min": str(512 * 1024 * 1024),
                "memory_dynamic_min": str(1024 * 1024 * 1024),
                "memory_dynamic_max": str(2048 * 1024 * 1024),
                "memory_static_max": str(4096 * 1024 * 1024)
            }
        }
        # Simulate XenAPI live scaling failure
        client.proxy.VM.set_VCPUs_number_live.return_value = {
            "Status": "Failure",
            "ErrorDescription": ["FEATURE_RESTRICTED", "Hotplug disabled in guest kernel"]
        }

        res = client.set_vm_vcpus("Alpine-Linux", 3)
        self.assertFalse(res["success"])
        self.assertIn("FEATURE_RESTRICTED", res["error"])

    # 18. Allocation History Recording in Database
    def test_18_allocation_history_recording(self):
        """Verify that scaling actions are audited into the resource_allocation_history table."""
        monitor = XenResourceMonitor.get_instance(self.config)
        action_data = {
            "vm_name": "Alpine-Linux",
            "vm_uuid": "app-vm-uuid-111",
            "resource_type": "cpu",
            "previous_value": 2,
            "requested_value": 3,
            "actual_value": 3,
            "trigger_reason": "High CPU workload (>80%)",
            "action_type": "auto_scale",
            "execution_status": "success",
            "error_message": None,
            "initiated_by": "auto"
        }
        monitor._persist_allocation_action(action_data)

        history = monitor.get_allocation_history(vm_name="Alpine-Linux", limit=10)
        self.assertTrue(len(history) > 0)
        latest = history[0]
        self.assertEqual(latest["vm_name"], "Alpine-Linux")
        self.assertEqual(latest["resource_type"], "cpu")
        self.assertEqual(int(latest["requested_value"]), 3)
        self.assertEqual(latest["execution_status"], "success")

    # 19. Administrator Authorization Gating
    def test_19_administrator_authorization(self):
        """Verify that allocation actuation routes require administrator authorization."""
        # Unauthenticated request -> 401
        res1 = self.test_client.post("/api/xen/allocation/enable")
        self.assertEqual(res1.status_code, 401)

        # Student token -> 403 Forbidden
        headers_student = {"Authorization": f"Bearer {self.student_token}"}
        res2 = self.test_client.post("/api/xen/allocation/enable", headers=headers_student)
        self.assertEqual(res2.status_code, 403)

        # Admin token -> 200 OK
        headers_admin = {"Authorization": f"Bearer {self.admin_token}"}
        res3 = self.test_client.post("/api/xen/allocation/enable", headers=headers_admin)
        self.assertEqual(res3.status_code, 200)

        # Disable allocation with admin token -> 200 OK
        res4 = self.test_client.post("/api/xen/allocation/disable", headers=headers_admin)
        self.assertEqual(res4.status_code, 200)

    # 20. Emergency Stop Safety Interlock
    def test_20_emergency_stop(self):
        """Verify that engaging Emergency Stop blocks automated scaling immediately."""
        self.engine.set_emergency_stop(True)
        self.assertTrue(self.engine.emergency_stop)

        vm_metrics = {
            "name": "Alpine-Linux",
            "uuid": "app-vm-uuid-111",
            "vcpu_count": 2,
            "allocated_ram_mb": 2048.0,
            "cpu_percent": 99.0,
            "ram_percent": 99.0
        }
        dec = self.engine.evaluate_vm(vm_metrics)
        self.assertEqual(dec["cpu_action"], "BLOCKED")
        self.assertEqual(dec["ram_action"], "BLOCKED")
        self.assertIn("EMERGENCY STOP", dec["rationale"])

        # Disengage
        self.engine.set_emergency_stop(False)
        self.assertFalse(self.engine.emergency_stop)

    # 21. Real XenAPI vCPU Live Actuation & Post-Change Verification
    def test_21_xenapi_set_vm_vcpus_actuation(self):
        """Verify live vCPU change via XenAPI and post-change verification."""
        client = self._create_mock_client()
        client.proxy.VM.get_record.side_effect = [
            # First call: pre-change
            {
                "Status": "Success",
                "Value": {
                    "VCPUs_max": "4",
                    "VCPUs_at_startup": "2",
                    "power_state": "Running"
                }
            },
            # Second call: post-change verification
            {
                "Status": "Success",
                "Value": {
                    "VCPUs_max": "4",
                    "VCPUs_at_startup": "3",
                    "power_state": "Running"
                }
            }
        ]
        client.proxy.VM.set_VCPUs_number_live.return_value = {"Status": "Success"}
        client.proxy.VM.set_VCPUs_at_startup.return_value = {"Status": "Success"}

        res = client.set_vm_vcpus("Alpine-Linux", 3)
        self.assertTrue(res["success"])
        self.assertEqual(res["requested_value"], 3)
        self.assertEqual(res["actual_value"], 3)
        self.assertEqual(res["previous_value"], 2)

    # 22. Real XenAPI Dynamic Memory Ballooning Actuation & Invariant Verification
    def test_22_xenapi_set_vm_dynamic_memory_actuation(self):
        """Verify dynamic memory ballooning via XenAPI and limits enforcement."""
        client = self._create_mock_client()
        client.proxy.VM.get_record.side_effect = [
            # Pre-change
            {
                "Status": "Success",
                "Value": {
                    "memory_static_min": str(512 * 1024 * 1024),
                    "memory_dynamic_min": str(1024 * 1024 * 1024),
                    "memory_dynamic_max": str(2048 * 1024 * 1024),
                    "memory_static_max": str(4096 * 1024 * 1024),
                    "power_state": "Running"
                }
            },
            # Post-change verification
            {
                "Status": "Success",
                "Value": {
                    "memory_static_min": str(512 * 1024 * 1024),
                    "memory_dynamic_min": str(1024 * 1024 * 1024),
                    "memory_dynamic_max": str(2560 * 1024 * 1024),
                    "memory_static_max": str(4096 * 1024 * 1024),
                    "power_state": "Running"
                }
            }
        ]
        client.proxy.VM.set_memory_dynamic_range.return_value = {"Status": "Success"}
        client.proxy.VM.set_memory_target_live.return_value = {"Status": "Success"}

        # Mock host capacity
        client.proxy.host.get_all_records.return_value = {
            "Status": "Success",
            "Value": {"ref_host": {"uuid": "h-uuid", "name_label": "XCP-ng", "metrics": "ref_hm"}}
        }
        client.proxy.host_metrics.get_record.return_value = {
            "Status": "Success",
            "Value": {"memory_total": str(8192 * 1024 * 1024), "memory_free": str(4096 * 1024 * 1024)}
        }
        client.proxy.host_cpu.get_all_records.return_value = {"Status": "Success", "Value": {}}

        res = client.set_vm_dynamic_memory("Alpine-Linux", 2560.0)
        self.assertTrue(res["success"])
        self.assertEqual(res["requested_value"], 2560.0)
        self.assertEqual(res["actual_value"], 2560.0)
        self.assertEqual(res["previous_value"], 2048.0)

    # 23. Verification failure handling for vCPU
    def test_23_verification_failure_vcpu(self):
        """Verify that if Xen post-actuation verification fails (value unchanged), success=False is returned."""
        client = self._create_mock_client()
        client.proxy.VM.get_record.side_effect = [
            # Pre-change
            {
                "Status": "Success",
                "Value": {
                    "VCPUs_max": "4",
                    "VCPUs_at_startup": "2",
                    "power_state": "Running"
                }
            },
            # Post-change readback returns unchanged or mismatched value
            {
                "Status": "Success",
                "Value": {
                    "VCPUs_max": "4",
                    "VCPUs_at_startup": "2",  # Failed to update in Xen
                    "power_state": "Running"
                }
            }
        ]
        client.proxy.VM.set_VCPUs_number_live.return_value = {"Status": "Success"}
        client.proxy.VM.set_VCPUs_at_startup.return_value = {"Status": "Success"}

        res = client.set_vm_vcpus("Alpine-Linux", 3)
        self.assertFalse(res["success"])
        self.assertEqual(res["actual_value"], 2)
        self.assertIn("Verification failed", res["error"])

    # 24. Verification failure handling for RAM dynamic memory
    def test_24_verification_failure_ram(self):
        """Verify that if Xen post-actuation RAM verification fails, success=False is returned."""
        client = self._create_mock_client()
        client.proxy.VM.get_record.side_effect = [
            # Pre-change
            {
                "Status": "Success",
                "Value": {
                    "memory_static_min": str(512 * 1024 * 1024),
                    "memory_dynamic_min": str(1024 * 1024 * 1024),
                    "memory_dynamic_max": str(2048 * 1024 * 1024),
                    "memory_static_max": str(4096 * 1024 * 1024),
                    "power_state": "Running"
                }
            },
            # Post-change readback returns unchanged memory
            {
                "Status": "Success",
                "Value": {
                    "memory_static_min": str(512 * 1024 * 1024),
                    "memory_dynamic_min": str(1024 * 1024 * 1024),
                    "memory_dynamic_max": str(2048 * 1024 * 1024),  # Not updated
                    "memory_static_max": str(4096 * 1024 * 1024),
                    "power_state": "Running"
                }
            }
        ]
        client.proxy.VM.set_memory_dynamic_range.return_value = {"Status": "Success"}
        client.proxy.VM.set_memory_target_live.return_value = {"Status": "Success"}

        # Host capacity ok
        client.proxy.host.get_all_records.return_value = {
            "Status": "Success",
            "Value": {"ref_host": {"uuid": "h-uuid", "name_label": "XCP-ng", "metrics": "ref_hm"}}
        }
        client.proxy.host_metrics.get_record.return_value = {
            "Status": "Success",
            "Value": {"memory_total": str(8192 * 1024 * 1024), "memory_free": str(4096 * 1024 * 1024)}
        }
        client.proxy.host_cpu.get_all_records.return_value = {"Status": "Success", "Value": {}}

        res = client.set_vm_dynamic_memory("Alpine-Linux", 2560.0)
        self.assertFalse(res["success"])
        self.assertIn("Verification failed", res["error"])

    # 25. Per-VM Policy for Application VM (Alpine-Linux: 1024-4096 MB RAM, 1-4 vCPUs)
    def test_25_per_vm_policy_application_vm(self):
        """Verify that Application VM policy boundaries (1024-4096 MB RAM, 1-4 vCPUs) are strictly enforced."""
        client = self._create_mock_client()
        # Out of bounds RAM < 1024 MB
        res_low_ram = client.set_vm_dynamic_memory("Alpine-Linux", 512.0)
        self.assertFalse(res_low_ram["success"])
        self.assertIn("violates configured limits", res_low_ram["error"])

        # Out of bounds RAM > 4096 MB
        res_high_ram = client.set_vm_dynamic_memory("Alpine-Linux", 6144.0)
        self.assertFalse(res_high_ram["success"])
        self.assertIn("violates configured limits", res_high_ram["error"])

        # Out of bounds vCPUs < 1
        res_low_cpu = client.set_vm_vcpus("Alpine-Linux", 0)
        self.assertFalse(res_low_cpu["success"])
        self.assertIn("violates configured limits", res_low_cpu["error"])

        # Out of bounds vCPUs > 4
        res_high_cpu = client.set_vm_vcpus("Alpine-Linux", 5)
        self.assertFalse(res_high_cpu["success"])
        self.assertIn("violates configured limits", res_high_cpu["error"])

    # 26. Per-VM Policy for Database VM: Baseline Allocation Preservation
    def test_26_per_vm_policy_database_vm_preservation(self):
        """Verify that Alpine-DB baseline allocation is preserved when preserve_initial=True."""
        vm_metrics = {
            "name": "Alpine-DB",
            "uuid": "db-vm-uuid-222",
            "vcpu_count": 2,
            "allocated_ram_mb": 2048.0,
            "cpu_percent": 95.0,  # High CPU
            "ram_percent": 95.0   # High RAM
        }
        dec = self.engine.evaluate_vm(vm_metrics)
        self.assertEqual(dec["cpu_action"], "HOLD")
        self.assertEqual(dec["ram_action"], "HOLD")
        self.assertIn("Preserving initial Alpine-DB resource baseline", dec["rationale"])

    # 27. Manual Allocation Works When Automatic Allocation is Disabled
    def test_27_manual_allocation_works_when_auto_disabled(self):
        """Verify that manual administrator override operates even when ALLOCATION_MODE='manual'."""
        client = self._create_mock_client()
        monitor = XenResourceMonitor(self.config)
        monitor.client = client
        monitor.set_allocation_mode("manual")
        self.assertEqual(monitor.get_allocation_status()["allocation_mode"], "manual")

        # Mock XenAPI for vCPU set
        client.proxy.VM.get_record.side_effect = [
            # Pre-change
            {"Status": "Success", "Value": {"VCPUs_max": "4", "VCPUs_at_startup": "2", "power_state": "Running"}},
            # Post-change verification
            {"Status": "Success", "Value": {"VCPUs_max": "4", "VCPUs_at_startup": "3", "power_state": "Running"}},
            # Pre-change RAM
            {"Status": "Success", "Value": {
                "memory_static_min": str(512 * 1024 * 1024), "memory_dynamic_min": str(1024 * 1024 * 1024),
                "memory_dynamic_max": str(2048 * 1024 * 1024), "memory_static_max": str(4096 * 1024 * 1024),
                "power_state": "Running"
            }},
            # Post-change RAM verification
            {"Status": "Success", "Value": {
                "memory_static_min": str(512 * 1024 * 1024), "memory_dynamic_min": str(1024 * 1024 * 1024),
                "memory_dynamic_max": str(2560 * 1024 * 1024), "memory_static_max": str(4096 * 1024 * 1024),
                "power_state": "Running"
            }}
        ]
        client.proxy.VM.set_VCPUs_number_live.return_value = {"Status": "Success"}
        client.proxy.VM.set_VCPUs_at_startup.return_value = {"Status": "Success"}
        client.proxy.VM.set_memory_dynamic_range.return_value = {"Status": "Success"}
        client.proxy.VM.set_memory_target_live.return_value = {"Status": "Success"}
        client.proxy.host.get_all_records.return_value = {
            "Status": "Success",
            "Value": {"ref_host": {"uuid": "h-uuid", "name_label": "XCP-ng", "metrics": "ref_hm"}}
        }
        client.proxy.host_metrics.get_record.return_value = {
            "Status": "Success",
            "Value": {"memory_total": str(8192 * 1024 * 1024), "memory_free": str(4096 * 1024 * 1024)}
        }
        client.proxy.host_cpu.get_all_records.return_value = {"Status": "Success", "Value": {}}

        # Manual CPU
        cpu_res = monitor.apply_manual_cpu("Alpine-Linux", 3, initiated_by="admin")
        self.assertTrue(cpu_res["success"])
        self.assertEqual(cpu_res["actual_value"], 3)

        # Manual RAM
        ram_res = monitor.apply_manual_ram("Alpine-Linux", 2560.0, initiated_by="admin")
        self.assertTrue(ram_res["success"])
        self.assertEqual(ram_res["actual_value"], 2560.0)

        # Verify last_xen_operation
        status = monitor.get_allocation_status()
        self.assertIsNotNone(status.get("last_xen_operation"))
        self.assertEqual(status["last_xen_operation"]["status"], "verified")

    # 28. Safe Baseline Transition to 1 vCPU / 1024 MB
    def test_28_safe_baseline_transition(self):
        """Verify safe transition of an overprovisioned VM down to 1 vCPU and 1024 MB RAM baseline."""
        client = self._create_mock_client()
        monitor = XenResourceMonitor(self.config)
        monitor.client = client

        client.proxy.VM.get_record.side_effect = [
            # vCPU pre
            {"Status": "Success", "Value": {"VCPUs_max": "4", "VCPUs_at_startup": "4", "power_state": "Running"}},
            # vCPU post verification
            {"Status": "Success", "Value": {"VCPUs_max": "4", "VCPUs_at_startup": "1", "power_state": "Running"}},
            # RAM pre
            {"Status": "Success", "Value": {
                "memory_static_min": str(512 * 1024 * 1024), "memory_dynamic_min": str(1024 * 1024 * 1024),
                "memory_dynamic_max": str(4096 * 1024 * 1024), "memory_static_max": str(4096 * 1024 * 1024),
                "power_state": "Running"
            }},
            # RAM post verification
            {"Status": "Success", "Value": {
                "memory_static_min": str(512 * 1024 * 1024), "memory_dynamic_min": str(1024 * 1024 * 1024),
                "memory_dynamic_max": str(1024 * 1024 * 1024), "memory_static_max": str(4096 * 1024 * 1024),
                "power_state": "Running"
            }}
        ]
        client.proxy.VM.set_VCPUs_number_live.return_value = {"Status": "Success"}
        client.proxy.VM.set_VCPUs_at_startup.return_value = {"Status": "Success"}
        client.proxy.VM.set_memory_dynamic_range.return_value = {"Status": "Success"}
        client.proxy.VM.set_memory_target_live.return_value = {"Status": "Success"}
        client.proxy.host.get_all_records.return_value = {
            "Status": "Success",
            "Value": {"ref_host": {"uuid": "h-uuid", "name_label": "XCP-ng", "metrics": "ref_hm"}}
        }
        client.proxy.host_metrics.get_record.return_value = {
            "Status": "Success",
            "Value": {"memory_total": str(8192 * 1024 * 1024), "memory_free": str(4096 * 1024 * 1024)}
        }
        client.proxy.host_cpu.get_all_records.return_value = {"Status": "Success", "Value": {}}

        trans_res = monitor.transition_to_baseline("Alpine-Linux", initiated_by="admin")
        self.assertTrue(trans_res["success"])
        self.assertEqual(trans_res["target_baseline"]["vcpus"], 1)
        self.assertEqual(trans_res["target_baseline"]["ram_mb"], 1024.0)

    # 29. CPU Workload Simulator Start, Status, and Stop
    def test_29_cpu_workload_simulator(self):
        """Verify starting, tracking, and stopping authentic synthetic CPU workload."""
        from backend.services.workload_service import WorkloadSimulatorService
        svc = WorkloadSimulatorService.get_instance()

        start_res = svc.start_cpu_workload(
            target_vm="Alpine-Linux",
            intensity_percent=75.0,
            workers=1,
            duration_sec=30,
            initiated_by="admin"
        )
        self.assertTrue(start_res["success"])
        session_id = start_res["session_id"]

        status = svc.get_status()
        self.assertIsNotNone(status["running_cpu_session"])
        self.assertEqual(status["running_cpu_session"]["session_id"], session_id)

        # Stop
        stop_res = svc.stop_workload(session_id)
        self.assertTrue(stop_res["success"])
        status_after = svc.get_status()
        self.assertIsNone(status_after["running_cpu_session"])

    # 30. RAM Workload Simulator & OOM Headroom Safety Protection
    def test_30_ram_workload_simulator_oom_protection(self):
        """Verify that RAM workload generator validates guest memory and prevents OOM."""
        from backend.services.workload_service import WorkloadSimulatorService
        svc = WorkloadSimulatorService.get_instance()

        # Attempt to allocate unsafe excessive memory (e.g. 500,000 MB)
        reject_res = svc.start_ram_workload(
            target_vm="Alpine-Linux",
            allocated_mb=500000.0,
            duration_sec=30,
            initiated_by="admin"
        )
        self.assertFalse(reject_res["success"])
        self.assertIn("Safety check rejected RAM allocation", reject_res["error"])

        # Allocate safe 128 MB
        safe_res = svc.start_ram_workload(
            target_vm="Alpine-Linux",
            allocated_mb=128.0,
            duration_sec=30,
            initiated_by="admin"
        )
        self.assertTrue(safe_res["success"])
        session_id = safe_res["session_id"]

        status = svc.get_status()
        self.assertIsNotNone(status["running_ram_session"])

        # Clean up
        svc.stop_workload(session_id)

    # 31. Database Workload Simulator & Student Record Safety
    def test_31_database_workload_simulator_data_safety(self):
        """Verify that Database workload exercises MariaDB without touching student/course records."""
        from backend.services.workload_service import WorkloadSimulatorService
        svc = WorkloadSimulatorService.get_instance()

        # Count original students and courses
        original_students = query_db("SELECT COUNT(*) as count FROM students")
        original_courses = query_db("SELECT COUNT(*) as count FROM courses")

        db_res = svc.start_database_workload(
            target_vm="Alpine-DB",
            intensity="low",
            workers=1,
            duration_sec=30,
            initiated_by="admin"
        )
        self.assertTrue(db_res["success"])
        session_id = db_res["session_id"]

        time.sleep(0.5)

        # Confirm original data was never modified or deleted
        curr_students = query_db("SELECT COUNT(*) as count FROM students")
        curr_courses = query_db("SELECT COUNT(*) as count FROM courses")
        self.assertEqual(original_students[0]["count"], curr_students[0]["count"])
        self.assertEqual(original_courses[0]["count"], curr_courses[0]["count"])

        svc.stop_workload(session_id)

    # 32. Emergency Stop Halts Active Workloads Immediately
    def test_32_emergency_stop_halts_active_workloads(self):
        """Verify that engaging Emergency Stop halts all active workload sessions."""
        from backend.services.workload_service import WorkloadSimulatorService
        svc = WorkloadSimulatorService.get_instance()

        cpu_res = svc.start_cpu_workload("Alpine-Linux", intensity_percent=50.0, workers=1, duration_sec=60)
        self.assertTrue(cpu_res["success"])
        self.assertIsNotNone(svc.get_status()["running_cpu_session"])

        # Engage Emergency Stop via monitor
        monitor = XenResourceMonitor(self.config)
        monitor.set_emergency_stop(True)

        # Active workload must now be halted
        status = svc.get_status()
        self.assertIsNone(status["running_cpu_session"])
        self.assertTrue(monitor.allocation_engine.emergency_stop)

        # Disengage
        monitor.set_emergency_stop(False)

    # 33. Stale Telemetry Handling
    def test_33_stale_telemetry_handling(self):
        """Verify that stale telemetry holds scaling decisions to prevent erroneous actuation."""
        vm_metrics = {
            "name": "Alpine-Linux",
            "uuid": "app-vm-uuid-111",
            "vcpu_count": 2,
            "allocated_ram_mb": 2048.0,
            "cpu_percent": 99.0,
            "ram_percent": 99.0,
            "is_stale": True
        }
        dec = self.engine.evaluate_vm(vm_metrics)
        self.assertEqual(dec["cpu_action"], "HOLD")
        self.assertEqual(dec["ram_action"], "HOLD")
        self.assertIn("stale or offline", dec["rationale"])

    # 34. Unsupported Hotplug / Ballooning Reports Maintenance Required
    def test_34_unsupported_hotplug_maintenance(self):
        """Verify that unsupported CPU hotplug or ballooning reports maintenance requirement."""
        vm_metrics = {
            "name": "Alpine-Linux",
            "uuid": "app-vm-uuid-111",
            "vcpu_count": 3,
            "allocated_ram_mb": 2560.0,
            "cpu_percent": 10.0,
            "ram_percent": 20.0,
            "supports_vcpu_hotplug": False,
            "supports_ballooning": False
        }
        # Run through 6 consecutive intervals to trigger scale-down evaluation
        for _ in range(5):
            self.engine.evaluate_vm(vm_metrics)
        dec = self.engine.evaluate_vm(vm_metrics)
        self.assertEqual(dec["cpu_action"], "MAINTENANCE_REQUIRED")
        self.assertEqual(dec["ram_action"], "MAINTENANCE_REQUIRED")
        self.assertIn("maintenance", dec["rationale"].lower())


if __name__ == "__main__":
    unittest.main()
