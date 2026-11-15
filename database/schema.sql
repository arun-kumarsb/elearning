-- ============================================================================
-- Xen-Based Dynamic Resource Allocation for Scalable E-Learning Services
-- Complete Database Schema Specification
-- Database: MariaDB 11.8.9 (Alpine Linux 3.24)
-- Host: 10.240.109.248:3306
-- ============================================================================

CREATE DATABASE IF NOT EXISTS elearning CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE elearning;

-- ----------------------------------------------------------------------------
-- Table: students
-- Purpose: Registered students in the e-learning system
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS students (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(191) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- Table: courses
-- Purpose: Available courses offered in the e-learning system
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS courses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    course_code VARCHAR(50) NULL,
    title VARCHAR(191) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- Table: users
-- Purpose: Authentication credentials and role-based access control
-- Roles: 'admin', 'student'
-- ----------------------------------------------------------------------------
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

-- ----------------------------------------------------------------------------
-- Table: enrollments
-- Purpose: Student course enrollments with unique constraint to prevent duplicates
-- ----------------------------------------------------------------------------
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

-- ----------------------------------------------------------------------------
-- Initial Sample Data (Preserves Existing Records)
-- ----------------------------------------------------------------------------
INSERT IGNORE INTO students (id, name, email) VALUES 
(1, 'Student One', 'student@example.com');

INSERT IGNORE INTO courses (id, course_code, title, description) VALUES 
(1, 'CS-101', 'Introduction to E-Learning', 'First sample course introducing virtual learning environments and scalable architectures.');

-- Default Admin User: admin@elearning.local / Admin@123
INSERT IGNORE INTO users (email, password_hash, role, student_id) VALUES 
('admin@elearning.local', 'pbkdf2:sha256:1000000$8PRaFkqRFhvD58t0$55904342ce6f616b382ffb49c8ed5cd043449892f6764cf212b748f88fe71506', 'admin', NULL);

-- Default Student User: student@example.com / Student@123
INSERT IGNORE INTO users (email, password_hash, role, student_id) VALUES 
('student@example.com', 'pbkdf2:sha256:1000000$RWXgbhlbmE35xz0a$994a0d0b032a7bbf0c1adfa4ea2db1dea45675833da8310a1c4b0dc758c6a8f5', 'student', 1);

-- Initial Enrollment
INSERT IGNORE INTO enrollments (student_id, course_id) VALUES (1, 1);

-- ----------------------------------------------------------------------------
-- Phase 2: Table: vm_metrics_history
-- Purpose: Persistent real-time Xen hypervisor & VM telemetry storage
-- ----------------------------------------------------------------------------
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

-- ----------------------------------------------------------------------------
-- Phase 2: Table: allocation_decisions_history
-- Purpose: History of rule-based dynamic resource scaling recommendations
-- ----------------------------------------------------------------------------
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

-- ----------------------------------------------------------------------------
-- Phase 3: Table: resource_allocation_history
-- Purpose: Audit log of CPU and RAM dynamic allocation actuation events
-- ----------------------------------------------------------------------------
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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_alloc_vm_time (vm_name, created_at),
    INDEX idx_alloc_status (execution_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- Phase 3: Table: workload_simulation_sessions
-- Purpose: Tracking live synthetic CPU, RAM, and Database workload sessions
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS workload_simulation_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL UNIQUE,
    target_vm VARCHAR(100) NOT NULL,
    workload_type VARCHAR(20) NOT NULL,
    intensity_percent FLOAT NULL,
    workers INT NOT NULL DEFAULT 1,
    allocated_mb FLOAT NULL,
    duration_sec INT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    stopped_at TIMESTAMP NULL,
    initiated_by VARCHAR(100) NOT NULL DEFAULT 'admin',
    details TEXT NULL,
    INDEX idx_sim_vm_status (target_vm, status),
    INDEX idx_sim_time (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- Phase 3: Table: workload_simulation_test
-- Purpose: Dedicated transient table for safe MariaDB load generation
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS workload_simulation_test (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    payload VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_sim_test_session (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- Phase 3: Table: student_load_test_sessions
-- Purpose: Tracking real student load testing sessions (1 to 200 concurrent users)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS student_load_test_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL UNIQUE,
    target_vm VARCHAR(50) NOT NULL,
    simulated_students INT NOT NULL,
    ramp_up_sec INT NOT NULL DEFAULT 10,
    test_duration_sec INT NOT NULL DEFAULT 60,
    workload_intensity VARCHAR(30) NOT NULL DEFAULT 'medium',
    requests_per_student FLOAT NOT NULL DEFAULT 2.0,
    status VARCHAR(30) NOT NULL DEFAULT 'running',
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



