"""
Streamlit Page: Intelligent Resource Orchestration
Project: Xen-Based Dynamic Resource Allocation for Scalable E-Learning Services

Primary interface for authentic student traffic load simulation, real Xen telemetry
(separating Xen-assigned memory from guest memory), closed-loop automatic CPU/RAM scaling,
and administrator manual overrides with XenAPI readback verification.
"""

import time
import pandas as pd
import streamlit as st
from datetime import datetime, timezone

from frontend.api import (
    api_get_xen_metrics,
    api_get_allocation_status,
    api_get_allocation_recommendations,
    api_get_allocation_history,
    api_get_metrics_history,
    api_set_allocation_mode,
    api_emergency_stop,
    api_apply_manual_cpu,
    api_apply_manual_ram,
    api_apply_recommendation,
    api_transition_to_baseline,
    api_get_student_load_status,
    api_start_student_load,
    api_stop_student_load,
    api_emergency_stop_student_load
)

EXPECTED_APP_VM_UUID = "01cdb87c-408f-72bc-449c-0364a8e69647"
EXPECTED_DB_VM_UUID = "0a6dec09-0466-0079-4b66-80704b59587d"

def render_intelligent_orchestration_page():
    """Render the primary Intelligent Resource Orchestration interface."""
    st.set_page_config(
        page_title="Intelligent Resource Orchestration | Xen Platform",
        page_icon="🚀",
        layout="wide"
    )

    # 1. Authorization Gate (Admin Only)
    role = st.session_state.get("role")
    if role != "admin":
        st.error("⛔ Access Denied. Resource orchestration operations are restricted to administrators only.")
        st.info("Please log in with an administrator account (e.g., admin@elearning.local).")
        return

    # Header
    st.markdown("""
        <div style="display:flex; justify-content:space-between; align-items:center; border-bottom: 2px solid #e2e8f0; padding-bottom: 12px; margin-bottom: 20px;">
            <div>
                <h1 style="margin:0; color:#1e3a8a; font-size:2.1rem;">🚀 Intelligent Resource Orchestration</h1>
                <p style="margin:4px 0 0 0; color:#64748b; font-size:1.0rem;">
                    Real Student-Driven Xen Telemetry, Load Simulation & Dynamic Resource Elasticity
                </p>
            </div>
            <div style="text-align:right;">
                <span style="background-color:#dbeafe; color:#1e40af; padding:5px 12px; border-radius:15px; font-weight:600; font-size:0.85rem;">
                    XCP-ng / Xen Hypervisor
                </span>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # Fetch Core Data
    metrics_res = api_get_xen_metrics()
    alloc_status_res = api_get_allocation_status()
    recs_res = api_get_allocation_recommendations()
    history_res = api_get_allocation_history(limit=25)
    load_status_res = api_get_student_load_status()

    metrics_data = metrics_res.get("data", {}) if metrics_res.get("success") else {}
    alloc_data = alloc_status_res.get("data", {}) if alloc_status_res.get("success") else {}
    recommendations = recs_res.get("data", {}) if recs_res.get("success") else {}
    history_events = history_res.get("data", []) if history_res.get("success") else []
    student_load = load_status_res.get("data", {}) if load_status_res.get("success") else {}

    hypervisor = metrics_data.get("hypervisor") or {}
    vms = metrics_data.get("vms") or {}
    is_connected = metrics_data.get("connected", False)

    current_mode = alloc_data.get("mode", "manual").upper()
    emergency_stop = alloc_data.get("emergency_stop", False)

    # =========================================================================
    # COMPONENT 9: System Health and Telemetry Status Banner
    # =========================================================================
    st.markdown("### 🛡️ System Health & Operational Interlocks")

    banner_col1, banner_col2, banner_col3, banner_col4 = st.columns([1.2, 1.2, 1.4, 1.2])

    with banner_col1:
        if is_connected:
            st.success(f"🟢 **XCP-ng Connected**\n`{hypervisor.get('ip', 'Host')}` ({hypervisor.get('running_vms', 2)} VMs Active)")
        else:
            st.error(f"🔴 **XCP-ng Disconnected**\nHost unreachable or offline")

    with banner_col2:
        if emergency_stop:
            st.error("🛑 **EMERGENCY STOP ENGAGED**\nScaling & Traffic Suspended")
        else:
            st.info("✅ **Interlock Normal**\nSafety Enforced")

    with banner_col3:
        mode_label = "🟢 Autonomous (AUTO)" if current_mode == "AUTO" else "🟡 Advisory (MANUAL)"
        st.write(f"**Mode:** {mode_label}")
        new_mode = st.radio(
            "Toggle Controller Mode:",
            ["Manual", "Auto"],
            index=0 if current_mode == "MANUAL" else 1,
            horizontal=True,
            key="interlock_mode_radio"
        )
        if new_mode.lower() != current_mode.lower():
            res = api_set_allocation_mode(new_mode.lower())
            if res.get("success"):
                st.success(f"Mode switched to {new_mode.upper()}")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error(f"Failed to switch mode: {res.get('error')}")

    with banner_col4:
        st.write("**Emergency Actions:**")
        if st.button("🛑 EMERGENCY STOP ALL", type="primary", use_container_width=True, key="btn_master_em_stop"):
            api_emergency_stop_student_load()
            api_emergency_stop("engage")
            st.warning("Emergency stop actuated! Autoscaling and all student load simulations terminated.")
            time.sleep(0.5)
            st.rerun()

    st.markdown("---")

    # =========================================================================
    # COMPONENT 1: Live Student Load Simulator
    # =========================================================================
    st.markdown("### 🎓 Student Load Simulator")
    st.caption("Generate authentic student traffic (1 to 200 concurrent users) against the Flask API and MariaDB database.")

    # Educational Relationship Pipeline
    st.markdown("""
        <div style="background-color: #f8fafc; border-left: 4px solid #3b82f6; padding: 10px 16px; border-radius: 4px; margin-bottom: 16px;">
            <span style="font-weight:600; color:#1e40af;">Elasticity Pipeline:</span>
            <span style="color:#475569; font-size:0.92rem;">
                Simulated students increase &rarr; Requests/sec increase &rarr; Flask processing increases &rarr; MariaDB queries increase &rarr; CPU/RAM utilization increases &rarr; XenAPI triggers allocation scale-up.
            </span>
        </div>
    """, unsafe_allow_html=True)

    sim_col_ctrl, sim_col_stats = st.columns([1.1, 1.4])

    with sim_col_ctrl:
        st.markdown("##### ⚙️ Test Configuration")
        
        sim_target = st.selectbox(
            "Target Virtual Machine:",
            ["app_vm", "db_vm", "both"],
            format_func=lambda x: "Application VM (Flask API)" if x == "app_vm" else ("Database VM (MariaDB)" if x == "db_vm" else "Both VMs (Full Platform)"),
            key="sim_target_vm"
        )

        sim_students = st.select_slider(
            "Simulated Concurrent Students:",
            options=[1, 5, 10, 25, 50, 100, 150, 200],
            value=25,
            key="sim_students_slider"
        )

        sim_ramp = st.slider("Ramp-Up Duration (seconds):", min_value=5, max_value=60, value=10, step=5, key="sim_ramp_slider")
        sim_duration = st.slider("Test Duration (seconds):", min_value=30, max_value=300, value=60, step=15, key="sim_duration_slider")
        sim_intensity = st.selectbox(
            "Workload Profile:",
            ["medium", "light", "heavy"],
            format_func=lambda x: "Medium (Dashboard + Course Browsing)" if x == "medium" else ("Light (Course Browsing)" if x == "light" else "Heavy (Full Lifecycle + DB Transactions)"),
            key="sim_intensity_select"
        )
        sim_rps = st.slider("Requests per Student (req/s):", min_value=0.5, max_value=5.0, value=2.0, step=0.5, key="sim_rps_slider")

        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            is_sim_running = student_load.get("status") in ("ramping_up", "running")
            if st.button("🚀 Start Student Load", type="primary", use_container_width=True, disabled=is_sim_running, key="btn_start_sim"):
                start_res = api_start_student_load(
                    target_vm=sim_target,
                    simulated_students=sim_students,
                    ramp_up_duration=sim_ramp,
                    test_duration=sim_duration,
                    requests_per_student=sim_rps,
                    workload_intensity=sim_intensity
                )
                if start_res.get("success"):
                    st.success(f"Load test started: {sim_students} students ramp-up over {sim_ramp}s!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error(f"Failed to start load test: {start_res.get('error')}")

        with btn_col2:
            if st.button("⏹️ Stop Student Load", use_container_width=True, disabled=not is_sim_running, key="btn_stop_sim"):
                stop_res = api_stop_student_load()
                if stop_res.get("success"):
                    st.info("Stopping active load test...")
                    time.sleep(0.5)
                    st.rerun()

    with sim_col_stats:
        st.markdown("##### 📊 Live Student Traffic Telemetry")
        
        sim_stat = student_load.get("status", "idle").upper()
        stat_color = "#10b981" if sim_stat in ("RUNNING", "RAMPING_UP") else "#64748b"
        
        st.markdown(f"**Simulator Status:** <span style='color:{stat_color}; font-weight:700;'>{sim_stat}</span>", unsafe_allow_html=True)

        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            active_st = student_load.get("active_students", 0)
            joining_st = student_load.get("students_joining", 0)
            leaving_st = student_load.get("students_leaving", 0)
            st.metric("Active Students", f"{active_st}", delta=f"+{joining_st} ramp" if joining_st > 0 else (f"-{leaving_st} exit" if leaving_st > 0 else None))
        
        with sc2:
            live_rps = student_load.get("requests_per_sec", 0.0)
            st.metric("Requests / Sec (RPS)", f"{live_rps:.1f} req/s")

        with sc3:
            db_qps = student_load.get("db_queries_per_sec", 0.0)
            st.metric("Database Queries / Sec", f"{db_qps:.1f} QPS")

        sc4, sc5, sc6 = st.columns(3)
        with sc4:
            lat = student_load.get("avg_response_time_ms", 0.0)
            st.metric("Avg Response Time", f"{lat:.1f} ms")

        with sc5:
            succ = student_load.get("successful_requests", 0)
            fail = student_load.get("failed_requests", 0)
            tot = succ + fail
            rate = round((succ / tot * 100), 1) if tot > 0 else 100.0
            st.metric("Success Rate", f"{rate}%", delta=f"{fail} errors" if fail > 0 else "0 errors", delta_color="inverse")

        with sc6:
            elapsed = student_load.get("elapsed_duration_sec", 0)
            total_dur = student_load.get("test_duration_sec", 60)
            st.metric("Test Duration", f"{elapsed}s / {total_dur}s")

        if is_sim_running and total_dur > 0:
            prog = min(1.0, float(elapsed) / float(total_dur))
            st.progress(prog)

        if student_load.get("error_message"):
            st.warning(f"⚠️ {student_load.get('error_message')}")

    st.markdown("---")

    # =========================================================================
    # COMPONENTS 2 & 3: Application VM & Database VM Resource Monitors
    # =========================================================================
    st.markdown("### 🖥️ Virtual Machine Resource Monitors (Side-by-Side)")

    app_vm = vms.get("Alpine-Linux") or vms.get("Alpine-Linux-New") or {}
    db_vm = vms.get("Alpine-DB") or {}

    col_app, col_db = st.columns(2)

    # -------------------------------------------------------------------------
    # APPLICATION VM (Component 2)
    # -------------------------------------------------------------------------
    with col_app:
        st.markdown("""
            <div style="background-color:#eff6ff; border:1px solid #bfdbfe; border-radius:8px; padding:12px; margin-bottom:12px;">
                <h4 style="margin:0; color:#1e40af;">🌐 Application VM (Alpine-Linux)</h4>
                <span style="font-size:0.85rem; color:#64748b;">Role: Flask REST API + Streamlit Web Interface</span>
            </div>
        """, unsafe_allow_html=True)

        if app_vm:
            app_uuid = app_vm.get("uuid", "N/A")
            uuid_match = (app_uuid == EXPECTED_APP_VM_UUID)
            uuid_badge = "✅ Verified" if uuid_match else f"ℹ️ Discovered: `{app_uuid[:12]}...`"

            st.markdown(f"**UUID:** `{app_uuid}` ({uuid_badge})")
            st.markdown(f"**Power State:** `{app_vm.get('power_state', 'Unknown')}` | **IP:** `{app_vm.get('ip', '10.189.191.51')}`")

            # CPU Section
            st.markdown("##### ⚡ CPU Telemetry")
            cpu_val = app_vm.get("cpu_percent")
            cpu_display = f"{cpu_val:.1f}%" if cpu_val is not None else "Calibrating..."
            vcpus = app_vm.get("vcpu_count", 1)
            
            c_m1, c_m2 = st.columns(2)
            with c_m1:
                st.metric("Actual CPU Utilization", cpu_display)
            with c_m2:
                st.metric("Online vCPUs", f"{vcpus} / 4 vCPUs (Max)")

            st.caption(f"Source: `{app_vm.get('cpu_source', 'xen_cpu_time_counter')}` | Freshness: `{app_vm.get('freshness_seconds', 0.0)}s`")

            # RAM Section
            st.markdown("##### 🧠 Memory Telemetry (Xen vs Guest)")
            xen_assigned_ram = app_vm.get("xen_assigned_ram_mb") or app_vm.get("allocated_ram_mb", 1024.0)
            g_total = app_vm.get("guest_total_ram_mb")
            g_used = app_vm.get("guest_used_ram_mb")
            g_avail = app_vm.get("guest_available_ram_mb")
            g_pct = app_vm.get("guest_ram_percent")
            g_pressure = app_vm.get("guest_memory_pressure", "N/A")

            r_m1, r_m2 = st.columns(2)
            with r_m1:
                st.metric("Xen-Assigned RAM", f"{xen_assigned_ram:.0f} MB", help="Actual hypervisor memory allocated to VM")
            with r_m2:
                avail_disp = f"{g_avail:.0f} MB" if g_avail is not None else "N/A"
                st.metric("Guest Available RAM", avail_disp, help="Real available memory inside Alpine Linux guest OS")

            r_m3, r_m4 = st.columns(2)
            with r_m3:
                used_disp = f"{g_used:.0f} MB" if g_used is not None else "N/A"
                st.metric("Guest Used RAM", used_disp)
            with r_m4:
                pct_disp = f"{g_pct:.1f}%" if g_pct is not None else "N/A"
                st.metric("Guest RAM %", pct_disp, delta=f"Pressure: {g_pressure}")

            st.caption(f"Memory Source: `{app_vm.get('memory_source', 'guest_proc_meminfo')}` (No fake 100% calculation)")

            # Baseline Transition
            st.markdown("##### 🎯 Baseline Control")
            if st.button("Transition to Baseline (1 vCPU, 1024 MB)", key="btn_base_app", use_container_width=True):
                b_res = api_transition_to_baseline("Alpine-Linux")
                if b_res.get("success"):
                    st.success("Alpine-Linux safely transitioned to baseline!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error(f"Transition failed: {b_res.get('error')}")

        else:
            st.warning("Application VM telemetry not currently discovered.")

    # -------------------------------------------------------------------------
    # DATABASE VM (Component 3)
    # -------------------------------------------------------------------------
    with col_db:
        st.markdown("""
            <div style="background-color:#fefce8; border:1px solid #fef08a; border-radius:8px; padding:12px; margin-bottom:12px;">
                <h4 style="margin:0; color:#854d0e;">🗄️ Database VM (Alpine-DB)</h4>
                <span style="font-size:0.85rem; color:#64748b;">Role: MariaDB 11.8.9 Relational Storage</span>
            </div>
        """, unsafe_allow_html=True)

        if db_vm:
            db_uuid = db_vm.get("uuid", "N/A")
            db_uuid_match = (db_uuid == EXPECTED_DB_VM_UUID)
            db_uuid_badge = "✅ Verified" if db_uuid_match else f"ℹ️ Discovered: `{db_uuid[:12]}...`"

            st.markdown(f"**UUID:** `{db_uuid}` ({db_uuid_badge})")
            st.markdown(f"**Power State:** `{db_vm.get('power_state', 'Unknown')}` | **IP:** `{db_vm.get('ip', '10.189.191.248')}:3306`")

            # CPU Section
            st.markdown("##### ⚡ CPU Telemetry")
            db_cpu_val = db_vm.get("cpu_percent")
            db_cpu_display = f"{db_cpu_val:.1f}%" if db_cpu_val is not None else "Calibrating..."
            db_vcpus = db_vm.get("vcpu_count", 1)

            d_m1, d_m2 = st.columns(2)
            with d_m1:
                st.metric("Actual CPU Utilization", db_cpu_display)
            with d_m2:
                st.metric("Online vCPUs", f"{db_vcpus} / 4 vCPUs (Max)")

            st.caption(f"Source: `{db_vm.get('cpu_source', 'xen_cpu_time_counter')}` | Freshness: `{db_vm.get('freshness_seconds', 0.0)}s`")

            # RAM Section
            st.markdown("##### 🧠 Memory Telemetry (Xen vs Guest)")
            db_xen_assigned_ram = db_vm.get("xen_assigned_ram_mb") or db_vm.get("allocated_ram_mb", 1024.0)
            db_g_used = db_vm.get("guest_used_ram_mb")
            db_g_avail = db_vm.get("guest_available_ram_mb")
            db_g_pct = db_vm.get("guest_ram_percent")

            dr_m1, dr_m2 = st.columns(2)
            with dr_m1:
                st.metric("Xen-Assigned RAM", f"{db_xen_assigned_ram:.0f} MB", help="Actual hypervisor memory allocated to VM")
            with dr_m2:
                db_avail_disp = f"{db_g_avail:.0f} MB" if db_g_avail is not None else "N/A"
                st.metric("Guest Available RAM", db_avail_disp, help="Real available memory inside MariaDB VM (N/A when guest agent is not installed)")

            dr_m3, dr_m4 = st.columns(2)
            with dr_m3:
                db_used_disp = f"{db_g_used:.0f} MB" if db_g_used is not None else "N/A"
                st.metric("Guest Used RAM", db_used_disp)
            with dr_m4:
                db_pct_disp = f"{db_g_pct:.1f}%" if db_g_pct is not None else "N/A"
                st.metric("Guest RAM %", db_pct_disp)

            st.caption(f"Memory Source: `{db_vm.get('memory_source', 'xen_hypervisor_only')}` (Unsafe scale-down withheld when guest RAM is N/A)")

            # Baseline Transition
            st.markdown("##### 🎯 Baseline Control")
            if st.button("Transition to Baseline (1 vCPU, 1024 MB)", key="btn_base_db", use_container_width=True):
                b_res = api_transition_to_baseline("Alpine-DB")
                if b_res.get("success"):
                    st.success("Alpine-DB safely transitioned to baseline with MariaDB safety verification!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error(f"Transition failed: {b_res.get('error')}")

        else:
            st.warning("Database VM telemetry not currently discovered.")

    st.markdown("---")

    # =========================================================================
    # COMPONENTS 4 & 5: Automatic CPU & RAM Allocation Status
    # =========================================================================
    st.markdown("### ⚙️ Elasticity Decision Matrix & Automatic Scaling")

    st.markdown("""
        <div style="background-color:#f1f5f9; border-radius:6px; padding:10px 14px; margin-bottom:14px; font-size:0.9rem; color:#334155;">
            <strong>Autonomous Actuation Rules:</strong>
            Scale-Up requires <strong>3 consecutive intervals</strong> (>80% CPU or >85% Guest RAM) to confirm sustained demand.
            Scale-Down requires <strong>6 consecutive intervals</strong> (<25% CPU or <30% Guest RAM) to prevent thrashing.
            Independent 60s cooldown is enforced per resource.
        </div>
    """, unsafe_allow_html=True)

    rec_rows = []
    for vm_key, rec in recommendations.items():
        rec_rows.append({
            "Target VM": rec.get("vm_name", vm_key),
            "CPU Action": rec.get("cpu_action", "HOLD"),
            "Current vCPUs": rec.get("current_vcpus", 1),
            "Recommended vCPUs": rec.get("recommended_vcpus", 1),
            "RAM Action": rec.get("ram_action", "HOLD"),
            "Current RAM": f"{rec.get('current_ram_mb', 1024):.0f} MB",
            "Recommended RAM": f"{rec.get('recommended_ram_mb', 1024):.0f} MB",
            "Rationale": rec.get("rationale", "Normal nominal workload"),
            "Cooldown Active": "Active" if rec.get("cooldown_active") else "Clear"
        })

    if rec_rows:
        st.dataframe(pd.DataFrame(rec_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No active recommendations currently generated.")

    # 1-Click apply recommendation if mode is manual
    if current_mode == "MANUAL":
        st.markdown("##### ⚡ 1-Click Apply Pending Recommendation")
        apply_col1, apply_col2 = st.columns([2, 1])
        with apply_col1:
            vm_to_apply = st.selectbox("Select Target VM for Recommendation:", list(recommendations.keys()) if recommendations else ["Alpine-Linux"])
        with apply_col2:
            st.write("&nbsp;")
            if st.button("Apply Recommendation", use_container_width=True, key="btn_apply_rec"):
                res = api_apply_recommendation(vm_to_apply)
                if res.get("success"):
                    st.success(f"Recommendation applied for {vm_to_apply}!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error(f"Application failed: {res.get('error')}")

    st.markdown("---")

    # =========================================================================
    # COMPONENT 6: Manual Resource Override
    # =========================================================================
    st.markdown("### 🛠️ Manual Administrator Resource Override")
    st.caption("Authorized administrator controls to scale vCPUs or RAM ballooning with verified XenAPI readback.")

    man_col1, man_col2 = st.columns(2)

    with man_col1:
        st.markdown("##### ⚡ Manual vCPU Allocation")
        man_cpu_vm = st.selectbox("Target VM for vCPU:", ["Alpine-Linux", "Alpine-DB"], key="man_cpu_vm_select")
        man_vcpus = st.slider("Select Target vCPUs:", min_value=1, max_value=4, value=2, step=1, key="man_cpu_slider")
        man_cpu_reason = st.text_input("Change Reason:", value="Administrative capacity override", key="man_cpu_reason")
        man_cpu_confirm = st.checkbox("Confirm live vCPU modification via XenAPI", key="man_cpu_confirm")

        if st.button("Apply vCPU Change", type="primary", disabled=not man_cpu_confirm, key="btn_apply_manual_cpu"):
            res = api_apply_manual_cpu(man_cpu_vm, man_vcpus, man_cpu_reason)
            if res.get("success"):
                st.success(f"Successfully scaled {man_cpu_vm} to {res.get('actual_value', man_vcpus)} vCPUs (Verified via XenAPI)!")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error(f"vCPU allocation failed: {res.get('error')}")

    with man_col2:
        st.markdown("##### 🧠 Manual Dynamic RAM Ballooning")
        man_ram_vm = st.selectbox("Target VM for RAM:", ["Alpine-Linux", "Alpine-DB"], key="man_ram_vm_select")
        man_ram_mb = st.slider("Select Dynamic RAM Target (MB):", min_value=1024, max_value=4096, value=2048, step=512, key="man_ram_slider")
        man_ram_reason = st.text_input("Change Reason:", value="Administrative memory expansion", key="man_ram_reason")
        man_ram_confirm = st.checkbox("Confirm live dynamic RAM ballooning via XenAPI", key="man_ram_confirm")

        if st.button("Apply RAM Ballooning", type="primary", disabled=not man_ram_confirm, key="btn_apply_manual_ram"):
            res = api_apply_manual_ram(man_ram_vm, man_ram_mb, man_ram_reason)
            if res.get("success"):
                st.success(f"Successfully adjusted dynamic RAM for {man_ram_vm} to {res.get('actual_value', man_ram_mb)} MB (Verified via XenAPI)!")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error(f"RAM allocation failed: {res.get('error')}")

    st.markdown("---")

    # =========================================================================
    # COMPONENT 7: Real-Time Resource Allocation Charts
    # =========================================================================
    st.markdown("### 📈 Real-Time Multi-Metric Trend Charts")

    hist_res = api_get_metrics_history(limit=60)
    history_records = hist_res.get("data", []) if hist_res.get("success") else []

    if history_records:
        df_hist = pd.DataFrame(history_records)
        df_hist["timestamp"] = pd.to_datetime(df_hist["timestamp"])

        ch_col1, ch_col2 = st.columns(2)

        with ch_col1:
            st.markdown("##### ⚡ CPU Utilization (%) Over Time")
            df_app_cpu = df_hist[df_hist["vm_name"].str.contains("Linux", case=False, na=False)][["timestamp", "cpu_percent"]].rename(columns={"cpu_percent": "Alpine-Linux CPU %"})
            df_db_cpu = df_hist[df_hist["vm_name"].str.contains("DB", case=False, na=False)][["timestamp", "cpu_percent"]].rename(columns={"cpu_percent": "Alpine-DB CPU %"})
            
            merged_cpu = pd.merge_asof(df_app_cpu.sort_values("timestamp"), df_db_cpu.sort_values("timestamp"), on="timestamp")
            if not merged_cpu.empty:
                st.line_chart(merged_cpu.set_index("timestamp"))
            else:
                st.info("Gathering initial CPU metrics samples...")

        with ch_col2:
            st.markdown("##### 🧠 Dynamic RAM Allocation (MB) Over Time")
            df_app_ram = df_hist[df_hist["vm_name"].str.contains("Linux", case=False, na=False)][["timestamp", "allocated_ram_mb"]].rename(columns={"allocated_ram_mb": "Alpine-Linux RAM (MB)"})
            df_db_ram = df_hist[df_hist["vm_name"].str.contains("DB", case=False, na=False)][["timestamp", "allocated_ram_mb"]].rename(columns={"allocated_ram_mb": "Alpine-DB RAM (MB)"})
            
            merged_ram = pd.merge_asof(df_app_ram.sort_values("timestamp"), df_db_ram.sort_values("timestamp"), on="timestamp")
            if not merged_ram.empty:
                st.line_chart(merged_ram.set_index("timestamp"))
            else:
                st.info("Gathering initial RAM metrics samples...")

    else:
        st.info("Historical metrics collector active; telemetry charts will populate with subsequent polling cycles.")

    st.markdown("---")

    # =========================================================================
    # COMPONENT 8: Allocation Event History
    # =========================================================================
    st.markdown("### 📜 Resource Allocation Event History")
    st.caption("Immutable audit log of all manual and automated scaling operations with XenAPI readback verification.")

    if history_events:
        hist_table = []
        for ev in history_events:
            hist_table.append({
                "Timestamp": ev.get("created_at", "N/A"),
                "Target VM": ev.get("vm_name", "Unknown"),
                "Resource": str(ev.get("resource_type", "")).upper(),
                "Previous": ev.get("previous_value", "N/A"),
                "Requested": ev.get("requested_value", "N/A"),
                "Actual Verified": ev.get("actual_value", "N/A"),
                "Trigger Rationale": ev.get("trigger_reason", "N/A"),
                "Status": "✅ SUCCESS" if ev.get("execution_status") == "SUCCESS" else f"❌ {ev.get('execution_status')}",
                "Initiated By": ev.get("initiated_by", "system")
            })
        st.dataframe(pd.DataFrame(hist_table), use_container_width=True, hide_index=True)
    else:
        st.info("No resource scaling operations have been actuated yet in this session.")
