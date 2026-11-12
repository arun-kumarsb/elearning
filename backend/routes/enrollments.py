from flask import Blueprint, request, jsonify
from backend.services.enrollment_service import (
    get_all_enrollments,
    get_student_enrollments,
    enroll_student,
    delete_enrollment
)

enrollments_bp = Blueprint("enrollments", __name__, url_prefix="/api")

@enrollments_bp.route("/enrollments", methods=["GET"])
def list_enrollments():
    """
    GET /api/enrollments
    Returns all enrollments with student and course metadata.
    """
    try:
        enrollments = get_all_enrollments()
        return jsonify({
            "success": True,
            "count": len(enrollments),
            "data": enrollments
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@enrollments_bp.route("/enrollments", methods=["POST"])
def create_enrollment():
    """
    POST /api/enrollments
    Request body: { "student_id": 1, "course_id": 2 }
    """
    data = request.get_json(silent=True) or {}
    student_id = data.get("student_id")
    course_id = data.get("course_id")
    
    if student_id is None or course_id is None:
        return jsonify({"success": False, "error": "Both student_id and course_id are required"}), 400
        
    try:
        student_id = int(student_id)
        course_id = int(course_id)
        result = enroll_student(student_id, course_id)
        return jsonify({
            "success": True,
            "message": result["message"],
            "data": result
        }), 201
    except ValueError as ve:
        # Handles duplicate enrollment or non-existent entity with friendly 400 Bad Request
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@enrollments_bp.route("/students/<int:student_id>/enrollments", methods=["GET"])
def get_enrollments_for_student(student_id):
    """
    GET /api/students/<id>/enrollments
    Returns all courses enrolled by a specific student.
    """
    try:
        enrollments = get_student_enrollments(student_id)
        return jsonify({
            "success": True,
            "student_id": student_id,
            "count": len(enrollments),
            "data": enrollments
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@enrollments_bp.route("/enrollments/<int:enrollment_id>", methods=["DELETE"])
def remove_enrollment(enrollment_id):
    """
    DELETE /api/enrollments/<id>
    Unenrolls student from course.
    """
    try:
        deleted = delete_enrollment(enrollment_id)
        if not deleted:
            return jsonify({"success": False, "error": f"Enrollment ID {enrollment_id} not found"}), 404
        return jsonify({
            "success": True,
            "message": f"Enrollment {enrollment_id} canceled successfully"
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

