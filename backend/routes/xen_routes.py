from flask import Blueprint, jsonify
from backend.services.xen_service import get_xen_cluster_metadata, read_local_vm_telemetry

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

