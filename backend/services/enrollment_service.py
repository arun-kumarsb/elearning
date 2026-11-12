import logging
from backend.database import query_db, execute_db

logger = logging.getLogger(__name__)

def get_all_enrollments() -> list:
    """
    Retrieve all enrollment records joined with student and course details.
    """
    query = """
        SELECT 
            e.id,
            e.student_id,
            s.name AS student_name,
            s.email AS student_email,
            e.course_id,
            COALESCE(c.course_code, CONCAT('CS-', c.id)) AS course_code,
            c.title AS course_title,
            e.enrolled_at,
            e.status
        FROM enrollments e
        JOIN students s ON e.student_id = s.id
        JOIN courses c ON e.course_id = c.id
        ORDER BY e.enrolled_at DESC
    """
    rows = query_db(query)
    for r in rows:
        if r.get("enrolled_at"):
            r["enrolled_at"] = str(r["enrolled_at"])
    return rows

def get_student_enrollments(student_id: int) -> list:
    """
    Retrieve all courses enrolled by a specific student.
    """
    query = """
        SELECT 
            e.id AS enrollment_id,
            c.id AS course_id,
            COALESCE(c.course_code, CONCAT('CS-', c.id)) AS course_code,
            c.title AS course_title,
            c.description AS course_description,
            e.enrolled_at,
            e.status
        FROM enrollments e
        JOIN courses c ON e.course_id = c.id
        WHERE e.student_id = %s
        ORDER BY e.enrolled_at DESC
    """
    rows = query_db(query, (student_id,))
    for r in rows:
        if r.get("enrolled_at"):
            r["enrolled_at"] = str(r["enrolled_at"])
    return rows

def enroll_student(student_id: int, course_id: int) -> dict:
    """
    Enroll a student into a course.
    Enforces existence checks and duplicate prevention.
    """
    # 1. Verify student exists
    student = query_db("SELECT id, name, email FROM students WHERE id = %s", (student_id,), one=True)
    if not student:
        raise ValueError(f"Student with ID {student_id} does not exist.")
        
    # 2. Verify course exists
    course = query_db("SELECT id, title, course_code FROM courses WHERE id = %s", (course_id,), one=True)
    if not course:
        raise ValueError(f"Course with ID {course_id} does not exist.")
        
    # 3. Check duplicate enrollment
    existing = query_db(
        "SELECT id FROM enrollments WHERE student_id = %s AND course_id = %s",
        (student_id, course_id),
        one=True
    )
    if existing:
        raise ValueError(f"Student '{student['name']}' is already enrolled in '{course['title']}'.")
        
    # 4. Insert enrollment
    enrollment_id = execute_db(
        "INSERT INTO enrollments (student_id, course_id, status) VALUES (%s, %s, 'enrolled')",
        (student_id, course_id),
        return_last_id=True
    )
    
    return {
        "enrollment_id": enrollment_id,
        "student_id": student["id"],
        "student_name": student["name"],
        "student_email": student["email"],
        "course_id": course["id"],
        "course_title": course["title"],
        "course_code": course.get("course_code") or f"CS-{course['id']}",
        "message": f"Successfully enrolled {student['name']} in {course['title']}!"
    }

def delete_enrollment(enrollment_id: int) -> bool:
    """
    Cancel or delete an enrollment record.
    """
    existing = query_db("SELECT id FROM enrollments WHERE id = %s", (enrollment_id,), one=True)
    if not existing:
        return False
        
    execute_db("DELETE FROM enrollments WHERE id = %s", (enrollment_id,))
    return True
