import logging
from backend.database import query_db
from backend.config import Config

logger = logging.getLogger(__name__)

def get_dashboard_summary() -> dict:
    """
    Retrieve real-time metrics and summary stats directly from MariaDB.
    """
    # 1. Total Students
    students_res = query_db("SELECT COUNT(*) AS total FROM students", one=True)
    total_students = students_res["total"] if students_res else 0
    
    # 2. Total Courses
    courses_res = query_db("SELECT COUNT(*) AS total FROM courses", one=True)
    total_courses = courses_res["total"] if courses_res else 0
    
    # 3. Total Enrollments
    enrollments_res = query_db("SELECT COUNT(*) AS total FROM enrollments", one=True)
    total_enrollments = enrollments_res["total"] if enrollments_res else 0
    
    # 4. Recent Enrollments (Top 5)
    recent_query = """
        SELECT 
            e.id,
            s.name AS student_name,
            s.email AS student_email,
            c.title AS course_title,
            COALESCE(c.course_code, CONCAT('CS-', c.id)) AS course_code,
            e.enrolled_at,
            e.status
        FROM enrollments e
        JOIN students s ON e.student_id = s.id
        JOIN courses c ON e.course_id = c.id
        ORDER BY e.enrolled_at DESC
        LIMIT 5
    """
    recent_enrollments = query_db(recent_query)
    for r in recent_enrollments:
        if r.get("enrolled_at"):
            r["enrolled_at"] = str(r["enrolled_at"])
            
    # 5. Course Distribution / Popularity
    popular_query = """
        SELECT 
            c.id,
            COALESCE(c.course_code, CONCAT('CS-', c.id)) AS course_code,
            c.title,
            COUNT(e.id) AS enrolled_count
        FROM courses c
        LEFT JOIN enrollments e ON c.id = e.course_id
        GROUP BY c.id, c.course_code, c.title
        ORDER BY enrolled_count DESC
        LIMIT 5
    """
    popular_courses = query_db(popular_query)
    
    return {
        "total_students": total_students,
        "total_courses": total_courses,
        "total_enrollments": total_enrollments,
        "available_courses": total_courses,
        "recent_enrollments": recent_enrollments,
        "popular_courses": popular_courses,
        "infrastructure": {
            "app_vm": Config.APP_VM_IP,
            "db_vm": Config.DB_VM_IP,
            "xcp_host": Config.XCP_NG_HOST,
            "environment": Config.XEN_ENVIRONMENT
        }
    }
