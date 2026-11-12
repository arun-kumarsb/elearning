import hmac
import hashlib
import json
import base64
import time
from werkzeug.security import generate_password_hash, check_password_hash
from backend.database import query_db, execute_db
from backend.config import Config

def hash_password(password: str) -> str:
    """Generate secure password hash using PBKDF2:SHA256 (compatible with Python 3.14)."""
    return generate_password_hash(password, method="pbkdf2:sha256")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify candidate password against stored hash."""
    if not hashed_password or not plain_password:
        return False
    # If standard werkzeug hash
    try:
        return check_password_hash(hashed_password, plain_password)
    except Exception:
        # Fallback simple constant-time comparison in case of legacy plain-text (not recommended)
        return hmac.compare_digest(plain_password, hashed_password)

def generate_session_token(user_id: int, email: str, role: str) -> str:
    """
    Generate a simple tamper-proof signed session token without heavy external libraries.
    """
    payload = {
        "uid": user_id,
        "email": email,
        "role": role,
        "exp": int(time.time()) + 86400 * 7 # 7 days
    }
    raw_json = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    b64_payload = base64.urlsafe_b64encode(raw_json).decode('utf-8').rstrip('=')
    
    signature = hmac.new(
        Config.SECRET_KEY.encode('utf-8'),
        b64_payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return f"{b64_payload}.{signature}"

def verify_session_token(token: str) -> dict | None:
    """Validate token and return payload if valid, otherwise None."""
    if not token or "." not in token:
        return None
    try:
        b64_payload, signature = token.split(".", 1)
        expected_sig = hmac.new(
            Config.SECRET_KEY.encode('utf-8'),
            b64_payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(signature, expected_sig):
            return None
            
        # Add padding back if necessary
        padding = '=' * (4 - len(b64_payload) % 4) if len(b64_payload) % 4 != 0 else ''
        payload_bytes = base64.urlsafe_b64decode(b64_payload + padding)
        payload = json.loads(payload_bytes.decode('utf-8'))
        
        if payload.get("exp", 0) < time.time():
            return None # Expired
            
        return payload
    except Exception:
        return None

def authenticate_user(email: str, password: str) -> dict | None:
    """
    Authenticate user against MariaDB `users` table.
    Returns user details and token on success, None on failure.
    """
    if not email or not password:
        return None
        
    query = """
        SELECT u.id, u.email, u.password_hash, u.role, u.student_id, 
               s.name AS student_name
        FROM users u
        LEFT JOIN students s ON u.student_id = s.id
        WHERE LOWER(u.email) = LOWER(%s)
        LIMIT 1
    """
    user = query_db(query, (email.strip(),), one=True)
    
    # If user not in `users` table, check if email is an existing student without a user record
    if not user:
        student = query_db("SELECT id, name, email FROM students WHERE LOWER(email) = LOWER(%s) LIMIT 1", (email.strip(),), one=True)
        if student and password in ("Student@123", "password", "student123"):
            # Create user record automatically for existing sample student
            new_hash = hash_password(password)
            user_id = execute_db(
                "INSERT INTO users (email, password_hash, role, student_id) VALUES (%s, %s, %s, %s)",
                (student["email"], new_hash, "student", student["id"]),
                return_last_id=True
            )
            token = generate_session_token(user_id, student["email"], "student")
            return {
                "id": user_id,
                "email": student["email"],
                "role": "student",
                "student_id": student["id"],
                "name": student["name"],
                "token": token
            }
        return None
        
    if verify_password(password, user["password_hash"]):
        token = generate_session_token(user["id"], user["email"], user["role"])
        return {
            "id": user["id"],
            "email": user["email"],
            "role": user["role"],
            "student_id": user["student_id"],
            "name": user["student_name"] or ("Administrator" if user["role"] == "admin" else user["email"].split("@")[0]),
            "token": token
        }
        
    return None

def create_user_record(email: str, password: str, role: str = "student", student_id: int = None) -> int:
    """Create a new user in the users table."""
    hashed = hash_password(password)
    query = """
        INSERT INTO users (email, password_hash, role, student_id)
        VALUES (%s, %s, %s, %s)
    """
    return execute_db(query, (email.strip().lower(), hashed, role, student_id), return_last_id=True)
