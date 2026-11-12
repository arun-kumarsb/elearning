from flask import Blueprint, jsonify
from backend.database import test_connection
from backend.config import Config

health_bp = Blueprint("health", __name__, url_prefix="/api")

@health_bp.route("/health", methods=["GET"])
def health():
    """
    GET /api/health
    Checks backend status and connection to MariaDB VM.
    """
    db_status = test_connection()
    status_code = 200 if db_status.get("connected") else 503
    
    return jsonify({
        "status": "healthy" if db_status.get("connected") else "degraded",
        "service": "Xen E-Learning Flask API",
        "app_vm": Config.APP_VM_IP,
        "database_vm": {
            "target": f"{Config.DB_HOST}:{Config.DB_PORT}",
            "status": db_status
        }
    }), status_code
