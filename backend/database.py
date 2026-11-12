import os
import socket
import logging
import sqlite3
from contextlib import contextmanager
from backend.config import Config

logger = logging.getLogger(__name__)

# Track active database mode
ACTIVE_DB_MODE = None
LOCAL_SQLITE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database", "elearning_local.db")

def is_mariadb_reachable() -> bool:
    """Test if MariaDB server at Config.DB_HOST:Config.DB_PORT is reachable."""
    if Config.USE_MOCK_DB:
        return False
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.5)
        res = s.connect_ex((Config.DB_HOST, Config.DB_PORT))
        s.close()
        return res == 0
    except Exception:
        return False

def get_sqlite_connection():
    """Return an initialized SQLite connection with custom functions and Row factory."""
    os.makedirs(os.path.dirname(LOCAL_SQLITE_PATH), exist_ok=True)
    conn = sqlite3.connect(LOCAL_SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    
    # Register MySQL/MariaDB compatibility functions
    conn.create_function("CONCAT", -1, lambda *args: "".join(str(a) if a is not None else "" for a in args))
    conn.create_function("LPAD", 3, lambda s, length, pad: str(s).rjust(length, pad))
    return conn

def init_sqlite_schema(conn):
    """Initialize local SQLite database mirroring the exact MariaDB schema and sample data."""
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_code TEXT,
            title TEXT NOT NULL,
            description TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student',
            student_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS enrollments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            course_id INTEGER NOT NULL,
            enrolled_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'enrolled',
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
            FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
            UNIQUE(student_id, course_id)
        );

        -- Preserved Sample Student
        INSERT OR IGNORE INTO students (id, name, email) 
        VALUES (1, 'Student One', 'student@example.com');

        -- Preserved Sample Course
        INSERT OR IGNORE INTO courses (id, course_code, title, description) 
        VALUES (1, 'CS-101', 'Introduction to E-Learning', 'First sample course introducing virtual learning environments and scalable architectures.');

        -- Seed Default Administrator: admin@elearning.local / Admin@123
        INSERT OR IGNORE INTO users (email, password_hash, role, student_id)
        VALUES ('admin@elearning.local', 'pbkdf2:sha256:1000000$8PRaFkqRFhvD58t0$55904342ce6f616b382ffb49c8ed5cd043449892f6764cf212b748f88fe71506', 'admin', NULL);

        -- Seed Default Student: student@example.com / Student@123
        INSERT OR IGNORE INTO users (email, password_hash, role, student_id)
        VALUES ('student@example.com', 'pbkdf2:sha256:1000000$RWXgbhlbmE35xz0a$994a0d0b032a7bbf0c1adfa4ea2db1dea45675833da8310a1c4b0dc758c6a8f5', 'student', 1);

        -- Seed Sample Enrollment
        INSERT OR IGNORE INTO enrollments (student_id, course_id) VALUES (1, 1);
    """)
    conn.commit()

def get_connection():
    """
    Establish connection to MariaDB if reachable; otherwise fall back to local SQLite.
    """
    global ACTIVE_DB_MODE
    if is_mariadb_reachable():
        import pymysql
        import pymysql.cursors
        ACTIVE_DB_MODE = "mariadb"
        return pymysql.connect(
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            database=Config.DB_NAME,
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=5,
            autocommit=True,
            charset="utf8mb4"
        )
    else:
        ACTIVE_DB_MODE = "sqlite"
        conn = get_sqlite_connection()
        init_sqlite_schema(conn)
        return conn

@contextmanager
def get_db_cursor(commit=True):
    """
    Context manager yielding a cursor that supports dictionary outputs for both MariaDB and SQLite.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        yield cur
        if commit:
            conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def _adapt_query(query: str) -> str:
    """Adapt query syntax between MariaDB and SQLite."""
    if ACTIVE_DB_MODE == "sqlite":
        # SQLite uses ? instead of %s
        query = query.replace("%s", "?")
        # Replace MariaDB specific ON DUPLICATE KEY UPDATE with INSERT OR REPLACE where appropriate
        if "ON DUPLICATE KEY UPDATE" in query:
            query = query.split("ON DUPLICATE KEY UPDATE")[0].replace("INSERT INTO", "INSERT OR REPLACE INTO")
    return query

def query_db(query, args=(), one=False):
    """Execute a read query and return dictionary result(s)."""
    global ACTIVE_DB_MODE
    with get_db_cursor(commit=False) as cursor:
        sql = _adapt_query(query)
        cursor.execute(sql, args)
        if ACTIVE_DB_MODE == "sqlite":
            rows = [dict(row) for row in cursor.fetchall()]
        else:
            rows = cursor.fetchall()
        return (rows[0] if rows else None) if one else rows

def execute_db(query, args=(), return_last_id=False):
    """Execute an INSERT, UPDATE, or DELETE query and return affected rows or last insert ID."""
    global ACTIVE_DB_MODE
    with get_db_cursor(commit=True) as cursor:
        sql = _adapt_query(query)
        affected = cursor.execute(sql, args)
        if return_last_id:
            return cursor.lastrowid
        return affected.rowcount if hasattr(affected, "rowcount") else cursor.rowcount

def test_connection():
    """Test connectivity and return engine type and active tables."""
    try:
        if is_mariadb_reachable():
            import pymysql
            conn = get_connection()
            with conn.cursor() as cursor:
                cursor.execute("SELECT VERSION() AS version")
                version_info = cursor.fetchone()
                cursor.execute("SHOW TABLES")
                raw_tables = cursor.fetchall()
                tables = [list(t.values())[0] for t in raw_tables]
            conn.close()
            return {
                "connected": True,
                "engine": "MariaDB 11.8.9 (Alpine-DB VM)",
                "host": Config.DB_HOST,
                "port": Config.DB_PORT,
                "database": Config.DB_NAME,
                "version": version_info.get("version", "Unknown"),
                "tables": tables
            }
        else:
            conn = get_sqlite_connection()
            init_sqlite_schema(conn)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r["name"] for r in cur.fetchall()]
            conn.close()
            return {
                "connected": True,
                "engine": "SQLite Engine (Local Dev Mode - MariaDB 10.240.109.248 Unreachable)",
                "host": "localhost",
                "database": "elearning_local.db",
                "version": sqlite3.sqlite_version,
                "tables": tables
            }
    except Exception as e:
        return {
            "connected": False,
            "host": Config.DB_HOST,
            "port": Config.DB_PORT,
            "error": str(e)
        }

def ensure_schema():
    """Ensure schema tables are initialized."""
    try:
        if is_mariadb_reachable():
            res = test_connection()
            tables = res.get("tables", [])
            if "users" not in tables or "enrollments" not in tables:
                migration_path = os.path.join(os.path.dirname(__file__), "..", "database", "migrations.sql")
                if os.path.exists(migration_path):
                    with open(migration_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    statements = [stmt.strip() for stmt in content.split(";") if stmt.strip()]
                    with get_db_cursor() as cursor:
                        for stmt in statements:
                            if stmt.upper().startswith("USE ") or stmt.startswith("--"):
                                continue
                            try:
                                cursor.execute(stmt)
                            except Exception as ex:
                                logger.debug(f"Migration statement notice: {ex}")
        else:
            conn = get_sqlite_connection()
            init_sqlite_schema(conn)
            conn.close()
        return True
    except Exception as e:
        logger.error(f"ensure_schema failed: {e}")
        return False
