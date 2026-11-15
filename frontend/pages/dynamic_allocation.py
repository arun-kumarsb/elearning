"""
Streamlit Page: Dynamic Resource Allocation Control Panel (Phase 3)
Project: Xen-Based Dynamic Resource Allocation for Scalable E-Learning Services

Provides administrator controls for automated and manual Xen hypervisor scaling:
- Automation status & Emergency Stop
- Real-time VM resource cards (vCPU, Dynamic RAM limits)
- Elasticity recommendations table & 1-click apply
- Manual CPU & RAM adjustment with confirmation gates
- Audit history & Static vs. Dynamic efficiency analysis
"""

import os
import time
import pandas as pd
import streamlit as st
from datetime import datetime, timezone
from typing import Dict, Any, List

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
    api_get_xen_history
)
from frontend.components.cards import render_section_title, render_metric_card

def render_dynamic_allocation_page():
    render_section_title(
        "⚡ Dynamic Resource Allocation",
        "Autonomous elasticity controller & administrator actuation panel for XCP-ng / Xen"
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

    # Fetch live state
    with st.spinner("Connecting to Xen Allocation Controller..."):
        alloc_status_resp = api_get_allocation_status()
        metrics_resp = api_get_xen_metrics()
        monitor_status_resp = api_get_xen_monitor_status()
        alloc_history_resp = api_get_allocation_history(limit=50)

    alloc_data = alloc_status_resp.get("data", {}) if alloc_status_resp.get("success") else {}
    metrics_data = metrics_resp.get("data", {}) if metrics_resp.get("success") else {}
    monitor_data = monitor_status_resp.get("data", {}) if monitor_status_resp.get("success") else {}
    history_records = alloc_history_resp.get("data", []) if alloc_history_resp.get("success") else []

    is_connected = metrics_data.get("connected", False)
    mode = alloc_data.get("allocation_mode", "manual").upper()
    emergency_stop = alloc_data.get("emergency_stop", False)
    poll_interval = alloc_data.get("poll_interval_sec", 5)
    last_update = metrics_data.get("last_successful_update_iso") or "Never"

    # Get last action from history
    last_action_str = "None recorded"
    if history_records:
        latest_act = history_records[0]
        last_action_str = f"{latest_act.get('action_type')} on {latest_act.get('vm_name')} ({latest_act.get('execution_status')}) at {latest_act.get('created_at', '')[:19]}"

    # =============================================================
    # SECTION A: AUTOMATION STATUS
    # =============================================================
    st.markdown("### 🎛️ **A. Automation Controller Status**")

    # Emergency stop alert banner if engaged
    if emergency_stop:
        st.error(
            "🚨 **EMERGENCY STOP ENGAGED**: All automated dynamic scaling operations are currently blocked! "
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
        render_metric_card("Emergency Stop", estop_badge, "Automated scaling blocked" if emergency_stop else "Automated actuation permitted")
    with sc4:
        render_metric_card("Polling Interval", f"{poll_interval}s", f"Last sync: {last_update[-8:] if len(last_update) > 8 else last_update}")

    st.caption(f"**Last Allocation Event:** {last_action_str}")
    st.markdown("---")

    # =============================================================
    # SECTION B: VM RESOURCE CARDS
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

    col_vm1, col_vm2 = st.columns(2)

    with col_vm1:
        st.markdown(
            f"""
            <div style="background:#F8FAFC; border:1px solid #CBD5E1; border-top:4px solid #3B82F6; padding:16px; border-radius:10px; margin-bottom:15px;">
                <h4 style="margin:0 0 8px 0; color:#1E3A8A;">🖥️ Application VM: {app_vm.get('name', app_vm_name)}</h4>
                <div style="font-size:0.8rem; color:#64748B; margin-bottom:12px;">
                    UUID: <code>{app_vm.get('uuid', 'N/A')}</code> | State: <b>{app_vm.get('power_state', 'N/A')}</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        c1, c2 = st.columns(2)
        with c1:
            st.metric("vCPUs Allocated", f"{app_vm.get('vcpu_count', 'N/A')}")
            st.metric("CPU Utilization", f"{app_vm.get('cpu_percent', 'N/A')}%")
            st.metric("Recommended vCPUs", f"{app_rec.get('recommended_vcpus', app_vm.get('vcpu_count', 'N/A'))}")
        with c2:
            st.metric("Allocated Dynamic RAM", f"{app_vm.get('allocated_ram_mb', 'N/A')} MB")
            st.metric("RAM Utilization", f"{app_vm.get('ram_percent', 'N/A')}%")
            st.metric("Recommended RAM", f"{app_rec.get('recommended_ram_mb', app_vm.get('allocated_ram_mb', 'N/A'))} MB")

    with col_vm2:
        st.markdown(
            f"""
            <div style="background:#F8FAFC; border:1px solid #CBD5E1; border-top:4px solid #10B981; padding:16px; border-radius:10px; margin-bottom:15px;">
                <h4 style="margin:0 0 8px 0; color:#065F46;">🗄️ Database VM: {db_vm.get('name', db_vm_name)}</h4>
                <div style="font-size:0.8rem; color:#64748B; margin-bottom:12px;">
                    UUID: <code>{db_vm.get('uuid', 'N/A')}</code> | State: <b>{db_vm.get('power_state', 'N/A')}</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        c1, c2 = st.columns(2)
        with c1:
            st.metric("vCPUs Allocated", f"{db_vm.get('vcpu_count', 'N/A')}")
            st.metric("CPU Utilization", f"{db_vm.get('cpu_percent', 'N/A')}%")
            st.metric("Recommended vCPUs", f"{db_rec.get('recommended_vcpus', db_vm.get('vcpu_count', 'N/A'))}")
        with c2:
            st.metric("Allocated Dynamic RAM", f"{db_vm.get('allocated_ram_mb', 'N/A')} MB")
            st.metric("RAM Utilization", f"{db_vm.get('ram_percent', 'N/A')}%")
            st.metric("Recommended RAM", f"{db_rec.get('recommended_ram_mb', db_vm.get('allocated_ram_mb', 'N/A'))} MB")

    st.markdown("---")

    # =============================================================
    # SECTION C: ALLOCATION RECOMMENDATIONS
    # =============================================================
    st.markdown("### 📋 **C. Real-Time Elasticity Recommendations**")

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
    # SECTION D: ADMINISTRATOR CONTROLS
    # =============================================================
    st.markdown("### 🛠️ **D. Administrator Control Panel**")

    ctrl_tab1, ctrl_tab2, ctrl_tab3 = st.tabs([
        "⚙️ Automation & Safety Mode",
        "🎛️ Manual CPU Allocation",
        "🎈 Manual RAM Dynamic Ballooning"
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
                        st.warning("Emergency stop engaged! All scaling halted.")
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
        cur_vcpus = int(app_vm.get("vcpu_count", 1) if target_vm_cpu == app_vm.get("name", app_vm_name) else db_vm.get("vcpu_count", 1))

        new_vcpus = st.slider(
            "Target vCPU Count",
            min_value=1,
            max_value=4,
            value=cur_vcpus,
            step=1,
            help="Configured boundary: 1 to 4 vCPUs"
        )
        cpu_reason = st.text_input("Operational Reason", value="Administrator manual capacity adjustment", key="cpu_reason_input")
        cpu_confirm = st.checkbox(f"⚠️ I confirm live vCPU modification of '{target_vm_cpu}' to {new_vcpus} vCPUs.", key="cpu_confirm_chk")

        if st.button("🚀 Apply vCPU Modification", disabled=not cpu_confirm or (new_vcpus == cur_vcpus), type="primary"):
            with st.spinner("Actuating XenAPI set_VCPUs_number_live..."):
                res = api_apply_manual_cpu(target_vm_cpu, new_vcpus, reason=cpu_reason)
            if res.get("success"):
                st.success(f"Successfully scaled vCPUs for {target_vm_cpu} to {res.get('actual_value')}!")
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
        cur_ram = float(app_vm.get("allocated_ram_mb", 1024.0) if target_vm_ram == app_vm.get("name", app_vm_name) else db_vm.get("allocated_ram_mb", 1024.0))

        ram_options = [1024, 1536, 2048, 2560, 3072, 3584, 4096]
        closest_ram = min(ram_options, key=lambda x: abs(x - cur_ram))

        new_ram = st.select_slider(
            "Target Dynamic Memory Ceiling (MB)",
            options=ram_options,
            value=closest_ram,
            help="Dynamic limits: 1024 MB minimum, 4096 MB maximum (512 MB step increments)"
        )
        ram_reason = st.text_input("Operational Reason", value="Administrator dynamic memory adjustment", key="ram_reason_input")
        ram_confirm = st.checkbox(f"⚠️ I confirm dynamic memory adjustment of '{target_vm_ram}' to {new_ram} MB.", key="ram_confirm_chk")

        if st.button("🎈 Apply Memory Ballooning", disabled=not ram_confirm or (new_ram == cur_ram), type="primary"):
            with st.spinner("Actuating XenAPI set_memory_dynamic_range & ballooning..."):
                res = api_apply_manual_ram(target_vm_ram, float(new_ram), reason=ram_reason)
            if res.get("success"):
                st.success(f"Successfully adjusted dynamic memory for {target_vm_ram} to {res.get('actual_value')} MB!")
                time.sleep(1)
                st.rerun()
            else:
                st.error(f"Failed to adjust dynamic memory: {res.get('error')}")

    st.markdown("---")

    # =============================================================
    # SECTION E: PERFORMANCE MONITORING & VISUALIZATION (Section 12)
    # =============================================================
    st.markdown("### 📊 **E. Performance Telemetry & Allocation Audit Trail**")

    v_tab1, v_tab2, v_tab3 = st.tabs([
        "📜 Resource Allocation Audit History",
        "📈 Telemetry Trends (CPU & RAM)",
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
        else:
            st.caption("Telemetry history is loading from MariaDB/SQLite...")

    with v_tab3:
        st.markdown("##### Static Overprovisioning vs. Dynamic Resource Elasticity")
        st.markdown(
            """
            In traditional static virtualization, virtual machines must be provisioned for theoretical peak capacity
            (e.g., 4 vCPUs and 4096 MB RAM per VM). This results in massive hypervisor resource waste during off-peak hours.

            **Xen Dynamic Resource Allocation Advantages:**
            - **vCPU Elasticity:** Cores are hot-plugged on demand (>80% utilization) and reclaimed (<25%) when idle.
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
