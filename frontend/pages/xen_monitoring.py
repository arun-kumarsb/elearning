"""
Streamlit Page: Xen Resource Monitoring
Displays live hypervisor and VM CPU, RAM, Network telemetry, historical charts,
and dynamic elasticity recommendations.
"""

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
                    Host: <b>{metrics_data.get('hypervisor', {}).get('ip', 'N/A')}</b> |
                    Last Successful Update: <b>{last_update}</b> | Polling Interval: <b>5s</b>
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
                    Target Host: <b>{status_data.get('config', {}).get('xcp_host', '10.240.109.196')}</b> |
                    Reason: <code>{err_msg}</code>
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
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            render_metric_card("Host CPU Cores", host.get("total_cpu_cores", 0), "Physical CPU cores")
        with c2:
            render_metric_card("Host CPU Load", f"{host.get('cpu_percent', 0.0)}%", "Aggregate CPU utilization")
        with c3:
            render_metric_card("Total Physical RAM", f"{host.get('total_ram_mb', 0.0)} MB", f"Used: {host.get('used_ram_mb', 0.0)} MB")
        with c4:
            render_metric_card("Active Virtual Machines", host.get("running_vms", 0), f"Total provisioned: {host.get('total_vms', 0)}")

        # Host Progress Bars
        pcol1, pcol2 = st.columns(2)
        with pcol1:
            cpu_val = min(100.0, max(0.0, float(host.get("cpu_percent", 0.0))))
            st.caption(f"Host CPU Utilization: **{cpu_val}%**")
            st.progress(cpu_val / 100.0)
        with pcol2:
            ram_val = min(100.0, max(0.0, float(host.get("ram_percent", 0.0))))
            st.caption(f"Host RAM Utilization: **{ram_val}%** ({host.get('used_ram_mb', 0)}MB / {host.get('total_ram_mb', 0)}MB)")
            st.progress(ram_val / 100.0)
    else:
        st.info("Host hypervisor live metrics unavailable while disconnected from XCP-ng XAPI.")

    st.markdown("---")

    # 2. Virtual Machines Real-Time Metrics
    st.markdown("### 📦 **Virtual Machines Real-Time Telemetry**")
    vms_dict = metrics_data.get("vms", {}) if is_online else {}
    app_vm = vms_dict.get("Alpine-Linux-New", {})
    db_vm = vms_dict.get("Alpine-DB", {})

    col_app, col_db = st.columns(2)

    with col_app:
        st.markdown(
            """
            <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-top:4px solid #2563EB; padding:16px; border-radius:8px; margin-bottom:12px;">
                <h4 style="margin:0 0 6px 0; color:#1E40AF;">🚀 Application VM: Alpine-Linux-New</h4>
                <div style="font-size:0.8rem; color:#64748B;">Role: Flask API (5000) + Streamlit UI (8501)</div>
            </div>
            """,
            unsafe_allow_html=True
        )
        if app_vm and app_vm.get("status") == "online":
            mc1, mc2 = st.columns(2)
            with mc1:
                render_metric_card("Configured vCPUs", app_vm.get("vcpu_count", 1), f"Load: {app_vm.get('cpu_percent', 0.0)}%")
            with mc2:
                render_metric_card("Memory Allocated", f"{app_vm.get('allocated_ram_mb', 0)} MB", f"Used: {app_vm.get('used_ram_mb', 0)} MB")

            app_cpu = min(100.0, max(0.0, float(app_vm.get("cpu_percent", 0.0))))
            app_ram = min(100.0, max(0.0, float(app_vm.get("ram_percent", 0.0))))
            st.caption(f"App VM CPU Usage: **{app_cpu}%**")
            st.progress(app_cpu / 100.0)
            st.caption(f"App VM RAM Usage: **{app_ram}%**")
            st.progress(app_ram / 100.0)
            st.caption(f"Network Throughput: **{app_vm.get('network_rate_human', 'N/A')}**")
        else:
            st.warning("Alpine-Linux-New telemetry offline or VM not discovered.")

    with col_db:
        st.markdown(
            """
            <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-top:4px solid #059669; padding:16px; border-radius:8px; margin-bottom:12px;">
                <h4 style="margin:0 0 6px 0; color:#065F46;">🗄️ Database VM: Alpine-DB</h4>
                <div style="font-size:0.8rem; color:#64748B;">Role: MariaDB 11.8.9 (Port 3306)</div>
            </div>
            """,
            unsafe_allow_html=True
        )
        if db_vm and db_vm.get("status") == "online":
            mc1, mc2 = st.columns(2)
            with mc1:
                render_metric_card("Configured vCPUs", db_vm.get("vcpu_count", 1), f"Load: {db_vm.get('cpu_percent', 0.0)}%")
            with mc2:
                render_metric_card("Memory Allocated", f"{db_vm.get('allocated_ram_mb', 0)} MB", f"Used: {db_vm.get('used_ram_mb', 0)} MB")

            db_cpu = min(100.0, max(0.0, float(db_vm.get("cpu_percent", 0.0))))
            db_ram = min(100.0, max(0.0, float(db_vm.get("ram_percent", 0.0))))
            st.caption(f"DB VM CPU Usage: **{db_cpu}%**")
            st.progress(db_cpu / 100.0)
            st.caption(f"DB VM RAM Usage: **{db_ram}%**")
            st.progress(db_ram / 100.0)
            st.caption(f"Network Throughput: **{db_vm.get('network_rate_human', 'N/A')}**")
        else:
            st.warning("Alpine-DB telemetry offline or VM not discovered.")

    st.markdown("---")

    # 3. Side-by-Side Comparison Table
    st.markdown("### 📊 **Virtual Machine Resource Allocations & Status**")
    all_vms = metrics_data.get("all_discovered_vms", [])
    if all_vms:
        df_vms = pd.DataFrame(all_vms)
        st.dataframe(df_vms, use_container_width=True, hide_index=True)
    else:
        st.caption("No dynamic VM list available from hypervisor.")

    st.markdown("---")

    # 4. Dynamic Allocation Recommendations (Phase 3 Preparation)
    st.markdown("### ⚖️ **Dynamic Elasticity & Allocation Recommendations (Phase 3 Prep)**")
    st.caption("Rule-based elasticity policies evaluated in real-time with anti-thrashing cooldown timers.")

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
        st.info("Recommendations will be computed as soon as telemetry streams from XCP-ng.")

    st.markdown("---")

    # 5. Historical Telemetry Charts
    st.markdown("### 📈 **Historical Telemetry Trends**")
    st.caption("Persistently stored metrics retrieved from database history.")

    hist_resp = api_get_xen_history(limit=50)
    history_records = hist_resp.get("data", []) if hist_resp.get("success") else []

    if history_records:
        df_hist = pd.DataFrame(history_records)
        df_hist["timestamp"] = pd.to_datetime(df_hist["timestamp"])

        tab_cpu, tab_ram, tab_net = st.tabs(["CPU Utilization (%)", "RAM Utilization (%)", "Network Traffic (Bytes)"])

        with tab_cpu:
            pivot_cpu = df_hist.pivot_table(index="timestamp", columns="vm_name", values="cpu_percent", aggfunc="mean").fillna(method="ffill")
            st.line_chart(pivot_cpu, use_container_width=True)

        with tab_ram:
            pivot_ram = df_hist.pivot_table(index="timestamp", columns="vm_name", values="ram_percent", aggfunc="mean").fillna(method="ffill")
            st.line_chart(pivot_ram, use_container_width=True)

        with tab_net:
            pivot_net = df_hist.pivot_table(index="timestamp", columns="vm_name", values="network_rx_bytes", aggfunc="mean").fillna(method="ffill")
            st.line_chart(pivot_net, use_container_width=True)
    else:
        st.caption("No historical records recorded yet. As the monitoring engine runs, time-series data will populate here.")

    # Auto-refresh loop
    if auto_refresh:
        time.sleep(5)
        st.rerun()
