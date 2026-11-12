import streamlit as st
import pandas as pd
from frontend.api import (
    api_get_enrollments,
    api_get_student_enrollments,
    api_enroll_student,
    api_delete_enrollment,
    api_get_students,
    api_get_courses
)
from frontend.components.cards import render_section_title

def render_enrollments_page():
    user = st.session_state.get("user", {})
    is_admin = user.get("role") == "admin"
    student_id = user.get("student_id")

    if is_admin:
        render_admin_enrollments()
    else:
        render_student_enrollments(student_id)

def render_student_enrollments(student_id: int):
    render_section_title("📝 My Enrolled Courses", "Review your active academic enrollments")

    if not student_id:
        st.warning("Your user account is not linked to a student profile.")
        return

    with st.spinner("Loading your enrollments from MariaDB..."):
        resp = api_get_student_enrollments(student_id)

    if not resp.get("success"):
        st.error(f"Failed to fetch enrollments: {resp.get('error')}")
        return

    enrollments = resp.get("data", [])
    if not enrollments:
        st.info("You are not currently enrolled in any courses.")
        st.markdown("Navigate to **Available Courses** in the sidebar to register for coursework.")
        return

    st.success(f"You are currently enrolled in **{len(enrollments)}** course(s).")

    for item in enrollments:
        enr_id = item["enrollment_id"]
        with st.container():
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(
                    f"""
                    <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-left:4px solid #10B981; padding:15px; border-radius:8px; margin-bottom:10px;">
                        <span style="background:#D1FAE5; color:#065F46; font-size:0.75rem; font-weight:700; padding:2px 8px; border-radius:4px;">
                            {item.get('course_code')}
                        </span>
                        <h4 style="margin:6px 0 4px 0; color:#1E3A8A;">{item.get('course_title')}</h4>
                        <div style="color:#64748B; font-size:0.85rem;">
                            Enrolled On: <b>{item.get('enrolled_at', 'N/A')}</b> | Status: <b>{item.get('status', 'enrolled').capitalize()}</b>
                        </div>
                        <p style="color:#475569; font-size:0.9rem; margin-top:6px;">{item.get('course_description') or ''}</p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            with col2:
                st.markdown("<div style='height: 25px;'></div>", unsafe_allow_html=True)
                if st.button("Drop Course", key=f"drop_{enr_id}", type="secondary"):
                    with st.spinner("Canceling enrollment..."):
                        del_res = api_delete_enrollment(enr_id)
                    if del_res.get("success"):
                        st.success(f"Dropped {item.get('course_title')}.")
                        st.rerun()
                    else:
                        st.error(f"Failed: {del_res.get('error')}")


def render_admin_enrollments():
    render_section_title("📝 Enrollment Overview", "Track and manage all student course enrollments in MariaDB")

    tab_all, tab_manual = st.tabs(["📋 All Enrollments", "➕ Manual Enrollment"])

    with tab_all:
        with st.spinner("Fetching enrollments from MariaDB..."):
            resp = api_get_enrollments()

        if not resp.get("success"):
            st.error(f"Failed to fetch enrollments: {resp.get('error')}")
            return

        enrollments = resp.get("data", [])
        if not enrollments:
            st.info("No enrollment records currently exist in MariaDB.")
            return

        st.caption(f"Total enrollment records: **{len(enrollments)}**")

        df = pd.DataFrame(enrollments)
        df_display = df.rename(columns={
            "id": "Enrollment ID",
            "student_name": "Student Name",
            "student_email": "Student Email",
            "course_code": "Course Code",
            "course_title": "Course Title",
            "enrolled_at": "Enrolled Date",
            "status": "Status"
        })[["Enrollment ID", "Student Name", "Student Email", "Course Code", "Course Title", "Enrolled Date", "Status"]]
        st.dataframe(df_display, use_container_width=True, hide_index=True)

        st.markdown("---")
        with st.expander("🗑️ Cancel or Remove Enrollment"):
            enr_map = {
                f"[ID {e['id']}] {e['student_name']} in {e['course_title']}": e["id"] 
                for e in enrollments
            }
            target_enr = st.selectbox("Select enrollment to cancel:", list(enr_map.keys()))
            target_id = enr_map[target_enr]
            if st.button("Confirm Cancel Enrollment", type="primary"):
                del_res = api_delete_enrollment(target_id)
                if del_res.get("success"):
                    st.success(f"Enrollment ID {target_id} removed.")
                    st.rerun()
                else:
                    st.error(f"Failed: {del_res.get('error')}")

    with tab_manual:
        st.markdown("#### Manually Enroll Student into Course")
        st.caption("Administrator shortcut to register any student into any course.")

        # Fetch students and courses for dropdown
        st_resp = api_get_students()
        cr_resp = api_get_courses()

        students = st_resp.get("data", []) if st_resp.get("success") else []
        courses = cr_resp.get("data", []) if cr_resp.get("success") else []

        if not students or not courses:
            st.warning("Both students and courses must exist to perform enrollments.")
            return

        st_options = {f"[ID {s['id']}] {s['name']} ({s['email']})": s["id"] for s in students}
        cr_options = {f"[ID {c['id']}] {c.get('course_code', '')} - {c['title']}": c["id"] for c in courses}

        with st.form("manual_enroll_form"):
            selected_student_str = st.selectbox("Select Student:", list(st_options.keys()))
            selected_course_str = st.selectbox("Select Course:", list(cr_options.keys()))
            enroll_btn = st.form_submit_button("Enroll Student", type="primary", use_container_width=True)

            if enroll_btn:
                sid = st_options[selected_student_str]
                cid = cr_options[selected_course_str]
                with st.spinner("Processing enrollment in MariaDB..."):
                    res = api_enroll_student(sid, cid)
                if res.get("success"):
                    st.success(f"✅ {res.get('message', 'Enrolled successfully!')}")
                    st.rerun()
                else:
                    st.error(f"Enrollment Error: {res.get('error')}")

