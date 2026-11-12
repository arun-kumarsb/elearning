import logging
from backend.database import query_db, execute_db

logger = logging.getLogger(__name__)

def get_all_courses() -> list:
    """
    Retrieve all courses from MariaDB, along with the count of enrolled students.
    Handles legacy column variations (title / name, course_code).
    """
    query = """
        SELECT 
            c.id,
            COALESCE(c.course_code, CONCAT('CS-', LPAD(c.id, 3, '0'))) AS course_code,
            c.title,
            COALESCE(c.description, '') AS description,
            c.created_at,
            COUNT(e.id) AS enrolled_students_count
        FROM courses c
        LEFT JOIN enrollments e ON c.id = e.course_id
        GROUP BY c.id, c.course_code, c.title, c.description, c.created_at
        ORDER BY c.id ASC
    """
    rows = query_db(query)
    for r in rows:
        if r.get("created_at"):
            r["created_at"] = str(r["created_at"])
    return rows

def get_course_by_id(course_id: int) -> dict | None:
    """
    Retrieve single course by ID with its list of enrolled students.
    """
    query = """
        SELECT 
            id,
            COALESCE(course_code, CONCAT('CS-', LPAD(id, 3, '0'))) AS course_code,
            title,
            COALESCE(description, '') AS description,
            created_at
        FROM courses
        WHERE id = %s
    """
    course = query_db(query, (course_id,), one=True)
    if not course:
        return None
        
    if course.get("created_at"):
        course["created_at"] = str(course["created_at"])
        
    # Get enrolled students for this course
    students_query = """
        SELECT 
            s.id,
            s.name,
            s.email,
            e.enrolled_at,
            e.status
        FROM enrollments e
        JOIN students s ON e.student_id = s.id
        WHERE e.course_id = %s
        ORDER BY e.enrolled_at DESC
    """
    enrolled_students = query_db(students_query, (course_id,))
    for s in enrolled_students:
        if s.get("enrolled_at"):
            s["enrolled_at"] = str(s["enrolled_at"])
            
    course["enrolled_students"] = enrolled_students
    course["enrolled_students_count"] = len(enrolled_students)
    return course

def create_course(course_code: str, title: str, description: str) -> dict:
    """
    Create a new course in MariaDB.
    """
    title = (title or "").strip()
    description = (description or "").strip()
    course_code = (course_code or "").strip().upper()
    
    if not title:
        raise ValueError("Course title is required.")
        
    # If no course code provided, auto-generate placeholder
    if not course_code:
        course_code = f"CS-{abs(hash(title)) % 900 + 100}"
        
    query = """
        INSERT INTO courses (course_code, title, description)
        VALUES (%s, %s, %s)
    """
    course_id = execute_db(query, (course_code, title, description), return_last_id=True)
    
    return {
        "id": course_id,
        "course_code": course_code,
        "title": title,
        "description": description
    }

def update_course(course_id: int, course_code: str, title: str, description: str) -> dict | None:
    """
    Update an existing course in MariaDB.
    """
    existing = query_db("SELECT id FROM courses WHERE id = %s", (course_id,), one=True)
    if not existing:
        return None
        
    title = (title or "").strip()
    description = (description or "").strip()
    course_code = (course_code or "").strip().upper()
    
    if not title:
        raise ValueError("Course title cannot be empty.")
        
    query = """
        UPDATE courses 
        SET course_code = %s, title = %s, description = %s
        WHERE id = %s
    """
    execute_db(query, (course_code, title, description, course_id))
    return get_course_by_id(course_id)

def delete_course(course_id: int) -> bool:
    """
    Delete a course by ID from MariaDB. Cascades to enrollments.
    """
    existing = query_db("SELECT id FROM courses WHERE id = %s", (course_id,), one=True)
    if not existing:
        return False
        
    execute_db("DELETE FROM courses WHERE id = %s", (course_id,))
    return True
