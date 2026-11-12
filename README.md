# Xen-Based Dynamic Resource Allocation for Scalable E-Learning Services

🎓 **College Project MVP**  
**Virtualization Platform:** XCP-ng (Xen Cloud Platform)  
**Management Console:** XO Lite (`10.240.109.196`)  
**Target Operating System:** Alpine Linux 3.24  
**Runtime:** Python 3.14  

---

## 1. Project Overview

This project implements a functional, decoupled, and scalable e-learning web application MVP engineered to demonstrate multi-VM virtualization on an **XCP-ng / Xen** hypervisor infrastructure.

The platform separates the **Application Tier** (running Flask REST API + Streamlit Web Interface on Alpine Linux) from the **Database Tier** (running MariaDB 11.8.9 on an isolated Alpine Linux VM), communicating strictly over a private virtual network.

### Key Capabilities:
- **Role-Based Authentication:** Administrator and Student roles with cryptographic password hashing (PBKDF2-SHA256) and session management.
- **Main Dashboard:** Real-time metrics fetched from MariaDB (registered students, active courses, total enrollments, recent activity).
- **Student Management:** Full administrative lifecycle to view, search, inspect coursework, and register new students.
- **Course Management:** Administrative CRUD (create, view, update, delete with safety confirmation).
- **Course Enrollment:** Student catalog browsing, one-click enrollment, duplicate enrollment prevention (enforced at both application and database constraint levels).
- **Xen Elasticity Architecture:** Decoupled modular design prepared for Phase 2 dynamic CPU and RAM allocation via Xen XAPI and the Xen balloon driver (`xen-balloon`).

---

## 2. Infrastructure & Virtual Machine Configuration

| Entity | Role | IP Address | Port(s) | OS & Software Stack |
| :--- | :--- | :--- | :--- | :--- |
| **XCP-ng Host** | Hypervisor | `10.240.109.196` | 80 / 443 | XCP-ng (Xen 4.17+), XO Lite |
| **VM 1: Alpine-DB** | Database Server | `10.240.109.248` | `3306` | Alpine Linux 3.24, MariaDB 11.8.9 |
| **VM 2: Alpine-Linux-New** | Application Server | `10.240.109.201` | `5000` (API), `8501` (UI), `80` (Nginx) | Alpine Linux 3.24, Python 3.14, Nginx 1.30.6 |

### Multi-Tier Decoupled Architecture

```
   ┌──────────────────────────────────────────────────────────────┐
   │                  Student / Administrator                     │
   │               (Browser on external laptop)                   │
   └──────────────────────────────┬───────────────────────────────┘
                                  │ HTTP (Port 8501 or 80)
                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│ VM 2: Alpine-Linux-New (10.240.109.201)                                │
│                                                                        │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │ Streamlit Frontend (Port 8501)                                 │   │
│   │ (Modern Blue/White UI: Dashboard, Courses, Enrollments, Admin)  │   │
│   └─────────────────────────────┬──────────────────────────────────┘   │
│                                 │ REST API (JSON / HTTP Port 5000)     │
│                                 ▼                                      │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │ Flask REST API Backend (Port 5000)                             │   │
│   │ (Authentication, Validation, Business Services, Xen Telemetry) │   │
│   └─────────────────────────────┬──────────────────────────────────┘   │
└─────────────────────────────────┼──────────────────────────────────────┘
                                  │ TCP Port 3306 (PyMySQL)
                                  │ Private Network: 10.240.109.201 -> 10.240.109.248
                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│ VM 1: Alpine-DB (10.240.109.248)                                       │
│                                                                        │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │ MariaDB 11.8.9 (Database: elearning)                           │   │
│   │ Tables: students, courses, users, enrollments                  │   │
│   │ (Preserved existing records: Student One & Sample Course)      │   │
│   └────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Project Directory Structure

```
XenLearn/
├── backend/
│   ├── app.py                      # Flask Application Factory & Blueprints
│   ├── config.py                   # Environment configuration & DB parameters
│   ├── database.py                 # PyMySQL connection factory & auto-migration
│   ├── requirements.txt            # Backend dependencies (Python 3.14 compatible)
│   ├── routes/
│   │   ├── auth.py                 # POST /api/login, POST /api/logout, GET /api/auth/me
│   │   ├── dashboard.py            # GET /api/dashboard
│   │   ├── students.py             # GET, POST, DELETE /api/students
│   │   ├── courses.py              # GET, POST, PUT, DELETE /api/courses
│   │   ├── enrollments.py          # GET, POST, DELETE /api/enrollments
│   │   ├── health.py               # GET /api/health (Database connectivity check)
│   │   └── xen_routes.py           # GET /api/xen/status (Xen cluster metadata)
│   └── services/
│       ├── auth_service.py         # Password hashing & HMAC session tokens
│       ├── course_service.py       # Course CRUD logic
│       ├── dashboard_service.py    # MariaDB statistical aggregation
│       ├── enrollment_service.py   # Enrollment logic & duplicate prevention
│       ├── student_service.py      # Student profile & user account linkage
│       └── xen_service.py          # Guest telemetry & Xen Phase 2 spec
├── frontend/
│   ├── app.py                      # Streamlit entrypoint & authentication routing
│   ├── api.py                      # REST API client connecting to Flask
│   ├── requirements.txt            # Frontend dependencies (Streamlit, requests)
│   ├── assets/
│   │   └── style.css               # Clean academic blue & white CSS design
│   ├── components/
│   │   ├── cards.py                # Reusable metric KPI cards & system banner
│   │   └── sidebar.py              # Role-aware navigation & user details card
│   └── pages/
│       ├── dashboard.py            # Real MariaDB metrics, charts, & recent activity
│       ├── students.py             # Student management (Admin)
│       ├── courses.py              # Course catalog (Student) & Course CRUD (Admin)
│       ├── enrollments.py          # My Enrollments (Student) & Registry (Admin)
│       ├── admin.py                # Administrator diagnostic hub
│       └── xen_architecture.py     # Educational visualization of Xen infrastructure
├── database/
│   ├── schema.sql                  # Complete canonical database schema
│   ├── migrations.sql              # Non-destructive, idempotent migration script
│   └── apply_migrations.py         # Automated database inspection & migration runner
├── xen_monitor/
│   ├── resource_monitor.py         # Modular Xen Dynamic Allocation controller
│   └── README.md                   # Mathematical model for CPU/RAM ballooning
├── nginx/
│   └── elearning.conf              # Nginx reverse proxy config for Alpine Linux
├── tests/
│   └── test_api.py                 # Automated unit tests for all REST endpoints
├── .env.example                    # Environment variable reference
├── .env                            # Working configuration
├── .gitignore                      # Git exclusion rules
├── setup_alpine.sh                 # One-click Alpine Linux dependency installer
├── start_backend.sh                # Script to start Flask on 0.0.0.0:5000
├── start_frontend.sh               # Script to start Streamlit on 0.0.0.0:8501
└── README.md                       # Comprehensive project documentation
```

---

## 4. Database Schema & Migration Details

### Existing Records Preserved:
- **Database:** `elearning` on `10.240.109.248:3306`
- **User:** `elearning` / `elearning123`
- **Sample Student:** `Student One` (`student@example.com`)
- **Sample Course:** `Introduction to E-Learning`

### Non-Destructive Migration (`database/migrations.sql`):
1. **`students`:** Ensures `id`, `name`, `email`, and `created_at` exist.
2. **`courses`:** Adds `course_code` (`CS-101`) and `created_at` if missing.
3. **`users`:** Role-based access table (`id`, `email`, `password_hash`, `role`, `student_id`).
4. **`enrollments`:** Junction table with `UNIQUE (student_id, course_id)` to prevent duplicate enrollments.

---

## 5. Alpine Linux Installation & Deployment Guide

Follow these steps on **VM 2: Alpine-Linux-New** (`10.240.109.201`).

### Step 1: Update System & Install Dependencies
Run in the Alpine Linux terminal:
```bash
apk update
apk add python3 py3-pip py3-virtualenv gcc musl-dev python3-dev libffi-dev mariadb-client curl nginx
```
*(Alternatively, execute `./setup_alpine.sh` which automates all steps).*

### Step 2: Create Python Virtual Environment
```bash
cd /opt/XenLearn   # Or your project directory
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
```

### Step 3: Install Required Python Packages
```bash
pip install -r backend/requirements.txt
pip install -r frontend/requirements.txt
```

### Step 4: Run Database Migration
Verify network connectivity to the database VM and apply the migration:
```bash
# Verify TCP connectivity from VM 2 to VM 1
nc -zv 10.240.109.248 3306

# Run the automated migration script
python3 database/apply_migrations.py
```
*Expected output: `[SUCCESS] Database is fully synchronized and ready for backend operations!`*

---

## 6. Starting the Services

### Running the Backend (Flask REST API)
In terminal 1 (or background via tmux / nohup):
```bash
./start_backend.sh
```
*Flask binds to `0.0.0.0:5000`.*

### Running the Frontend (Streamlit)
In terminal 2 (or background via tmux / nohup):
```bash
./start_frontend.sh
```
*Streamlit binds to `0.0.0.0:8501` and is accessible across the entire network.*

---

## 7. Accessing from Another Laptop on the Network

To access the platform from another laptop connected to the same network:

1. Open your web browser (Chrome, Firefox, Edge, Safari).
2. Enter the URL:
   ```
   http://10.240.109.201:8501
   ```
3. You will see the **Xen E-Learning Platform** login portal.

### Optional: Nginx Reverse Proxy (Port 80)
If you prefer accessing via standard HTTP port 80 (`http://10.240.109.201/`):
```bash
cp nginx/elearning.conf /etc/nginx/http.d/elearning.conf
rc-service nginx restart
```

---

## 8. Default Login Credentials

| Role | Email Address | Password | Profile / Linkage |
| :--- | :--- | :--- | :--- |
| **🛡️ Administrator** | `admin@elearning.local` | `Admin@123` | Full access to students, courses, enrollments, and diagnostics |
| **🎓 Student** | `student@example.com` | `Student@123` | Linked to existing record: `Student One` (ID: 1) |

*(Quick test demo buttons are also provided on the login page for rapid 1-click evaluation).*

---

## 9. REST API Endpoint Reference & Testing

All endpoints can be verified using `curl` from any computer:

### 1. Health Check
```bash
curl -s http://10.240.109.201:5000/api/health
```

### 2. User Authentication
```bash
curl -s -X POST http://10.240.109.201:5000/api/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@elearning.local", "password":"Admin@123"}'
```

### 3. Dashboard Real Metrics
```bash
curl -s http://10.240.109.201:5000/api/dashboard
```

### 4. Course Management
```bash
# List all courses
curl -s http://10.240.109.201:5000/api/courses

# Create a new course
curl -s -X POST http://10.240.109.201:5000/api/courses \
  -H "Content-Type: application/json" \
  -d '{"course_code":"CS-201", "title":"Cloud Virtualization", "description":"Hands-on Xen and XCP-ng"}'

# Update a course
curl -s -X PUT http://10.240.109.201:5000/api/courses/1 \
  -H "Content-Type: application/json" \
  -d '{"course_code":"CS-101", "title":"Introduction to E-Learning (Updated)", "description":"Updated description"}'

# Delete a course
curl -s -X DELETE http://10.240.109.201:5000/api/courses/2
```

### 5. Student Management
```bash
# List all students
curl -s http://10.240.109.201:5000/api/students

# Register a student
curl -s -X POST http://10.240.109.201:5000/api/students \
  -H "Content-Type: application/json" \
  -d '{"name":"Alice Smith", "email":"alice@example.com", "password":"Student@123"}'

# Inspect student details & enrolled coursework
curl -s http://10.240.109.201:5000/api/students/1
```

### 6. Course Enrollment
```bash
# Enroll student 1 into course 1
curl -s -X POST http://10.240.109.201:5000/api/enrollments \
  -H "Content-Type: application/json" \
  -d '{"student_id": 1, "course_id": 1}'

# View all enrollments
curl -s http://10.240.109.201:5000/api/enrollments

# View student-specific enrollments
curl -s http://10.240.109.201:5000/api/students/1/enrollments
```

### 7. Xen Virtualization Telemetry
```bash
curl -s http://10.240.109.201:5000/api/xen/status
```

---

## 10. Xen-Based Dynamic Resource Allocation (Phase 2 Design)

The project title emphasizes: **"Xen-Based Dynamic Resource Allocation for Scalable E-Learning Services"**.

### Phase 1 MVP (Current Deliverable):
- Functional, responsive e-learning web application decoupled across two Alpine Linux VMs.
- Telemetry interfaces and modular architecture established in `xen_monitor/`.

### Phase 2 Architecture (Future Expansion):
Located in `xen_monitor/resource_monitor.py`:
1. **Dynamic Memory Ballooning:**
   - Guest VM runs Alpine Linux with the native Xen Balloon driver (`xen-balloon`).
   - When application memory pressure exceeds 85%, the hypervisor expands the dynamic ceiling:
     ```bash
     xe vm-memory-limits-set uuid=<VM_UUID> dynamic-max=3072MiB
     ```
2. **Dynamic vCPU Allocation:**
   - Under heavy student registration or online examination load, vCPUs are scaled dynamically:
     ```bash
     xe vm-vcpu-set uuid=<VM_UUID> vcpus-number=4
     ```
3. **Decoupled Security:**
   - The hypervisor automation module runs independently from the student-facing web app to ensure zero privilege escalation risks.

---

## 11. Running Unit Tests

Run the included automated test suite:
```bash
python3 -m unittest tests/test_api.py
```
*Result: 16/16 tests passing.*
