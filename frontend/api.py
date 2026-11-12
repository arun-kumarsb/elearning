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

def get_headers() -> Dict[str, str]:
    """Return common request headers including session token if present."""
    headers = {"Content-Type": "application/json"}
    user = st.session_state.get("user")
    if user and "token" in user:
        headers["Authorization"] = f"Bearer {user['token']}"
    return headers

def safe_request(method: str, endpoint: str, data: Optional[Dict] = None, timeout: int = 5) -> Dict[str, Any]:
    """Execute HTTP request with standardized error handling."""
    url = f"{API_BASE_URL}/{endpoint.lstrip('/')}"
    try:
        if method.upper() == "GET":
            response = requests.get(url, headers=get_headers(), timeout=timeout)
        elif method.upper() == "POST":
            response = requests.post(url, json=data or {}, headers=get_headers(), timeout=timeout)
        elif method.upper() == "PUT":
            response = requests.put(url, json=data or {}, headers=get_headers(), timeout=timeout)
        elif method.upper() == "DELETE":
            response = requests.delete(url, headers=get_headers(), timeout=timeout)
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

def api_get_health() -> Dict[str, Any]:
    return safe_request("GET", "health")
