"""
Streamlit Page: Dynamic Resource Allocation Control Panel (Phase 3)
Project: Xen-Based Dynamic Resource Allocation for Scalable E-Learning Services

Provides comprehensive administrator controls for Xen hypervisor autoscaling:
- Section A: Automation controller status, XenAPI health, and emergency interlocks
- Section B: Real-time side-by-side VM resource cards (configured vs. actual allocations, guest ballooning/hotplug capabilities)
- Section C: Live Workload Simulator (authentic CPU, RAM, and Database synthetic load generation with OOM protection)
- Section D: Real-time elasticity recommendations with 1-click apply
- Section E: Administrator manual allocation controls & safe baseline transition
- Section F: Historical audit trail, telemetry trend charts (CPU, RAM, vCPU count, memory allocation), event timeline, and efficiency analysis
"""

import os
import time
import pandas as pd
import streamlit as st
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from frontend.api import (
    api_get_xen_metrics,
    api_get_xen_monitor_status,
    api_get_allocation_status,
    api_get_allocation_recommendations,
    api_get_allocation_history,
    api_enable_allocation,
    api_disable_allocation,
    api_emergency_stop,
    api_apply_manual_cpu,
    api_apply_manual_ram,
    api_apply_recommended,
    api_get_xen_history,
    api_transition_to_baseline,
    api_get_workload_status,
    api_start_cpu_workload,
    api_stop_cpu_workload,
    api_start_ram_workload,
    api_stop_ram_workload,
    api_start_db_workload,
    api_stop_db_workload,
    api_workload_emergency_stop
)
from frontend.components.cards import render_section_title, render_metric_card

def render_dynamic_allocation_page():
    render_section_title(
        "⚡ Dynamic Resource Allocation",
        "Autonomous elasticity controller, live workload simulator & administrator actuation panel for XCP-ng / Xen"
    )

    # -------------------------------------------------------------
    # Role Authorization Check (Rule: Admin only)
    # -------------------------------------------------------------
    user = st.session_state.get("user")
    if not user or user.get("role") != "admin":
        st.error("⛔ Access Denied. Dynamic resource allocation operations are restricted to administrators only.")
        return

    # Top Action Bar: Refresh & Auto-Refresh
    col_bar1, col_bar2, col_bar3 = st.columns([3, 1, 1])
    with col_bar2:
        if st.button("🔄 Refresh Telemetry", use_container_width=True):
            st.rerun()
    with col_bar3:
        auto_refresh = st.checkbox("Auto-refresh (5s)", value=False, key="dyn_auto_refresh")

    # Fetch live state from backend APIs
    with st.spinner("Connecting to Xen Allocation Controller..."):
        alloc_status_resp = api_get_allocation_status()
        metrics_resp = api_get_xen_metrics()
        monitor_status_resp = api_get_xen_monitor_status()
        alloc_history_resp = api_get_allocation_history(limit=50)
        workload_status_resp = api_get_workload_status()

    alloc_data = alloc_status_resp.get("data", {}) if alloc_status_resp.get("success") else {}
    metrics_data = metrics_resp.get("data", {}) if metrics_resp.get("success") else {}
    monitor_data = monitor_status_resp.get("data", {}) if monitor_status_resp.get("success") else {}
    history_records = alloc_history_resp.get("data", []) if alloc_history_resp.get("success") else []
    workload_data = workload_status_resp.get("data", {}) if workload_status_resp.get("success") else {}

    is_connected = metrics_data.get("connected", False)
    mode = alloc_data.get("allocation_mode", "manual").upper()
    emergency_stop = alloc_data.get("emergency_stop", False)
    poll_interval = alloc_data.get("poll_interval_sec", 5)
    last_update = metrics_data.get("last_successful_update_iso") or "Never"

    # Get last XenAPI operation
    last_op = alloc_data.get("last_xen_operation")
    if last_op:
        last_op_str = f"✅ {last_op.get('operation')} on {last_op.get('vm_name')} (Actual: {last_op.get('actual_value')}) at {last_op.get('timestamp_iso', '')[:19]}"
    elif history_records:
        latest_act = history_records[0]
        last_op_str = f"{latest_act.get('action_type')} on {latest_act.get('vm_name')} ({latest_act.get('execution_status')}) at {latest_act.get('created_at', '')[:19]}"
    else:
        last_op_str = "None executed yet"

    # =============================================================
    # SECTION A: AUTOMATION STATUS & SAFETY INTERLOCKS
    # =============================================================
    st.markdown("### 🎛️ **A. Automation Controller & Safety Mode**")

    # Emergency stop alert banner if engaged
    if emergency_stop:
        st.error(
            "🚨 **EMERGENCY STOP ENGAGED**: All automated dynamic scaling and active synthetic load tests are currently halted! "
            "VMs remain running without interruption. Disengage below to resume automated scaling."
        )

    # Status summary cards
    sc1, sc2, sc3, sc4 = st.columns(4)
    with sc1:
        xen_badge = "🟢 Connected" if is_connected else "🔴 Disconnected"
        render_metric_card("XenAPI Status", xen_badge, f"Host: {os.getenv('XCP_NG_HOST', '10.189.191.175')}")
    with sc2:
        mode_badge = "🟢 AUTOMATIC" if mode == "AUTO" else "🟡 MANUAL"
        render_metric_card("Allocation Mode", mode_badge, "Autonomous closed-loop scaling" if mode == "AUTO" else "Admin authorization required")
    with sc3:
        estop_badge = "🚨 ENGAGED" if emergency_stop else "✅ Normal (Clear)"
        render_metric_card("Emergency Stop", estop_badge, "Scaling & load tests suspended" if emergency_stop else "Automated actuation permitted")
    with sc4:
        render_metric_card("Polling Interval", f"{poll_interval}s", f"Last sync: {last_update[-8:] if len(last_update) > 8 else last_update}")

    st.markdown(
        f"""
        <div style="background:#F1F5F9; border:1px solid #CBD5E1; padding:10px 14px; border-radius:6px; margin-top:8px; font-size:0.85rem; color:#334155;">
            <b>⚡ Last Successful XenAPI Operation:</b> <code>{last_op_str}</code>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.markdown("---")

    # =============================================================
    # SECTION B: VM RESOURCE CARDS (Both VMs Side by Side)
    # =============================================================
    st.markdown("### 🖥️ **B. Virtual Machine Resource Allocations & Telemetry**")

    vms_map = metrics_data.get("vms", {})
    recs_map = alloc_data.get("recommendations", {})

    app_vm_name = os.getenv("APP_VM_NAME", "Alpine-Linux")
    db_vm_name = os.getenv("DB_VM_NAME", "Alpine-DB")

    def get_vm_data(target_name: str) -> Dict[str, Any]:
        """Lookup VM telemetry by exact name or alias."""
        if target_name in vms_map:
            return vms_map[target_name]
        for k, v in vms_map.items():
            if isinstance(v, dict):
                if k.lower() == target_name.lower():
                    return v
        return {}

    app_vm = get_vm_data(app_vm_name) or get_vm_data("Alpine-Linux-New")
    db_vm = get_vm_data(db_vm_name)

    app_rec = recs_map.get(app_vm.get("name", app_vm_name), recs_map.get(app_vm_name, {}))
    db_rec = recs_map.get(db_vm.get("name", db_vm_name), recs_map.get(db_vm_name, {}))

    app_policy = alloc_data.get("app_vm_policy", {})
    db_policy = alloc_data.get("db_vm_policy", {})

    col_vm1, col_vm2 = st.columns(2)

    with col_vm1:
        st.markdown(
            f"""
            <div style="background:#F8FAFC; border:1px solid #CBD5E1; border-top:4px solid #3B82F6; padding:16px; border-radius:10px; margin-bottom:15px;">
                <h4 style="margin:0 0 6px 0; color:#1E3A8A;">🖥️ Application VM: {app_vm.get('name', app_vm_name)}</h4>
                <div style="font-size:0.8rem; color:#64748B; margin-bottom:8px;">
                    UUID: <code>{app_vm.get('uuid', 'N/A')}</code> | State: <b>{app_vm.get('power_state', 'Running')}</b>
                </div>
                <div style="font-size:0.75rem; color:#475569; margin-bottom:12px;">
                    Guest Ballooning: <b>{'🟢 Supported' if app_vm.get('supports_ballooning') else '⚪ Unsupported'}</b> |
                    vCPU Hotplug: <b>{'🟢 Supported' if app_vm.get('supports_vcpu_hotplug') else '⚪ Unsupported'}</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        c1, c2 = st.columns(2)
        with c1:
            st.metric("vCPUs (Actual / Limit)", f"{app_vm.get('vcpu_count', 'N/A')} / {app_policy.get('max_vcpus', 4)}")
            st.metric("CPU Utilization", f"{app_vm.get('cpu_percent', 'N/A')}%")
            st.metric("Recommended vCPUs", f"{app_rec.get('recommended_vcpus', app_vm.get('vcpu_count', 'N/A'))}")
            st.caption(f"Configured vCPU Policy: **{app_policy.get('min_vcpus', 1)} – {app_policy.get('max_vcpus', 4)}**")
        with c2:
            st.metric("Allocated Dynamic RAM", f"{app_vm.get('allocated_ram_mb', 'N/A')} MB")
            st.metric("Actual Guest Used RAM", f"{app_vm.get('used_ram_mb', 'N/A')} MB ({app_vm.get('ram_percent', 'N/A')}%)")
            st.metric("Guest Available RAM", f"{app_vm.get('available_ram_mb', 'N/A')} MB")
            st.caption(f"Configured RAM Policy: **{app_policy.get('min_ram_mb', 1024)} – {app_policy.get('max_ram_mb', 4096)} MB**")

        if st.button("🎯 Transition App VM to 1 vCPU / 1024 MB Baseline", key="trans_app_btn", use_container_width=True):
            with st.spinner("Actuating safe baseline transition for Alpine-Linux..."):
                res = api_transition_to_baseline(app_vm.get("name", app_vm_name))
            if res.get("success"):
                st.success(res.get("message", "App VM transitioned to baseline!"))
                time.sleep(1)
                st.rerun()
            else:
                st.error(f"Transition error: {res.get('error', res.get('message'))}")

    with col_vm2:
        st.markdown(
            f"""
            <div style="background:#F8FAFC; border:1px solid #CBD5E1; border-top:4px solid #10B981; padding:16px; border-radius:10px; margin-bottom:15px;">
                <h4 style="margin:0 0 6px 0; color:#065F46;">🗄️ Database VM: {db_vm.get('name', db_vm_name)}</h4>
                <div style="font-size:0.8rem; color:#64748B; margin-bottom:8px;">
                    UUID: <code>{db_vm.get('uuid', 'N/A')}</code> | State: <b>{db_vm.get('power_state', 'Running')}</b>
                </div>
                <div style="font-size:0.75rem; color:#475569; margin-bottom:12px;">
                    Guest Ballooning: <b>{'🟢 Supported' if db_vm.get('supports_ballooning') else '⚪ Unsupported'}</b> |
                    Policy: <b>{'🔒 Preserving Initial Baseline' if db_policy.get('preserve_initial') else '⚡ Elastic'}</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        c1, c2 = st.columns(2)
        with c1:
            st.metric("vCPUs (Actual / Limit)", f"{db_vm.get('vcpu_count', 'N/A')} / {db_policy.get('max_vcpus', 4)}")
            st.metric("CPU Utilization", f"{db_vm.get('cpu_percent', 'N/A')}%")
            st.metric("Recommended vCPUs", f"{db_rec.get('recommended_vcpus', db_vm.get('vcpu_count', 'N/A'))}")
            st.caption(f"Configured vCPU Policy: **{db_policy.get('min_vcpus', 1)} – {db_policy.get('max_vcpus', 4)}**")
        with c2:
            st.metric("Allocated Dynamic RAM", f"{db_vm.get('allocated_ram_mb', 'N/A')} MB")
            st.metric("Actual Guest Used RAM", f"{db_vm.get('used_ram_mb', 'N/A')} MB ({db_vm.get('ram_percent', 'N/A')}%)")
            st.metric("Guest Available RAM", f"{db_vm.get('available_ram_mb', 'N/A')} MB")
            st.caption(f"Configured RAM Policy: **{db_policy.get('min_ram_mb', 1024)} – {db_policy.get('max_ram_mb', 4096)} MB**")

        if st.button("🎯 Transition DB VM to 1 vCPU / 1024 MB Baseline", key="trans_db_btn", use_container_width=True):
            with st.spinner("Actuating safe baseline transition for Alpine-DB..."):
                res = api_transition_to_baseline(db_vm.get("name", db_vm_name))
            if res.get("success"):
                st.success(res.get("message", "DB VM transitioned to baseline!"))
                time.sleep(1)
                st.rerun()
            else:
                st.error(f"Transition error: {res.get('error', res.get('message'))}")

    st.markdown("---")

    # =============================================================
    # SECTION C: LIVE WORKLOAD SIMULATOR (Major Demonstration Feature)
    # =============================================================
    st.markdown("### 🔥 **C. Live Workload Simulator**")
    st.caption(
        "Generate controlled, authentic synthetic CPU, RAM, and Database workloads to test and demonstrate "
        "real-time Xen autoscaling and live ballooning. Workloads run inside guest VMs with strict safety limits."
    )

    # Emergency stop for all workloads
    c_stop1, c_stop2 = st.columns([3, 1])
    with c_stop2:
        if st.button("🛑 Stop All Active Workloads", key="stop_all_sim_btn", type="primary", use_container_width=True):
            with st.spinner("Halting all synthetic workload generators..."):
                stop_res = api_workload_emergency_stop()
            if stop_res.get("success"):
                st.warning(stop_res.get("message", "All active workloads halted."))
                time.sleep(1)
                st.rerun()
            else:
                st.error(f"Error: {stop_res.get('error')}")

    sim_tab1, sim_tab2, sim_tab3 = st.tabs([
        "🖥️ Application VM Workloads (CPU & RAM)",
        "🗄️ Database VM Workload (MariaDB)",
        "📜 Active Workload Sessions"
    ])

    # Tab 1: App VM Workloads
    with sim_tab1:
        st.markdown("#### Synthetic Load for `Alpine-Linux` (Application VM)")
        w_col1, w_col2 = st.columns(2)

        # CPU Load Controls
        with w_col1:
            st.markdown(
                """
                <div style="background:#EFF6FF; border:1px solid #BFDBFE; padding:12px; border-radius:8px; margin-bottom:10px;">
                    <b style="color:#1D4ED8;">⚡ CPU Load Generator</b><br/>
                    <small style="color:#4B5563;">Calibrated mathematical computation duty cycle to breach >80% threshold.</small>
                </div>
                """,
                unsafe_allow_html=True
            )
            running_cpu = workload_data.get("running_cpu_session")
            if running_cpu:
                st.success(f"🟢 **CPU Load Active**: {running_cpu.get('intensity_percent')}% intensity across {running_cpu.get('workers')} worker(s)")
                st.write(f"Started: {running_cpu.get('started_at', '')[:19]} (Duration: {running_cpu.get('duration_sec')}s)")
                if st.button("⏹️ Stop CPU Load", key="stop_cpu_btn", use_container_width=True):
                    api_stop_cpu_workload(running_cpu.get("session_id"))
                    st.rerun()
            else:
                cpu_intensity = st.select_slider(
                    "Target CPU Intensity (%)",
                    options=[25.0, 50.0, 75.0, 90.0],
                    value=75.0,
                    help="Select intensity: 90% triggers scale-up (>80%), 25% allows scale-down (<25%)."
                )
                cpu_workers = st.selectbox("Worker Threads", options=[1, 2, 3, 4], index=1)
                cpu_duration = st.selectbox("Duration (seconds)", options=[30, 60, 120, 180], index=1)

                if st.button("🚀 Start CPU Load Test", key="start_cpu_btn", type="primary", use_container_width=True):
                    with st.spinner("Starting CPU workload generator on Alpine-Linux..."):
                        c_res = api_start_cpu_workload(
                            target_vm=app_vm.get("name", app_vm_name),
                            intensity_percent=cpu_intensity,
                            workers=cpu_workers,
                            duration_sec=cpu_duration
                        )
                    if c_res.get("success"):
                        st.success(c_res.get("message", "CPU load started!"))
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(f"Error: {c_res.get('error')}")

        # RAM Load Controls
        with w_col2:
            st.markdown(
                """
                <div style="background:#FDF2F8; border:1px solid #FBCFE8; padding:12px; border-radius:8px; margin-bottom:10px;">
                    <b style="color:#BE185D;">🎈 RAM Load Generator</b><br/>
                    <small style="color:#4B5563;">Commits real physical heap pages with OOM headroom protection.</small>
                </div>
                """,
                unsafe_allow_html=True
            )
            running_ram = workload_data.get("running_ram_session")
            guest_avail_ram = workload_data.get("guest_available_ram_mb", 2048.0)
            st.caption(f"Current Guest Available RAM: **{guest_avail_ram} MB** (Minimum 256 MB safety cushion enforced)")

            if running_ram:
                st.success(f"🟢 **RAM Load Active**: {running_ram.get('allocated_mb')} MB allocated in heap")
                st.write(f"Started: {running_ram.get('started_at', '')[:19]} (Duration: {running_ram.get('duration_sec')}s)")
                if st.button("⏹️ Stop RAM Load & Free Memory", key="stop_ram_btn", use_container_width=True):
                    api_stop_ram_workload(running_ram.get("session_id"))
                    st.rerun()
            else:
                ram_alloc_choice = st.selectbox(
                    "RAM Allocation Amount (MB)",
                    options=[128.0, 256.0, 512.0, 768.0],
                    index=1,
                    help="Select heap allocation. Must fit inside available memory with safety cushion."
                )
                ram_duration = st.selectbox("Duration (seconds)", options=[30, 60, 120, 180], index=1, key="ram_dur_sel")

                if st.button("🚀 Start RAM Load Test", key="start_ram_btn", type="primary", use_container_width=True):
                    with st.spinner(f"Allocating {ram_alloc_choice} MB heap pages on Alpine-Linux..."):
                        r_res = api_start_ram_workload(
                            target_vm=app_vm.get("name", app_vm_name),
                            allocated_mb=ram_alloc_choice,
                            duration_sec=ram_duration
                        )
                    if r_res.get("success"):
                        st.success(r_res.get("message", "RAM load started!"))
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(f"Error: {r_res.get('error')}")

    # Tab 2: Database VM Workload
    with sim_tab2:
        st.markdown("#### Safe MariaDB Transaction Load for `Alpine-DB` (Database VM)")
        st.info(
            "🔒 **Data Isolation Guarantee**: This workload executes queries exclusively against a dedicated transient table "
            "(`workload_simulation_test`) and rolls back or cleans up transactions. "
            "Real student, course, enrollment, and application user records are NEVER modified or deleted."
        )

        running_db = workload_data.get("running_db_session")
        if running_db:
            st.success(f"🟢 **Database Workload Active**: ~{running_db.get('intensity_percent')} QPS on MariaDB across {running_db.get('workers')} worker(s)")
            st.write(f"Started: {running_db.get('started_at', '')[:19]} (Duration: {running_db.get('duration_sec')}s)")
            if st.button("⏹️ Stop Database Workload", key="stop_db_btn", use_container_width=True):
                api_stop_db_workload(running_db.get("session_id"))
                st.rerun()
        else:
            d_col1, d_col2 = st.columns(2)
            with d_col1:
                db_intensity = st.selectbox(
                    "Query Intensity",
                    options=["low", "medium", "high"],
                    index=1,
                    help="Low (~10 QPS), Medium (~30 QPS), High (~60 QPS)"
                )
                db_workers = st.selectbox("Concurrent DB Workers", options=[1, 2, 3, 4], index=1, key="db_worker_sel")
            with d_col2:
                db_duration = st.selectbox("Duration (seconds)", options=[30, 60, 120, 180], index=1, key="db_dur_sel")
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                if st.button("🚀 Start MariaDB Load Test", key="start_db_btn", type="primary", use_container_width=True):
                    with st.spinner("Connecting to MariaDB and generating safe queries..."):
                        d_res = api_start_db_workload(
                            target_vm=db_vm.get("name", db_vm_name),
                            intensity=db_intensity,
                            workers=db_workers,
                            duration_sec=db_duration
                        )
                    if d_res.get("success"):
                        st.success(d_res.get("message", "Database workload started!"))
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(f"Error: {d_res.get('error')}")

    # Tab 3: Active Sessions Table
    with sim_tab3:
        st.markdown("#### Synthetic Workload History (`workload_simulation_sessions`)")
        recent_sessions = workload_data.get("recent_sessions", [])
        if recent_sessions:
            df_sim = pd.DataFrame(recent_sessions)
            display_sim_cols = [
                "session_id", "target_vm", "workload_type", "intensity_percent",
                "allocated_mb", "workers", "duration_sec", "status", "started_at"
            ]
            valid_sim_cols = [c for c in display_sim_cols if c in df_sim.columns]
            st.dataframe(df_sim[valid_sim_cols], use_container_width=True, hide_index=True)
        else:
            st.info("No workload simulation sessions recorded yet.")

    st.markdown("---")

    # =============================================================
    # SECTION D: ALLOCATION RECOMMENDATIONS
    # =============================================================
    st.markdown("### 📋 **D. Real-Time Elasticity Recommendations**")

    rec_rows = []
    for vm_key, r in recs_map.items():
        # CPU row
        cpu_act = r.get("cpu_action", "HOLD")
        cpu_cur = r.get("current_vcpus", "N/A")
        cpu_rec = r.get("recommended_vcpus", "N/A")
        rec_rows.append({
            "VM Name": r.get("vm_name", vm_key),
            "Resource": "CPU (vCPUs)",
            "Current": str(cpu_cur),
            "Recommended": str(cpu_rec),
            "Decision": cpu_act,
            "Rationale": r.get("rationale", "Nominal workload")
        })
        # RAM row
        ram_act = r.get("ram_action", "HOLD")
        ram_cur = f"{r.get('current_ram_mb', 'N/A')} MB"
        ram_rec = f"{r.get('recommended_ram_mb', 'N/A')} MB"
        rec_rows.append({
            "VM Name": r.get("vm_name", vm_key),
            "Resource": "RAM (Dynamic Balloon)",
            "Current": ram_cur,
            "Recommended": ram_rec,
            "Decision": ram_act,
            "Rationale": r.get("rationale", "Nominal workload")
        })

    if rec_rows:
        df_recs = pd.DataFrame(rec_rows)
        st.dataframe(df_recs, use_container_width=True, hide_index=True)

        # 1-Click apply recommendation buttons
        st.markdown("##### ⚡ **One-Click Apply Recommended Scaling**")
        app_cols = st.columns(len(recs_map) if recs_map else 1)
        for idx, (v_name, r_info) in enumerate(recs_map.items()):
            with app_cols[idx]:
                has_pending = (r_info.get("cpu_action") in ("SCALE_UP", "SCALE_DOWN") or 
                               r_info.get("ram_action") in ("SCALE_UP", "SCALE_DOWN"))
                btn_label = f"Apply for {r_info.get('vm_name', v_name)}"
                if st.button(btn_label, key=f"apply_rec_{v_name}", disabled=not has_pending or emergency_stop, use_container_width=True):
                    with st.spinner(f"Actuating XenAPI scaling for {v_name}..."):
                        res = api_apply_recommended(r_info.get("vm_name", v_name))
                    if res.get("success"):
                        st.success(f"Successfully applied recommended resources for {v_name}!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(f"Scaling failed: {res.get('error', 'Unknown XenAPI error')}")
    else:
        st.info("No active recommendations at this moment. Telemetry is within nominal boundaries.")

    st.markdown("---")

    # =============================================================
    # SECTION E: ADMINISTRATOR CONTROLS
    # =============================================================
    st.markdown("### 🛠️ **E. Administrator Control Panel**")

    ctrl_tab1, ctrl_tab2, ctrl_tab3, ctrl_tab4 = st.tabs([
        "⚙️ Automation & Safety Mode",
        "🎛️ Manual CPU Allocation",
        "🎈 Manual RAM Dynamic Ballooning",
        "🎯 Safe Baseline Transition"
    ])

    # Tab 1: Automation & Emergency Stop
    with ctrl_tab1:
        st.markdown("#### Mode & Safety Interlocks")
        c_mode1, c_mode2 = st.columns(2)

        with c_mode1:
            st.markdown("##### Automation Policy")
            st.write(f"Current mode: **{mode}**")
            if mode == "MANUAL":
                st.caption("Manual mode: The system analyzes telemetry and suggests scaling, but requires admin confirmation.")
                if st.button("🟢 Enable Automated Allocation (Auto Mode)", use_container_width=True, type="primary"):
                    res = api_enable_allocation()
                    if res.get("success"):
                        st.success("Automated dynamic allocation enabled!")
                        st.rerun()
                    else:
                        st.error(f"Error: {res.get('error')}")
            else:
                st.caption("Auto mode: The system autonomously scales vCPUs and RAM dynamically when sustained breaches occur.")
                if st.button("⏸️ Switch to Manual Mode", use_container_width=True):
                    res = api_disable_allocation()
                    if res.get("success"):
                        st.info("Automated allocation disabled. Manual mode active.")
                        st.rerun()
                    else:
                        st.error(f"Error: {res.get('error')}")

        with c_mode2:
            st.markdown("##### Emergency Interlock")
            st.write(f"Emergency stop: **{'🚨 ENGAGED' if emergency_stop else '✅ CLEAR'}**")
            st.caption("Emergency stop immediately halts all automated resource adjustments without stopping or rebooting VMs.")
            if not emergency_stop:
                if st.button("🛑 ENGAGE EMERGENCY STOP", use_container_width=True, type="primary"):
                    res = api_emergency_stop("engage")
                    if res.get("success"):
                        st.warning("Emergency stop engaged! All scaling and load tests halted.")
                        st.rerun()
                    else:
                        st.error(f"Error: {res.get('error')}")
            else:
                if st.button("🟢 Disengage Emergency Stop & Resume", use_container_width=True):
                    res = api_emergency_stop("resume")
                    if res.get("success"):
                        st.success("Emergency stop cleared. Operations resumed.")
                        st.rerun()
                    else:
                        st.error(f"Error: {res.get('error')}")

    # Tab 2: Manual CPU Allocation
    with ctrl_tab2:
        st.markdown("#### Live vCPU Modification")
        st.caption("Directly adjust vCPU count on running VM via XenAPI. Verified immediately post-change.")

        target_vm_cpu = st.selectbox(
            "Select Target Virtual Machine",
            [app_vm.get("name", app_vm_name), db_vm.get("name", db_vm_name)],
            key="cpu_vm_select"
        )
        is_app_selected = (target_vm_cpu == app_vm.get("name", app_vm_name))
        selected_policy = app_policy if is_app_selected else db_policy
        vm_target_data = app_vm if is_app_selected else db_vm

        cur_vcpus = int(vm_target_data.get("vcpu_count", 1))
        min_v = int(selected_policy.get("min_vcpus", 1))
        max_v = int(selected_policy.get("max_vcpus", 4))

        new_vcpus = st.slider(
            f"Target vCPU Count ({target_vm_cpu})",
            min_value=min_v,
            max_value=max_v,
            value=max(min_v, min(max_v, cur_vcpus)),
            step=1,
            help=f"Configured boundary for {target_vm_cpu}: {min_v} to {max_v} vCPUs"
        )
        cpu_reason = st.text_input("Operational Reason", value="Administrator manual capacity adjustment", key="cpu_reason_input")
        cpu_confirm = st.checkbox(f"⚠️ I confirm live vCPU modification of '{target_vm_cpu}' to {new_vcpus} vCPUs.", key="cpu_confirm_chk")

        if st.button("🚀 Apply vCPU Modification", disabled=not cpu_confirm or (new_vcpus == cur_vcpus), type="primary"):
            with st.spinner("Actuating XenAPI set_VCPUs_number_live & verifying..."):
                res = api_apply_manual_cpu(target_vm_cpu, new_vcpus, reason=cpu_reason)
            if res.get("success"):
                st.success(f"Successfully scaled vCPUs for {target_vm_cpu} to {res.get('actual_value')} (Verified via XenAPI)!")
                time.sleep(1)
                st.rerun()
            else:
                st.error(f"Failed to modify vCPUs: {res.get('error')}")

    # Tab 3: Manual RAM Dynamic Ballooning
    with ctrl_tab3:
        st.markdown("#### Dynamic Memory Ballooning")
        st.caption("Adjust dynamic memory ceiling without rebooting. Xen balloon driver reclaims or expands memory in real-time.")

        target_vm_ram = st.selectbox(
            "Select Target Virtual Machine",
            [app_vm.get("name", app_vm_name), db_vm.get("name", db_vm_name)],
            key="ram_vm_select"
        )
        is_app_ram_selected = (target_vm_ram == app_vm.get("name", app_vm_name))
        selected_ram_policy = app_policy if is_app_ram_selected else db_policy
        vm_target_ram_data = app_vm if is_app_ram_selected else db_vm

        cur_ram = float(vm_target_ram_data.get("allocated_ram_mb", 1024.0))
        min_r = int(selected_ram_policy.get("min_ram_mb", 1024))
        max_r = int(selected_ram_policy.get("max_ram_mb", 4096))

        # Dynamic options within VM policy range
        ram_options = [r for r in [1024, 1536, 2048, 2560, 3072, 3584, 4096] if min_r <= r <= max_r]
        closest_ram = min(ram_options, key=lambda x: abs(x - cur_ram))

        new_ram = st.select_slider(
            f"Target Dynamic Memory Ceiling for {target_vm_ram} (MB)",
            options=ram_options,
            value=closest_ram,
            help=f"Dynamic limits for {target_vm_ram}: {min_r} MB minimum, {max_r} MB maximum (512 MB step increments)"
        )
        ram_reason = st.text_input("Operational Reason", value="Administrator dynamic memory adjustment", key="ram_reason_input")
        ram_confirm = st.checkbox(f"⚠️ I confirm dynamic memory adjustment of '{target_vm_ram}' to {new_ram} MB.", key="ram_confirm_chk")

        if st.button("🎈 Apply Memory Ballooning", disabled=not ram_confirm or (new_ram == cur_ram), type="primary"):
            with st.spinner("Actuating XenAPI set_memory_dynamic_range & verifying..."):
                res = api_apply_manual_ram(target_vm_ram, float(new_ram), reason=ram_reason)
            if res.get("success"):
                st.success(f"Successfully adjusted dynamic memory for {target_vm_ram} to {res.get('actual_value')} MB (Verified via XenAPI)!")
                time.sleep(1)
                st.rerun()
            else:
                st.error(f"Failed to adjust dynamic memory: {res.get('error')}")

    # Tab 4: Safe Baseline Transition
    with ctrl_tab4:
        st.markdown("#### Safe Baseline Policy Transition")
        st.caption(
            "Safely transition virtual machines from overprovisioned configurations (e.g. 4 vCPUs / 4096 MB) "
            "down to the target college project baseline (1 vCPU, 1024 MB RAM) with XenAPI verification."
        )
        trans_vm = st.selectbox(
            "Select VM to Transition",
            [app_vm.get("name", app_vm_name), db_vm.get("name", db_vm_name)],
            key="trans_vm_sel"
        )
        t_confirm = st.checkbox(f"⚠️ I authorize downsizing '{trans_vm}' to 1 vCPU and 1024 MB RAM baseline.", key="t_confirm_chk")
        if st.button(f"🎯 Execute Baseline Transition for {trans_vm}", disabled=not t_confirm, type="primary"):
            with st.spinner(f"Actuating baseline transition for {trans_vm}..."):
                res = api_transition_to_baseline(trans_vm)
            if res.get("success"):
                st.success(res.get("message"))
                time.sleep(1)
                st.rerun()
            else:
                st.error(f"Error: {res.get('error', res.get('message'))}")

    st.markdown("---")

    # =============================================================
    # SECTION F: PERFORMANCE TELEMETRY, TIMELINE & EFFICIENCY ANALYSIS
    # =============================================================
    st.markdown("### 📊 **F. Performance Telemetry, Timeline & Efficiency Analysis**")

    v_tab1, v_tab2, v_tab3, v_tab4 = st.tabs([
        "📜 Resource Allocation Audit History",
        "📈 Telemetry Trends (CPU & RAM)",
        "⏱️ Scaling Event Timeline",
        "🔬 Static vs. Dynamic Allocation Efficiency"
    ])

    with v_tab1:
        st.markdown("##### Historical Record of Resource Scaling Actions (`resource_allocation_history`)")
        if history_records:
            df_hist = pd.DataFrame(history_records)
            display_cols = [
                "created_at", "vm_name", "resource_type", "action_type",
                "previous_value", "requested_value", "actual_value",
                "execution_status", "trigger_reason", "initiated_by"
            ]
            valid_cols = [c for c in display_cols if c in df_hist.columns]
            st.dataframe(df_hist[valid_cols], use_container_width=True, hide_index=True)
        else:
            st.info("No allocation history events recorded yet in the database.")

    with v_tab2:
        st.markdown("##### Live Workload Telemetry Trends")
        with st.spinner("Loading telemetry history..."):
            hist_resp = api_get_xen_history(limit=50)

        if hist_resp.get("success") and hist_resp.get("data"):
            hist_data = hist_resp.get("data")
            df_trend = pd.DataFrame(hist_data)
            if not df_trend.empty and "timestamp" in df_trend.columns:
                df_trend["timestamp"] = pd.to_datetime(df_trend["timestamp"])
                df_trend = df_trend.sort_values("timestamp")

                c_plot1, c_plot2 = st.columns(2)
                with c_plot1:
                    st.markdown("###### CPU Utilization (%)")
                    chart_cpu = df_trend.pivot_table(index="timestamp", columns="vm_name", values="cpu_percent")
                    st.line_chart(chart_cpu, height=260)
                with c_plot2:
                    st.markdown("###### RAM Utilization (%)")
                    chart_ram = df_trend.pivot_table(index="timestamp", columns="vm_name", values="ram_percent")
                    st.line_chart(chart_ram, height=260)

                c_plot3, c_plot4 = st.columns(2)
                with c_plot3:
                    st.markdown("###### vCPU Allocation (Online Cores)")
                    if "vcpu_count" in df_trend.columns:
                        chart_vcpus = df_trend.pivot_table(index="timestamp", columns="vm_name", values="vcpu_count")
                        st.line_chart(chart_vcpus, height=260)
                with c_plot4:
                    st.markdown("###### Dynamic RAM Allocation (MB)")
                    if "allocated_ram_mb" in df_trend.columns:
                        chart_alloc_ram = df_trend.pivot_table(index="timestamp", columns="vm_name", values="allocated_ram_mb")
                        st.line_chart(chart_alloc_ram, height=260)
        else:
            st.caption("Telemetry history is loading from MariaDB/SQLite...")

    with v_tab3:
        st.markdown("##### Resource Allocation Event Timeline")
        if history_records:
            st.caption("Observed scaling events chronologically ordered:")
            for item in history_records[:10]:
                t_str = str(item.get("created_at", ""))[:19]
                vm = item.get("vm_name", "")
                res_t = item.get("resource_type", "").upper()
                p_val = item.get("previous_value", "")
                a_val = item.get("actual_value", "")
                reason = item.get("trigger_reason", "")
                status = item.get("execution_status", "")

                icon = "🟢" if status.lower() == "success" else "🔴"
                st.markdown(
                    f"""
                    <div style="border-left: 3px solid #3B82F6; padding-left: 12px; margin-bottom: 8px;">
                        <b>{t_str}</b> — {icon} <b>{vm}</b> {res_t} scaled from <code>{p_val}</code> to <code>{a_val}</code><br/>
                        <small style="color:#64748B;">Trigger: {reason}</small>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
        else:
            st.info("No scaling events recorded yet. Run a workload test or adjust resources to generate timeline events.")

    with v_tab4:
        st.markdown("##### Static Overprovisioning vs. Dynamic Resource Elasticity")
        st.markdown(
            """
            In traditional static virtualization, virtual machines must be provisioned for theoretical peak capacity
            (e.g., 4 vCPUs and 4096 MB RAM per VM). This results in massive hypervisor resource waste during off-peak hours.

            **Xen Dynamic Resource Allocation Advantages:**
            - **vCPU Elasticity:** Cores are hot-plugged on demand (>80% utilization for 3 intervals) and reclaimed (<25% for 6 intervals) when idle.
            - **Memory Ballooning:** Dynamic ranges (`dynamic_min` to `dynamic_max`) allow the Xen hypervisor to pool free RAM and grant memory to workloads under pressure without rebooting.
            - **Energy & Density Efficiency:** Up to **3.2x higher VM density** on the same physical XCP-ng server.
            """
        )

        comp_data = {
            "Metric / Architecture": ["Allocated vCPUs (Average)", "Allocated RAM (Average)", "Hypervisor Headroom", "Responsiveness to Load Spikes", "Downtime Required"],
            "Static Overprovisioning": ["4 vCPUs (Locked)", "4096 MB (Locked)", "Exhausted (Low VM density)", "None (Rigid)", "Reboot required to resize"],
            "Dynamic Xen Elasticity (Phase 3)": ["1-2 vCPUs (Elastic)", "1024-2048 MB (Ballooned)", "High (Reclaimed for other VMs)", "Autonomous Scale-Up in <5s", "Zero Downtime (Live XenAPI)"]
        }
        st.table(pd.DataFrame(comp_data))

    # Auto-refresh loop
    if auto_refresh:
        time.sleep(5)
        st.rerun()
