import streamlit as st
from frontend.api import api_get_health, api_get_dashboard
from frontend.components.cards import render_section_title, render_metric_card

def render_admin_page():
    render_section_title("🛡️ Administrator Hub", "System administration, database diagnostics, and quick management links")

    user = st.session_state.get("user", {})
    if user.get("role") != "admin":
        st.warning("⚠️ Access restricted to Administrators.")
        return

    # Diagnostic Health Check
    health = api_get_health()
    db_ok = health.get("status") == "healthy"

    # Status Banner
    st.markdown(
        f"""
        <div style="background:{'#ECFDF5' if db_ok else '#FEF2F2'}; border:1px solid {'#10B981' if db_ok else '#EF4444'}; padding:16px; border-radius:8px; margin-bottom:20px;">
            <div style="font-weight:700; color:{'#065F46' if db_ok else '#991B1B'}; font-size:1.1rem;">
                {'✅ System Operational - MariaDB Connected' if db_ok else '⚠️ Database Connection Warning'}
            </div>
            <div style="font-size:0.85rem; color:#475569; margin-top:4px;">
                Application Server: <b>Alpine-Linux-New (10.240.109.201)</b> | Target Database: <b>Alpine-DB (10.240.109.248:3306)</b>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # Metrics Summary
    dash_resp = api_get_dashboard()
    if dash_resp.get("success"):
        stats = dash_resp.get("data", {})
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            render_metric_card("Students", stats.get("total_students", 0), "In MariaDB")
        with c2:
            render_metric_card("Courses", stats.get("total_courses", 0), "Active offerings")
        with c3:
            render_metric_card("Enrollments", stats.get("total_enrollments", 0), "Total records")
        with c4:
            render_metric_card("Xen Host", "XCP-ng", "10.240.109.196")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### ⚡ **Administrative Shortcuts**")
    
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.markdown(
            """
            <div style="background:#FFFFFF; border:1px solid #E2E8F0; padding:16px; border-radius:8px;">
                <h4 style="margin:0 0 8px 0; color:#1E40AF;">👥 Students</h4>
                <p style="font-size:0.85rem; color:#64748B;">Add students, view student details, and inspect enrolled courses.</p>
            </div>
            """,
            unsafe_allow_html=True
        )
    with col_b:
        st.markdown(
            """
            <div style="background:#FFFFFF; border:1px solid #E2E8F0; padding:16px; border-radius:8px;">
                <h4 style="margin:0 0 8px 0; color:#1E40AF;">📚 Courses</h4>
                <p style="font-size:0.85rem; color:#64748B;">Add courses, update descriptions, and manage offerings.</p>
            </div>
            """,
            unsafe_allow_html=True
        )
    with col_c:
        st.markdown(
            """
            <div style="background:#FFFFFF; border:1px solid #E2E8F0; padding:16px; border-radius:8px;">
                <h4 style="margin:0 0 8px 0; color:#1E40AF;">📝 Enrollments</h4>
                <p style="font-size:0.85rem; color:#64748B;">Overview enrollments, manually enroll students, and drop courses.</p>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown("---")
    st.markdown("#### 🛠️ **System Diagnostics**")
    with st.expander("Inspect Raw MariaDB Connection Response"):
        st.json(health)

