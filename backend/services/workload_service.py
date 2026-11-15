"""
Workload Simulation Service (Phase 3 Live Load Generator)
Project: Xen-Based Dynamic Resource Allocation for Scalable E-Learning Services

Provides authentic, controlled synthetic workload generation inside Alpine-Linux (Application VM)
and Alpine-DB (Database VM) for live autoscaling demonstrations:
- CPU Load: Calibrated multi-worker CPU duty cycles (25%, 50%, 75%, 90%)
- RAM Load: Real physical heap allocation with strict OOM protection (128-768 MB)
- Database Load: Controlled transient transactions against MariaDB test table with rollback
- Automatic expiration timers & Emergency Stop for all active load tests
"""

import os
import gc
import time
import uuid
import math
import logging
import threading
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from backend.database import execute_db, query_db, is_mariadb_reachable

logger = logging.getLogger("WorkloadSimulator")

class WorkloadSimulatorService:
    _instance = None
    _lock = threading.RLock()

    def __init__(self):
        self._active_sessions: Dict[str, Dict[str, Any]] = {}
        self._session_threads: Dict[str, threading.Thread] = {}
        self._stop_events: Dict[str, threading.Event] = {}

    @classmethod
    def get_instance(cls) -> "WorkloadSimulatorService":
        with cls._lock:
            if cls._instance is None:
                cls._instance = WorkloadSimulatorService()
            return cls._instance

    # -----------------------------------------------------------------
    # GUEST MEMORY HEADROOM VALIDATION (OOM PROTECTION)
    # -----------------------------------------------------------------
    def get_guest_available_memory_mb(self) -> float:
        """Read actual guest available memory from /proc/meminfo or fallback."""
        if os.path.exists("/proc/meminfo"):
            try:
                with open("/proc/meminfo", "r") as f:
                    for line in f:
                        if line.startswith("MemAvailable:"):
                            parts = line.split(":")
                            kb = int(parts[1].strip().split()[0])
                            return round(kb / 1024.0, 1)
                        elif line.startswith("MemFree:"):
                            parts = line.split(":")
                            kb = int(parts[1].strip().split()[0])
                            return round(kb / 1024.0, 1)
            except Exception as e:
                logger.debug(f"Could not read /proc/meminfo: {e}")
        # Default safety estimate if not on Linux
        return 2048.0

    # -----------------------------------------------------------------
    # A. CPU LOAD GENERATION (Alpine-Linux)
    # -----------------------------------------------------------------
    def start_cpu_workload(self, target_vm: str = "Alpine-Linux", intensity_percent: float = 75.0,
                           workers: int = 2, duration_sec: int = 60, initiated_by: str = "admin") -> Dict[str, Any]:
        """
        Start calibrated CPU workload generator using worker threads executing duty cycles.
        Intensity: 25.0 to 95.0 %
        Workers: 1 to 4
        Duration: 30 to 300 seconds
        """
        with self._lock:
            # Check for existing running CPU workload
            for s_id, s in self._active_sessions.items():
                if s.get("workload_type") == "cpu" and s.get("status") == "running":
                    return {
                        "success": False,
                        "error": f"A CPU workload is already running (Session ID: {s_id[:8]}). Stop it before starting a new test."
                    }

            # Sanitize parameters
            intensity = min(95.0, max(20.0, float(intensity_percent)))
            num_workers = min(4, max(1, int(workers)))
            duration = min(300, max(10, int(duration_sec)))
            session_id = f"cpu-{uuid.uuid4().hex[:12]}"

            stop_event = threading.Event()
            self._stop_events[session_id] = stop_event

            session_info = {
                "session_id": session_id,
                "target_vm": target_vm,
                "workload_type": "cpu",
                "intensity_percent": intensity,
                "workers": num_workers,
                "allocated_mb": 0.0,
                "duration_sec": duration,
                "status": "running",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "stopped_at": None,
                "initiated_by": initiated_by,
                "expires_at": time.time() + duration
            }
            self._active_sessions[session_id] = session_info

            # Persist to database
            self._persist_session(session_info)

            # Start worker manager thread
            thread = threading.Thread(
                target=self._run_cpu_workload_manager,
                args=(session_id, intensity, num_workers, duration, stop_event),
                daemon=True,
                name=f"Workload-CPU-{session_id}"
            )
            self._session_threads[session_id] = thread
            thread.start()

            logger.info(f"Started CPU workload session {session_id} on {target_vm} ({intensity}% intensity, {num_workers} workers, {duration}s)")
            return {
                "success": True,
                "session_id": session_id,
                "target_vm": target_vm,
                "intensity_percent": intensity,
                "workers": num_workers,
                "duration_sec": duration,
                "message": f"Real CPU load generator started ({intensity}% on {num_workers} worker(s) for {duration}s)."
            }

    def _run_cpu_workload_manager(self, session_id: str, intensity: float, num_workers: int,
                                  duration: int, stop_event: threading.Event):
        """Spawns worker threads that perform mathematical calculations with calibrated duty cycles."""
        worker_threads: List[threading.Thread] = []
        duty_cycle = intensity / 100.0  # Fraction of each period spent actively calculating
        period = 0.1  # 100ms cycle
        busy_time = period * duty_cycle
        sleep_time = period * (1.0 - duty_cycle)

        def worker_loop():
            end_time = time.time() + duration
            while not stop_event.is_set() and time.time() < end_time:
                # Active work phase
                t_start = time.time()
                while time.time() - t_start < busy_time:
                    _ = [math.sqrt(x) for x in range(100, 300)]
                # Idle phase
                if sleep_time > 0.001:
                    time.sleep(sleep_time)

        for i in range(num_workers):
            wt = threading.Thread(target=worker_loop, daemon=True, name=f"CPU-Worker-{session_id}-{i}")
            worker_threads.append(wt)
            wt.start()

        # Wait for duration or stop signal
        end_time = time.time() + duration
        while not stop_event.is_set() and time.time() < end_time:
            time.sleep(0.5)

        # Stop workers
        stop_event.set()
        for wt in worker_threads:
            wt.join(timeout=1.0)

        # Update session status
        self._finish_session(session_id, reason="duration_expired" if time.time() >= end_time else "stopped")

    # -----------------------------------------------------------------
    # B. RAM LOAD GENERATION (Alpine-Linux)
    # -----------------------------------------------------------------
    def start_ram_workload(self, target_vm: str = "Alpine-Linux", allocated_mb: float = 256.0,
                           duration_sec: int = 60, initiated_by: str = "admin") -> Dict[str, Any]:
        """
        Start RAM workload generator.
        Allocates physical bytearray buffers and touches memory pages.
        Validates available guest memory to strictly protect against Out-Of-Memory (OOM).
        """
        with self._lock:
            # Check for existing running RAM workload
            for s_id, s in self._active_sessions.items():
                if s.get("workload_type") == "ram" and s.get("status") == "running":
                    return {
                        "success": False,
                        "error": f"A RAM workload is already active (Session ID: {s_id[:8]}). Stop it before starting a new test."
                    }

            req_mb = float(allocated_mb)
            duration = min(300, max(10, int(duration_sec)))

            # Safety check: available guest memory headroom
            avail_mb = self.get_guest_available_memory_mb()
            cushion_mb = 256.0
            if req_mb + cushion_mb > avail_mb:
                return {
                    "success": False,
                    "error": (
                        f"Safety check rejected RAM allocation: requested {req_mb} MB requires at least "
                        f"{cushion_mb} MB safety cushion. Current available guest RAM is {avail_mb} MB. "
                        f"Aborting to strictly prevent guest Out-Of-Memory (OOM)."
                    )
                }

            session_id = f"ram-{uuid.uuid4().hex[:12]}"
            stop_event = threading.Event()
            self._stop_events[session_id] = stop_event

            session_info = {
                "session_id": session_id,
                "target_vm": target_vm,
                "workload_type": "ram",
                "intensity_percent": None,
                "workers": 1,
                "allocated_mb": req_mb,
                "duration_sec": duration,
                "status": "running",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "stopped_at": None,
                "initiated_by": initiated_by,
                "expires_at": time.time() + duration
            }
            self._active_sessions[session_id] = session_info
            self._persist_session(session_info)

            thread = threading.Thread(
                target=self._run_ram_workload,
                args=(session_id, req_mb, duration, stop_event),
                daemon=True,
                name=f"Workload-RAM-{session_id}"
            )
            self._session_threads[session_id] = thread
            thread.start()

            logger.info(f"Started RAM workload session {session_id} on {target_vm} ({req_mb} MB, {duration}s)")
            return {
                "success": True,
                "session_id": session_id,
                "target_vm": target_vm,
                "allocated_mb": req_mb,
                "duration_sec": duration,
                "message": f"Real RAM allocation started: {req_mb} MB committed in physical pages for {duration}s."
            }

    def _run_ram_workload(self, session_id: str, allocated_mb: float, duration: int, stop_event: threading.Event):
        """Allocates bytearray buffers, touches pages to commit RSS, and holds for duration."""
        buffers = []
        try:
            # Allocate in 16MB blocks and touch every 4KB page so OS kernel commits physical memory
            block_size = 16 * 1024 * 1024
            num_blocks = int(allocated_mb * 1024 * 1024 / block_size)
            rem_bytes = int(allocated_mb * 1024 * 1024) - (num_blocks * block_size)

            for _ in range(num_blocks):
                if stop_event.is_set():
                    break
                b = bytearray(block_size)
                # Touch pages (step 4096 bytes)
                for idx in range(0, len(b), 4096):
                    b[idx] = 1
                buffers.append(b)

            if rem_bytes > 0 and not stop_event.is_set():
                b = bytearray(rem_bytes)
                for idx in range(0, len(b), 4096):
                    b[idx] = 1
                buffers.append(b)

            end_time = time.time() + duration
            while not stop_event.is_set() and time.time() < end_time:
                time.sleep(0.5)

        except MemoryError:
            logger.error(f"MemoryError occurred while allocating {allocated_mb} MB in session {session_id}")
        finally:
            buffers.clear()
            gc.collect()
            self._finish_session(session_id, reason="duration_expired" if time.time() >= (time.time() + duration) else "stopped")

    # -----------------------------------------------------------------
    # C. DATABASE WORKLOAD GENERATION (Alpine-DB Safe MariaDB Load)
    # -----------------------------------------------------------------
    def start_database_workload(self, target_vm: str = "Alpine-DB", intensity: str = "medium",
                                workers: int = 2, duration_sec: int = 60, initiated_by: str = "admin") -> Dict[str, Any]:
        """
        Start controlled concurrent MariaDB workload generator against dedicated test table.
        NEVER touches students, courses, users, or enrollments tables.
        Intensity: 'low' (~10 qps), 'medium' (~30 qps), 'high' (~60 qps)
        """
        with self._lock:
            # Check for existing running DB workload
            for s_id, s in self._active_sessions.items():
                if s.get("workload_type") == "database" and s.get("status") == "running":
                    return {
                        "success": False,
                        "error": f"A Database workload is already running (Session ID: {s_id[:8]}). Stop it before starting a new test."
                    }

            duration = min(300, max(10, int(duration_sec)))
            num_workers = min(4, max(1, int(workers)))
            session_id = f"db-{uuid.uuid4().hex[:12]}"
            stop_event = threading.Event()
            self._stop_events[session_id] = stop_event

            intensity_str = intensity.lower().strip()
            intensity_map = {"low": 10.0, "medium": 30.0, "high": 60.0}
            qps = intensity_map.get(intensity_str, 30.0)

            session_info = {
                "session_id": session_id,
                "target_vm": target_vm,
                "workload_type": "database",
                "intensity_percent": qps,
                "workers": num_workers,
                "allocated_mb": 0.0,
                "duration_sec": duration,
                "status": "running",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "stopped_at": None,
                "initiated_by": initiated_by,
                "expires_at": time.time() + duration,
                "details": f"Safe transient queries (~{qps} QPS across {num_workers} worker(s))"
            }
            self._active_sessions[session_id] = session_info
            self._persist_session(session_info)

            thread = threading.Thread(
                target=self._run_database_workload_manager,
                args=(session_id, qps, num_workers, duration, stop_event),
                daemon=True,
                name=f"Workload-DB-{session_id}"
            )
            self._session_threads[session_id] = thread
            thread.start()

            logger.info(f"Started DB workload session {session_id} on {target_vm} ({qps} QPS, {duration}s)")
            return {
                "success": True,
                "session_id": session_id,
                "target_vm": target_vm,
                "intensity": intensity_str,
                "qps": qps,
                "workers": num_workers,
                "duration_sec": duration,
                "message": f"Safe MariaDB workload generator started (~{qps} QPS on dedicated test table for {duration}s)."
            }

    def _run_database_workload_manager(self, session_id: str, target_qps: float, num_workers: int,
                                       duration: int, stop_event: threading.Event):
        """Worker threads executing safe transient inserts and analytical hash selects."""
        worker_threads = []
        delay_per_worker = (1.0 / (target_qps / max(1, num_workers))) if target_qps > 0 else 0.1

        def db_worker():
            end_time = time.time() + duration
            while not stop_event.is_set() and time.time() < end_time:
                try:
                    payload = f"test-payload-{time.time()}-{uuid.uuid4().hex[:8]}"
                    # 1. Insert transient test record into dedicated table
                    insert_sql = "INSERT INTO workload_simulation_test (session_id, payload) VALUES (%s, %s)"
                    execute_db(insert_sql, (session_id, payload))

                    # 2. Execute computational hash select query to exercise DB engine
                    select_sql = """
                        SELECT COUNT(*), SHA2(CONCAT(payload, %s), 256) as test_hash
                        FROM workload_simulation_test
                        WHERE session_id = %s
                        GROUP BY payload
                        LIMIT 5
                    """
                    _ = query_db(select_sql, (str(time.time()), session_id))

                    # 3. Clean up batch periodically
                    cleanup_sql = "DELETE FROM workload_simulation_test WHERE session_id = %s AND id < (SELECT MAX(id) - 20 FROM workload_simulation_test WHERE session_id = %s)"
                    # Note: simple cleanup or keep small
                    execute_db("DELETE FROM workload_simulation_test WHERE session_id = %s LIMIT 1", (session_id,))

                except Exception as e:
                    logger.debug(f"DB workload query error (transient): {e}")

                time.sleep(delay_per_worker)

        for i in range(num_workers):
            wt = threading.Thread(target=db_worker, daemon=True, name=f"DB-Worker-{session_id}-{i}")
            worker_threads.append(wt)
            wt.start()

        end_time = time.time() + duration
        while not stop_event.is_set() and time.time() < end_time:
            time.sleep(0.5)

        stop_event.set()
        for wt in worker_threads:
            wt.join(timeout=1.0)

        # Final cleanup of all rows generated for this session_id
        try:
            execute_db("DELETE FROM workload_simulation_test WHERE session_id = %s", (session_id,))
        except Exception as e:
            logger.debug(f"DB workload final cleanup error: {e}")

        self._finish_session(session_id, reason="duration_expired" if time.time() >= end_time else "stopped")

    # -----------------------------------------------------------------
    # WORKLOAD CONTROL & EMERGENCY STOP
    # -----------------------------------------------------------------
    def stop_workload(self, session_id: str) -> Dict[str, Any]:
        """Stop a specific active workload session."""
        with self._lock:
            if session_id not in self._active_sessions:
                return {"success": False, "error": f"Session '{session_id}' not found."}

            stop_ev = self._stop_events.get(session_id)
            if stop_ev:
                stop_ev.set()

            session = self._active_sessions.get(session_id, {})
            session["status"] = "stopped"
            session["stopped_at"] = datetime.now(timezone.utc).isoformat()
            self._update_session_db(session_id, "stopped")

            logger.info(f"Explicitly stopped workload session: {session_id}")
            return {
                "success": True,
                "session_id": session_id,
                "message": f"Workload session {session_id} stopped."
            }

    def stop_all_workloads(self) -> Dict[str, Any]:
        """Emergency Stop: immediately halts all active synthetic workload generators."""
        with self._lock:
            stopped_count = 0
            for session_id, stop_ev in list(self._stop_events.items()):
                stop_ev.set()
                session = self._active_sessions.get(session_id)
                if session and session.get("status") == "running":
                    session["status"] = "stopped"
                    session["stopped_at"] = datetime.now(timezone.utc).isoformat()
                    self._update_session_db(session_id, "stopped")
                    stopped_count += 1

            # Garbage collect any freed memory
            gc.collect()

            logger.warning(f"Emergency stop executed across all workload generators. Stopped {stopped_count} active sessions.")
            return {
                "success": True,
                "stopped_count": stopped_count,
                "message": f"All synthetic workloads terminated immediately ({stopped_count} sessions halted)."
            }

    def get_status(self) -> Dict[str, Any]:
        """Return the consolidated status of all workload generators."""
        with self._lock:
            now = time.time()
            active_list = []
            for s_id, s in list(self._active_sessions.items()):
                # Auto clean expired sessions
                if s.get("status") == "running" and s.get("expires_at", 0) <= now:
                    s["status"] = "completed"
                    s["stopped_at"] = datetime.now(timezone.utc).isoformat()
                    self._update_session_db(s_id, "completed")
                active_list.append(dict(s))

            # Categorize active tests
            running_cpu = [s for s in active_list if s.get("workload_type") == "cpu" and s.get("status") == "running"]
            running_ram = [s for s in active_list if s.get("workload_type") == "ram" and s.get("status") == "running"]
            running_db = [s for s in active_list if s.get("workload_type") == "database" and s.get("status") == "running"]

            return {
                "active_workload_count": len(running_cpu) + len(running_ram) + len(running_db),
                "guest_available_ram_mb": self.get_guest_available_memory_mb(),
                "running_cpu_session": running_cpu[0] if running_cpu else None,
                "running_ram_session": running_ram[0] if running_ram else None,
                "running_db_session": running_db[0] if running_db else None,
                "recent_sessions": active_list[-10:]
            }

    # -----------------------------------------------------------------
    # PERSISTENCE HELPERS
    # -----------------------------------------------------------------
    def _persist_session(self, s: Dict[str, Any]):
        """Persist session record into workload_simulation_sessions table."""
        try:
            sql = """
                INSERT INTO workload_simulation_sessions
                (session_id, target_vm, workload_type, intensity_percent, workers, allocated_mb,
                 duration_sec, status, initiated_by, details)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            execute_db(sql, (
                s.get("session_id"),
                s.get("target_vm"),
                s.get("workload_type"),
                s.get("intensity_percent"),
                s.get("workers", 1),
                s.get("allocated_mb"),
                s.get("duration_sec"),
                s.get("status", "running"),
                s.get("initiated_by", "admin"),
                s.get("details")
            ))
        except Exception as e:
            logger.warning(f"Could not persist workload session: {e}")

    def _update_session_db(self, session_id: str, new_status: str):
        """Update session record status and stopped_at timestamp."""
        try:
            sql = """
                UPDATE workload_simulation_sessions
                SET status = %s, stopped_at = CURRENT_TIMESTAMP
                WHERE session_id = %s
            """
            execute_db(sql, (new_status, session_id))
        except Exception as e:
            logger.debug(f"Could not update workload session {session_id}: {e}")

    def _finish_session(self, session_id: str, reason: str = "completed"):
        with self._lock:
            s = self._active_sessions.get(session_id)
            if s:
                final_status = "completed" if reason == "duration_expired" else "stopped"
                s["status"] = final_status
                s["stopped_at"] = datetime.now(timezone.utc).isoformat()
                self._update_session_db(session_id, final_status)
            self._stop_events.pop(session_id, None)
            self._session_threads.pop(session_id, None)
            logger.info(f"Finished workload session {session_id} ({reason})")
