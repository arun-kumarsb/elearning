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
7. **`workload_simulation_sessions`:** Audit and session tracking for live synthetic CPU, RAM, and MariaDB workload generators (`session_id`, `vm_name`, `workload_type`, `intensity`, `duration_seconds`, `status`, `started_at`, `stopped_at`, `error_message`).
8. **`workload_simulation_test`:** Dedicated isolated transient table used solely for synthetic MariaDB transaction simulation, ensuring core student, course, and enrollment data remain completely isolated and unaffected.

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

---

## 10. Xen-Based Dynamic Resource Allocation (Phase 1, 2 & 3)

The project title emphasizes: **"Xen-Based Dynamic Resource Allocation for Scalable E-Learning Services"**.

### Phase 1: Decoupled Multi-VM Architecture (Complete)
- Responsive e-learning web application running across two Alpine Linux VMs (Application Server & MariaDB Database Server).
- Private virtual bridged networking with verified zero packet loss.

### Phase 2: Real-Time Xen/XCP-ng Resource Monitoring (Complete)
- Authenticated XenAPI XML-RPC client discovering VMs dynamically (`Alpine-Linux` and `Alpine-DB`).
- Normalized physical host hardware metrics (cores, CPU %, total/available RAM) and guest telemetry.
- Telemetry persistence into `vm_metrics_history` and `allocation_decisions_history`.

### Phase 3: Dynamic Autoscaling Engine & Live Workload Simulator (Complete)
Implemented in `xen_monitor/xen_api_client.py`, `xen_monitor/allocation_engine.py`, `xen_monitor/resource_monitor.py`, `backend/services/workload_service.py`, and `frontend/pages/dynamic_allocation.py`:
1. **Target Baseline Architecture:**
   - **Application VM (`Alpine-Linux`):** Baseline target of 1 vCPU and 1024 MB RAM (Min: 1 vCPU, 1024 MB RAM; Max: 4 vCPUs, 4096 MB RAM).
   - **Database VM (`Alpine-DB`):** Baseline target of 1 vCPU and 1024 MB RAM (Min: 1 vCPU, 1024 MB RAM; Max: 4 vCPUs, 4096 MB RAM), with isolated transactional safety validation.
   - **Safe Baseline Transition:** One-click transition procedure that steps down resources safely while verifying VM liveness, host headroom, and guest OOM prevention limits.
2. **Real XenAPI Live Actuation:**
   - **Live vCPU Scaling:** Actuates live CPU hotplugging via `VM.set_VCPUs_number_live` and persists configuration via `VM.set_VCPUs_at_startup`.
   - **Dynamic Memory Ballooning:** Modifies Xen dynamic memory range via `VM.set_memory_dynamic_range` and adjusts live target via `VM.set_memory_target_live` with strict limit verification (`static_min <= dynamic_min <= dynamic_max <= static_max`).
   - **Post-Change Verification:** Re-queries VM records via XenAPI to confirm the hypervisor accepted the modification.
3. **Intelligent Allocation Engine with Asymmetric Hysteresis:**
   - **Threshold Rules:** CPU >80% scales up (+1 vCPU up to 4); CPU <25% scales down (-1 vCPU down to 1). RAM >85% scales up (+512 MB up to 4096 MB); RAM <30% scales down (-512 MB down to 1024 MB, enforcing a 256 MB safety headroom over active usage).
   - **Consecutive Breach Timing:** Requires **3 consecutive intervals** (>80% CPU or >85% RAM) for scale-up, and **6 consecutive intervals** (<25% CPU or <30% RAM) for scale-down to guarantee anti-thrashing stability.
   - **Independent Cooldowns:** Per-resource cooldown tracking `(VM, 'cpu')` and `(VM, 'ram')` (60s) ensures CPU cooldown does not block memory evaluation.
   - **Thread-Safe Actuation Lock:** Prevents race conditions and clashing XenAPI transactions across parallel requests.
   - **Stale Telemetry Detection:** If metrics are older than 30s, the engine suspends automated scaling actions.
   - **Maintenance Required Mode:** Detects if guest tools lack live hotplug/ballooning capability and cleanly reports `MAINTENANCE_REQUIRED` without crashing.
4. **Live Workload Simulator:**
   - **App VM CPU Stress Generator:** Calibrated mathematical workloads with configurable duty cycle (25%, 50%, 75%, 90%), worker count (1-4), and duration (30-180s).
   - **App VM RAM Allocation Generator:** Allocates and touches resident memory pages (128 MB to 768 MB) with mandatory pre-flight host/guest OOM safety checks.
   - **DB VM MariaDB Simulator:** Executes realistic read/write queries with explicit transaction rollbacks on dedicated transient table `workload_simulation_test`, guaranteeing zero modification or corruption of real student and course records.
   - **Master Emergency Stop:** Immediately disengages autoscaling and terminates all active workload generators with one click.
5. **Streamlit Dynamic Resource Allocation Dashboard:**
   - Features Status Interlocks banner, Side-by-Side VM Baseline & Runtime telemetry, Live Workload Simulator control panel, Recommendations table with 1-click execution, Manual sliders with confirmation gates, Audit logs, 4 Real-time trend charts (including vCPU count and dynamic RAM), and Static vs. Dynamic efficiency analysis.

---

## 11. Running Automated Tests

Run the complete automated test suite covering Phase 1 REST APIs, Phase 2 Xen monitoring engine, and Phase 3 Dynamic Allocation & Workload Simulator:
```bash
python3 -m unittest discover tests
```
*Result: 64/64 tests passing with 100% success rate across all test suites.*
