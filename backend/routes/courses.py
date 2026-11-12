from flask import Blueprint, request, jsonify
from backend.services.course_service import (
    get_all_courses,
    get_course_by_id,
    create_course,
    update_course,
    delete_course
)

courses_bp = Blueprint("courses", __name__, url_prefix="/api")

@courses_bp.route("/courses", methods=["GET"])
def list_courses():
    """
    GET /api/courses
    Returns list of all courses with enrollment counts.
    """
    try:
        courses = get_all_courses()
        return jsonify({
            "success": True,
            "count": len(courses),
            "data": courses
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@courses_bp.route("/courses", methods=["POST"])
def add_course():
    """
    POST /api/courses
    Request body: { "course_code": "CS-102", "title": "...", "description": "..." }
    """
    data = request.get_json(silent=True) or {}
    course_code = data.get("course_code")
    title = data.get("title")
    description = data.get("description", "")
    
    try:
        course = create_course(course_code, title, description)
        return jsonify({
            "success": True,
            "message": "Course created successfully in MariaDB",
            "data": course
        }), 201
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@courses_bp.route("/courses/<int:course_id>", methods=["GET"])
def get_course(course_id):
    """
    GET /api/courses/<id>
    """
    try:
        course = get_course_by_id(course_id)
        if not course:
            return jsonify({"success": False, "error": f"Course ID {course_id} not found"}), 404
        return jsonify({"success": True, "data": course}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@courses_bp.route("/courses/<int:course_id>", methods=["PUT"])
def edit_course(course_id):
    """
    PUT /api/courses/<id>
    Request body: { "course_code": "...", "title": "...", "description": "..." }
    """
    data = request.get_json(silent=True) or {}
    course_code = data.get("course_code")
    title = data.get("title")
    description = data.get("description", "")
    
    try:
        updated = update_course(course_id, course_code, title, description)
        if not updated:
            return jsonify({"success": False, "error": f"Course ID {course_id} not found"}), 404
        return jsonify({
            "success": True,
            "message": "Course updated successfully",
            "data": updated
        }), 200
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@courses_bp.route("/courses/<int:course_id>", methods=["DELETE"])
def remove_course(course_id):
    """
    DELETE /api/courses/<id>
    """
    try:
        deleted = delete_course(course_id)
        if not deleted:
            return jsonify({"success": False, "error": f"Course ID {course_id} not found"}), 404
        return jsonify({
            "success": True,
            "message": f"Course ID {course_id} deleted successfully"
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
