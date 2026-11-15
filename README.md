# Xen-Based Dynamic Resource Allocation for Scalable E-Learning Services

🎓 **College Project MVP**  
**Virtualization Platform:** XCP-ng (Xen Cloud Platform)  
**Management Console:** XO Lite (`10.189.191.175`)  
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
- **Real-Time Xen Monitoring:** Genuine telemetry collection from XCP-ng XAPI (physical host CPU/RAM, VM vCPUs, actual allocated RAM, CPU utilization %, memory ballooning %, network RX/TX).
- **Elasticity Preparation (Phase 3):** Advisory threshold evaluation and anti-thrashing cooldown engine.

---

## 2. Infrastructure & Virtual Machine Configuration

| Entity | Role | Current IP Address | Port(s) | OS & Software Stack |
| :--- | :--- | :--- | :--- | :--- |
| **XCP-ng Host** | Hypervisor | `10.189.191.175` | 80 / 443 | XCP-ng (Xen 4.17+), XO Lite |
| **VM 1: Alpine-DB** | Database Server | `10.189.191.248` | `3306` | Alpine Linux 3.24, MariaDB 11.8.9 |
| **VM 2: Alpine-Linux** | Application Server | `10.189.191.51` | `5000` (API), `8501` (UI), `80` (Nginx) | Alpine Linux 3.24, Python 3.14, Nginx 1.30.6 |

*Note: All IP addresses and VM names are read dynamically from environment variables (`.env`). No addresses are hardcoded.*

### Multi-Tier Decoupled Architecture

```
   ┌──────────────────────────────────────────────────────────────┐
   │                  Student / Administrator                     │
   │               (Browser on external laptop)                   │
   └──────────────────────────────┬───────────────────────────────┘
                                  │ HTTP (Port 8501 or 80)
                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│ VM 2: Alpine-Linux (10.189.191.51)                                     │
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
                                  │ Private Network: 10.189.191.51 -> 10.189.191.248
                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│ VM 1: Alpine-DB (10.189.191.248)                                       │
│                                                                        │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │ MariaDB 11.8.9 (Database: elearning)                           │   │
│   │ Tables: students, courses, users, enrollments, metrics_history │   │
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
│   ├── database.py                 # PyMySQL connection factory & idempotent migrations
│   ├── requirements.txt            # Backend dependencies (Python 3.14 compatible)
│   ├── routes/
│   │   ├── auth.py                 # POST /api/login, POST /api/logout, GET /api/auth/me
│   │   ├── dashboard.py            # GET /api/dashboard
│   │   ├── students.py             # GET, POST, DELETE /api/students
│   │   ├── courses.py              # GET, POST, PUT, DELETE /api/courses
│   │   ├── enrollments.py          # GET, POST, DELETE /api/enrollments
│   │   ├── health.py               # GET /api/health (Database connectivity check)
│   │   └── xen_routes.py           # Xen status, metrics, host, vms, and history routes
│   └── services/
│       ├── auth_service.py         # Password hashing & HMAC session tokens
│       ├── course_service.py       # Course CRUD logic
│       ├── dashboard_service.py    # MariaDB statistical aggregation
│       ├── enrollment_service.py   # Enrollment logic & duplicate prevention
│       ├── student_service.py      # Student profile & user account linkage
│       └── xen_service.py          # Xen monitoring engine service interface
├── frontend/
│   ├── app.py                      # Streamlit entrypoint & authentication routing
│   ├── api.py                      # REST API client connecting to Flask
│   ├── requirements.txt            # Frontend dependencies (Streamlit, requests, pandas)
│   ├── assets/
│   │   └── style.css               # Clean academic blue & white CSS design
│   ├── components/
│   │   ├── cards.py                # Reusable metric KPI cards & dynamic system banner
│   │   └── sidebar.py              # Role-aware navigation & infrastructure summary
│   └── pages/
│       ├── dashboard.py            # Real MariaDB metrics, charts, & recent activity
│       ├── students.py             # Student management (Admin)
│       ├── courses.py              # Course catalog (Student) & Course CRUD (Admin)
│       ├── enrollments.py          # My Enrollments (Student) & Registry (Admin)
│       ├── admin.py                # Administrator diagnostic hub
│       ├── xen_monitoring.py       # Live Xen Resource Monitoring Dashboard & Gauges
│       └── xen_architecture.py     # Educational visualization of Xen infrastructure
├── database/
│   ├── schema.sql                  # Complete canonical database schema
│   ├── migrations.sql              # Non-destructive, idempotent migration script
│   └── apply_migrations.py         # Automated database inspection & migration runner
├── xen_monitor/
│   ├── resource_monitor.py         # Background monitoring daemon & persistence scheduler
│   ├── xen_api_client.py           # Authenticated XCP-ng XAPI XML-RPC client
│   ├── vm_metrics.py               # Metric normalization & hardware mapping
│   ├── network_monitor.py          # Network RX/TX rate delta calculator
│   ├── allocation_engine.py        # Elasticity recommendation engine with cooldown
│   ├── monitor_config.py           # Threshold & credential environment parser
│   └── README.md                   # Phase 2 & 3 architectural specification
├── nginx/
│   └── elearning.conf              # Nginx reverse proxy config for Alpine Linux
├── tests/
│   ├── test_api.py                 # Automated unit tests for Phase 1 REST endpoints
│   └── test_xen_monitoring.py      # Automated unit tests for Phase 2 Xen monitoring (14 tests)
├── .env.example                    # Comprehensive environment variable reference
├── setup_alpine.sh                 # One-click Alpine Linux dependency installer
├── start_backend.sh                # Script to start Flask on 0.0.0.0:5000
├── start_frontend.sh               # Script to start Streamlit on 0.0.0.0:8501
└── README.md                       # Comprehensive project documentation
```

---

## 4. Database Schema & Migration Details

### Existing Records Preserved:
- **Database:** `elearning` on `10.189.191.248:3306`
- **User:** `elearning` / `elearning123`
- **Sample Student:** `Student One` (`student@example.com`)
- **Sample Course:** `Introduction to E-Learning`

### Non-Destructive Migration (`database/migrations.sql`):
1. **`students`:** Ensures `id`, `name`, `email`, and `created_at` exist.
2. **`courses`:** Adds `course_code` (`CS-101`) and `created_at` if missing.
3. **`users`:** Role-based access table (`id`, `email`, `password_hash`, `role`, `student_id`).
4. **`enrollments`:** Junction table with `UNIQUE (student_id, course_id)` to prevent duplicate enrollments.
5. **`vm_metrics_history`:** Time-series telemetry storage for host & VM metrics (`timestamp`, `vm_name`, `vm_uuid`, `entity_type`, `cpu_percent`, `ram_percent`, `allocated_ram_mb`, `used_ram_mb`, `vcpu_count`, `network_rx_bytes`, `network_tx_bytes`).
6. **`allocation_decisions_history`:** Audit trail for Phase 3 elasticity recommendations (`vm_name`, `cpu_action`, `ram_action`, `current_vcpus`, `recommended_vcpus`, `current_ram_mb`, `recommended_ram_mb`, `rationale`, `cooldown_active`).

---

## 5. Alpine Linux Installation & Deployment Guide

Follow these steps on **VM 2: Alpine-Linux** (`10.189.191.51`).

### Step 1: Update System & Install Dependencies
Run in the Alpine Linux terminal:
```bash
apk update
apk add python3 py3-pip py3-virtualenv gcc musl-dev python3-dev libffi-dev mariadb-client curl nginx
```
*(Alternatively, execute `./setup_alpine.sh` which automates all steps).*

### Step 2: Create Python Virtual Environment
```bash
cd /opt/elearning   # Or your project directory
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
nc -zv 10.189.191.248 3306

# Run the automated migration script
python3 database/apply_migrations.py
```
*Expected output: `[SUCCESS] 8 migration statements processed successfully!`*

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
   http://10.189.191.51:8501
   ```
3. You will see the **Xen E-Learning Platform** login portal.

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
curl -s http://10.189.191.51:5000/api/health
```

### 2. User Authentication
```bash
curl -s -X POST http://10.189.191.51:5000/api/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@elearning.local", "password":"Admin@123"}'
```

### 3. Dashboard Real Metrics
```bash
curl -s http://10.189.191.51:5000/api/dashboard
```

### 4. Course Management
```bash
curl -s http://10.189.191.51:5000/api/courses
```

### 5. Student Management
```bash
curl -s http://10.189.191.51:5000/api/students
```

### 6. Course Enrollment
```bash
curl -s http://10.189.191.51:5000/api/enrollments
```

### 7. Xen Virtualization Telemetry
```bash
curl -s http://10.189.191.51:5000/api/xen/status
```

### 8. Real-Time Consolidated Xen Metrics
```bash
curl -s http://10.189.191.51:5000/api/xen/metrics
```

### 9. Hypervisor Host Hardware Metrics
```bash
curl -s http://10.189.191.51:5000/api/xen/host
```

### 10. Discovered Virtual Machines
```bash
curl -s http://10.189.191.51:5000/api/xen/vms
```

### 11. Single VM Runtime Telemetry (App VM or DB VM)
```bash
curl -s http://10.189.191.51:5000/api/xen/vms/Alpine-Linux/metrics
```

### 12. Monitoring Daemon Health & Status
```bash
curl -s http://10.189.191.51:5000/api/xen/monitor/status
```

### 13. Historical Telemetry for Time-Series Charting
```bash
curl -s "http://10.189.191.51:5000/api/xen/history?limit=50"
```

---

## 10. Xen-Based Dynamic Resource Allocation (Phase 2 & Phase 3)

The project title emphasizes: **"Xen-Based Dynamic Resource Allocation for Scalable E-Learning Services"**.

### Phase 1: Decoupled Multi-VM Architecture (Complete)
- Responsive e-learning web application running across two Alpine Linux VMs (Application Server & MariaDB Database Server).
- Private virtual bridged networking with verified zero packet loss.

### Phase 2: Real-Time Xen/XCP-ng Resource Monitoring (Complete)
Implemented in `xen_monitor/`:
1. **XCP-ng XAPI Client (`xen_api_client.py`):**
   - Connects to XCP-ng hypervisor (`10.189.191.175`) over XML-RPC (port 443/80) with timeout socket transports.
   - Dynamically discovers guest VM UUIDs by actual Xen name (`Alpine-Linux` and `Alpine-DB`).
   - Retrieves host hardware cores, CPU load, total/free RAM, and running VM count.
   - Extracts VM vCPU counts, allocated RAM, guest memory usage, and VIF network RX/TX bytes.
2. **Metric Normalization & Rate Tracking (`vm_metrics.py`, `network_monitor.py`):**
   - Calculates real-time network throughput (KB/s, MB/s) from delta byte counters.
   - Normalizes host and VM metrics into unified data structures.
3. **Database Telemetry Persistence (`resource_monitor.py`):**
   - Stores time-series metrics into `vm_metrics_history` and `allocation_decisions_history`.
4. **Streamlit Monitoring Interface (`frontend/pages/xen_monitoring.py`):**
   - Displays real-time hypervisor status banner, CPU and RAM radial gauges, KPI metric cards, VM comparison matrix, and historical line charts.
   - Includes automatic 5-second polling refresh toggle and immediate manual refresh.

### Phase 3: Elasticity Recommendation Engine (Prepared & Non-Destructive)
Implemented in `xen_monitor/allocation_engine.py`:
- **CPU Scaling Rules:** Recommends scaling vCPUs up when CPU utilization exceeds 75%; recommends scaling down when utilization falls below 25%.
- **Memory Scaling Rules:** Recommends ballooning RAM by +512 MB when RAM utilization exceeds 80%.
- **Safety Hysteresis:** Enforces minimum/maximum hardware bounds and a 60-second cooldown period to prevent resource flapping.
- **Safety Guarantee:** Phase 2 recommendations are purely advisory and logged to MariaDB; no automatic reboots or hypervisor reconfigurations occur.

---

## 11. Running Automated Tests

Run the complete automated test suite covering Phase 1 REST APIs and Phase 2 Xen monitoring engine:
```bash
python3 -m unittest discover tests
```
*Result: 30/30 tests passing.*
