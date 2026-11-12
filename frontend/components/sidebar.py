import streamlit as st
from frontend.api import api_logout

def render_sidebar():
    """Render the sidebar with role-aware navigation and session details."""
    with st.sidebar:
        st.markdown("### 🎓 **Xen E-Learning**")
        st.caption("Virtualized on XCP-ng / Xen")
        
        user = st.session_state.get("user")
        if not user:
            st.info("Please log in to continue.")
            return None
            
        role = user.get("role", "student")
        role_badge = "🛡️ Administrator" if role == "admin" else "🎓 Student"
        
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
        
        if role == "admin":
            nav_options = [
                "📊 Dashboard",
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
        st.markdown(
            """
            <div style="font-size:0.75rem; color:#475569; line-height:1.5;">
                • <b>Host:</b> 10.240.109.196 (XCP-ng)<br>
                • <b>App VM:</b> 10.240.109.201:8501<br>
                • <b>API:</b> 10.240.109.201:5000<br>
                • <b>DB VM:</b> 10.240.109.248:3306<br>
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
