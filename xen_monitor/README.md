# Xen-Based Dynamic Resource Allocation Engine (Phase 2 & Phase 3)

## College Project Overview
- **Title:** Xen-Based Dynamic Resource Allocation for Scalable E-Learning Services
- **Virtualization Platform:** XCP-ng (Xen Cloud Platform)
- **Host Management IP:** Configurable via `XCP_NG_HOST` (default `10.240.109.196`)
- **Application VM:** `Alpine-Linux-New` (`10.240.109.51`)
- **Database VM:** `Alpine-DB` (`10.240.109.248`)

---

## 1. Phase 2 Architecture: Real-Time Resource Monitoring

Phase 2 implements a robust, genuine monitoring engine that collects physical hypervisor and virtual machine metrics using the **XCP-ng XAPI (XenAPI XML-RPC interface)**. No metrics or UUIDs are fabricated: when the hypervisor is offline or unreachable, the system transparently indicates disconnected/offline status with full diagnostic details.

```
       ┌────────────────────────────────────────────────────────────┐
       │                XCP-ng Hypervisor (Dom0)                    │
       │                   IP: 10.240.109.196                       │
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
| `xen_api_client.py` | Authenticated XML-RPC client for XCP-ng. Implements SSL verification toggle, timeout socket transports, session management, dynamic VM discovery by name, and physical host hardware queries. |
| `vm_metrics.py` | Normalizes heterogeneous XAPI records into standard dictionaries: Host cores/RAM/running VMs, and guest vCPUs, CPU %, RAM allocation/usage %, and network I/O. |
| `network_monitor.py` | Calculates network throughput (KB/s, MB/s) by taking deltas across consecutive polling intervals. |
| `allocation_engine.py` | Evaluates CPU and RAM pressure against configurable elasticity thresholds, checks min/max boundaries, enforces cooldown periods (hysteresis), and produces non-destructive Phase 3 scaling recommendations. |
| `monitor_config.py` | Reads all hypervisor credentials, IP addresses, VM names, thresholds, and intervals from environment variables. |
| `resource_monitor.py` | Orchestrates the monitoring daemon thread, runs periodic polling (default 5s), persists historical metrics to MariaDB/SQLite, caches latest state, and exposes thread-safe query methods for Flask. |

---

## 3. Metrics Collected

### Hypervisor (Host) Metrics:
- **Total Physical CPU Cores:** Derived from `host_cpu.get_all_records`.
- **Host CPU Utilization (%):** Average utilization across physical cores.
- **Physical RAM:** Total, used, available, and percentage.
- **VM Count:** Total VMs and currently running VMs.

### Guest VM Metrics (Application VM & Database VM):
- **VM Identity:** Dynamic UUID, name label, and power state (`Running` / `Halted`).
- **CPU Metrics:** vCPU count and current CPU utilization percentage.
- **RAM Metrics:** Configured dynamic/static limits, actual allocated RAM (MB), current memory usage (MB), and utilization percentage.
- **Network I/O:** Total bytes received (RX) and transmitted (TX), plus calculated throughput (KB/s, MB/s).

---

## 4. Phase 3 Elasticity Recommendation Rules

The `allocation_engine.py` module evaluates telemetry against defined thresholds:

- **CPU Scale-Up:** If VM CPU utilization > `CPU_SCALE_UP_THRESHOLD` (default 80%), recommends incrementing vCPUs by +1 (up to max bound 4 vCPUs).
- **CPU Scale-Down:** If VM CPU utilization < `CPU_SCALE_DOWN_THRESHOLD` (default 20%), recommends decrementing vCPUs by -1 (down to min bound 1 vCPU).
- **RAM Scale-Up:** If VM memory utilization > `RAM_SCALE_UP_THRESHOLD` (default 85%), recommends ballooning RAM by +512 MB (up to max bound 4096 MB).
- **Cooldown Hysteresis:** An active scaling recommendation initiates a 60-second cooldown period per VM to prevent rapid flapping or oscillating resource changes.
- **Safety Guarantee:** Phase 2 recommendations are strictly advisory and recorded in `allocation_decisions_history`. No automatic hypervisor resizing or reboots occur without explicit authorization.

---

## 5. Configuration & Environment Variables

All settings are configured through environment variables:

```ini
# XCP-ng / Xen Hypervisor
XCP_NG_HOST=10.240.109.196
XCP_NG_USERNAME=root
XCP_NG_PASSWORD=your_password
XCP_NG_VERIFY_SSL=False

# Guest Virtual Machines
APP_VM_NAME=Alpine-Linux-New
APP_VM_IP=10.240.109.51
DB_VM_NAME=Alpine-DB
DB_VM_IP=10.240.109.248

# Monitoring & Elasticity Engine
MONITOR_INTERVAL=5
MONITOR_MODE=standalone
CPU_SCALE_UP_THRESHOLD=80.0
CPU_SCALE_DOWN_THRESHOLD=20.0
RAM_SCALE_UP_THRESHOLD=85.0
```

---

## 6. Running Standalone

To execute a single monitoring poll or run the monitor as an independent process:

```bash
# Single poll output in JSON format
python -c "from xen_monitor.resource_monitor import XenResourceMonitor; m = XenResourceMonitor(); print(m.poll_once())"

# Continuous monitoring daemon
python xen_monitor/resource_monitor.py
```
