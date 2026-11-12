import os
import sys
import logging

# Ensure root directory is on Python path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from flask import Flask, jsonify
try:
    from flask_cors import CORS
except ImportError:
    def CORS(app, **kwargs):
        @app.after_request
        def add_cors_headers(response):
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
            response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
            return response
        return app
from backend.config import Config
from backend.database import ensure_schema
from backend.routes.auth import auth_bp
from backend.routes.dashboard import dashboard_bp
from backend.routes.students import students_bp
from backend.routes.courses import courses_bp
from backend.routes.enrollments import enrollments_bp
from backend.routes.xen_routes import xen_bp
from backend.routes.health import health_bp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("elearning_backend")

def create_app():
    """Application factory for Flask REST API."""
    app = Flask(__name__)
    app.config.from_object(Config)

    # Enable Cross-Origin Resource Sharing for Streamlit frontend
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Register API Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(students_bp)
    app.register_blueprint(courses_bp)
    app.register_blueprint(enrollments_bp)
    app.register_blueprint(xen_bp)
    app.register_blueprint(health_bp)

    @app.route("/", methods=["GET"])
    def index():
        return jsonify({
            "service": "Xen-Based E-Learning REST API",
            "version": "1.0.0",
            "project": "Xen-Based Dynamic Resource Allocation for Scalable E-Learning Services",
            "endpoints": [
                "/api/health",
                "/api/login",
                "/api/logout",
                "/api/dashboard",
                "/api/students",
                "/api/courses",
                "/api/enrollments",
                "/api/xen/status"
            ]
        })

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"success": False, "error": "Endpoint not found"}), 404

    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({"success": False, "error": "Internal server error"}), 500

    return app

if __name__ == "__main__":
    logger.info("Initializing database schema check on MariaDB (10.240.109.248)...")
    try:
        ensure_schema()
    except Exception as e:
        logger.warning(f"Initial schema check deferred: {e}")

    app = create_app()
    logger.info(f"Starting Flask API on {Config.FLASK_HOST}:{Config.FLASK_PORT}")
    app.run(
        host=Config.FLASK_HOST,
        port=Config.FLASK_PORT,
        debug=Config.DEBUG
    )
