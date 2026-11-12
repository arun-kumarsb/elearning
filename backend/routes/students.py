from flask import Blueprint, request, jsonify
from backend.services.student_service import (
    get_all_students, 
    get_student_by_id, 
    create_student, 
    delete_student
)

students_bp = Blueprint("students", __name__, url_prefix="/api")

@students_bp.route("/students", methods=["GET"])
def list_students():
    """
    GET /api/students
    Returns list of all students from MariaDB.
    """
    try:
        students = get_all_students()
        return jsonify({
            "success": True,
            "count": len(students),
            "data": students
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@students_bp.route("/students", methods=["POST"])
def add_student():
    """
    POST /api/students
    Request body: { "name": "...", "email": "...", "password": "..." (optional) }
    """
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    
    try:
        new_student = create_student(name, email, password)
        return jsonify({
            "success": True,
            "message": "Student created successfully in MariaDB",
            "data": new_student
        }), 201
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@students_bp.route("/students/<int:student_id>", methods=["GET"])
def get_student(student_id):
    """
    GET /api/students/<id>
    Returns student details and their enrolled courses.
    """
    try:
        student = get_student_by_id(student_id)
        if not student:
            return jsonify({"success": False, "error": f"Student ID {student_id} not found"}), 404
        return jsonify({"success": True, "data": student}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@students_bp.route("/students/<int:student_id>", methods=["DELETE"])
def remove_student(student_id):
    """
    DELETE /api/students/<id>
    """
    try:
        deleted = delete_student(student_id)
        if not deleted:
            return jsonify({"success": False, "error": f"Student ID {student_id} not found"}), 404
        return jsonify({"success": True, "message": f"Student ID {student_id} deleted successfully"}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

