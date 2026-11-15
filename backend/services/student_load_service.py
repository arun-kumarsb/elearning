"""
Student Load Simulator Service
Project: Xen-Based Dynamic Resource Allocation for Scalable E-Learning Services

Generates authentic, real student web traffic against the Flask REST API and MariaDB database
using dedicated synthetic accounts (@elearning.test) with staggered ramp-up (1 to 200 students),
live throughput and latency measurement, and automatic safety interlocks.
"""

import time
import uuid
import random
import logging
import threading
from typing import Dict, Any, List, Optional
from collections import deque
import requests

from backend.config import Config
from backend.database import query_db, execute_db, ensure_simulated_student_pool

logger = logging.getLogger("StudentLoadSimulator")

class StudentLoadSimulatorService:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.current_session: Optional[Dict[str, Any]] = None
        self._stop_event = threading.Event()
        self._worker_threads: List[threading.Thread] = []
        self._orchestrator_thread: Optional[threading.Thread] = None
        self._live_stats_lock = threading.Lock()

        # Pre-seed dedicated simulated student accounts if needed
        ensure_simulated_student_pool(200)

        # Sliding window for RPS and latency calculations
        self._recent_requests: deque = deque(maxlen=500) # (timestamp, latency_ms, is_success, is_db)
        
        # Live counters
        self._active_students: int = 0
        self._students_joining: int = 0
        self._students_leaving: int = 0
        self._total_requests: int = 0
        self._successful_requests: int = 0
        self._failed_requests: int = 0
        self._db_queries_total: int = 0

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def get_status(self) -> Dict[str, Any]:
        """Return the current live status and statistics of the student simulator."""
        with self._live_stats_lock:
            if not self.current_session:
                return {
                    "status": "idle",
                    "session_id": None,
                    "target_vm": "app_vm",
                    "simulated_students": 0,
                    "active_students": 0,
                    "students_joining": 0,
                    "students_leaving": 0,
                    "requests_per_sec": 0.0,
                    "successful_requests": 0,
                    "failed_requests": 0,
                    "total_requests": 0,
                    "avg_response_time_ms": 0.0,
                    "db_queries_per_sec": 0.0,
                    "db_queries_total": 0,
                    "elapsed_duration_sec": 0,
                    "test_duration_sec": 0,
                    "ramp_up_duration_sec": 0,
                    "error_message": None
                }

            now = time.time()
            elapsed = int(now - self.current_session["started_at"]) if self.current_session.get("started_at") else 0
            
            # Calculate rolling RPS and latency in the last 2 seconds
            cutoff = now - 2.0
            recent = [r for r in self._recent_requests if r[0] >= cutoff]
            rps = round(len(recent) / 2.0, 1) if recent else 0.0
            
            db_recent = [r for r in recent if r[3]]
            db_qps = round(len(db_recent) / 2.0, 1) if db_recent else 0.0
            
            avg_lat = round(sum(r[1] for r in recent) / len(recent), 1) if recent else 0.0

            return {
                "status": self.current_session.get("status", "running"),
                "session_id": self.current_session["session_id"],
                "target_vm": self.current_session["target_vm"],
                "simulated_students": self.current_session["simulated_students"],
                "active_students": self._active_students,
                "students_joining": self._students_joining,
                "students_leaving": self._students_leaving,
                "requests_per_sec": rps,
                "successful_requests": self._successful_requests,
                "failed_requests": self._failed_requests,
                "total_requests": self._total_requests,
                "avg_response_time_ms": avg_lat,
                "db_queries_per_sec": db_qps,
                "db_queries_total": self._db_queries_total,
                "elapsed_duration_sec": elapsed,
                "test_duration_sec": self.current_session["test_duration_sec"],
                "ramp_up_duration_sec": self.current_session["ramp_up_duration_sec"],
                "workload_intensity": self.current_session["workload_intensity"],
                "error_message": self.current_session.get("error_message")
            }

    def start_load_test(
        self,
        target_vm: str = "app_vm",
        simulated_students: int = 10,
        ramp_up_duration: int = 10,
        test_duration: int = 60,
        requests_per_student: float = 2.0,
        workload_intensity: str = "medium",
        initiated_by: str = "admin"
    ) -> Dict[str, Any]:
        """
        Start an authentic student traffic load test with gradual ramp-up.
        """
        with self._lock:
            if self.current_session and self.current_session.get("status") in ("ramping_up", "running"):
                return {
                    "success": False,
                    "error": f"A student load test session is already active ({self.current_session['session_id']}). Stop it first.",
                    "session_id": self.current_session["session_id"]
                }

            # Normalize parameters
            valid_students = [1, 5, 10, 25, 50, 100, 150, 200]
            if simulated_students not in valid_students:
                # Find nearest valid
                simulated_students = min(valid_students, key=lambda x: abs(x - simulated_students))

            simulated_students = max(1, min(200, int(simulated_students)))
            ramp_up_duration = max(0, min(120, int(ramp_up_duration)))
            test_duration = max(10, min(600, int(test_duration)))
            requests_per_student = max(0.5, min(10.0, float(requests_per_student)))
            
            clean_target = target_vm.lower().strip()
            if clean_target not in ("app_vm", "db_vm", "both"):
                clean_target = "app_vm"

            session_id = f"load-test-{uuid.uuid4().hex[:12]}"
            self._stop_event.clear()
            self._worker_threads = []
            
            with self._live_stats_lock:
                self._recent_requests.clear()
                self._active_students = 0
                self._students_joining = simulated_students
                self._students_leaving = 0
                self._total_requests = 0
                self._successful_requests = 0
                self._failed_requests = 0
                self._db_queries_total = 0

                self.current_session = {
                    "session_id": session_id,
                    "target_vm": clean_target,
                    "simulated_students": simulated_students,
                    "ramp_up_duration_sec": ramp_up_duration,
                    "test_duration_sec": test_duration,
                    "requests_per_student": requests_per_student,
                    "workload_intensity": workload_intensity,
                    "status": "ramping_up",
                    "started_at": time.time(),
                    "stopped_at": None,
                    "initiated_by": initiated_by,
                    "error_message": None
                }

            # Persist session to database
            try:
                execute_db(
                    """
                    INSERT INTO student_load_test_sessions (
                        session_id, target_vm, simulated_students, ramp_up_sec,
                        test_duration_sec, workload_intensity, requests_per_student,
                        status, initiated_by
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        session_id, clean_target, simulated_students, ramp_up_duration,
                        test_duration, workload_intensity, requests_per_student,
                        "ramping_up", initiated_by
                    )
                )
            except Exception as e:
                logger.warning(f"Could not persist student load test session to DB: {e}")

            # Launch master orchestrator thread
            self._orchestrator_thread = threading.Thread(
                target=self._orchestrate_load_test,
                args=(session_id, clean_target, simulated_students, ramp_up_duration, test_duration, requests_per_student, workload_intensity),
                daemon=True,
                name=f"LoadOrchestrator-{session_id}"
            )
            self._orchestrator_thread.start()

            logger.info(f"Started Student Load Test {session_id}: {simulated_students} students against {clean_target} ({workload_intensity})")
            return {
                "success": True,
                "session_id": session_id,
                "target_vm": clean_target,
                "simulated_students": simulated_students,
                "test_duration_sec": test_duration,
                "status": "ramping_up"
            }

    def stop_load_test(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Gracefully stop active student load test session."""
        with self._lock:
            if not self.current_session or self.current_session.get("status") not in ("ramping_up", "running"):
                return {"success": True, "message": "No active student load test running."}

            if session_id and self.current_session.get("session_id") != session_id:
                return {"success": False, "error": f"Session ID mismatch: {session_id}"}

            self._stop_event.set()
            self.current_session["status"] = "stopping"
            self.current_session["stopped_at"] = time.time()

            logger.info(f"Signaled stop for student load test: {self.current_session['session_id']}")
            return {
                "success": True,
                "session_id": self.current_session["session_id"],
                "status": "stopping"
            }

    def emergency_stop_all(self) -> Dict[str, Any]:
        """
        Master emergency stop: halts all student load generation immediately
        and stops automated scaling decisions.
        """
        self._stop_event.set()
        with self._lock:
            if self.current_session:
                self.current_session["status"] = "emergency_stopped"
                self.current_session["stopped_at"] = time.time()
                sid = self.current_session["session_id"]
            else:
                sid = None

        with self._live_stats_lock:
            self._active_students = 0
            self._students_joining = 0
            self._students_leaving = 0

        # Also trigger allocation engine emergency stop if not already engaged
        try:
            from xen_monitor.resource_monitor import XenResourceMonitor
            mon = XenResourceMonitor.get_instance()
            if hasattr(mon, "allocation_engine") and not mon.allocation_engine.emergency_stop:
                mon.allocation_engine.set_emergency_stop(True)
        except Exception as e:
            logger.debug(f"Could not signal allocation engine emergency stop: {e}")

        logger.warning(f"EMERGENCY STOP executed across all student load simulators. Session: {sid}")
        return {
            "success": True,
            "session_id": sid,
            "status": "emergency_stopped",
            "message": "All student load generators and autonomous scaling halted immediately."
        }

    # --------------------------------------------------------------------------
    # Internal Orchestration & Worker Loop
    # --------------------------------------------------------------------------

    def _orchestrate_load_test(
        self,
        session_id: str,
        target_vm: str,
        simulated_students: int,
        ramp_up_duration: int,
        test_duration: int,
        requests_per_student: float,
        workload_intensity: str
    ):
        """Orchestrates ramp-up, steady state, safety monitoring, and ramp-down."""
        start_time = time.time()
        
        # Calculate spawn delay between students during ramp-up
        if ramp_up_duration > 0 and simulated_students > 1:
            spawn_interval = float(ramp_up_duration) / float(simulated_students)
        else:
            spawn_interval = 0.0

        workers = []
        for i in range(1, simulated_students + 1):
            if self._stop_event.is_set():
                break

            worker = threading.Thread(
                target=self._student_worker_loop,
                args=(i, session_id, target_vm, requests_per_student, workload_intensity),
                daemon=True,
                name=f"SimStudent-{session_id}-{i}"
            )
            workers.append(worker)
            worker.start()

            with self._live_stats_lock:
                self._active_students += 1
                self._students_joining = max(0, simulated_students - self._active_students)

            if spawn_interval > 0:
                time.sleep(spawn_interval)

        with self._lock:
            if self.current_session and not self._stop_event.is_set():
                self.current_session["status"] = "running"
        with self._live_stats_lock:
            self._students_joining = 0

        # Steady state loop with safety checks
        while not self._stop_event.is_set():
            now = time.time()
            elapsed = now - start_time
            if elapsed >= test_duration:
                logger.info(f"Student load test {session_id} completed duration ({test_duration}s).")
                break

            # Safety check: if failure rate > 50% across at least 30 requests, auto-terminate
            with self._live_stats_lock:
                tot = self._total_requests
                fail = self._failed_requests
            if tot >= 30 and (fail / tot) > 0.50:
                logger.warning(f"Safety limit tripped: Error rate exceeded 50% ({fail}/{tot}). Terminating load test.")
                with self._lock:
                    if self.current_session:
                        self.current_session["status"] = "stopped_safety_limit"
                        self.current_session["error_message"] = "Safety threshold tripped: High failure rate > 50%."
                break

            time.sleep(1.0)

        # Ramp-down
        self._stop_event.set()
        with self._live_stats_lock:
            self._students_leaving = self._active_students

        # Wait briefly for workers to finish
        for w in workers:
            w.join(timeout=1.0)

        with self._live_stats_lock:
            self._active_students = 0
            self._students_leaving = 0

        # Update final database record
        final_status = "completed"
        with self._lock:
            if self.current_session:
                if self.current_session.get("status") in ("emergency_stopped", "stopped_safety_limit"):
                    final_status = self.current_session["status"]
                self.current_session["status"] = final_status
                self.current_session["stopped_at"] = time.time()

        try:
            execute_db(
                """
                UPDATE student_load_test_sessions
                SET status = %s, total_requests = %s, successful_requests = %s,
                    failed_requests = %s, db_queries_total = %s, stopped_at = CURRENT_TIMESTAMP
                WHERE session_id = %s
                """,
                (
                    final_status, self._total_requests, self._successful_requests,
                    self._failed_requests, self._db_queries_total, session_id
                )
            )
        except Exception as e:
            logger.debug(f"Could not update final session state in DB: {e}")

        logger.info(f"Finished Student Load Test {session_id} with status '{final_status}'. Total Requests: {self._total_requests}")

    def _student_worker_loop(
        self,
        student_index: int,
        session_id: str,
        target_vm: str,
        requests_per_student: float,
        workload_intensity: str
    ):
        """Simulates one authentic student user making realistic requests."""
        # Dedicated synthetic student account: sim_student_X@elearning.test
        email = f"sim_student_{student_index}@elearning.test"
        password = "SimStudent@123"
        base_url = f"http://127.0.0.1:{Config.FLASK_PORT}/api"
        sleep_interval = 1.0 / max(0.5, requests_per_student)

        session = requests.Session()
        token = None

        # 1. Authentic Login
        t0 = time.time()
        try:
            res = session.post(
                f"{base_url}/login",
                json={"email": email, "password": password},
                timeout=3.0
            )
            lat = (time.time() - t0) * 1000.0
            success = (res.status_code == 200)
            if success:
                token = res.json().get("token")
            self._record_request(lat, success, is_db=False)
        except Exception:
            lat = (time.time() - t0) * 1000.0
            self._record_request(lat, False, is_db=False)

        headers = {"Authorization": f"Bearer {token}"} if token else {}

        # 2. Main simulated student lifecycle loop
        actions = ["dashboard", "courses", "course_details", "profile"]
        if target_vm in ("db_vm", "both") or workload_intensity == "heavy":
            actions.append("db_transaction")

        while not self._stop_event.is_set():
            action = random.choice(actions)
            t_start = time.time()
            is_db = False
            success = False

            try:
                if action == "dashboard":
                    r = session.get(f"{base_url}/dashboard", headers=headers, timeout=4.0)
                    success = (r.status_code == 200)
                    is_db = True # Dashboard executes DB queries

                elif action == "courses":
                    r = session.get(f"{base_url}/courses", headers=headers, timeout=4.0)
                    success = (r.status_code == 200)
                    is_db = True

                elif action == "course_details":
                    r = session.get(f"{base_url}/courses/1", headers=headers, timeout=4.0)
                    success = (r.status_code in (200, 404))

                elif action == "profile":
                    r = session.get(f"{base_url}/auth/me", headers=headers, timeout=4.0)
                    success = (r.status_code == 200)

                elif action == "db_transaction":
                    # Safe transient MariaDB write & query on dedicated table workload_simulation_test
                    is_db = True
                    r = session.post(
                        f"{base_url}/xen/student-load/db-query",
                        headers=headers,
                        json={"session_id": session_id, "student_id": student_index},
                        timeout=5.0
                    )
                    success = (r.status_code == 200)

                lat = (time.time() - t_start) * 1000.0
                self._record_request(lat, success, is_db=is_db)

            except Exception as e:
                lat = (time.time() - t_start) * 1000.0
                self._record_request(lat, False, is_db=is_db)

            # Jittered sleep according to configured requests per student
            jitter = random.uniform(0.85, 1.15)
            time.sleep(sleep_interval * jitter)

    def _record_request(self, latency_ms: float, is_success: bool, is_db: bool):
        """Thread-safe update of live metrics."""
        now = time.time()
        with self._live_stats_lock:
            self._total_requests += 1
            if is_success:
                self._successful_requests += 1
            else:
                self._failed_requests += 1

            if is_db:
                self._db_queries_total += 1

            self._recent_requests.append((now, latency_ms, is_success, is_db))
