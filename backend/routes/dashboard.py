from flask import Blueprint, jsonify
from backend.services.dashboard_service import get_dashboard_summary

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/api")

@dashboard_bp.route("/dashboard", methods=["GET"])
def dashboard():
    """
    GET /api/dashboard
    Returns real MariaDB counts:
    - total_students
    - total_courses
    - total_enrollments
    - available_courses
    - recent_enrollments
    - popular_courses
    """
    try:
        data = get_dashboard_summary()
        return jsonify({
            "success": True,
            "data": data
        }), 200
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Failed to retrieve dashboard data from MariaDB: {str(e)}"
        }), 500
