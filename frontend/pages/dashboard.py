import streamlit as st
import pandas as pd
from frontend.api import api_get_dashboard, api_get_health
from frontend.components.cards import render_metric_card, render_section_title

def render_dashboard_page():
    render_section_title("📊 System Dashboard", "Real-time metrics retrieved directly from MariaDB (10.240.109.248)")

    with st.spinner("Fetching latest data from backend API..."):
        resp = api_get_dashboard()

    if not resp.get("success"):
        st.error(f"⚠️ Failed to load dashboard: {resp.get('error')}")
        st.info("Ensure MariaDB VM (10.240.109.248) is running and Flask backend is listening on port 5000.")
        return

    data = resp.get("data", {})
    total_students = data.get("total_students", 0)
    total_courses = data.get("total_courses", 0)
    total_enrollments = data.get("total_enrollments", 0)
    available_courses = data.get("available_courses", 0)

    # Metric KPI Cards
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        render_metric_card("Registered Students", total_students, "Total active student accounts")
    with col2:
        render_metric_card("Offered Courses", total_courses, "Active academic courses")
    with col3:
        render_metric_card("Total Enrollments", total_enrollments, "Course enrollments recorded")
    with col4:
        render_metric_card("Available Courses", available_courses, "Ready for enrollment")

    st.markdown("<br>", unsafe_allow_html=True)

    # Main dashboard columns
    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.markdown("#### 🕒 **Recent Course Enrollments**")
        recent = data.get("recent_enrollments", [])
        if recent:
            df_recent = pd.DataFrame(recent)
            # Rename columns for clean presentation
            df_display = df_recent.rename(columns={
                "student_name": "Student",
                "student_email": "Email",
                "course_code": "Code",
                "course_title": "Course Title",
                "enrolled_at": "Enrolled On",
                "status": "Status"
            })[["Student", "Code", "Course Title", "Enrolled On", "Status"]]
            st.dataframe(df_display, use_container_width=True, hide_index=True)
        else:
            st.info("No enrollment records found in MariaDB yet.")

    with col_right:
        st.markdown("#### 📈 **Course Popularity**")
        popular = data.get("popular_courses", [])
        if popular:
            df_pop = pd.DataFrame(popular)
            df_pop_display = df_pop.rename(columns={
                "course_code": "Code",
                "title": "Course",
                "enrolled_count": "Enrolled Students"
            })[["Code", "Course", "Enrolled Students"]]
            st.dataframe(df_pop_display, use_container_width=True, hide_index=True)
        else:
            st.info("No course metrics available.")

    st.markdown("---")
    
    # Infrastructure Status Section
    st.markdown("#### 🌐 **Virtualized Infrastructure Overview**")
    infra_col1, infra_col2, infra_col3 = st.columns(3)
    with infra_col1:
        st.markdown(
            """
            <div style="background:#FFFFFF; border:1px solid #E2E8F0; padding:12px; border-radius:8px;">
                <b style="color:#1E40AF;">Hypervisor:</b> XCP-ng / Xen<br>
                <b>Management IP:</b> <code>10.240.109.196</code><br>
                <b>Interface:</b> XO Lite
            </div>
            """,
            unsafe_allow_html=True
        )
    with infra_col2:
        st.markdown(
            """
            <div style="background:#FFFFFF; border:1px solid #E2E8F0; padding:12px; border-radius:8px;">
                <b style="color:#1E40AF;">Application VM:</b> Alpine-Linux-New<br>
                <b>Private IP:</b> <code>10.240.109.201</code><br>
                <b>Stack:</b> Python 3.14 + Flask + Streamlit
            </div>
            """,
            unsafe_allow_html=True
        )
    with infra_col3:
        st.markdown(
            """
            <div style="background:#FFFFFF; border:1px solid #E2E8F0; padding:12px; border-radius:8px;">
                <b style="color:#1E40AF;">Database VM:</b> Alpine-DB<br>
                <b>Private IP:</b> <code>10.240.109.248:3306</code><br>
                <b>Database:</b> MariaDB 11.8.9 (elearning)
            </div>
            """,
            unsafe_allow_html=True
        )
