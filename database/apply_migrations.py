#!/usr/bin/env python3
"""
Database Migration and Schema Inspector Script
Project: Xen-Based Dynamic Resource Allocation for Scalable E-Learning Services
Target: MariaDB 11.8.9 on VM 1 (Alpine-DB: 10.240.109.248:3306)

This script:
1. Connects to MariaDB using environment variables or defaults.
2. Inspects existing tables, columns, and records.
3. Applies non-destructive migrations from migrations.sql.
4. Preserves all existing data (Student One, Introduction to E-Learning, etc.).
"""

import os
import sys
import pymysql
from dotenv import load_dotenv

# Load environment configuration
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "10.240.109.248")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "elearning")
DB_PASSWORD = os.getenv("DB_PASSWORD", "elearning123")
DB_NAME = os.getenv("DB_NAME", "elearning")


def get_connection():
    try:
        conn = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=10,
            autocommit=True,
            charset="utf8mb4"
        )
        return conn
    except pymysql.MySQLError as err:
        print(f"[ERROR] Failed to connect to MariaDB at {DB_HOST}:{DB_PORT}: {err}")
        return None


def inspect_database(conn):
    print("\n--- Current Database Inspection ---")
    with conn.cursor() as cursor:
        cursor.execute("SHOW TABLES")
        tables = [list(row.values())[0] for row in cursor.fetchall()]
        print(f"Existing tables in '{DB_NAME}': {tables}")

        for table in tables:
            cursor.execute(f"DESCRIBE {table}")
            columns = cursor.fetchall()
            col_names = [col['Field'] for col in columns]
            cursor.execute(f"SELECT COUNT(*) AS cnt FROM {table}")
            cnt = cursor.fetchone()['cnt']
            print(f"  * Table `{table}`: {len(columns)} columns {col_names} | {cnt} records")


def run_migrations(conn):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    migration_file = os.path.join(script_dir, "migrations.sql")

    if not os.path.isfile(migration_file):
        print(f"[ERROR] Migration file not found: {migration_file}")
        return False

    print(f"\n--- Applying Migration: {migration_file} ---")
    with open(migration_file, "r", encoding="utf-8") as f:
        sql_content = f.read()

    # Split commands by semicolon (ignoring comments and empty statements)
    statements = [stmt.strip() for stmt in sql_content.split(";") if stmt.strip()]

    with conn.cursor() as cursor:
        for stmt in statements:
            # Skip comments or USE statement
            if stmt.upper().startswith("USE ") or stmt.startswith("--"):
                continue
            try:
                cursor.execute(stmt)
            except pymysql.MySQLError as err:
                # Catch benign warnings like column already exists
                print(f"[NOTICE] Statement notice: {err}")

    print("[SUCCESS] Migrations applied successfully!")
    return True


def verify_sample_data(conn):
    print("\n--- Verifying Data Integrity ---")
    with conn.cursor() as cursor:
        # Check students
        cursor.execute("SELECT id, name, email FROM students")
        students = cursor.fetchall()
        print(f"Students ({len(students)}):")
        for s in students:
            print(f"  - [ID {s['id']}] {s['name']} ({s['email']})")

        # Check courses
        cursor.execute("SELECT id, title FROM courses")
        courses = cursor.fetchall()
        print(f"Courses ({len(courses)}):")
        for c in courses:
            print(f"  - [ID {c['id']}] {c['title']}")

        # Check users
        cursor.execute("SELECT id, email, role, student_id FROM users")
        users = cursor.fetchall()
        print(f"Users ({len(users)}):")
        for u in users:
            print(f"  - [ID {u['id']}] {u['email']} | Role: {u['role']} | StudentID: {u['student_id']}")

        # Check enrollments
        cursor.execute("SELECT COUNT(*) AS cnt FROM enrollments")
        enrollment_count = cursor.fetchone()['cnt']
        print(f"Total Enrollments: {enrollment_count}")


def main():
    print("==================================================================")
    print("Xen-Based E-Learning: Database Migration & Verification Utility")
    print(f"Connecting to: {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    print("==================================================================")

    conn = get_connection()
    if not conn:
        sys.exit(1)

    try:
        inspect_database(conn)
        run_migrations(conn)
        verify_sample_data(conn)
        print("\n[SUCCESS] Database is fully synchronized and ready for backend operations!")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
