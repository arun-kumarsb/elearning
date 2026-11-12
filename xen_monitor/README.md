# Xen-Based Dynamic Resource Allocation Architecture (Phase 2 Design)

## College Project Context
- **Title:** Xen-Based Dynamic Resource Allocation for Scalable E-Learning Services
- **Platform:** XCP-ng (Xen Cloud Platform)
- **Host Management IP:** `10.240.109.196` (XO Lite / XAPI)
- **Application VM:** Alpine-Linux-New (`10.240.109.51`)
- **Database VM:** Alpine-DB (`10.240.109.248`)

---

## 1. Architectural Philosophy
In Phase 1 (current MVP), the multi-tier virtualized e-learning web application is decoupled and operational across two separate Alpine Linux VMs communicating over a private virtual bridge.

In Phase 2, this module (`xen_monitor/`) provides hypervisor-level elasticity:
1. **Workload Monitoring:** Real-time polling of VM CPU utilization, memory pressure, active network sockets, and database query concurrency.
2. **Elasticity Algorithm:** Threshold-based dynamic scaling with cooldown hysteresis to prevent resource flapping.
3. **Hypervisor Actuation:** Direct programmatic interaction with XCP-ng XAPI (XenAPI XML-RPC or `xe` CLI commands) to adjust vCPUs and dynamically resize memory via the Xen ballooning driver (`xen-balloon`).

---

## 2. Xen Dynamic Scaling Mechanics

### A. Memory Dynamic Allocation (Memory Ballooning)
Xen employs the **Balloon Driver** (`xen-balloon`) within the guest kernel (supported natively in Alpine Linux).
- **Static Maximum:** Hardware upper limit of RAM assigned to the VM.
- **Dynamic Maximum:** Target ceiling currently granted by the hypervisor.
- **Dynamic Minimum:** Guaranteed baseline RAM the VM will not be squeezed below.

When memory load on `Alpine-Linux-New` exceeds 85%:
```bash
# Hypervisor Command (executed on XCP-ng host 10.240.109.196)
xe vm-memory-limits-set uuid=<VM_UUID> \
    static-min=1024MiB \
    dynamic-min=1024MiB \
    dynamic-max=3072MiB \
    static-max=4096MiB
```

### B. Dynamic vCPU Allocation
Xen's credit scheduler allows hot-plugging and adjusting virtual CPU allocations:
```bash
# Increase vCPUs from 2 to 4 under peak exam or quiz load
xe vm-vcpu-set uuid=<VM_UUID> vcpus-number=4
```

---

## 3. Modular Separation
To guarantee absolute reliability and follow strict software engineering practices:
- The core Flask backend (`backend/`) and Streamlit frontend (`frontend/`) do **not** depend on hypervisor root privileges.
- The `xen_monitor` module can be deployed as an independent daemon or run directly on the management domain (Dom0 / XCP-ng host) or an orchestration controller.

