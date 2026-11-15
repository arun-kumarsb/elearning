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
│       ├── student_load_service.py # Real Student Load Simulator (1-200 concurrent HTTP/DB threads)
│       ├── workload_service.py     # Live CPU, RAM, & MariaDB transactional workload simulator
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
│       ├── intelligent_orchestration.py # Unified Intelligent Resource Orchestration & Load Simulator
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
│   ├── test_xen_monitoring.py      # Automated unit tests for Phase 2 Xen monitoring (14 tests)
│   ├── test_dynamic_allocation.py  # Automated unit tests for Phase 3 Dynamic Allocation (28 tests)
│   └── test_student_load_orchestration.py # Verification of genuine telemetry, simulator & orchestration (20 tests)
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
7. **`workload_simulation_sessions`:** Audit and session tracking for live synthetic CPU, RAM, and MariaDB workload generators (`session_id`, `vm_name`, `workload_type`, `intensity`, `duration_seconds`, `status`, `started_at`, `stopped_at`, `error_message`).
8. **`workload_simulation_test`:** Dedicated isolated transient table used solely for synthetic MariaDB transaction simulation, ensuring core student, course, and enrollment data remain completely isolated and unaffected.
9. **`student_load_test_sessions`:** Audit and live metric tracking for student-driven load simulation sessions (`session_id`, `target_service`, `concurrent_students`, `ramp_up_seconds`, `duration_seconds`, `intensity_profile`, `status`, `total_requests`, `successful_requests`, `failed_requests`, `avg_rps`, `avg_latency_ms`, `peak_latency_ms`, `avg_qps`, `started_at`, `stopped_at`, `error_message`).
10. **Pre-Seeded Simulated Student Pool:** Dedicated pool of 200 synthetic student accounts (`sim_student_1@elearning.test` to `sim_student_200@elearning.test`) created with standard credentials (`SimStudent@123`), guaranteeing production and evaluation student records are never corrupted.

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
*Expected output: `[SUCCESS] 9 migration statements processed successfully!`*

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

### 14. Dynamic Resource Allocation Status
```bash
curl -s http://10.189.191.51:5000/api/xen/allocation/status
```

### 15. Real-Time Allocation Recommendations
```bash
curl -s http://10.189.191.51:5000/api/xen/allocation/recommendations
```

### 16. Allocation Audit Trail History
```bash
curl -s "http://10.189.191.51:5000/api/xen/allocation/history?limit=50"
```

### 17. Enable Autonomous Dynamic Scaling (Admin Auth Required)
```bash
curl -s -X POST http://10.189.191.51:5000/api/xen/allocation/enable \
  -H "Authorization: Bearer <ADMIN_TOKEN>"
```

### 18. Emergency Stop (Safety Interlock)
```bash
curl -s -X POST http://10.189.191.51:5000/api/xen/allocation/emergency-stop \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"action":"engage"}'
```

### 19. Manual Live vCPU Allocation
```bash
curl -s -X POST http://10.189.191.51:5000/api/xen/allocation/cpu \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"vm_name":"Alpine-Linux", "vcpus": 3, "reason":"Capacity scaling"}'
```

### 20. Manual Dynamic RAM Ballooning
```bash
curl -s -X POST http://10.189.191.51:5000/api/xen/allocation/ram \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"vm_name":"Alpine-Linux", "ram_mb": 2560.0, "reason":"Memory expansion"}'
```

### 21. Live Workload Simulator: Start CPU Stress
```bash
curl -s -X POST http://10.189.191.51:5000/api/xen/workload/cpu \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"vm_name":"Alpine-Linux", "intensity": 75.0, "workers": 2, "duration_seconds": 60}'
```

### 22. Live Workload Simulator: Start RAM Allocation
```bash
curl -s -X POST http://10.189.191.51:5000/api/xen/workload/ram \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"vm_name":"Alpine-Linux", "ram_mb": 256.0, "duration_seconds": 60}'
```

### 23. Live Workload Simulator: Start MariaDB Synthetic Load
```bash
curl -s -X POST http://10.189.191.51:5000/api/xen/workload/db \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"vm_name":"Alpine-DB", "qps": 20.0, "duration_seconds": 60}'
```

### 24. Live Workload Simulator: Status & Active Sessions
```bash
curl -s http://10.189.191.51:5000/api/xen/workload/status
```

### 25. Emergency Stop (All Workloads + Scaling Halted Immediately)
```bash
curl -s -X POST http://10.189.191.51:5000/api/xen/workload/emergency-stop \
  -H "Authorization: Bearer <ADMIN_TOKEN>"
```

### 26. Safe Baseline Transition (1 vCPU, 1024 MB RAM)
```bash
curl -s -X POST http://10.189.191.51:5000/api/xen/allocation/transition-baseline \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"vm_name":"Alpine-Linux"}'
```

### 27. Student Load Simulator: Status & Live Statistics
```bash
curl -s http://10.189.191.51:5000/api/xen/student-load/status
```

### 28. Student Load Simulator: Start Multi-Student Test (1 to 200 Students)
```bash
curl -s -X POST http://10.189.191.51:5000/api/xen/student-load/start \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"target_service":"both", "concurrent_students":50, "intensity_profile":"medium", "duration_seconds":120, "ramp_up_seconds":10}'
```

### 29. Student Load Simulator: Stop Running Test
```bash
curl -s -X POST http://10.189.191.51:5000/api/xen/student-load/stop \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"load-test-abc123"}'
```

### 30. Student Load Simulator: Master Emergency Stop
```bash
curl -s -X POST http://10.189.191.51:5000/api/xen/student-load/emergency-stop \
  -H "Authorization: Bearer <ADMIN_TOKEN>"
```

### 31. Student Load Simulator: Execute Simulated Student DB Transaction
```bash
curl -s -X POST http://10.189.191.51:5000/api/xen/student-load/db-query \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"student_email":"sim_student_1@elearning.test"}'
```

---

## 10. Xen-Based Dynamic Resource Allocation & Intelligent Orchestration

The project title emphasizes: **"Xen-Based Dynamic Resource Allocation for Scalable E-Learning Services"**.

Active Development Branch: `phase3-student-load-autoscaling`

### Phase 1: Decoupled Multi-VM Architecture (Complete)
- Responsive e-learning web application running across two Alpine Linux VMs (Application Server & MariaDB Database Server).
- Private virtual bridged networking with verified zero packet loss.

### Phase 2: Real-Time Xen/XCP-ng Resource Monitoring (Complete)
- Authenticated XenAPI XML-RPC client discovering VMs dynamically (`Alpine-Linux` and `Alpine-DB`).
- Normalized physical host hardware metrics (cores, CPU %, total/available RAM) and guest telemetry.
- Telemetry persistence into `vm_metrics_history` and `allocation_decisions_history`.

### Phase 3: Real Student-Driven Dynamic Allocation & Unified Orchestration (Complete)
Implemented in `backend/services/student_load_service.py`, `xen_monitor/xen_api_client.py`, `xen_monitor/allocation_engine.py`, `xen_monitor/resource_monitor.py`, `xen_monitor/vm_metrics.py`, and `frontend/pages/intelligent_orchestration.py`:

#### Unified Primary Section: `🚀 Intelligent Resource Orchestration`
Replaced the previous two disparate sections (`📈 Xen Resource Monitoring` and `⚡ Dynamic Resource Allocation`) with a single high-performance orchestration control deck comprising 9 coordinated components:

1. **System Status & Quick Action Banner:**
   - Displays real-time Xen hypervisor connection status, discovered VM state, active scaling mode (`Auto` vs `Manual`), and a prominent one-click Emergency Stop toggle.
2. **Student Load Simulator:**
   - Generates authentic, multi-threaded HTTP and database transactions representing 1, 5, 10, 25, 50, 100, 150, or 200 concurrent simulated students.
   - Three intensity profiles:
     - `Light`: Browsing courses, viewing profile (1–2 req/s per student).
     - `Medium`: Enrolling in courses, viewing dashboard, fetching active enrollments (3–5 req/s per student).
     - `Heavy`: High-frequency course enrollment, unenrollment, search, and transactional queries (8–12 req/s per student).
   - Gradual ramp-up (5s to 30s) avoiding sudden artificial spikes.
   - Dedicated pool of 200 synthetic accounts (`sim_student_1@elearning.test` to `sim_student_200@elearning.test`), preserving production data.
   - Live real-time KPIs: Active Students, Joining/Leaving status, Requests/sec (RPS), Database QPS, Latency (average & p95 ms), and Success Rate %.
3. **Side-by-Side VM Baseline vs. Live Telemetry Monitors:**
   - Displays real-time status for `Alpine-Linux` (UUID: `01cdb87c-408f-72bc-449c-0364a8e69647`) and `Alpine-DB` (UUID: `0a6dec09-0466-0079-4b66-80704b59587d`).
   - Dynamic UUID discovery by VM name with verification fallback.
   - Genuine CPU utilization calculated from consecutive Xen `VCPUs_CPU_usage` deltas divided by elapsed wall-clock time and vCPU count (with guest `/proc/stat` validation).
   - Strict separation of Xen-assigned memory (`memory_actual`) from guest OS memory (`/proc/meminfo` or `VM_guest_metrics`), completely eliminating the fake 100% RAM display.
   - Explicit `N/A` reporting when guest memory metrics are unavailable, triggering a safe `HOLD` to prevent hazardous premature downscaling.
4. **Real-Time Telemetry & Scaling Actuation Charts:**
   - Synchronized historical time-series plots:
     - Real-Time CPU Utilization % (App VM vs DB VM with 80% Scale-Up and 25% Scale-Down threshold lines).
     - Guest RAM Utilization % (App VM vs DB VM with 85% Scale-Up and 30% Scale-Down threshold lines).
     - Dynamic vCPU Count (Live stepping 1 -> 2 -> 3 -> 4 vCPUs).
     - Dynamic RAM Allocation vs Guest Used (MB) showing actual ballooning actions.
5. **Dynamic Autoscaling Decision Feed:**
   - Real-time display of evaluated scaling recommendations for both VMs.
   - Visual progress indicators for asymmetric hysteresis consecutive sample counters (Scale-up: 3 samples, Scale-down: 6 samples).
   - Explicit display of rationale, cooldown timers, and safety hold reasons.
6. **Autonomous Scaling Controls & Policy Rules:**
   - Mode switcher: `Autonomous Auto-Scaling` vs `Manual Administrator Override`.
   - Asymmetric Hysteresis Engine:
     - CPU Scale-Up: 3 consecutive readings >80% (+1 vCPU up to 4).
     - CPU Scale-Down: 6 consecutive readings <25% (-1 vCPU down to 1).
     - RAM Scale-Up: 3 consecutive readings >85% (+512 MB up to 4096 MB).
     - RAM Scale-Down: 6 consecutive readings <30% (-512 MB down to 1024 MB with 256 MB safety headroom).
     - Cooldown: 60s per-VM per-resource `(VM, 'cpu')` and `(VM, 'ram')`.
7. **Manual Resource Allocation Sliders:**
   - Live administrator controls to scale vCPUs (1 to 4) and RAM (1024 to 4096 MB in 256/512 MB increments).
   - Two-step confirmation with readback verification from XenAPI before reporting success.
8. **Safety Invariants & Diagnostic Health Panel:**
   - Master Emergency Stop halts both autoscaling and all active load simulator sessions within one polling tick.
   - Automated Safety Cutoff: Auto-terminates load tests if API/DB error rates exceed 50%.
   - Host capacity check: Requires at least 256 MB host free RAM headroom before any scale-up.
   - Non-destructive invariant: Zero VM reboots, shutdowns, or migrations.
9. **Historical Allocation & Student Load Audit Logs:**
   - Comprehensive audit trail of all manual and autonomous scaling actions, previous vs new values, success/failure status, and XenAPI error messages.
   - Complete history of student load simulation sessions with duration, total requests, error counts, and peak latency.

---

## 11. Running Automated Tests

Run the complete automated test suite covering Phase 1 REST APIs, Phase 2 Xen monitoring engine, Phase 3 Dynamic Allocation, and Phase 3 Student Load Orchestration:
```bash
python3 -m unittest discover tests
```
*Result: 86/86 tests passing with 100% success rate across all test suites.*
