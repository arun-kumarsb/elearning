"""
Frontend REST API Client for Xen E-Learning Platform
Communicates exclusively with the Flask REST API on Alpine-Linux-New (port 5000).
Streamlit never connects directly to MariaDB.
"""

import os
import requests
import streamlit as st
from typing import Dict, Any, Optional

# Read backend URL from environment or default to local/VM address
# Default on VM 2: http://127.0.0.1:5000/api or http://10.240.109.201:5000/api
API_BASE_URL = os.getenv("BACKEND_API_URL", "http://127.0.0.1:5000/api").rstrip("/")
LOCAL_FALLBACK_URL = "http://127.0.0.1:5000/api"

# Configure HTTP session that bypasses proxy interference on local dev machines
http_session = requests.Session()
http_session.trust_env = False

def get_headers() -> Dict[str, str]:
    """Return common request headers including session token if present."""
    headers = {"Content-Type": "application/json"}
    user = st.session_state.get("user")
    if user and "token" in user:
        headers["Authorization"] = f"Bearer {user['token']}"
    return headers

def safe_request(method: str, endpoint: str, data: Optional[Dict] = None, timeout: int = 5) -> Dict[str, Any]:
    """Execute HTTP request with standardized error handling and local fallback."""
    global API_BASE_URL
    url = f"{API_BASE_URL}/{endpoint.lstrip('/')}"
    try:
        if method.upper() == "GET":
            response = http_session.get(url, headers=get_headers(), timeout=timeout)
        elif method.upper() == "POST":
            response = http_session.post(url, json=data or {}, headers=get_headers(), timeout=timeout)
        elif method.upper() == "PUT":
            response = http_session.put(url, json=data or {}, headers=get_headers(), timeout=timeout)
        elif method.upper() == "DELETE":
            response = http_session.delete(url, headers=get_headers(), timeout=timeout)
        else:
            return {"success": False, "error": f"Unsupported HTTP method: {method}"}

        try:
            res_json = response.json()
        except Exception:
            res_json = {"success": response.ok, "raw_response": response.text}

        if not response.ok:
            error_msg = res_json.get("error") or res_json.get("message") or f"HTTP {response.status_code}"
            return {"success": False, "error": error_msg, "status_code": response.status_code}

        return res_json
    except requests.exceptions.ConnectionError:
        # If API_BASE_URL failed and was pointing to the remote VM, auto-fallback to localhost
        if API_BASE_URL != LOCAL_FALLBACK_URL:
            try:
                fallback_url = f"{LOCAL_FALLBACK_URL}/{endpoint.lstrip('/')}"
                if method.upper() == "GET":
                    response = http_session.get(fallback_url, headers=get_headers(), timeout=timeout)
                elif method.upper() == "POST":
                    response = http_session.post(fallback_url, json=data or {}, headers=get_headers(), timeout=timeout)
                elif method.upper() == "PUT":
                    response = http_session.put(fallback_url, json=data or {}, headers=get_headers(), timeout=timeout)
                elif method.upper() == "DELETE":
                    response = http_session.delete(fallback_url, headers=get_headers(), timeout=timeout)
                else:
                    return {"success": False, "error": f"Unsupported HTTP method: {method}"}

                API_BASE_URL = LOCAL_FALLBACK_URL
                return response.json()
            except Exception:
                pass

        return {
            "success": False, 
            "error": f"Cannot connect to Flask Backend API at {API_BASE_URL}. "
                     f"Please ensure Flask is running (python backend/app.py)."
        }
    except requests.exceptions.Timeout:
        return {"success": False, "error": f"Request to Flask Backend API timed out ({timeout}s)."}
    except Exception as e:
        return {"success": False, "error": str(e)}

# Authentication
def api_login(email: str, password: str) -> Dict[str, Any]:
    return safe_request("POST", "login", {"email": email, "password": password})

def api_logout() -> Dict[str, Any]:
    return safe_request("POST", "logout")

# Dashboard
def api_get_dashboard() -> Dict[str, Any]:
    return safe_request("GET", "dashboard")

# Students
def api_get_students() -> Dict[str, Any]:
    return safe_request("GET", "students")

def api_get_student(student_id: int) -> Dict[str, Any]:
    return safe_request("GET", f"students/{student_id}")

def api_create_student(name: str, email: str, password: Optional[str] = None) -> Dict[str, Any]:
    payload = {"name": name, "email": email}
    if password:
        payload["password"] = password
    return safe_request("POST", "students", payload)

def api_delete_student(student_id: int) -> Dict[str, Any]:
    return safe_request("DELETE", f"students/{student_id}")

# Courses
def api_get_courses() -> Dict[str, Any]:
    return safe_request("GET", "courses")

def api_get_course(course_id: int) -> Dict[str, Any]:
    return safe_request("GET", f"courses/{course_id}")

def api_create_course(course_code: str, title: str, description: str) -> Dict[str, Any]:
    return safe_request("POST", "courses", {
        "course_code": course_code,
        "title": title,
        "description": description
    })

def api_update_course(course_id: int, course_code: str, title: str, description: str) -> Dict[str, Any]:
    return safe_request("PUT", f"courses/{course_id}", {
        "course_code": course_code,
        "title": title,
        "description": description
    })

def api_delete_course(course_id: int) -> Dict[str, Any]:
    return safe_request("DELETE", f"courses/{course_id}")

# Enrollments
def api_get_enrollments() -> Dict[str, Any]:
    return safe_request("GET", "enrollments")

def api_get_student_enrollments(student_id: int) -> Dict[str, Any]:
    return safe_request("GET", f"students/{student_id}/enrollments")

def api_enroll_student(student_id: int, course_id: int) -> Dict[str, Any]:
    return safe_request("POST", "enrollments", {
        "student_id": student_id,
        "course_id": course_id
    })

def api_delete_enrollment(enrollment_id: int) -> Dict[str, Any]:
    return safe_request("DELETE", f"enrollments/{enrollment_id}")

# Xen & Infrastructure Status
def api_get_xen_status() -> Dict[str, Any]:
    return safe_request("GET", "xen/status")

def api_get_xen_metrics() -> Dict[str, Any]:
    return safe_request("GET", "xen/metrics")

def api_get_xen_host() -> Dict[str, Any]:
    return safe_request("GET", "xen/host")

def api_get_xen_vms() -> Dict[str, Any]:
    return safe_request("GET", "xen/vms")

def api_get_xen_vm_metrics(vm_id: str) -> Dict[str, Any]:
    return safe_request("GET", f"xen/vms/{vm_id}/metrics")

def api_get_xen_monitor_status() -> Dict[str, Any]:
    return safe_request("GET", "xen/monitor/status")

def api_get_metrics_history(vm_name: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
    """
    Retrieve historical VM telemetry records from Flask backend.
    Calls GET /api/xen/history?limit=... (or /api/xen/metrics/history).
    Returns a standardized dictionary with {"success": True/False, "count": int, "data": List[Dict]}.
    Never fabricates telemetry; returns empty history data if no records exist.
    """
    endpoint = f"xen/history?limit={limit}"
    if vm_name:
        endpoint += f"&vm_name={vm_name}"
    res = safe_request("GET", endpoint)
    if not isinstance(res, dict):
        return {"success": False, "count": 0, "data": [], "error": "Invalid response format from API"}
    if "data" not in res:
        res["data"] = []
    if "count" not in res:
        res["count"] = len(res["data"])
    return res

api_get_xen_history = api_get_metrics_history  # Alias for backward compatibility

def api_get_health() -> Dict[str, Any]:
    return safe_request("GET", "health")

# Phase 3: Dynamic Resource Allocation API Methods
def api_get_allocation_status() -> Dict[str, Any]:
    return safe_request("GET", "xen/allocation/status")

def api_get_allocation_recommendations() -> Dict[str, Any]:
    return safe_request("GET", "xen/allocation/recommendations")

def api_get_allocation_history(vm_name: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
    endpoint = f"xen/allocation/history?limit={limit}"
    if vm_name:
        endpoint += f"&vm_name={vm_name}"
    return safe_request("GET", endpoint)

def api_enable_allocation() -> Dict[str, Any]:
    return safe_request("POST", "xen/allocation/enable")

def api_disable_allocation() -> Dict[str, Any]:
    return safe_request("POST", "xen/allocation/disable")

def api_set_allocation_mode(mode: str) -> Dict[str, Any]:
    """
    Set dynamic allocation engine mode: 'auto' or 'manual'.
    Calls POST /api/xen/allocation/mode with fallback to enable/disable.
    """
    clean_mode = str(mode).strip().lower()
    res = safe_request("POST", "xen/allocation/mode", {"mode": clean_mode})
    if not res.get("success") and res.get("status_code") == 404:
        if clean_mode == "auto":
            return api_enable_allocation()
        else:
            return api_disable_allocation()
    return res

def api_emergency_stop(action: str = "engage") -> Dict[str, Any]:
    return safe_request("POST", "xen/allocation/emergency-stop", {"action": action})

def api_reset_emergency_stop(reason: str = "Admin inspected system nominal", confirmed: bool = True) -> Dict[str, Any]:
    return safe_request("POST", "xen/allocation/emergency-stop/reset", {
        "confirmed": confirmed,
        "reason": reason
    })

def api_reboot_vm(vm_name: str, reason: str = "Apply baseline configuration", confirmed: bool = True) -> Dict[str, Any]:
    return safe_request("POST", "xen/vm/reboot", {
        "vm_name": vm_name,
        "confirmed": confirmed,
        "reason": reason
    })

def api_apply_manual_cpu(vm_name: str, vcpus: int, reason: str = "Administrator manual adjustment") -> Dict[str, Any]:
    return safe_request("POST", "xen/allocation/cpu", {
        "vm_name": vm_name,
        "vcpus": vcpus,
        "reason": reason
    })

def api_apply_manual_ram(vm_name: str, ram_mb: float, reason: str = "Administrator manual adjustment") -> Dict[str, Any]:
    return safe_request("POST", "xen/allocation/ram", {
        "vm_name": vm_name,
        "ram_mb": ram_mb,
        "reason": reason
    })

def api_apply_recommendation(vm_name: str) -> Dict[str, Any]:
    """Apply pending scaling recommendation for a specific VM."""
    return safe_request("POST", "xen/allocation/apply-recommended", {"vm_name": vm_name})

api_apply_recommended = api_apply_recommendation  # Alias for backward compatibility

def api_transition_to_baseline(vm_name: str) -> Dict[str, Any]:
    return safe_request("POST", "xen/allocation/transition-baseline", {"vm_name": vm_name})

# -------------------------------------------------------------
# Workload Simulator API Endpoints
# -------------------------------------------------------------
def api_get_workload_status() -> Dict[str, Any]:
    return safe_request("GET", "xen/workload/status")

def api_start_cpu_workload(target_vm: str = "Alpine-Linux", intensity_percent: float = 75.0,
                           workers: int = 2, duration_sec: int = 60) -> Dict[str, Any]:
    return safe_request("POST", "xen/workload/cpu/start", {
        "target_vm": target_vm,
        "intensity_percent": intensity_percent,
        "workers": workers,
        "duration_sec": duration_sec
    })

def api_stop_cpu_workload(session_id: Optional[str] = None) -> Dict[str, Any]:
    payload = {"session_id": session_id} if session_id else {}
    return safe_request("POST", "xen/workload/cpu/stop", payload)

def api_start_ram_workload(target_vm: str = "Alpine-Linux", allocated_mb: float = 256.0,
                           duration_sec: int = 60) -> Dict[str, Any]:
    return safe_request("POST", "xen/workload/ram/start", {
        "target_vm": target_vm,
        "allocated_mb": allocated_mb,
        "duration_sec": duration_sec
    })

def api_stop_ram_workload(session_id: Optional[str] = None) -> Dict[str, Any]:
    payload = {"session_id": session_id} if session_id else {}
    return safe_request("POST", "xen/workload/ram/stop", payload)

def api_start_db_workload(target_vm: str = "Alpine-DB", intensity: str = "medium",
                          workers: int = 2, duration_sec: int = 60) -> Dict[str, Any]:
    return safe_request("POST", "xen/workload/db/start", {
        "target_vm": target_vm,
        "intensity": intensity,
        "workers": workers,
        "duration_sec": duration_sec
    })

def api_stop_db_workload(session_id: Optional[str] = None) -> Dict[str, Any]:
    payload = {"session_id": session_id} if session_id else {}
    return safe_request("POST", "xen/workload/db/stop", payload)

def api_workload_emergency_stop() -> Dict[str, Any]:
    return safe_request("POST", "xen/workload/emergency-stop")

# -------------------------------------------------------------
# Student Load Simulator API Endpoints
# -------------------------------------------------------------
def api_get_student_load_status() -> Dict[str, Any]:
    return safe_request("GET", "xen/student-load/status")

def api_start_student_load(
    target_vm: str = "app_vm",
    simulated_students: int = 10,
    ramp_up_duration: int = 10,
    test_duration: int = 60,
    requests_per_student: float = 2.0,
    workload_intensity: str = "medium"
) -> Dict[str, Any]:
    return safe_request("POST", "xen/student-load/start", {
        "target_vm": target_vm,
        "simulated_students": simulated_students,
        "ramp_up_duration": ramp_up_duration,
        "test_duration": test_duration,
        "requests_per_student": requests_per_student,
        "workload_intensity": workload_intensity
    })

def api_stop_student_load(session_id: Optional[str] = None) -> Dict[str, Any]:
    payload = {"session_id": session_id} if session_id else {}
    return safe_request("POST", "xen/student-load/stop", payload)

def api_emergency_stop_student_load() -> Dict[str, Any]:
    return safe_request("POST", "xen/student-load/emergency-stop")

def api_student_load_preflight() -> Dict[str, Any]:
    """Run preflight authentication check for synthetic student accounts."""
    return safe_request("POST", "xen/student-load/preflight")

def api_execute_baseline_maintenance(vm_name: str) -> Dict[str, Any]:
    """Execute administrator-approved controlled baseline maintenance procedure."""
    return safe_request("POST", "xen/vm/baseline-maintenance", {"vm_name": vm_name})




