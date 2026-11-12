import os
import sys
import streamlit as st

# Ensure root directory is on Python path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from frontend.api import api_login
from frontend.components.sidebar import render_sidebar
from frontend.components.cards import render_system_header
from frontend.pages.dashboard import render_dashboard_page
from frontend.pages.students import render_students_page
from frontend.pages.courses import render_courses_page
from frontend.pages.enrollments import render_enrollments_page
from frontend.pages.admin import render_admin_page
from frontend.pages.xen_architecture import render_xen_architecture_page

# Page Configuration
st.set_page_config(
    page_title="Xen E-Learning Platform",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load custom CSS
css_path = os.path.join(CURRENT_DIR, "assets", "style.css")
if os.path.isfile(css_path):
    with open(css_path, "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# Initialize Session State
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "user" not in st.session_state:
    st.session_state["user"] = None

def render_login_view():
    """Render a clean, professional login view with quick test shortcuts."""
    render_system_header()

    col_space1, col_login, col_space2 = st.columns([1, 2, 1])
    with col_login:
        st.markdown(
            """
            <div style="background:#FFFFFF; border:1px solid #E2E8F0; padding:2rem; border-radius:12px; box-shadow:0 4px 6px -1px rgba(0,0,0,0.05); margin-bottom:1.5rem;">
                <h3 style="margin:0 0 0.5rem 0; color:#1E3A8A; text-align:center;">User Authentication</h3>
                <p style="text-align:center; color:#64748B; font-size:0.9rem; margin-bottom:1.5rem;">
                    Sign in to access your e-learning dashboard
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )

        with st.form("login_form"):
            email = st.text_input("Email Address", placeholder="name@example.com")
            password = st.text_input("Password", type="password", placeholder="Enter your password")
            submit_btn = st.form_submit_button("Sign In", type="primary", use_container_width=True)

            if submit_btn:
                if not email or not password:
                    st.error("Please enter both email and password.")
                else:
                    with st.spinner("Authenticating with MariaDB..."):
                        resp = api_login(email, password)
                    if resp.get("success"):
                        st.session_state["authenticated"] = True
                        st.session_state["user"] = resp.get("user")
                        st.success("Login successful!")
                        st.rerun()
                    else:
                        st.error(f"Login failed: {resp.get('error', 'Invalid credentials')}")

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### ⚡ **College Demo Quick Credentials**")
        st.caption("Click either button below to auto-authenticate with MariaDB test credentials:")

        demo_c1, demo_c2 = st.columns(2)
        with demo_c1:
            if st.button("🛡️ Sign in as Admin", use_container_width=True):
                with st.spinner("Authenticating default Admin..."):
                    resp = api_login("admin@elearning.local", "Admin@123")
                if resp.get("success"):
                    st.session_state["authenticated"] = True
                    st.session_state["user"] = resp.get("user")
                    st.rerun()
                else:
                    st.error(f"Admin login failed: {resp.get('error')}")

        with demo_c2:
            if st.button("🎓 Sign in as Student", use_container_width=True):
                with st.spinner("Authenticating Student One..."):
                    resp = api_login("student@example.com", "Student@123")
                if resp.get("success"):
                    st.session_state["authenticated"] = True
                    st.session_state["user"] = resp.get("user")
                    st.rerun()
                else:
                    st.error(f"Student login failed: {resp.get('error')}")

def main():
    if not st.session_state.get("authenticated"):
        render_login_view()
        return

    # Render authenticated application
    selected_page = render_sidebar()
    render_system_header()

    if selected_page == "📊 Dashboard":
        render_dashboard_page()
    elif selected_page == "👥 Student Management":
        render_students_page()
    elif selected_page in ("📚 Course Management", "📚 Available Courses"):
        render_courses_page()
    elif selected_page in ("📝 Enrollment Overview", "📝 My Enrolled Courses"):
        render_enrollments_page()
    elif selected_page == "🛡️ Administrator Hub":
        render_admin_page()
    elif selected_page == "🔬 Xen Virtualization Architecture":
        render_xen_architecture_page()
    else:
        render_dashboard_page()

if __name__ == "__main__":
    main()

