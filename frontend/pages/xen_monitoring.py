"""
Streamlit Page: Xen Resource Monitoring
Displays live hypervisor and VM CPU, RAM, Network telemetry, historical charts,
and dynamic elasticity recommendations.
Configured dynamically through environment variables and backend API.
"""

import os
import time
import pandas as pd
import streamlit as st
from datetime import datetime, timezone

from frontend.api import (
    api_get_xen_metrics,
    api_get_xen_host,
    api_get_xen_vms,
    api_get_xen_monitor_status,
    api_get_xen_history
)
from frontend.components.cards import render_section_title, render_metric_card

def render_xen_monitoring_page():
    render_section_title(
        "📈 Xen Resource Monitoring",
        "Real-time XCP-ng hypervisor & virtual machine performance telemetry"
    )

    # Top Action Bar: Refresh & Auto-Refresh Controls
    col_status_info, col_refresh_btn, col_autorefresh = st.columns([3, 1, 1])

    with col_refresh_btn:
        manual_refresh = st.button("🔄 Refresh Now", use_container_width=True)

    with col_autorefresh:
        auto_refresh = st.checkbox("Auto-refresh (5s)", value=False, help="Automatically refreshes live telemetry every 5 seconds.")

    # Fetch live metrics & status
    with st.spinner("Fetching live telemetry from Xen Monitoring Engine..."):
        metrics_resp = api_get_xen_metrics()
        status_resp = api_get_xen_monitor_status()

    is_online = False
    metrics_data = {}
    status_data = {}

    if metrics_resp.get("success"):
        metrics_data = metrics_resp.get("data", {})
        is_online = metrics_data.get("connected", False)

    if status_resp.get("success"):
        status_data = status_resp.get("data", {})

    # Dynamic target configurations from backend or environment
    config_data = status_data.get("config", {})
    target_app_name = config_data.get("app_vm_name") or os.getenv("APP_VM_NAME", "Alpine-Linux")
    target_db_name = config_data.get("db_vm_name") or os.getenv("DB_VM_NAME", "Alpine-DB")
    target_xcp_host = config_data.get("xcp_host") or os.getenv("XCP_NG_HOST", "10.189.191.175")
    poll_interval = config_data.get("poll_interval_sec") or os.getenv("MONITOR_INTERVAL", "5")

    # Connection Status Banner
    last_update = metrics_data.get("last_successful_update_iso") or "Never"
    if is_online:
        st.markdown(
            f"""
            <div style="background:#ECFDF5; border:1px solid #10B981; border-left:5px solid #059669; padding:14px 18px; border-radius:8px; margin-bottom:18px;">
                <div style="font-weight:700; color:#065F46; font-size:1.05rem;">
                    🟢 XCP-ng Hypervisor: Online & Connected
                </div>
                <div style="font-size:0.85rem; color:#475569; margin-top:4px;">
                    Host IP: <b>{metrics_data.get('hypervisor', {}).get('ip') or target_xcp_host}</b> |
                    Last Successful Update: <b>{last_update}</b> | Polling Interval: <b>{poll_interval}s</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        err_msg = metrics_data.get("error") or status_data.get("error") or "XCP-ng host unreachable."
        st.markdown(
            f"""
            <div style="background:#FEF2F2; border:1px solid #EF4444; border-left:5px solid #DC2626; padding:14px 18px; border-radius:8px; margin-bottom:18px;">
                <div style="font-weight:700; color:#991B1B; font-size:1.05rem;">
                    🔴 XCP-ng Monitoring: Offline / Disconnected
                </div>
                <div style="font-size:0.85rem; color:#475569; margin-top:4px;">
                    Target Host: <b>{target_xcp_host}</b> |
                    Diagnostics: <code>{err_msg}</code>
                </div>
                <div style="font-size:0.8rem; color:#6B7280; margin-top:6px;">
                    <i>Note: Per system specifications, no simulated or fabricated data is displayed.
                    Ensure the XCP-ng host is powered on and accessible over the current network.</i>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    # 1. Hypervisor Metrics Section
    st.markdown("### 🖥️ **XCP-ng Hypervisor Host Telemetry**")
    host = metrics_data.get("hypervisor") if is_online else None

    if host:
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            render_metric_card("CPU Cores", host.get("total_cpu_cores", 0), "Physical host cores")
        with c2:
            render_metric_card("Host CPU Load", f"{host.get('cpu_percent', 0.0)}%", "Core utilization")
        with c3:
            render_metric_card("Physical RAM", f"{host.get('total_ram_mb', 0.0)} MB", f"Total installed")
        with c4:
            render_metric_card("Used / Free RAM", f"{host.get('used_ram_mb', 0.0)} MB", f"Free: {host.get('available_ram_mb', 0.0)} MB")
        with c5:
            render_metric_card("Active VMs", host.get("running_vms", 0), f"Total: {host.get('total_vms', 0)}")

        # Host Progress Bars
        pcol1, pcol2 = st.columns(2)
        with pcol1:
            cpu_val = min(100.0, max(0.0, float(host.get("cpu_percent", 0.0))))
            st.caption(f"Host CPU Utilization: **{cpu_val}%**")
            st.progress(cpu_val / 100.0)
        with pcol2:
            ram_val = min(100.0, max(0.0, float(host.get("ram_percent", 0.0))))
            free_ram = host.get("available_ram_mb", 0.0)
            st.caption(f"Host RAM Utilization: **{ram_val}%** (Used: {host.get('used_ram_mb', 0)} MB / Free: {free_ram} MB)")
            st.progress(ram_val / 100.0)
    else:
        st.info("Host hypervisor live metrics unavailable while disconnected from XCP-ng XAPI.")

    st.markdown("---")

    # 2. Virtual Machines Real-Time Metrics
    st.markdown("### 📦 **Virtual Machines Real-Time Telemetry**")
    vms_dict = metrics_data.get("vms", {}) if is_online else {}

    def lookup_vm(vms_map, target_name):
        if not vms_map:
            return {}
        # 1. Exact match
        if target_name in vms_map:
            return vms_map[target_name]
        # 2. Case-insensitive exact match
        for k, v in vms_map.items():
            if k.lower() == target_name.lower():
                return v
        # 3. Alias fallback (e.g. Alpine-Linux <-> Alpine-Linux-New)
        alias_map = {"alpine-linux-new": "alpine-linux", "alpine-linux": "alpine-linux-new"}
        alt = alias_map.get(target_name.lower())
        if alt:
            for k, v in vms_map.items():
                if k.lower() == alt:
                    return v
        # 4. Normalized match
        norm_t = target_name.lower().replace("-", "").replace("_", "").replace(" ", "")
        for k, v in vms_map.items():
            if k.lower().replace("-", "").replace("_", "").replace(" ", "") == norm_t:
                return v
        return {}

    app_vm = lookup_vm(vms_dict, target_app_name)
    db_vm = lookup_vm(vms_dict, target_db_name)

    app_display_name = app_vm.get("name") or target_app_name
    db_display_name = db_vm.get("name") or target_db_name

    col_app, col_db = st.columns(2)

    with col_app:
        app_power = app_vm.get("power_state", "Unknown") if app_vm else "Offline"
        app_power_badge = "🟢 Running" if app_power == "Running" else f"🔴 {app_power}"
        st.markdown(
            f"""
            <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-top:4px solid #2563EB; padding:16px; border-radius:8px; margin-bottom:12px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <h4 style="margin:0; color:#1E40AF;">🚀 Application VM: {app_display_name}</h4>
                    <span style="font-size:0.8rem; font-weight:600; padding:2px 8px; border-radius:12px; background:#EFF6FF; color:#1E40AF;">{app_power_badge}</span>
                </div>
                <div style="font-size:0.8rem; color:#64748B; margin-top:4px;">
                    UUID: <code>{app_vm.get('uuid', 'Dynamic Discovery')}</code> | Role: Flask API (5000) + Streamlit UI (8501)
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        if app_vm and (app_vm.get("status") == "online" or app_vm.get("power_state") == "Running"):
            mc1, mc2 = st.columns(2)
            with mc1:
                render_metric_card("Configured vCPUs", app_vm.get("vcpu_count", 1), f"Current Load: {app_vm.get('cpu_percent', 0.0)}%")
            with mc2:
                render_metric_card("Memory Allocation", f"{app_vm.get('allocated_ram_mb', 0)} MB", f"Used: {app_vm.get('used_ram_mb', 0)} MB ({app_vm.get('ram_percent', 0.0)}%)")

            app_cpu = min(100.0, max(0.0, float(app_vm.get("cpu_percent", 0.0))))
            app_ram = min(100.0, max(0.0, float(app_vm.get("ram_percent", 0.0))))
            st.caption(f"App VM CPU Utilization: **{app_cpu}%**")
            st.progress(app_cpu / 100.0)
            st.caption(f"App VM RAM Utilization: **{app_ram}%**")
            st.progress(app_ram / 100.0)
            
            rx_b = app_vm.get("network_rx_bytes", 0)
            tx_b = app_vm.get("network_tx_bytes", 0)
            st.caption(f"Network I/O: **RX: {round(rx_b / 1024 / 1024, 2)} MB** | **TX: {round(tx_b / 1024 / 1024, 2)} MB** ({app_vm.get('network_rate_human', 'Active')})")
        else:
            reason = app_vm.get("reason") if app_vm else f"VM named '{app_display_name}' not discovered on XCP-ng host."
            st.warning(f"{app_display_name} telemetry unavailable: {reason}")

    with col_db:
        db_power = db_vm.get("power_state", "Unknown") if db_vm else "Offline"
        db_power_badge = "🟢 Running" if db_power == "Running" else f"🔴 {db_power}"
        st.markdown(
            f"""
            <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-top:4px solid #059669; padding:16px; border-radius:8px; margin-bottom:12px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <h4 style="margin:0; color:#065F46;">🗄️ Database VM: {db_display_name}</h4>
                    <span style="font-size:0.8rem; font-weight:600; padding:2px 8px; border-radius:12px; background:#ECFDF5; color:#065F46;">{db_power_badge}</span>
                </div>
                <div style="font-size:0.8rem; color:#64748B; margin-top:4px;">
                    UUID: <code>{db_vm.get('uuid', 'Dynamic Discovery')}</code> | Role: MariaDB 11.8.9 (Port 3306)
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        if db_vm and (db_vm.get("status") == "online" or db_vm.get("power_state") == "Running"):
            mc1, mc2 = st.columns(2)
            with mc1:
                render_metric_card("Configured vCPUs", db_vm.get("vcpu_count", 1), f"Current Load: {db_vm.get('cpu_percent', 0.0)}%")
            with mc2:
                render_metric_card("Memory Allocation", f"{db_vm.get('allocated_ram_mb', 0)} MB", f"Used: {db_vm.get('used_ram_mb', 0)} MB ({db_vm.get('ram_percent', 0.0)}%)")

            db_cpu = min(100.0, max(0.0, float(db_vm.get("cpu_percent", 0.0))))
            db_ram = min(100.0, max(0.0, float(db_vm.get("ram_percent", 0.0))))
            st.caption(f"DB VM CPU Utilization: **{db_cpu}%**")
            st.progress(db_cpu / 100.0)
            st.caption(f"DB VM RAM Utilization: **{db_ram}%**")
            st.progress(db_ram / 100.0)

            rx_b = db_vm.get("network_rx_bytes", 0)
            tx_b = db_vm.get("network_tx_bytes", 0)
            st.caption(f"Network I/O: **RX: {round(rx_b / 1024 / 1024, 2)} MB** | **TX: {round(tx_b / 1024 / 1024, 2)} MB** ({db_vm.get('network_rate_human', 'Active')})")
        else:
            reason = db_vm.get("reason") if db_vm else f"VM named '{db_display_name}' not discovered on XCP-ng host."
            st.warning(f"{db_display_name} telemetry unavailable: {reason}")

    st.markdown("---")

    # 3. Side-by-Side Comparison Table
    st.markdown("### 📊 **Virtual Machine Resource Allocations & Comparison**")
    all_vms = metrics_data.get("all_discovered_vms", [])
    if all_vms:
        df_vms = pd.DataFrame(all_vms)
        st.dataframe(df_vms, use_container_width=True, hide_index=True)
    else:
        st.caption("No dynamic VM list available from hypervisor.")

    st.markdown("---")

    # 4. Dynamic Allocation Recommendations (Phase 3 Preparation - READ ONLY)
    st.markdown("### ⚖️ **Dynamic Elasticity Recommendations (Phase 3 Preparation - Read-Only)**")
    st.caption("Threshold-based elasticity model with anti-thrashing cooldown timers. Advisory recommendations only; no automated VM resizing or reboots.")

    recommendations = metrics_data.get("recommendations", {})
    if recommendations:
        rcol1, rcol2 = st.columns(2)
        for i, (vm_name, rec) in enumerate(recommendations.items()):
            target_col = rcol1 if i % 2 == 0 else rcol2
            with target_col:
                badge_color = "#10B981" if rec.get("cpu_action") == "HOLD" and rec.get("ram_action") == "HOLD" else "#F59E0B"
                st.markdown(
                    f"""
                    <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-left:4px solid {badge_color}; padding:14px; border-radius:8px; margin-bottom:12px;">
                        <h4 style="margin:0 0 6px 0; color:#1E40AF;">{vm_name}</h4>
                        <div style="font-size:0.85rem; color:#475569;">
                            CPU Action: <b>{rec.get('cpu_action')}</b> | RAM Action: <b>{rec.get('ram_action')}</b><br>
                            Recommended: <b>{rec.get('recommended_vcpus')} vCPUs</b> | <b>{rec.get('recommended_ram_mb')} MB RAM</b><br>
                            Cooldown Active: <b>{'Yes' if rec.get('cooldown_active') else 'No'}</b>
                        </div>
                        <div style="font-size:0.8rem; color:#64748B; margin-top:8px; background:#F8FAFC; padding:8px; border-radius:4px;">
                            💡 <b>Rationale:</b> {rec.get('rationale')}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
    else:
        st.info("Recommendations will be evaluated once live telemetry is received from XCP-ng.")

    st.markdown("---")

    # 5. Historical Telemetry Charts
    st.markdown("### 📈 **Historical Telemetry Trends**")
    st.caption("Persistently stored metrics retrieved from database history.")

    hist_resp = api_get_xen_history(limit=50)
    history_records = hist_resp.get("data", []) if hist_resp.get("success") else []

    if history_records:
        df_hist = pd.DataFrame(history_records)
        df_hist["timestamp"] = pd.to_datetime(df_hist["timestamp"])

        tab_cpu, tab_ram, tab_net, tab_comp = st.tabs([
            "CPU Utilization (%)",
            "RAM Utilization (%)",
            "Network Traffic (Bytes)",
            "VM Comparison Snapshot"
        ])

        with tab_cpu:
            try:
                pivot_cpu = df_hist.pivot_table(index="timestamp", columns="vm_name", values="cpu_percent", aggfunc="mean").bfill().ffill()
                st.line_chart(pivot_cpu, use_container_width=True)
            except Exception as e:
                st.line_chart(df_hist[["timestamp", "cpu_percent"]].set_index("timestamp"), use_container_width=True)

        with tab_ram:
            try:
                pivot_ram = df_hist.pivot_table(index="timestamp", columns="vm_name", values="ram_percent", aggfunc="mean").bfill().ffill()
                st.line_chart(pivot_ram, use_container_width=True)
            except Exception as e:
                st.line_chart(df_hist[["timestamp", "ram_percent"]].set_index("timestamp"), use_container_width=True)

        with tab_net:
            try:
                pivot_net = df_hist.pivot_table(index="timestamp", columns="vm_name", values="network_rx_bytes", aggfunc="mean").bfill().ffill()
                st.line_chart(pivot_net, use_container_width=True)
            except Exception as e:
                st.line_chart(df_hist[["timestamp", "network_rx_bytes"]].set_index("timestamp"), use_container_width=True)

        with tab_comp:
            st.caption("Latest recorded metrics comparison across virtual machines:")
            latest_vms = df_hist.sort_values("timestamp").groupby("vm_name").last().reset_index()
            comp_cols = ["vm_name", "cpu_percent", "ram_percent", "allocated_ram_mb", "vcpu_count"]
            available_comp_cols = [c for c in comp_cols if c in latest_vms.columns]
            st.dataframe(latest_vms[available_comp_cols], use_container_width=True, hide_index=True)
    else:
        st.info("No historical records available in the database yet. As the monitoring daemon polls XCP-ng, time-series data will populate automatically.")

    # Auto-refresh loop
    if auto_refresh:
        time.sleep(5)
        st.rerun()
