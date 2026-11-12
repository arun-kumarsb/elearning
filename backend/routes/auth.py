from flask import Blueprint, request, jsonify
from backend.services.auth_service import authenticate_user, verify_session_token

auth_bp = Blueprint("auth", __name__, url_prefix="/api")

@auth_bp.route("/login", methods=["POST"])
def login():
    """
    POST /api/login
    Request body: { "email": "...", "password": "..." }
    """
    data = request.get_json(silent=True) or {}
    email = data.get("email")
    password = data.get("password")
    
    if not email or not password:
        return jsonify({"success": False, "error": "Email and password are required"}), 400
        
    try:
        user_info = authenticate_user(email, password)
        if not user_info:
            return jsonify({"success": False, "error": "Invalid email or password"}), 401
            
        return jsonify({
            "success": True,
            "message": "Login successful",
            "user": user_info
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@auth_bp.route("/logout", methods=["POST"])
def logout():
    """
    POST /api/logout
    Clears session state.
    """
    return jsonify({
        "success": True,
        "message": "Logged out successfully"
    }), 200

@auth_bp.route("/auth/me", methods=["GET"])
def me():
    """
    GET /api/auth/me
    Headers: Authorization: Bearer <token>
    """
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip()
    payload = verify_session_token(token)
    
    if not payload:
        return jsonify({"success": False, "error": "Invalid or expired session"}), 401
        
    return jsonify({"success": True, "user": payload}), 200

