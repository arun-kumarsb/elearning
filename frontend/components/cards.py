import os
from typing import Any, Optional
import streamlit as st

def render_metric_card(label: str, value: Any, description: str = ""):
    """Render a clean, modern KPI card in blue & white."""
    desc_html = f'<div class="metric-card-desc">{description}</div>' if description else ""
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-card-label">{label}</div>
            <div class="metric-card-value">{value}</div>
            {desc_html}
        </div>
        """,
        unsafe_allow_html=True
    )

def render_system_header(
    app_vm_name: Optional[str] = None,
    app_vm_ip: Optional[str] = None,
    db_vm_name: Optional[str] = None,
    db_vm_ip: Optional[str] = None,
    xcp_host: Optional[str] = None
):
    """Render the top banner showcasing the Xen Virtualized Infrastructure dynamically."""
    app_name = app_vm_name or os.getenv("APP_VM_NAME", "Alpine-Linux")
    app_ip = app_vm_ip or os.getenv("APP_VM_IP", "10.189.191.51")
    db_name = db_vm_name or os.getenv("DB_VM_NAME", "Alpine-DB")
    db_ip = db_vm_ip or os.getenv("DB_VM_IP", "10.189.191.248")
    host_ip = xcp_host or os.getenv("XCP_NG_HOST", "10.189.191.175")

    st.markdown(
        f"""
        <div class="app-header-container">
            <div class="app-header-title">🎓 Xen E-Learning Platform</div>
            <div class="app-header-subtitle">
                Project: Xen-Based Dynamic Resource Allocation for Scalable E-Learning Services
            </div>
            <div class="vm-badge-bar">
                <span class="vm-badge">🖥️ App VM: {app_name} ({app_ip})</span>
                <span class="vm-badge">🗄️ DB VM: {db_name} ({db_ip})</span>
                <span class="vm-badge">⚙️ Hypervisor: XCP-ng / Xen ({host_ip})</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

def render_section_title(title: str, subtitle: str = ""):
    """Render a clean section header."""
    st.subheader(title)
    if subtitle:
        st.caption(subtitle)
