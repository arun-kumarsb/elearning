import os
import streamlit as st
from frontend.api import api_logout
from frontend.auth_utils import is_admin_user, sync_session_state, get_current_user

def render_sidebar():
    """Render the sidebar with role-aware navigation and session details."""
    sync_session_state()
    with st.sidebar:
        st.markdown("### 🎓 **Xen E-Learning**")
        st.caption("Virtualized on XCP-ng / Xen")
        
        user = get_current_user()
        if not user:
            st.info("Please log in to continue.")
            return None
            
        role_is_admin = is_admin_user()
        role_badge = "🛡️ Administrator" if role_is_admin else "🎓 Student"
        
        # User details card
        st.markdown(
            f"""
            <div style="background:#FFFFFF; border:1px solid #E2E8F0; padding:12px; border-radius:8px; margin-bottom:15px;">
                <div style="font-weight:600; color:#1E40AF; font-size:0.9rem;">{user.get('name', 'User')}</div>
                <div style="font-size:0.8rem; color:#64748B;">{user.get('email', '')}</div>
                <div style="margin-top:6px; display:inline-block; background:#EFF6FF; color:#1E40AF; padding:2px 8px; border-radius:12px; font-size:0.75rem; font-weight:600;">
                    {role_badge}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        st.markdown("#### **Navigation**")
        
        if role_is_admin:
            nav_options = [
                "📊 Dashboard",
                "🚀 Intelligent Resource Orchestration",
                "👥 Student Management",
                "📚 Course Management",
                "📝 Enrollment Overview",
                "🛡️ Administrator Hub",
                "🔬 Xen Virtualization Architecture"
            ]
        else:
            nav_options = [
                "📊 Dashboard",
                "📚 Available Courses",
                "📝 My Enrolled Courses"
            ]
            
        selected_page = st.radio(
            "Select Page",
            nav_options,
            label_visibility="collapsed"
        )
        
        st.markdown("---")
        st.markdown("#### **Xen Infrastructure**")
        xcp_host = os.getenv("XCP_NG_HOST", "10.189.191.175")
        app_ip = os.getenv("APP_VM_IP", "10.189.191.51")
        db_ip = os.getenv("DB_VM_IP", "10.189.191.248")
        db_port = os.getenv("DB_PORT", "3306")
        app_name = os.getenv("APP_VM_NAME", "Alpine-Linux")
        db_name = os.getenv("DB_VM_NAME", "Alpine-DB")

        st.markdown(
            f"""
            <div style="font-size:0.75rem; color:#475569; line-height:1.5;">
                • <b>Host:</b> {xcp_host} (XCP-ng)<br>
                • <b>App VM ({app_name}):</b> {app_ip}:8501<br>
                • <b>API:</b> {app_ip}:5000<br>
                • <b>DB VM ({db_name}):</b> {db_ip}:{db_port}<br>
                • <b>Network:</b> Private Bridged
            </div>
            """,
            unsafe_allow_html=True
        )
        
        st.markdown("---")
        if st.button("🚪 Log Out", use_container_width=True, type="secondary"):
            api_logout()
            st.session_state.clear()
            st.rerun()
            
        return selected_page

