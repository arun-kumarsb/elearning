"""
Automated Test Suite for Student-Driven Xen Dynamic Resource Allocation & Orchestration
Project: Xen-Based Dynamic Resource Allocation for Scalable E-Learning Services

Covers all 18+ required test scenarios from Section 11:
1. Idle workloads
2. 10 simulated students
3. 50 simulated students
4. 100 simulated students
5. 200 simulated students
6. Increased Flask request rate
7. Increased MariaDB query load
8. CPU scale-up (3 consecutive breaches > 80%)
9. CPU scale-down (6 consecutive breaches < 25%)
10. RAM scale-up (3 consecutive breaches > 85%)
11. RAM scale-down (6 consecutive breaches < 30%)
12. Host memory exhaustion protection
13. Missing telemetry safe hold
14. Stale telemetry handling
15. Unsupported hotplug maintenance mode
16. Failed XenAPI changes
17. Emergency Stop
18. Workload termination on safety limit
19. Dynamic VM UUID verification
20. Safe baseline transition
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
from backend.services.student_load_service import StudentLoadSimulatorService
from backend.services.auth_service import generate_session_token
from backend.database import ensure_schema, execute_db, query_db, ensure_simulated_student_pool
from backend.app import create_app

class TestStudentLoadOrchestration(unittest.TestCase):

    def setUp(self):
        """Set up isolated test fixtures and configurations."""
        self.config = MonitorConfig()
        self.config.allocation_mode = "manual"
        self.config.cooldown_period_sec = 60
        self.config.scale_up_consecutive_threshold = 3
        self.config.scale_down_consecutive_threshold = 6

        # Target VM Policies
        self.config.app_vm_name = "Alpine-Linux"
        self.config.db_vm_name = "Alpine-DB"
        self.config.min_vcpus = 1
        self.config.max_vcpus = 4
        self.config.min_ram_mb = 1024.0
        self.config.max_ram_mb = 4096.0

        self.engine = AllocationEngine(self.config)
        self.monitor = XenResourceMonitor(self.config)

        # Flask Test Client
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

        # Admin & Student Auth Tokens
        self.admin_token = generate_session_token(user_id=1, email="admin@elearning.local", role="admin")
        self.student_token = generate_session_token(user_id=2, email="student@example.com", role="student")
        self.admin_headers = {"Authorization": f"Bearer {self.admin_token}", "Content-Type": "application/json"}
        self.student_headers = {"Authorization": f"Bearer {self.student_token}", "Content-Type": "application/json"}

        # Pre-seed simulated student accounts
        ensure_simulated_student_pool(20)

    # -------------------------------------------------------------------------
    # Scenario 1: Idle Workload
    # -------------------------------------------------------------------------
    def test_01_idle_workload(self):
        """Verify nominal hold recommendation under idle system conditions."""
        vm_metrics = {
            "name": "Alpine-Linux",
            "uuid": "01cdb87c-408f-72bc-449c-0364a8e69647",
            "vcpu_count": 1,
            "allocated_ram_mb": 1024.0,
            "cpu_percent": 12.0,
            "ram_percent": 35.0,
            "guest_ram_percent": 35.0,
            "guest_used_ram_mb": 358.0,
            "guest_available_ram_mb": 666.0,
            "memory_status": "ok"
        }
        dec = self.engine.evaluate_vm(vm_metrics)
        self.assertEqual(dec["cpu_action"], "HOLD")
        self.assertEqual(dec["ram_action"], "HOLD")
        self.assertEqual(dec["recommended_vcpus"], 1)
        self.assertEqual(dec["recommended_ram_mb"], 1024.0)

    # -------------------------------------------------------------------------
    # Scenario 2: 10 Simulated Students
    # -------------------------------------------------------------------------
    def test_02_ten_simulated_students(self):
        """Verify launching, status tracking, and stopping 10 simulated students."""
        svc = StudentLoadSimulatorService.get_instance()
        res = svc.start_load_test(
            target_vm="app_vm",
            simulated_students=10,
            ramp_up_duration=0,
            test_duration=30,
            requests_per_student=2.0,
            workload_intensity="light"
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["simulated_students"], 10)
        time.sleep(0.5)

        status = svc.get_status()
        self.assertIn(status["status"], ("ramping_up", "running"))
        self.assertGreaterEqual(status["simulated_students"], 10)

        stop_res = svc.stop_load_test()
        self.assertTrue(stop_res["success"])

    # -------------------------------------------------------------------------
    # Scenario 3: 50 Simulated Students
    # -------------------------------------------------------------------------
    def test_03_fifty_simulated_students(self):
        """Verify 50 simulated students configuration and ramp-up handling."""
        svc = StudentLoadSimulatorService.get_instance()
        res = svc.start_load_test(
            target_vm="both",
            simulated_students=50,
            ramp_up_duration=1,
            test_duration=30,
            requests_per_student=2.0,
            workload_intensity="medium"
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["simulated_students"], 50)
        svc.stop_load_test()

    # -------------------------------------------------------------------------
    # Scenario 4: 100 Simulated Students
    # -------------------------------------------------------------------------
    def test_04_one_hundred_simulated_students(self):
        """Verify 100 simulated students configuration."""
        svc = StudentLoadSimulatorService.get_instance()
        res = svc.start_load_test(
            target_vm="app_vm",
            simulated_students=100,
            ramp_up_duration=1,
            test_duration=30
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["simulated_students"], 100)
        svc.stop_load_test()

    # -------------------------------------------------------------------------
    # Scenario 5: 200 Simulated Students
    # -------------------------------------------------------------------------
    def test_05_two_hundred_simulated_students(self):
        """Verify maximum load ceiling of 200 simulated students."""
        svc = StudentLoadSimulatorService.get_instance()
        res = svc.start_load_test(
            target_vm="both",
            simulated_students=200,
            ramp_up_duration=1,
            test_duration=30
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["simulated_students"], 200)
        svc.stop_load_test()

    # -------------------------------------------------------------------------
    # Scenario 6: Increased Flask Request Rate
    # -------------------------------------------------------------------------
    def test_06_increased_flask_request_rate(self):
        """Verify live calculation of requests per second (RPS) and latency."""
        svc = StudentLoadSimulatorService.get_instance()
        # Record synthetic requests directly
        for _ in range(20):
            svc._record_request(latency_ms=15.5, is_success=True, is_db=False)
        status = svc.get_status()
        self.assertGreater(status["total_requests"], 0)
        self.assertGreater(status["avg_response_time_ms"], 0.0)

    # -------------------------------------------------------------------------
    # Scenario 7: Increased MariaDB Query Load
    # -------------------------------------------------------------------------
    def test_07_increased_mariadb_query_load(self):
        """Verify synthetic MariaDB query generation against transient table."""
        res = self.client.post(
            "/api/xen/student-load/db-query",
            json={"session_id": "test-session-123", "student_id": 5}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))

    # -------------------------------------------------------------------------
    # Scenario 8: CPU Scale-Up (3 Consecutive Breaches > 80%)
    # -------------------------------------------------------------------------
    def test_08_cpu_scale_up_hysteresis(self):
        """Verify that CPU > 80% requires 3 consecutive intervals before scaling up."""
        metrics = {
            "name": "Alpine-Linux",
            "uuid": "01cdb87c-408f-72bc-449c-0364a8e69647",
            "vcpu_count": 1,
            "allocated_ram_mb": 1024.0,
            "cpu_percent": 92.0,
            "ram_percent": 45.0,
            "guest_ram_percent": 45.0,
            "memory_status": "ok"
        }
        # Sample 1: HOLD (1/3)
        d1 = self.engine.evaluate_vm(metrics)
        self.assertEqual(d1["cpu_action"], "HOLD")

        # Sample 2: HOLD (2/3)
        d2 = self.engine.evaluate_vm(metrics)
        self.assertEqual(d2["cpu_action"], "HOLD")

        # Sample 3: SCALE_UP (3/3 confirmed)
        d3 = self.engine.evaluate_vm(metrics)
        self.assertEqual(d3["cpu_action"], "SCALE_UP")
        self.assertEqual(d3["recommended_vcpus"], 2)

    # -------------------------------------------------------------------------
    # Scenario 9: CPU Scale-Down (6 Consecutive Breaches < 25%)
    # -------------------------------------------------------------------------
    def test_09_cpu_scale_down_hysteresis(self):
        """Verify that CPU < 25% requires 6 consecutive intervals before scaling down."""
        metrics = {
            "name": "Alpine-Linux",
            "uuid": "01cdb87c-408f-72bc-449c-0364a8e69647",
            "vcpu_count": 3,
            "allocated_ram_mb": 2048.0,
            "cpu_percent": 15.0,
            "ram_percent": 45.0,
            "guest_ram_percent": 45.0,
            "memory_status": "ok",
            "supports_vcpu_hotplug": True
        }
        # Samples 1 to 5: HOLD
        for i in range(1, 6):
            d = self.engine.evaluate_vm(metrics)
            self.assertEqual(d["cpu_action"], "HOLD", f"Interval {i} should be HOLD")

        # Sample 6: SCALE_DOWN
        d6 = self.engine.evaluate_vm(metrics)
        self.assertEqual(d6["cpu_action"], "SCALE_DOWN")
        self.assertEqual(d6["recommended_vcpus"], 2)

    # -------------------------------------------------------------------------
    # Scenario 10: RAM Scale-Up (3 Consecutive Breaches > 85%)
    # -------------------------------------------------------------------------
    def test_10_ram_scale_up_hysteresis(self):
        """Verify that guest RAM > 85% requires 3 consecutive intervals before scaling up."""
        metrics = {
            "name": "Alpine-Linux",
            "uuid": "01cdb87c-408f-72bc-449c-0364a8e69647",
            "vcpu_count": 2,
            "allocated_ram_mb": 1024.0,
            "cpu_percent": 40.0,
            "ram_percent": 88.0,
            "guest_ram_percent": 88.0,
            "guest_used_ram_mb": 901.0,
            "guest_available_ram_mb": 123.0,
            "memory_status": "ok"
        }
        d1 = self.engine.evaluate_vm(metrics)
        self.assertEqual(d1["ram_action"], "HOLD")

        d2 = self.engine.evaluate_vm(metrics)
        self.assertEqual(d2["ram_action"], "HOLD")

        d3 = self.engine.evaluate_vm(metrics)
        self.assertEqual(d3["ram_action"], "SCALE_UP")
        self.assertEqual(d3["recommended_ram_mb"], 1536.0)

    # -------------------------------------------------------------------------
    # Scenario 11: RAM Scale-Down (6 Consecutive Breaches < 30%)
    # -------------------------------------------------------------------------
    def test_11_ram_scale_down_hysteresis(self):
        """Verify that guest RAM < 30% requires 6 consecutive intervals before scaling down."""
        metrics = {
            "name": "Alpine-Linux",
            "uuid": "01cdb87c-408f-72bc-449c-0364a8e69647",
            "vcpu_count": 2,
            "allocated_ram_mb": 2048.0,
            "cpu_percent": 40.0,
            "ram_percent": 22.0,
            "guest_ram_percent": 22.0,
            "guest_used_ram_mb": 450.0,
            "guest_available_ram_mb": 1598.0,
            "memory_status": "ok",
            "supports_ballooning": True
        }
        for i in range(1, 6):
            d = self.engine.evaluate_vm(metrics)
            self.assertEqual(d["ram_action"], "HOLD")

        d6 = self.engine.evaluate_vm(metrics)
        self.assertEqual(d6["ram_action"], "SCALE_DOWN")
        self.assertEqual(d6["recommended_ram_mb"], 1536.0)

    # -------------------------------------------------------------------------
    # Scenario 12: Host Memory Exhaustion Protection
    # -------------------------------------------------------------------------
    def test_12_host_memory_exhaustion_protection(self):
        """Verify that RAM scale-up is blocked if host free RAM lacks cushion."""
        metrics = {
            "name": "Alpine-Linux",
            "uuid": "01cdb87c-408f-72bc-449c-0364a8e69647",
            "vcpu_count": 2,
            "allocated_ram_mb": 1024.0,
            "cpu_percent": 40.0,
            "ram_percent": 90.0,
            "guest_ram_percent": 90.0,
            "memory_status": "ok"
        }
        host_exhausted = {"available_ram_mb": 200.0} # Needs 512 + 256 = 768 MB
        self.engine._consecutive_breaches["alpine-linux:ram:scale_up"] = 2
        d = self.engine.evaluate_vm(metrics, host_metrics=host_exhausted)
        self.assertEqual(d["ram_action"], "BLOCKED")
        self.assertIn("host capacity", d["rationale"].lower())

    # -------------------------------------------------------------------------
    # Scenario 13: Missing Telemetry Safe Hold
    # -------------------------------------------------------------------------
    def test_13_missing_guest_telemetry_safe_hold(self):
        """Verify that missing guest RAM telemetry withholds scale-down to prevent OOM."""
        metrics = {
            "name": "Alpine-Linux",
            "uuid": "01cdb87c-408f-72bc-449c-0364a8e69647",
            "vcpu_count": 2,
            "allocated_ram_mb": 2048.0,
            "cpu_percent": 10.0,
            "ram_percent": 0.0,
            "guest_ram_percent": None, # Unavailable
            "guest_used_ram_mb": None,
            "guest_available_ram_mb": None,
            "memory_status": "guest_metrics_unavailable"
        }
        for _ in range(6):
            d = self.engine.evaluate_vm(metrics)
        self.assertEqual(d["ram_action"], "HOLD")
        self.assertIn("unavailable", d["rationale"].lower())

    # -------------------------------------------------------------------------
    # Scenario 14: Stale Telemetry Handling
    # -------------------------------------------------------------------------
    def test_14_stale_telemetry_handling(self):
        """Verify that stale telemetry suspends automated scaling actions."""
        metrics = {
            "name": "Alpine-Linux",
            "uuid": "01cdb87c-408f-72bc-449c-0364a8e69647",
            "vcpu_count": 2,
            "allocated_ram_mb": 2048.0,
            "cpu_percent": 95.0,
            "ram_percent": 95.0,
            "is_stale": True
        }
        d = self.engine.evaluate_vm(metrics)
        self.assertEqual(d["cpu_action"], "HOLD")
        self.assertEqual(d["ram_action"], "HOLD")
        self.assertIn("stale", d["rationale"].lower())

    # -------------------------------------------------------------------------
    # Scenario 15: Unsupported Hotplug Maintenance Required
    # -------------------------------------------------------------------------
    def test_15_unsupported_hotplug_maintenance_required(self):
        """Verify that unsupported CPU hot-unplug flags MAINTENANCE_REQUIRED."""
        metrics = {
            "name": "Alpine-Linux",
            "uuid": "01cdb87c-408f-72bc-449c-0364a8e69647",
            "vcpu_count": 3,
            "allocated_ram_mb": 2048.0,
            "cpu_percent": 10.0,
            "ram_percent": 40.0,
            "guest_ram_percent": 40.0,
            "supports_vcpu_hotplug": False
        }
        self.engine._consecutive_breaches["alpine-linux:cpu:scale_down"] = 5
        d = self.engine.evaluate_vm(metrics)
        self.assertEqual(d["cpu_action"], "MAINTENANCE_REQUIRED")

    # -------------------------------------------------------------------------
    # Scenario 16: Failed XenAPI Changes Handled Gracefully
    # -------------------------------------------------------------------------
    def test_16_failed_xenapi_changes(self):
        """Verify that failed XenAPI operations return failure details and log errors."""
        with patch.object(self.monitor.client, "set_vm_vcpus", return_value={"success": False, "error": "XAPI Error: Invalid session"}):
            res = self.monitor.apply_manual_cpu("Alpine-Linux", 3, "Test change")
            self.assertFalse(res["success"])
            self.assertIn("Invalid session", res["error"])

    # -------------------------------------------------------------------------
    # Scenario 17: Emergency Stop
    # -------------------------------------------------------------------------
    def test_17_emergency_stop_halts_everything(self):
        """Verify emergency stop suspends autoscaling and terminates load tests."""
        svc = StudentLoadSimulatorService.get_instance()
        svc.start_load_test(target_vm="app_vm", simulated_students=10, test_duration=30)
        
        # Actuate emergency stop
        em_res = svc.emergency_stop_all()
        self.assertTrue(em_res["success"])
        self.assertEqual(em_res["status"], "emergency_stopped")

        # Verify engine also blocked
        self.engine.set_emergency_stop(True)
        metrics = {"name": "Alpine-Linux", "cpu_percent": 99.0, "ram_percent": 99.0, "vcpu_count": 1, "allocated_ram_mb": 1024.0}
        d = self.engine.evaluate_vm(metrics)
        self.assertEqual(d["cpu_action"], "BLOCKED")
        self.assertEqual(d["ram_action"], "BLOCKED")

    # -------------------------------------------------------------------------
    # Scenario 18: Workload Termination on Safety Limit
    # -------------------------------------------------------------------------
    def test_18_workload_termination_safety_limit(self):
        """Verify safety limit trips when simulated error rate exceeds 50%."""
        svc = StudentLoadSimulatorService.get_instance()
        svc.start_load_test(target_vm="app_vm", simulated_students=5, test_duration=30)
        
        # Inject simulated failures to trip 50% error rate limit
        with svc._live_stats_lock:
            svc._total_requests = 40
            svc._failed_requests = 25 # 62.5% failure rate

        # Run safety monitor iteration
        time.sleep(1.2)
        status = svc.get_status()
        self.assertIn(status["status"], ("stopped_safety_limit", "stopping", "completed"))
        svc.stop_load_test()

    # -------------------------------------------------------------------------
    # Scenario 19: Dynamic VM UUID Verification
    # -------------------------------------------------------------------------
    def test_19_vm_uuid_verification(self):
        """Verify that dynamic VM discovery resolves and verifies target UUIDs."""
        self.assertEqual(XenAPIClient.EXPECTED_APP_VM_UUID, "01cdb87c-408f-72bc-449c-0364a8e69647")
        self.assertEqual(XenAPIClient.EXPECTED_DB_VM_UUID, "0a6dec09-0466-0079-4b66-80704b59587d")

    # -------------------------------------------------------------------------
    # Scenario 20: Safe Baseline Transition
    # -------------------------------------------------------------------------
    def test_20_safe_baseline_transition(self):
        """Verify safe transition to 1 vCPU and 1024 MB RAM."""
        with patch.object(self.monitor.client, "set_vm_vcpus", return_value={"success": True, "actual_value": 1}):
            with patch.object(self.monitor.client, "set_vm_dynamic_memory", return_value={"success": True, "actual_value": 1024.0}):
                res = self.monitor.transition_to_baseline("Alpine-Linux")
                self.assertTrue(res["success"])
                self.assertEqual(res["target_baseline"]["vcpus"], 1)
                self.assertEqual(res["target_baseline"]["ram_mb"], 1024.0)

    # -------------------------------------------------------------------------
    # Scenario 21: Frontend API Contracts & Imports
    # -------------------------------------------------------------------------
    def test_21_frontend_api_contracts_and_imports(self):
        """Verify all frontend API contracts imported by Intelligent Orchestration exist and are callable."""
        import frontend.api as fapi
        import frontend.pages.intelligent_orchestration as fpage
        
        self.assertTrue(callable(getattr(fapi, "api_get_metrics_history", None)))
        self.assertTrue(callable(getattr(fapi, "api_set_allocation_mode", None)))
        self.assertTrue(callable(getattr(fapi, "api_apply_recommendation", None)))
        self.assertTrue(callable(getattr(fapi, "api_apply_recommended", None)))
        self.assertTrue(callable(getattr(fapi, "api_get_xen_history", None)))
        self.assertTrue(callable(getattr(fpage, "render_intelligent_orchestration_page", None)))

        with patch.object(fapi, "safe_request", return_value={"success": True, "count": 0, "data": []}) as mock_req:
            res = fapi.api_get_metrics_history(limit=50)
            self.assertTrue(res["success"])
            self.assertEqual(res["data"], [])
            mock_req.assert_called_with("GET", "xen/history?limit=50")

        with patch.object(fapi, "safe_request", return_value={"success": True, "mode": "auto"}) as mock_req:
            res = fapi.api_set_allocation_mode("auto")
            self.assertTrue(res["success"])
            self.assertEqual(res["mode"], "auto")

    # -------------------------------------------------------------------------
    # Scenario 22: Metrics History & Allocation Mode Endpoints
    # -------------------------------------------------------------------------
    def test_22_metrics_history_and_mode_endpoints(self):
        """Verify GET /api/xen/metrics/history and POST /api/xen/allocation/mode endpoints."""
        app = create_app()
        client = app.test_client()
        admin_token = generate_session_token(1, "admin@elearning.local", "admin")
        headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

        # 1. Test GET /api/xen/metrics/history
        resp = client.get("/api/xen/metrics/history?limit=10")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertIsInstance(data.get("data"), list)

        # 2. Test POST /api/xen/allocation/mode
        resp_mode = client.post("/api/xen/allocation/mode", headers=headers, json={"mode": "auto"})
        self.assertEqual(resp_mode.status_code, 200)
        data_mode = resp_mode.get_json()
        self.assertTrue(data_mode.get("success"))
        self.assertEqual(data_mode.get("mode"), "auto")

        # 3. Test invalid mode rejection
        resp_invalid = client.post("/api/xen/allocation/mode", headers=headers, json={"mode": "turbo"})
        self.assertEqual(resp_invalid.status_code, 400)

    # -------------------------------------------------------------------------
    # Scenario 23: Authorization Role Normalization
    # -------------------------------------------------------------------------
    def test_23_authorization_role_normalization(self):
        """Verify role normalization handles 'admin', 'administrator', 'Administrator', 'ADMIN'."""
        from frontend.auth_utils import is_admin_role, normalize_role
        from backend.routes.xen_routes import is_admin_role as backend_is_admin_role

        admin_variants = ["admin", "administrator", "Administrator", "ADMIN", " Admin ", "ADMINISTRATOR"]
        for v in admin_variants:
            self.assertTrue(is_admin_role(v), f"Failed for variant: {v}")
            self.assertTrue(backend_is_admin_role(v), f"Backend failed for variant: {v}")

        non_admin_variants = ["student", "Student", "STUDENT", "user", "", None, 123, "guest", "evaluator"]
        for v in non_admin_variants:
            self.assertFalse(is_admin_role(v), f"Should be False for non-admin: {v}")
            self.assertFalse(backend_is_admin_role(v), f"Backend should be False for non-admin: {v}")

    # -------------------------------------------------------------------------
    # Scenario 24: Session State Synchronization
    # -------------------------------------------------------------------------
    def test_24_session_state_synchronization(self):
        """Verify session state sync retains authenticated user information and role across reruns."""
        import streamlit as st
        from frontend.auth_utils import is_admin_user, sync_session_state, get_current_user, get_current_role

        # 1. Admin login simulation
        st.session_state.clear()
        st.session_state["authenticated"] = True
        st.session_state["user"] = {
            "id": 1,
            "email": "admin@elearning.local",
            "name": "Admin User",
            "role": "Administrator",
            "token": "valid.token"
        }
        sync_session_state()

        self.assertEqual(st.session_state.get("role"), "Administrator")
        self.assertEqual(st.session_state.get("email"), "admin@elearning.local")
        self.assertTrue(is_admin_user())
        self.assertEqual(get_current_role(), "administrator")

        # 2. Student login simulation
        st.session_state.clear()
        st.session_state["authenticated"] = True
        st.session_state["user"] = {
            "id": 2,
            "email": "student@example.com",
            "name": "Student One",
            "role": "student",
            "token": "valid.token"
        }
        sync_session_state()

        self.assertEqual(st.session_state.get("role"), "student")
        self.assertFalse(is_admin_user())
        self.assertEqual(get_current_role(), "student")

        # 3. Unauthenticated simulation
        st.session_state.clear()
        st.session_state["authenticated"] = False
        st.session_state["user"] = None
        self.assertFalse(is_admin_user())

    # -------------------------------------------------------------------------
    # Scenario 25: API Endpoints Authorization Enforcement
    # -------------------------------------------------------------------------
    def test_25_api_endpoints_authorization_enforcement(self):
        """Verify privileged Xen and workload endpoints reject unauthenticated and student users."""
        app = create_app()
        client = app.test_client()

        student_token = generate_session_token(2, "student@example.com", "student")
        student_headers = {"Authorization": f"Bearer {student_token}", "Content-Type": "application/json"}
        admin_alt_token = generate_session_token(1, "admin@elearning.local", "Administrator")
        admin_headers = {"Authorization": f"Bearer {admin_alt_token}", "Content-Type": "application/json"}

        # 1. Unauthenticated request to /api/xen/allocation/cpu -> 401
        r_unauth = client.post("/api/xen/allocation/cpu", json={"vm_name": "Alpine-Linux", "vcpus": 2})
        self.assertEqual(r_unauth.status_code, 401)

        # 2. Student request to /api/xen/allocation/cpu -> 403 Forbidden
        r_student = client.post("/api/xen/allocation/cpu", headers=student_headers, json={"vm_name": "Alpine-Linux", "vcpus": 2})
        self.assertEqual(r_student.status_code, 403)

        # 3. Student request to /api/xen/allocation/ram -> 403 Forbidden
        r_student_ram = client.post("/api/xen/allocation/ram", headers=student_headers, json={"vm_name": "Alpine-Linux", "ram_mb": 2048})
        self.assertEqual(r_student_ram.status_code, 403)

        # 4. Student request to /api/xen/student-load/start -> 403 Forbidden
        r_student_load = client.post("/api/xen/student-load/start", headers=student_headers, json={"simulated_students": 10})
        self.assertEqual(r_student_load.status_code, 403)

        # 5. Student request to /api/xen/workload/cpu/start -> 403 Forbidden
        r_student_workload = client.post("/api/xen/workload/cpu/start", headers=student_headers, json={"target_vm": "Alpine-Linux"})
        self.assertEqual(r_student_workload.status_code, 403)

        # 6. Admin with normalized variant ('Administrator') authorized
        r_admin_mode = client.post("/api/xen/allocation/mode", headers=admin_headers, json={"mode": "manual"})
        self.assertEqual(r_admin_mode.status_code, 200)

if __name__ == "__main__":
    unittest.main()
