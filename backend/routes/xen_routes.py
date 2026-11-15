from functools import wraps
from flask import Blueprint, jsonify, request
from backend.services.auth_service import verify_session_token
from backend.services.xen_service import (
    get_xen_cluster_metadata,
    read_local_vm_telemetry,
    get_realtime_metrics,
    get_host_resource_metrics,
    get_discovered_vms,
    get_single_vm_metrics,
    get_monitor_health,
    get_metrics_history,
    get_allocation_controller_status,
    get_allocation_recommendations,
    get_allocation_history,
    set_automation_mode,
    set_emergency_stop_status,
    reset_emergency_stop_status,
    reboot_vm_service,
    apply_manual_cpu_allocation,
    apply_manual_ram_allocation,
    apply_pending_recommendation,
    transition_vm_to_baseline,
    execute_baseline_maintenance_service,
    get_workload_simulator_status,
    start_cpu_workload_service,
    start_ram_workload_service,
    start_database_workload_service,
    stop_workload_service,
    stop_all_workloads_service,
    get_student_load_status,
    start_student_load_service,
    stop_student_load_service,
    emergency_stop_student_load_service,
    run_student_load_preflight,
    execute_simulated_student_db_query
)

xen_bp = Blueprint("xen", __name__, url_prefix="/api/xen")

ADMIN_ROLE_VARIANTS = {"admin", "administrator", "adm", "root"}

def is_admin_role(role: Any) -> bool:
    """Safely check if role matches any administrator variation (admin, administrator, ADMIN, etc.)."""
    if not role or not isinstance(role, str):
        return False
    return role.strip().lower() in ADMIN_ROLE_VARIANTS

def admin_required(f):
    """Enforce administrator role authentication for critical actuation operations."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"success": False, "error": "Authorization header missing or invalid"}), 401
        token = auth_header.replace("Bearer ", "").strip()
        payload = verify_session_token(token)
        if not payload:
            return jsonify({"success": False, "error": "Invalid or expired session token"}), 401
        if not is_admin_role(payload.get("role")):
            return jsonify({"success": False, "error": "Administrator privilege required"}), 403
        request.user = payload
        return f(*args, **kwargs)
    return decorated_function

@xen_bp.route("/status", methods=["GET"])
def xen_status():
    """
    GET /api/xen/status
    Returns XCP-ng virtualization metadata, VM roles, and Phase 3 specifications.
    """
    try:
        data = get_xen_cluster_metadata()
        return jsonify({
            "success": True,
            "data": data
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/telemetry", methods=["GET"])
def vm_telemetry():
    """
    GET /api/xen/telemetry
    Returns real guest OS CPU and memory telemetry from current Alpine Linux host.
    """
    try:
        telemetry = read_local_vm_telemetry()
        return jsonify({
            "success": True,
            "data": telemetry
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/metrics", methods=["GET"])
def xen_metrics():
    """
    GET /api/xen/metrics
    Returns live consolidated metrics from XCP-ng hypervisor, Application VM, and Database VM.
    """
    try:
        data = get_realtime_metrics()
        return jsonify({
            "success": True,
            "data": data
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/host", methods=["GET"])
def xen_host():
    """
    GET /api/xen/host
    Returns physical hypervisor hardware metrics (cores, CPU %, total/available RAM, running VMs).
    """
    try:
        host_data = get_host_resource_metrics()
        return jsonify({
            "success": True,
            "data": host_data
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/vms", methods=["GET"])
def xen_vms():
    """
    GET /api/xen/vms
    Returns list of discovered VMs with power states, vCPUs, and memory limits.
    """
    try:
        vms_list = get_discovered_vms()
        return jsonify({
            "success": True,
            "count": len(vms_list),
            "data": vms_list
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/vms/<vm_id>/metrics", methods=["GET"])
def xen_vm_metrics(vm_id):
    """
    GET /api/xen/vms/<vm_id>/metrics
    Returns live metrics for a specific VM by UUID or name.
    """
    try:
        vm_data = get_single_vm_metrics(vm_id)
        if not vm_data:
            return jsonify({
                "success": False,
                "error": f"VM with identifier '{vm_id}' was not discovered on XCP-ng host."
            }), 404
        return jsonify({
            "success": True,
            "data": vm_data
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/monitor/status", methods=["GET"])
def xen_monitor_status():
    """
    GET /api/xen/monitor/status
    Returns monitoring engine status (online/offline, last update time, failures, config).
    """
    try:
        status_data = get_monitor_health()
        return jsonify({
            "success": True,
            "data": status_data
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/history", methods=["GET"])
@xen_bp.route("/metrics/history", methods=["GET"])
def xen_history():
    """
    GET /api/xen/history?limit=50&vm_name=...
    GET /api/xen/metrics/history?limit=50&vm_name=...
    Returns historical telemetry records from the database for time-series charting.
    Never fabricates telemetry; returns empty data if none exist.
    """
    try:
        vm_name = request.args.get("vm_name")
        limit_arg = request.args.get("limit", 50)
        try:
            limit = int(limit_arg)
        except (ValueError, TypeError):
            limit = 50

        history_data = get_metrics_history(vm_name=vm_name, limit=limit)
        return jsonify({
            "success": True,
            "count": len(history_data),
            "data": history_data or []
        }), 200
    except Exception as e:
        return jsonify({
            "success": True,
            "count": 0,
            "data": [],
            "warning": "Historical telemetry data temporarily unavailable."
        }), 200

# -------------------------------------------------------------
# Phase 3: Dynamic Resource Allocation Endpoints
# -------------------------------------------------------------
@xen_bp.route("/allocation/status", methods=["GET"])
def xen_allocation_status():
    """
    GET /api/xen/allocation/status
    Returns allocation controller mode, emergency stop status, limits, and recommendations.
    """
    try:
        data = get_allocation_controller_status()
        return jsonify({
            "success": True,
            "data": data
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/allocation/recommendations", methods=["GET"])
def xen_allocation_recommendations():
    """
    GET /api/xen/allocation/recommendations
    Returns real-time scaling recommendations for monitored VMs.
    """
    try:
        data = get_allocation_recommendations()
        return jsonify({
            "success": True,
            "data": data
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/allocation/history", methods=["GET"])
def xen_allocation_history_route():
    """
    GET /api/xen/allocation/history?limit=50&vm_name=...
    Returns audit trail of executed allocation actions from resource_allocation_history.
    """
    try:
        vm_name = request.args.get("vm_name")
        limit_arg = request.args.get("limit", 50)
        try:
            limit = int(limit_arg)
        except (ValueError, TypeError):
            limit = 50

        history = get_allocation_history(vm_name=vm_name, limit=limit)
        return jsonify({
            "success": True,
            "count": len(history),
            "data": history
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/allocation/enable", methods=["POST"])
@admin_required
def xen_allocation_enable():
    """
    POST /api/xen/allocation/enable
    Switches controller mode to 'auto' for automated closed-loop scaling.
    """
    try:
        mode = set_automation_mode("auto")
        return jsonify({
            "success": True,
            "message": "Automated dynamic resource allocation enabled.",
            "mode": mode
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/allocation/disable", methods=["POST"])
@admin_required
def xen_allocation_disable():
    """
    POST /api/xen/allocation/disable
    Switches controller mode to 'manual' (recommendations only, no automated scaling).
    """
    try:
        mode = set_automation_mode("manual")
        return jsonify({
            "success": True,
            "message": "Automated dynamic resource allocation disabled. Manual mode active.",
            "mode": mode
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/allocation/mode", methods=["POST"])
@admin_required
def xen_allocation_set_mode():
    """
    POST /api/xen/allocation/mode
    Switches dynamic resource allocation mode ('auto' or 'manual').
    Request JSON: { "mode": "auto" } or { "mode": "manual" }
    """
    try:
        data = request.get_json(silent=True) or {}
        requested_mode = str(data.get("mode", "manual")).lower().strip()
        if requested_mode not in ("auto", "manual"):
            return jsonify({
                "success": False,
                "error": f"Invalid mode '{requested_mode}'. Supported modes: 'auto', 'manual'"
            }), 400

        mode = set_automation_mode(requested_mode)
        message = (
            "Automated dynamic resource allocation enabled."
            if mode == "auto"
            else "Automated dynamic resource allocation disabled. Manual mode active."
        )
        return jsonify({
            "success": True,
            "message": message,
            "mode": mode
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/allocation/emergency-stop", methods=["POST"])
@admin_required
def xen_allocation_emergency_stop():
    """
    POST /api/xen/allocation/emergency-stop
    Immediately engages or disengages emergency stop.
    Request JSON: { "action": "engage" } or { "action": "resume" }
    """
    try:
        body = request.get_json(silent=True) or {}
        action = body.get("action", "engage").lower().strip()
        initiated_by = request.user.get("email", "admin")
        enabled = False if action in ("resume", "disengage", "false", "off", "reset") else True
        if enabled:
            new_state = set_emergency_stop_status(True, reason="Administrator emergency stop", initiated_by=initiated_by)
        else:
            new_state = reset_emergency_stop_status(reason="Administrator emergency stop disengaged", initiated_by=initiated_by)
        return jsonify({
            "success": True,
            "emergency_stop": new_state,
            "message": "Emergency stop ENGAGED. Automated scaling and synthetic load suspended." if new_state else "Emergency stop DISENGAGED. Mode returned to MANUAL."
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/allocation/emergency-stop/reset", methods=["POST"])
@admin_required
def xen_allocation_emergency_stop_reset():
    """
    POST /api/xen/allocation/emergency-stop/reset
    Explicit administrator reset of emergency stop with required reason and confirmation.
    Request JSON: { "confirmed": true, "reason": "System nominal" }
    """
    try:
        body = request.get_json(silent=True) or {}
        confirmed = body.get("confirmed", False)
        reason = body.get("reason", "").strip() or "Administrator inspected system and verified nominal state"
        if not confirmed:
            return jsonify({"success": False, "error": "Confirmation is required to reset emergency stop."}), 400

        initiated_by = request.user.get("email", "admin")
        reset_emergency_stop_status(reason=reason, initiated_by=initiated_by)
        return jsonify({
            "success": True,
            "emergency_stop": False,
            "mode": "manual",
            "message": f"Emergency stop successfully reset by {initiated_by}. Operational mode returned to MANUAL."
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/vm/reboot", methods=["POST"])
@admin_required
def xen_vm_reboot():
    """
    POST /api/xen/vm/reboot
    Controlled VM reboot via XenAPI to apply startup baseline configuration.
    Request JSON: { "vm_name": "Alpine-Linux", "confirmed": true, "reason": "..." }
    """
    try:
        body = request.get_json(silent=True) or {}
        vm_name = body.get("vm_name")
        confirmed = body.get("confirmed", False)
        reason = body.get("reason", "Controlled reboot to apply vCPU baseline")

        if not vm_name:
            return jsonify({"success": False, "error": "Field 'vm_name' is required."}), 400
        if not confirmed:
            return jsonify({"success": False, "error": "Explicit confirmation required to initiate VM reboot."}), 400

        initiated_by = request.user.get("email", "admin")
        res = reboot_vm_service(vm_name, reason=reason, initiated_by=initiated_by)
        status_code = 200 if res.get("success") else 500
        return jsonify(res), status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/allocation/cpu", methods=["POST"])
@admin_required
def xen_allocation_cpu():
    """
    POST /api/xen/allocation/cpu
    Admin manual CPU allocation request.
    Request JSON: { "vm_name": "Alpine-Linux", "vcpus": 2, "reason": "..." }
    """
    try:
        data = request.get_json(silent=True) or {}
        vm_name = data.get("vm_name")
        vcpus = data.get("vcpus")
        reason = data.get("reason", "Administrator manual adjustment")

        if not vm_name:
            return jsonify({"success": False, "error": "Field 'vm_name' is required."}), 400
        if vcpus is None:
            return jsonify({"success": False, "error": "Field 'vcpus' is required."}), 400

        try:
            vcpus = int(vcpus)
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "Field 'vcpus' must be an integer."}), 400

        initiated_by = request.user.get("email", "admin")
        result = apply_manual_cpu_allocation(vm_name, vcpus, reason=reason, initiated_by=initiated_by)
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/allocation/ram", methods=["POST"])
@admin_required
def xen_allocation_ram():
    """
    POST /api/xen/allocation/ram
    Admin manual dynamic RAM allocation (ballooning) request.
    Request JSON: { "vm_name": "Alpine-Linux", "ram_mb": 2048, "reason": "..." }
    """
    try:
        data = request.get_json(silent=True) or {}
        vm_name = data.get("vm_name")
        ram_mb = data.get("ram_mb")
        reason = data.get("reason", "Administrator manual adjustment")

        if not vm_name:
            return jsonify({"success": False, "error": "Field 'vm_name' is required."}), 400
        if ram_mb is None:
            return jsonify({"success": False, "error": "Field 'ram_mb' is required."}), 400

        try:
            ram_mb = float(ram_mb)
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "Field 'ram_mb' must be a numeric value."}), 400

        initiated_by = request.user.get("email", "admin")
        result = apply_manual_ram_allocation(vm_name, ram_mb, reason=reason, initiated_by=initiated_by)
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/allocation/apply-recommended", methods=["POST"])
@xen_bp.route("/allocation/apply-recommendation", methods=["POST"])
@admin_required
def xen_allocation_apply_recommended():
    """
    POST /api/xen/allocation/apply-recommended
    Apply pending recommendation for a specific VM.
    Request JSON: { "vm_name": "Alpine-Linux" }
    """
    try:
        data = request.get_json(silent=True) or {}
        vm_name = data.get("vm_name")
        if not vm_name:
            return jsonify({"success": False, "error": "Field 'vm_name' is required."}), 400

        initiated_by = request.user.get("email", "admin")
        result = apply_pending_recommendation(vm_name, initiated_by=initiated_by)
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/allocation/transition-baseline", methods=["POST"])
@admin_required
def xen_allocation_transition_baseline():
    """
    POST /api/xen/allocation/transition-baseline
    Admin approved transition of a VM to baseline policy (1 vCPU, 1024 MB RAM).
    Request JSON: { "vm_name": "Alpine-Linux" }
    """
    try:
        data = request.get_json(silent=True) or {}
        vm_name = data.get("vm_name")
        if not vm_name:
            return jsonify({"success": False, "error": "Field 'vm_name' is required."}), 400

        initiated_by = request.user.get("email", "admin")
        result = transition_vm_to_baseline(vm_name, initiated_by=initiated_by)
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/vm/baseline-maintenance", methods=["POST"])
@admin_required
def xen_vm_baseline_maintenance():
    """
    POST /api/xen/vm/baseline-maintenance
    Administrator-approved controlled baseline maintenance procedure:
    Gracefully halt -> configure startup 1 vCPU & 1024 MB RAM -> restart VM -> verify readback.
    Request JSON: { "vm_name": "Alpine-Linux" }
    """
    try:
        data = request.get_json(silent=True) or {}
        vm_name = data.get("vm_name")
        if not vm_name:
            return jsonify({"success": False, "error": "Field 'vm_name' is required."}), 400

        initiated_by = request.user.get("email", "admin")
        result = execute_baseline_maintenance_service(vm_name, initiated_by=initiated_by)
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# -------------------------------------------------------------
# Workload Simulator Endpoints
# -------------------------------------------------------------
@xen_bp.route("/workload/status", methods=["GET"])
def xen_workload_status():
    """
    GET /api/xen/workload/status
    Returns status of active synthetic workload tests and available guest memory.
    """
    try:
        status = get_workload_simulator_status()
        return jsonify({"success": True, "data": status}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/workload/cpu/start", methods=["POST"])
@admin_required
def xen_workload_cpu_start():
    """
    POST /api/xen/workload/cpu/start
    Start CPU workload generation.
    Request JSON: { "target_vm": "Alpine-Linux", "intensity_percent": 75, "workers": 2, "duration_sec": 60 }
    """
    try:
        data = request.get_json(silent=True) or {}
        target_vm = data.get("target_vm", "Alpine-Linux")
        intensity = float(data.get("intensity_percent", 75.0))
        workers = int(data.get("workers", 2))
        duration = int(data.get("duration_sec", 60))
        initiated_by = request.user.get("email", "admin")

        result = start_cpu_workload_service(
            target_vm=target_vm,
            intensity_percent=intensity,
            workers=workers,
            duration_sec=duration,
            initiated_by=initiated_by
        )
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/workload/cpu/stop", methods=["POST"])
@admin_required
def xen_workload_cpu_stop():
    """
    POST /api/xen/workload/cpu/stop
    Stop active CPU workload test.
    Request JSON: { "session_id": "..." } (optional, stops running CPU test if omitted)
    """
    try:
        data = request.get_json(silent=True) or {}
        session_id = data.get("session_id")
        if not session_id:
            # Find running CPU session
            status = get_workload_simulator_status()
            running = status.get("running_cpu_session")
            if running:
                session_id = running.get("session_id")

        if not session_id:
            return jsonify({"success": False, "error": "No running CPU workload session found."}), 404

        result = stop_workload_service(session_id)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/workload/ram/start", methods=["POST"])
@admin_required
def xen_workload_ram_start():
    """
    POST /api/xen/workload/ram/start
    Start RAM allocation workload with OOM safety check.
    Request JSON: { "target_vm": "Alpine-Linux", "allocated_mb": 256, "duration_sec": 60 }
    """
    try:
        data = request.get_json(silent=True) or {}
        target_vm = data.get("target_vm", "Alpine-Linux")
        allocated_mb = float(data.get("allocated_mb", 256.0))
        duration = int(data.get("duration_sec", 60))
        initiated_by = request.user.get("email", "admin")

        result = start_ram_workload_service(
            target_vm=target_vm,
            allocated_mb=allocated_mb,
            duration_sec=duration,
            initiated_by=initiated_by
        )
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/workload/ram/stop", methods=["POST"])
@admin_required
def xen_workload_ram_stop():
    """
    POST /api/xen/workload/ram/stop
    Stop active RAM allocation workload.
    """
    try:
        data = request.get_json(silent=True) or {}
        session_id = data.get("session_id")
        if not session_id:
            status = get_workload_simulator_status()
            running = status.get("running_ram_session")
            if running:
                session_id = running.get("session_id")

        if not session_id:
            return jsonify({"success": False, "error": "No running RAM workload session found."}), 404

        result = stop_workload_service(session_id)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/workload/db/start", methods=["POST"])
@admin_required
def xen_workload_db_start():
    """
    POST /api/xen/workload/db/start
    Start safe MariaDB transaction workload.
    Request JSON: { "target_vm": "Alpine-DB", "intensity": "medium", "workers": 2, "duration_sec": 60 }
    """
    try:
        data = request.get_json(silent=True) or {}
        target_vm = data.get("target_vm", "Alpine-DB")
        intensity = str(data.get("intensity", "medium"))
        workers = int(data.get("workers", 2))
        duration = int(data.get("duration_sec", 60))
        initiated_by = request.user.get("email", "admin")

        result = start_database_workload_service(
            target_vm=target_vm,
            intensity=intensity,
            workers=workers,
            duration_sec=duration,
            initiated_by=initiated_by
        )
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/workload/db/stop", methods=["POST"])
@admin_required
def xen_workload_db_stop():
    """
    POST /api/xen/workload/db/stop
    Stop active Database workload test.
    """
    try:
        data = request.get_json(silent=True) or {}
        session_id = data.get("session_id")
        if not session_id:
            status = get_workload_simulator_status()
            running = status.get("running_db_session")
            if running:
                session_id = running.get("session_id")

        if not session_id:
            return jsonify({"success": False, "error": "No running Database workload session found."}), 404

        result = stop_workload_service(session_id)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/workload/emergency-stop", methods=["POST"])
@admin_required
def xen_workload_emergency_stop():
    """
    POST /api/xen/workload/emergency-stop
    Immediate Emergency Stop for all active workload generators.
    """
    try:
        result = stop_all_workloads_service()
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# -------------------------------------------------------------
# Student Load Simulator Routes (Real Student Traffic)
# -------------------------------------------------------------

@xen_bp.route("/student-load/status", methods=["GET"])
def xen_student_load_status():
    """
    GET /api/xen/student-load/status
    Returns live statistics from real student load simulation.
    """
    try:
        status = get_student_load_status()
        return jsonify({"success": True, "data": status}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/student-load/start", methods=["POST"])
@admin_required
def xen_student_load_start():
    """
    POST /api/xen/student-load/start
    Start real student traffic generation (1 to 200 concurrent users).
    Body: { target_vm, simulated_students, ramp_up_duration, test_duration, requests_per_student, workload_intensity }
    """
    try:
        data = request.get_json(silent=True) or {}
        target_vm = data.get("target_vm", "app_vm")
        students = int(data.get("simulated_students", 10))
        ramp_up = int(data.get("ramp_up_duration", 10))
        duration = int(data.get("test_duration", 60))
        req_per_sec = float(data.get("requests_per_student", 2.0))
        intensity = str(data.get("workload_intensity", "medium"))
        initiated_by = request.user.get("email", "admin")

        res = start_student_load_service(
            target_vm=target_vm,
            simulated_students=students,
            ramp_up_duration=ramp_up,
            test_duration=duration,
            requests_per_student=req_per_sec,
            workload_intensity=intensity,
            initiated_by=initiated_by
        )
        status_code = 200 if res.get("success") else 400
        return jsonify(res), status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/student-load/stop", methods=["POST"])
@admin_required
def xen_student_load_stop():
    """
    POST /api/xen/student-load/stop
    Gracefully stops active student load test.
    """
    try:
        data = request.get_json(silent=True) or {}
        session_id = data.get("session_id")
        res = stop_student_load_service(session_id)
        return jsonify(res), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/student-load/emergency-stop", methods=["POST"])
@admin_required
def xen_student_load_emergency_stop():
    """
    POST /api/xen/student-load/emergency-stop
    Immediate Emergency Stop for student load generators and scaling decisions.
    """
    try:
        res = emergency_stop_student_load_service()
        return jsonify(res), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/student-load/db-query", methods=["POST"])
def xen_student_load_db_query():
    """
    POST /api/xen/student-load/db-query
    Internal endpoint called by simulated student workers to generate safe MariaDB transactions.
    """
    try:
        data = request.get_json(silent=True) or {}
        session_id = data.get("session_id", "sim-default")
        student_id = int(data.get("student_id", 1))
        res = execute_simulated_student_db_query(session_id, student_id)
        return jsonify(res), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@xen_bp.route("/student-load/preflight", methods=["GET", "POST"])
def xen_student_load_preflight():
    """
    GET/POST /api/xen/student-load/preflight
    Execute preflight authentication check to verify synthetic student login,
    bearer token generation, and REST API access before full load execution.
    """
    try:
        res = run_student_load_preflight()
        status_code = 200 if res.get("success") else 400
        return jsonify(res), status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


