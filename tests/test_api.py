import unittest
import json
from unittest.mock import patch
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.app import create_app
from backend.services.auth_service import hash_password

class TestElearningAPI(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    @patch("backend.routes.health.test_connection")
    def test_health_endpoint(self, mock_test_conn):
        mock_test_conn.return_value = {
            "connected": True,
            "host": "10.240.109.248",
            "port": 3306,
            "database": "elearning",
            "version": "11.8.9-MariaDB",
            "tables": ["students", "courses", "users", "enrollments"]
        }
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["app_vm"], "10.240.109.51")

    @patch("backend.services.auth_service.query_db")
    def test_login_admin_success(self, mock_query):
        hashed = hash_password("Admin@123")
        mock_query.return_value = {
            "id": 1,
            "email": "admin@elearning.local",
            "password_hash": hashed,
            "role": "admin",
            "student_id": None,
            "student_name": None
        }
        res = self.client.post("/api/login", json={
            "email": "admin@elearning.local",
            "password": "Admin@123"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["user"]["role"], "admin")
        self.assertIn("token", data["user"])

    @patch("backend.services.auth_service.query_db")
    def test_login_invalid_password(self, mock_query):
        hashed = hash_password("CorrectPass123")
        mock_query.return_value = {
            "id": 1,
            "email": "admin@elearning.local",
            "password_hash": hashed,
            "role": "admin",
            "student_id": None,
            "student_name": None
        }
        res = self.client.post("/api/login", json={
            "email": "admin@elearning.local",
            "password": "WrongPassword"
        })
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertFalse(data["success"])

    def test_logout(self):
        res = self.client.post("/api/logout")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])

    @patch("backend.services.dashboard_service.query_db")
    def test_dashboard_endpoint(self, mock_query):
        def side_effect(query, args=(), one=False):
            if "COUNT(*) AS total FROM students" in query:
                return {"total": 5}
            elif "COUNT(*) AS total FROM courses" in query:
                return {"total": 3}
            elif "COUNT(*) AS total FROM enrollments" in query:
                return {"total": 7}
            elif "ORDER BY e.enrolled_at DESC" in query:
                return []
            elif "GROUP BY c.id" in query:
                return []
            return []
        mock_query.side_effect = side_effect

        res = self.client.get("/api/dashboard")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()["data"]
        self.assertEqual(data["total_students"], 5)
        self.assertEqual(data["total_courses"], 3)
        self.assertEqual(data["total_enrollments"], 7)

    @patch("backend.services.student_service.query_db")
    def test_get_students(self, mock_query):
        mock_query.return_value = [
            {"id": 1, "name": "Student One", "email": "student@example.com", "created_at": "2026-11-13 00:00:00", "enrollment_count": 1}
        ]
        res = self.client.get("/api/students")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["data"][0]["name"], "Student One")

    @patch("backend.services.student_service.query_db")
    @patch("backend.services.student_service.execute_db")
    def test_create_student_success(self, mock_exec, mock_query):
        mock_query.return_value = None  # No existing duplicate
        mock_exec.return_value = 2      # Generated student ID

        res = self.client.post("/api/students", json={
            "name": "Jane Doe",
            "email": "jane@example.com",
            "password": "Password123"
        })
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["name"], "Jane Doe")
        self.assertEqual(data["data"]["id"], 2)

    @patch("backend.services.student_service.query_db")
    def test_create_student_duplicate(self, mock_query):
        mock_query.return_value = {"id": 1} # Existing student
        res = self.client.post("/api/students", json={
            "name": "Student One",
            "email": "student@example.com"
        })
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data["success"])
        self.assertIn("already exists", data["error"])

    @patch("backend.services.student_service.query_db")
    def test_get_student_details(self, mock_query):
        def side_effect(query, args=(), one=False):
            if "FROM students WHERE id" in query:
                return {"id": 1, "name": "Student One", "email": "student@example.com", "created_at": None}
            elif "FROM enrollments e" in query:
                return [{"id": 1, "course_code": "CS-101", "title": "Intro to E-Learning", "description": "Desc", "enrolled_at": None, "status": "enrolled"}]
            return []
        mock_query.side_effect = side_effect

        res = self.client.get("/api/students/1")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()["data"]
        self.assertEqual(data["name"], "Student One")
        self.assertEqual(len(data["enrolled_courses"]), 1)

    @patch("backend.services.course_service.query_db")
    def test_get_courses(self, mock_query):
        mock_query.return_value = [
            {"id": 1, "course_code": "CS-101", "title": "Introduction to E-Learning", "description": "First sample course", "created_at": None, "enrolled_students_count": 1}
        ]
        res = self.client.get("/api/courses")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["data"][0]["title"], "Introduction to E-Learning")

    @patch("backend.services.course_service.execute_db")
    def test_create_course(self, mock_exec):
        mock_exec.return_value = 10
        res = self.client.post("/api/courses", json={
            "course_code": "CS-102",
            "title": "Cloud Virtualization",
            "description": "Virtual machine management"
        })
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["title"], "Cloud Virtualization")

    @patch("backend.services.course_service.query_db")
    @patch("backend.services.course_service.execute_db")
    def test_delete_course(self, mock_exec, mock_query):
        mock_query.return_value = {"id": 10}
        mock_exec.return_value = 1
        res = self.client.delete("/api/courses/10")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])

    @patch("backend.services.enrollment_service.query_db")
    @patch("backend.services.enrollment_service.execute_db")
    def test_enroll_student_success(self, mock_exec, mock_query):
        def side_effect(query, args=(), one=False):
            if "FROM students WHERE id" in query:
                return {"id": 1, "name": "Student One", "email": "student@example.com"}
            elif "FROM courses WHERE id" in query:
                return {"id": 2, "title": "Cloud Computing", "course_code": "CS-102"}
            elif "FROM enrollments WHERE student_id" in query:
                return None # Not already enrolled
            return None
        mock_query.side_effect = side_effect
        mock_exec.return_value = 101 # new enrollment id

        res = self.client.post("/api/enrollments", json={"student_id": 1, "course_id": 2})
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["enrollment_id"], 101)

    @patch("backend.services.enrollment_service.query_db")
    def test_enroll_student_prevent_duplicate(self, mock_query):
        def side_effect(query, args=(), one=False):
            if "FROM students WHERE id" in query:
                return {"id": 1, "name": "Student One", "email": "student@example.com"}
            elif "FROM courses WHERE id" in query:
                return {"id": 1, "title": "Introduction to E-Learning", "course_code": "CS-101"}
            elif "FROM enrollments WHERE student_id" in query:
                return {"id": 5} # ALREADY ENROLLED!
            return None
        mock_query.side_effect = side_effect

        res = self.client.post("/api/enrollments", json={"student_id": 1, "course_id": 1})
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data["success"])
        self.assertIn("already enrolled", data["error"])

    @patch("backend.services.enrollment_service.query_db")
    @patch("backend.services.enrollment_service.execute_db")
    def test_delete_enrollment(self, mock_exec, mock_query):
        mock_query.return_value = {"id": 101}
        mock_exec.return_value = 1
        res = self.client.delete("/api/enrollments/101")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])

    def test_xen_status_endpoint(self):
        res = self.client.get("/api/xen/status")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()["data"]
        self.assertIn("virtualization", data)
        self.assertEqual(data["virtualization"]["hypervisor"], "XCP-ng / Xen")
        self.assertEqual(data["virtualization"]["host_management_ip"], "10.240.109.196")

if __name__ == "__main__":
    unittest.main()
