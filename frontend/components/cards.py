from typing import Any
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

def render_system_header():
    """Render the top banner showcasing the Xen Virtualized Infrastructure."""
    st.markdown(
        """
        <div class="app-header-container">
            <div class="app-header-title">🎓 Xen E-Learning Platform</div>
            <div class="app-header-subtitle">
                Project: Xen-Based Dynamic Resource Allocation for Scalable E-Learning Services
            </div>
            <div class="vm-badge-bar">
                <span class="vm-badge">🖥️ App VM: Alpine-Linux-New (10.240.109.51)</span>
                <span class="vm-badge">🗄️ DB VM: Alpine-DB (10.240.109.248)</span>
                <span class="vm-badge">⚙️ Hypervisor: XCP-ng / Xen (10.240.109.196)</span>
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
