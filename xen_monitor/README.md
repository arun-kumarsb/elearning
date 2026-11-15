# Xen-Based Dynamic Resource Allocation Engine (Phase 2 & Phase 3)

## College Project Overview
- **Title:** Xen-Based Dynamic Resource Allocation for Scalable E-Learning Services
- **Virtualization Platform:** XCP-ng (Xen Cloud Platform)
- **Host Management IP:** Configurable via `XCP_NG_HOST` (current `10.189.191.175`)
- **Application VM:** `Alpine-Linux` (`10.189.191.51`)
- **Database VM:** `Alpine-DB` (`10.189.191.248`)

---

## 1. Phase 2 Architecture: Real-Time Resource Monitoring

Phase 2 implements a robust, genuine monitoring engine that collects physical hypervisor and virtual machine metrics using the **XCP-ng XAPI (XenAPI XML-RPC interface)**. No metrics or UUIDs are fabricated: when the hypervisor is offline or unreachable, the system transparently indicates disconnected/offline status with full diagnostic details.

```
       ┌────────────────────────────────────────────────────────────┐
       │                XCP-ng Hypervisor (Dom0)                    │
       │                   IP: 10.189.191.175                       │
       │            XAPI Management Daemon (XML-RPC)                │
       └─────────────────────────────┬──────────────────────────────┘
                                     │ XML-RPC / HTTPS (port 443/80)
                                     ▼
       ┌────────────────────────────────────────────────────────────┐
       │          xen_monitor Engine (resource_monitor.py)          │
       │                                                            │
       │  ┌───────────────────────┐   ┌──────────────────────────┐  │
       │  │   xen_api_client.py   │   │     vm_metrics.py        │  │
       │  │ (Session, VM Discovery│   │ (Normalization & Format) │  │
       │  │  & Hardware Ingestion)│   └─────────────┬────────────┘  │
       │  └───────────┬───────────┘                 │               │
       │              │                             ▼               │
       │              │               ┌──────────────────────────┐  │
       │              │               │    network_monitor.py    │  │
       │              │               │(Throughput delta & rates)│  │
       │              │               └─────────────┬────────────┘  │
       │              ▼                             ▼               │
       │  ┌──────────────────────────────────────────────────────┐  │
       │  │        allocation_engine.py (Phase 3 Preparation)     │  │
       │  │  (Threshold Rules, Bounds, Cooldown Hysteresis)      │  │
       │  └───────────────────────────┬──────────────────────────┘  │
       └──────────────────────────────┼─────────────────────────────┘
                                      │
               ┌──────────────────────┴──────────────────────┐
               ▼                                             ▼
┌──────────────────────────────┐              ┌──────────────────────────────┐
│  MariaDB Persistence Tables  │              │    Flask Backend API & UI    │
│  - vm_metrics_history        │              │  - /api/xen/metrics          │
│  - allocation_decisions_hist │              │  - Streamlit Monitoring UI   │
└──────────────────────────────┘              └──────────────────────────────┘
```

---

## 2. Component Breakdown

| Module | Description |
| :--- | :--- |
| `xen_api_client.py` | Authenticated XML-RPC client for XCP-ng. Implements SSL verification toggle, timeout socket transports, session management, dynamic VM discovery by name (`Alpine-Linux`, `Alpine-DB`), and physical host hardware queries. |
| `vm_metrics.py` | Normalizes heterogeneous XAPI records into standard dictionaries: Host cores/RAM/running VMs, and guest vCPUs, CPU %, RAM allocation/usage %, and network I/O. |
| `network_monitor.py` | Calculates network throughput (KB/s, MB/s) by taking deltas across consecutive polling intervals. |
| `allocation_engine.py` | Evaluates CPU and RAM pressure against configurable elasticity thresholds, checks min/max boundaries, enforces cooldown periods (hysteresis), and produces non-destructive Phase 3 scaling recommendations. |
| `monitor_config.py` | Reads all hypervisor credentials, IP addresses, VM names, thresholds, and intervals dynamically from environment variables. |
| `resource_monitor.py` | Orchestrates the monitoring daemon thread, runs periodic polling (default 5s), persists historical metrics to MariaDB/SQLite, caches latest state, and exposes thread-safe query methods for Flask. |

---

## 3. Metrics Collected

### Hypervisor (Host) Metrics:
- **Total Physical CPU Cores:** Derived from `host_cpu.get_all_records`.
- **Host CPU Utilization (%):** Average utilization across physical cores.
- **Physical RAM:** Total, used, available, and percentage.
- **VM Count:** Total VMs and currently running VMs.

### Guest VM Metrics (Application VM & Database VM):
- **VM Identity:** Dynamic UUID, name label (`Alpine-Linux`, `Alpine-DB`), and power state (`Running` / `Halted`).
- **CPU Metrics:** vCPU count and current CPU utilization percentage.
- **RAM Metrics:** Configured dynamic/static limits, actual allocated RAM (MB), current memory usage (MB), and utilization percentage.
- **Network I/O:** Total bytes received (RX) and transmitted (TX), plus calculated throughput (KB/s, MB/s).

---

## 4. Phase 3: Dynamic CPU and RAM Allocation Architecture

Phase 3 implements real, closed-loop actuation and administrator controls over XCP-ng XenAPI:

### 1. Actuation Methods (`xen_api_client.py`):
- **Live vCPU Scaling:** Actuates live CPU hotplugging via `VM.set_VCPUs_number_live(session, vm_ref, vcpus)` on running VMs, and updates `VM.set_VCPUs_at_startup` for reboot persistence.
- **Dynamic Memory Ballooning:** Updates dynamic memory boundaries via `VM.set_memory_dynamic_range(session, vm_ref, dynamic_min, dynamic_max)` and live balloon targets via `VM.set_memory_target_live`.
- **Limits & Invariants Enforcement:** Strictly enforces `static_min <= dynamic_min <= dynamic_max <= static_max`. Prevents scaling beyond physical host RAM limits (with a 256 MB safety cushion).
- **Post-Change Verification:** Re-queries `VM.get_record` from XenAPI to confirm that the hypervisor successfully updated the configuration.

### 2. Intelligent Scaling Policy (`allocation_engine.py`):
- **Resource Baseline & Policies:**
  - **Application VM (`Alpine-Linux`):** Baseline 1 vCPU, 1024 MB RAM (Min: 1 vCPU, 1024 MB RAM; Max: 4 vCPUs, 4096 MB RAM).
  - **Database VM (`Alpine-DB`):** Baseline 1 vCPU, 1024 MB RAM (Min: 1 vCPU, 1024 MB RAM; Max: 4 vCPUs, 4096 MB RAM), with safe transition validation.
- **CPU Policy:**
  - `cpu_percent > 80.0%`: Scale up (+1 vCPU up to `max_vcpus=4`).
  - `cpu_percent < 25.0%`: Scale down (-1 vCPU down to `min_vcpus=1`).
  - `25.0% - 80.0%`: Hold nominal state.
- **RAM Policy:**
  - `ram_percent > 85.0%`: Scale up (+512 MB up to `max_ram_mb=4096`).
  - `ram_percent < 30.0%`: Scale down (-512 MB down to `min_ram_mb=1024`, preserving a 256 MB safety headroom over current usage).
  - `30.0% - 85.0%`: Hold nominal state.
- **Hysteresis & Consecutive Breach Tracking:**
  - **Scale-Up:** Requires 3 consecutive breaches (`scale_up_consecutive_threshold=3`) before triggering.
  - **Scale-Down:** Requires 6 consecutive breaches (`scale_down_consecutive_threshold=6`) before releasing resources to prevent thrashing.
- **Independent Cooldowns:** Independent per-resource tracking `(vm_name, 'cpu')` and `(vm_name, 'ram')` with a 60-second cooldown window.
- **Concurrency Locking:** Thread-safe `_allocation_lock` guarantees that simultaneous manual and automatic requests cannot trigger conflicting hypervisor calls.
- **Stale Telemetry Protection:** Telemetry older than 30 seconds is marked stale, and automatic scaling decisions are halted until fresh metrics arrive.
- **Maintenance Status:** When Xen guest tools or VM configuration lack hotplug or dynamic ballooning support, the engine marks the status as `MAINTENANCE_REQUIRED` instead of failing silently.

### 3. Safety Interlocks, Emergency Stop & Live Workload Simulator:
- `ALLOCATION_MODE=manual` (default) ensures scaling requires administrator confirmation. Switching to `auto` enables autonomous closed-loop execution.
- **Emergency Stop Toggle:** Immediately pauses automated scaling operations AND terminates all active synthetic workload generators without stopping, rebooting, or migrating virtual machines.
- **Live Workload Simulator (`backend/services/workload_service.py`):**
  - **CPU Stress Generator:** Configurable intensity (25%, 50%, 75%, 90%), worker threads (1-4), and duration (30-180s) with active duty-cycling.
  - **RAM Memory Allocator:** Allocates real resident memory (128 MB, 256 MB, 512 MB, 768 MB) touching 4096-byte pages with pre-allocation guest OOM headroom safety checks.
  - **MariaDB Workload Generator:** Safe synthetic transactional workload against dedicated transient table `workload_simulation_test`, rolling back transactions and guaranteeing zero impact on core e-learning student, course, and enrollment data.
  - **Audit Sessions:** Real-time state and completed runs tracked in `workload_simulation_sessions`.
- **Safety Invariant:** Never automatically reboots, halts, or migrates VMs.

---

## 5. Configuration & Environment Variables

All settings are configured through environment variables:

```ini
# XCP-ng / Xen Hypervisor
XCP_NG_HOST=10.189.191.175
XCP_NG_USERNAME=root
XCP_NG_PASSWORD=your_password
XCP_NG_VERIFY_SSL=False

# Guest Virtual Machines
APP_VM_NAME=Alpine-Linux
APP_VM_IP=10.189.191.51
DB_VM_NAME=Alpine-DB
DB_VM_IP=10.189.191.248

# Monitoring & Elasticity Engine (Phase 3 Parameters)
MONITOR_INTERVAL=5
ALLOCATION_MODE=manual
COOLDOWN_PERIOD=60
SCALE_UP_CONSECUTIVE_THRESHOLD=3
SCALE_DOWN_CONSECUTIVE_THRESHOLD=6

# CPU Allocation Limits & Thresholds
CPU_SCALE_UP_THRESHOLD=80.0
CPU_SCALE_DOWN_THRESHOLD=25.0
APP_MIN_VCPUS=1
APP_MAX_VCPUS=4
APP_INITIAL_VCPUS=1
DB_MIN_VCPUS=1
DB_MAX_VCPUS=4
DB_INITIAL_VCPUS=1

# RAM Dynamic Allocation Limits & Thresholds
RAM_SCALE_UP_THRESHOLD=85.0
RAM_SCALE_DOWN_THRESHOLD=30.0
RAM_INCREMENT_MB=512.0
APP_MIN_RAM_MB=1024.0
APP_MAX_RAM_MB=4096.0
APP_INITIAL_RAM_MB=1024.0
DB_MIN_RAM_MB=1024.0
DB_MAX_RAM_MB=4096.0
DB_INITIAL_RAM_MB=1024.0
```

---

## 6. Running Standalone

To execute a single monitoring poll or run the monitor as an independent process:

```bash
# Single poll output in JSON format
python3 -c "from xen_monitor.resource_monitor import XenResourceMonitor; m = XenResourceMonitor(); print(m.poll_once())"

# Continuous monitoring daemon
python3 xen_monitor/resource_monitor.py
```
