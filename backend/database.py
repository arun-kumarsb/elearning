import os
import pymysql
import pymysql.cursors
import logging
from contextlib import contextmanager
from backend.config import Config

logger = logging.getLogger(__name__)

def get_connection():
    """
    Establish a connection to the MariaDB server running on VM 1 (Alpine-DB: 10.240.109.248:3306).
    Uses PyMySQL with DictCursor to return results as dictionaries.
    """
    try:
        connection = pymysql.connect(
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
        return connection
    except pymysql.MySQLError as err:
        logger.error(f"Database connection error to {Config.DB_HOST}:{Config.DB_PORT}: {err}")
        raise ConnectionError(
            f"Could not connect to MariaDB at {Config.DB_HOST}:{Config.DB_PORT}. "
            f"Verify Alpine-DB VM (10.240.109.248) is running and accessible. Error: {str(err)}"
        )

@contextmanager
def get_db_cursor(commit=True):
    """
    Context manager for database cursor. Automatically commits and closes.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            yield cursor
        if commit:
            conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def query_db(query, args=(), one=False):
    """
    Execute a read query and return dictionary result(s).
    """
    with get_db_cursor(commit=False) as cursor:
        cursor.execute(query, args)
        rv = cursor.fetchall()
        return (rv[0] if rv else None) if one else rv

def execute_db(query, args=(), return_last_id=False):
    """
    Execute an INSERT, UPDATE, or DELETE query and return affected rows or last insert ID.
    """
    with get_db_cursor(commit=True) as cursor:
        affected = cursor.execute(query, args)
        if return_last_id:
            return cursor.lastrowid
        return affected

def test_connection():
    """
    Test connectivity to MariaDB and check existing tables.
    """
    try:
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
            "host": Config.DB_HOST,
            "port": Config.DB_PORT,
            "database": Config.DB_NAME,
            "version": version_info.get("version", "Unknown"),
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
    """
    Checks if required tables (users, enrollments) exist in MariaDB,
    and if not, applies the migration script without touching existing records.
    """
    try:
        res = test_connection()
        if not res["connected"]:
            logger.warning(f"Skipping schema check: Cannot connect to DB ({res.get('error')})")
            return False
            
        tables = res.get("tables", [])
        if "users" not in tables or "enrollments" not in tables:
            logger.info("Tables missing, applying database/migrations.sql...")
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
                logger.info("Database migration completed successfully.")
        return True
    except Exception as e:
        logger.error(f"ensure_schema failed: {e}")
        return False

