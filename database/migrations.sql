-- ============================================================================
-- Xen-Based Dynamic Resource Allocation for Scalable E-Learning Services
-- Database Migration Script (Non-Destructive)
-- Target Database: MariaDB 11.8.9 on VM 1 (Alpine-DB: 10.240.109.248:3306)
-- Database Name: elearning
--
-- This script preserves all existing records, existing tables, and existing IDs.
-- It applies idempotent migrations (IF NOT EXISTS / INSERT IGNORE).
-- ============================================================================

USE elearning;

-- 1. Ensure students table exists (preserves existing records)
CREATE TABLE IF NOT EXISTS students (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(191) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Ensure courses table exists (preserves existing records)
CREATE TABLE IF NOT EXISTS courses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    course_code VARCHAR(50) NULL,
    title VARCHAR(191) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. Add course_code if it does not already exist in legacy schema
-- MariaDB 10.5+ supports 'ADD COLUMN IF NOT EXISTS'
ALTER TABLE courses ADD COLUMN IF NOT EXISTS course_code VARCHAR(50) NULL AFTER id;
ALTER TABLE courses ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Update course_code for courses where it might be NULL
UPDATE courses 
SET course_code = CONCAT('CS-', LPAD(id, 3, '0')) 
WHERE course_code IS NULL OR course_code = '';

-- 4. Create authentication users table
-- Roles: 'admin', 'student'
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(191) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('admin', 'student') NOT NULL DEFAULT 'student',
    student_id INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_user_student FOREIGN KEY (student_id) 
        REFERENCES students(id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. Create enrollments table
-- Implements UNIQUE constraint to strictly prevent duplicate enrollments
CREATE TABLE IF NOT EXISTS enrollments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    course_id INT NOT NULL,
    enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'enrolled',
    CONSTRAINT fk_enrollment_student FOREIGN KEY (student_id) 
        REFERENCES students(id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_enrollment_course FOREIGN KEY (course_id) 
        REFERENCES courses(id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT uq_student_course UNIQUE (student_id, course_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6. Seed initial authentication credentials (Idempotent)
-- Default Administrator Account:
-- Email: admin@elearning.local
-- Password: Admin@123
INSERT IGNORE INTO users (email, password_hash, role, student_id)
VALUES (
    'admin@elearning.local',
    'pbkdf2:sha256:1000000$8PRaFkqRFhvD58t0$55904342ce6f616b382ffb49c8ed5cd043449892f6764cf212b748f88fe71506',
    'admin',
    NULL
);

-- Seed Student Account linked to existing sample student (student@example.com):
-- Email: student@example.com
-- Password: Student@123
INSERT IGNORE INTO users (email, password_hash, role, student_id)
SELECT 
    s.email,
    'pbkdf2:sha256:1000000$RWXgbhlbmE35xz0a$994a0d0b032a7bbf0c1adfa4ea2db1dea45675833da8310a1c4b0dc758c6a8f5',
    'student',
    s.id
FROM students s
WHERE s.email = 'student@example.com'
LIMIT 1;

-- Seed an enrollment for the sample student in the sample course if not already enrolled
INSERT IGNORE INTO enrollments (student_id, course_id, enrolled_at, status)
SELECT s.id, c.id, NOW(), 'enrolled'
FROM students s, courses c
WHERE s.email = 'student@example.com'
ORDER BY c.id ASC
LIMIT 1;

-- ============================================================================
-- Phase 2: Xen/XCP-ng Resource Monitoring & Historical Metrics Tables
-- ============================================================================

-- 7. Create VM and Host metrics history table
CREATE TABLE IF NOT EXISTS vm_metrics_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    vm_name VARCHAR(100) NOT NULL,
    vm_uuid VARCHAR(64) NULL,
    entity_type VARCHAR(20) NOT NULL DEFAULT 'vm',
    cpu_percent FLOAT NOT NULL DEFAULT 0.0,
    ram_percent FLOAT NOT NULL DEFAULT 0.0,
    allocated_ram_mb FLOAT NOT NULL DEFAULT 0.0,
    used_ram_mb FLOAT NOT NULL DEFAULT 0.0,
    vcpu_count INT NOT NULL DEFAULT 1,
    network_rx_bytes BIGINT NOT NULL DEFAULT 0,
    network_tx_bytes BIGINT NOT NULL DEFAULT 0,
    INDEX idx_metrics_vm_time (vm_name, timestamp),
    INDEX idx_metrics_time (timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 8. Create dynamic allocation recommendation history table
CREATE TABLE IF NOT EXISTS allocation_decisions_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    vm_name VARCHAR(100) NOT NULL,
    cpu_action VARCHAR(30) NOT NULL DEFAULT 'HOLD',
    ram_action VARCHAR(30) NOT NULL DEFAULT 'HOLD',
    current_vcpus INT NOT NULL DEFAULT 1,
    recommended_vcpus INT NOT NULL DEFAULT 1,
    current_ram_mb FLOAT NOT NULL DEFAULT 0.0,
    recommended_ram_mb FLOAT NOT NULL DEFAULT 0.0,
    rationale TEXT NULL,
    cooldown_active BOOLEAN NOT NULL DEFAULT FALSE,
    INDEX idx_decision_vm_time (vm_name, timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- Phase 3: Dynamic Resource Allocation Actuation & History
-- ============================================================================

-- 9. Create resource allocation history table for real CPU & RAM scaling events
CREATE TABLE IF NOT EXISTS resource_allocation_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    vm_name VARCHAR(100) NOT NULL,
    vm_uuid VARCHAR(64) NULL,
    resource_type VARCHAR(20) NOT NULL,
    previous_value FLOAT NOT NULL,
    requested_value FLOAT NOT NULL,
    actual_value FLOAT NOT NULL,
    trigger_reason TEXT NOT NULL,
    action_type VARCHAR(20) NOT NULL DEFAULT 'MANUAL',
    execution_status VARCHAR(20) NOT NULL DEFAULT 'SUCCESS',
    error_message TEXT NULL,
    initiated_by VARCHAR(100) NOT NULL DEFAULT 'system',
    controller_version VARCHAR(20) NOT NULL DEFAULT 'v2.0',
    xen_operation_id VARCHAR(64) NULL,
    verification_status VARCHAR(30) NOT NULL DEFAULT 'verified',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_alloc_vm_time (vm_name, created_at),
    INDEX idx_alloc_status (execution_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 10. Create workload simulation sessions table for live load generation tracking
CREATE TABLE IF NOT EXISTS workload_simulation_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL UNIQUE,
    target_vm VARCHAR(100) NOT NULL,
    workload_type VARCHAR(20) NOT NULL, -- 'cpu', 'ram', 'database'
    intensity_percent FLOAT NULL,
    workers INT NOT NULL DEFAULT 1,
    allocated_mb FLOAT NULL,
    duration_sec INT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'running', -- 'running', 'completed', 'stopped', 'error'
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    stopped_at TIMESTAMP NULL,
    initiated_by VARCHAR(100) NOT NULL DEFAULT 'admin',
    details TEXT NULL,
    INDEX idx_sim_vm_status (target_vm, status),
    INDEX idx_sim_time (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 11. Create dedicated transient test table for safe MariaDB load generation
-- Never interferes with real students, courses, enrollments or users tables
CREATE TABLE IF NOT EXISTS workload_simulation_test (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    payload VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_sim_test_session (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 12. Create student load test sessions table for real student traffic simulation
CREATE TABLE IF NOT EXISTS student_load_test_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL UNIQUE,
    target_vm VARCHAR(50) NOT NULL, -- 'app_vm', 'db_vm', 'both'
    simulated_students INT NOT NULL,
    ramp_up_sec INT NOT NULL DEFAULT 10,
    test_duration_sec INT NOT NULL DEFAULT 60,
    workload_intensity VARCHAR(30) NOT NULL DEFAULT 'medium',
    requests_per_student FLOAT NOT NULL DEFAULT 2.0,
    status VARCHAR(30) NOT NULL DEFAULT 'running', -- 'ramping_up', 'running', 'stopped', 'emergency_stopped', 'completed', 'error'
    total_requests INT NOT NULL DEFAULT 0,
    successful_requests INT NOT NULL DEFAULT 0,
    failed_requests INT NOT NULL DEFAULT 0,
    avg_response_time_ms FLOAT NOT NULL DEFAULT 0.0,
    peak_rps FLOAT NOT NULL DEFAULT 0.0,
    db_queries_total INT NOT NULL DEFAULT 0,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    stopped_at TIMESTAMP NULL,
    initiated_by VARCHAR(100) NOT NULL DEFAULT 'admin',
    error_message TEXT NULL,
    INDEX idx_sl_session (session_id),
    INDEX idx_sl_started (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- Phase 3 Upgrade: Controller Versioning & Verification Columns
-- ----------------------------------------------------------------------------
ALTER TABLE resource_allocation_history ADD COLUMN IF NOT EXISTS controller_version VARCHAR(20) DEFAULT 'v2.0';
ALTER TABLE resource_allocation_history ADD COLUMN IF NOT EXISTS xen_operation_id VARCHAR(64) NULL;
ALTER TABLE resource_allocation_history ADD COLUMN IF NOT EXISTS verification_status VARCHAR(30) DEFAULT 'verified';

