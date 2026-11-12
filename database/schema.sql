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

