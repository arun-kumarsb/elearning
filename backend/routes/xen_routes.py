from flask import Blueprint, jsonify, request
from backend.services.xen_service import (
    get_xen_cluster_metadata,
    read_local_vm_telemetry,
    get_realtime_metrics,
    get_host_resource_metrics,
    get_discovered_vms,
    get_single_vm_metrics,
    get_monitor_health,
    get_metrics_history
)

xen_bp = Blueprint("xen", __name__, url_prefix="/api/xen")

@xen_bp.route("/status", methods=["GET"])
def xen_status():
    """
    GET /api/xen/status
    Returns XCP-ng virtualization metadata, VM roles, and Phase 2 Dynamic Resource Allocation specifications.
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
def xen_history():
    """
    GET /api/xen/history?limit=50&vm_name=...
    Returns historical telemetry records from the database for time-series charting.
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
        # Avoid exposing credentials or internal stack traces
        return jsonify({
            "success": True,
            "count": 0,
            "data": [],
            "warning": "Historical telemetry data temporarily unavailable."
        }), 200
