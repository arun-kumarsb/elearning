import logging
from backend.database import query_db, execute_db
from backend.services.auth_service import hash_password

logger = logging.getLogger(__name__)

def get_all_students() -> list:
    """
    Retrieve all students from MariaDB with their active enrollment count.
    """
    query = """
        SELECT 
            s.id, 
            s.name, 
            s.email, 
            s.created_at,
            COUNT(e.id) AS enrollment_count
        FROM students s
        LEFT JOIN enrollments e ON s.id = e.student_id
        GROUP BY s.id, s.name, s.email, s.created_at
        ORDER BY s.id ASC
    """
    rows = query_db(query)
    # Serialize datetime to ISO string for JSON serialization
    for r in rows:
        if r.get("created_at"):
            r["created_at"] = str(r["created_at"])
    return rows

def get_student_by_id(student_id: int) -> dict | None:
    """
    Retrieve details for a specific student, including their enrolled courses.
    """
    student_query = "SELECT id, name, email, created_at FROM students WHERE id = %s"
    student = query_db(student_query, (student_id,), one=True)
    if not student:
        return None
        
    if student.get("created_at"):
        student["created_at"] = str(student["created_at"])
        
    # Get enrolled courses
    courses_query = """
        SELECT 
            c.id, 
            COALESCE(c.course_code, CONCAT('CS-', c.id)) AS course_code,
            c.title, 
            c.description, 
            e.enrolled_at,
            e.status
        FROM enrollments e
        JOIN courses c ON e.course_id = c.id
        WHERE e.student_id = %s
        ORDER BY e.enrolled_at DESC
    """
    enrolled_courses = query_db(courses_query, (student_id,))
    for c in enrolled_courses:
        if c.get("enrolled_at"):
            c["enrolled_at"] = str(c["enrolled_at"])
            
    student["enrolled_courses"] = enrolled_courses
    student["enrollment_count"] = len(enrolled_courses)
    return student

def create_student(name: str, email: str, password: str = None) -> dict:
    """
    Create a new student in MariaDB.
    Also creates a corresponding user record so the student can log in.
    """
    name = (name or "").strip()
    email = (email or "").strip().lower()
    
    if not name or not email:
        raise ValueError("Name and email are required.")
    if "@" not in email:
        raise ValueError("A valid email address is required.")
        
    # Check duplicate
    existing = query_db("SELECT id FROM students WHERE LOWER(email) = %s", (email,), one=True)
    if existing:
        raise ValueError(f"Student with email '{email}' already exists.")
        
    student_id = execute_db(
        "INSERT INTO students (name, email) VALUES (%s, %s)",
        (name, email),
        return_last_id=True
    )
    
    # Auto-create user login
    pwd = password if password else "Student@123"
    pwd_hash = hash_password(pwd)
    
    # Insert or update into users
    execute_db(
        """
        INSERT INTO users (email, password_hash, role, student_id)
        VALUES (%s, %s, 'student', %s)
        ON DUPLICATE KEY UPDATE password_hash = VALUES(password_hash), student_id = VALUES(student_id)
        """,
        (email, pwd_hash, student_id)
    )
    
    return {
        "id": student_id,
        "name": name,
        "email": email,
        "temporary_password": pwd if not password else None
    }

def delete_student(student_id: int) -> bool:
    """Delete a student and cascade to their enrollments and user account."""
    existing = query_db("SELECT id FROM students WHERE id = %s", (student_id,), one=True)
    if not existing:
        return False
        
    execute_db("DELETE FROM students WHERE id = %s", (student_id,))
    return True
