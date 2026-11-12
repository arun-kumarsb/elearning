import streamlit as st
import pandas as pd
from frontend.api import (
    api_get_courses,
    api_create_course,
    api_update_course,
    api_delete_course,
    api_enroll_student,
    api_get_student_enrollments
)
from frontend.components.cards import render_section_title

def render_courses_page():
    user = st.session_state.get("user", {})
    is_admin = user.get("role") == "admin"
    student_id = user.get("student_id")

    if is_admin:
        render_admin_course_management()
    else:
        render_student_course_catalog(student_id)

def render_student_course_catalog(student_id: int):
    render_section_title("📚 Available Courses Catalog", "Explore courses and enroll into your curriculum")

    # Fetch all courses
    with st.spinner("Fetching courses from MariaDB..."):
        courses_resp = api_get_courses()

    if not courses_resp.get("success"):
        st.error(f"Failed to load courses: {courses_resp.get('error')}")
        return

    courses = courses_resp.get("data", [])
    if not courses:
        st.info("No courses available yet. Please check back later.")
        return

    # Fetch currently enrolled courses for this student
    enrolled_ids = set()
    if student_id:
        enrolled_resp = api_get_student_enrollments(student_id)
        if enrolled_resp.get("success"):
            enrolled_list = enrolled_resp.get("data", [])
            enrolled_ids = {e["course_id"] for e in enrolled_list}

    # Search filter
    search = st.text_input("🔍 Search courses by title or code:", placeholder="e.g. Introduction...")
    filtered_courses = [
        c for c in courses 
        if search.lower() in c["title"].lower() or search.lower() in c.get("course_code", "").lower()
    ] if search else courses

    st.markdown(f"**{len(filtered_courses)}** courses available:")

    # Render course cards
    for c in filtered_courses:
        c_id = c["id"]
        is_enrolled = c_id in enrolled_ids

        with st.container():
            col_info, col_action = st.columns([4, 1])
            with col_info:
                st.markdown(
                    f"""
                    <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-left:4px solid {'#10B981' if is_enrolled else '#2563EB'}; padding:16px; border-radius:8px; margin-bottom:12px;">
                        <span style="background:{'#D1FAE5' if is_enrolled else '#DBEAFE'}; color:{'#065F46' if is_enrolled else '#1E40AF'}; font-size:0.75rem; font-weight:700; padding:3px 8px; border-radius:4px;">
                            {c.get('course_code', f'CS-{c_id}')}
                        </span>
                        {' <span style="background:#D1FAE5; color:#065F46; font-size:0.75rem; font-weight:700; padding:3px 8px; border-radius:4px;">✓ Enrolled</span>' if is_enrolled else ''}
                        <h4 style="margin:8px 0 4px 0; color:#1E3A8A;">{c.get('title')}</h4>
                        <p style="color:#475569; font-size:0.9rem; margin-bottom:4px;">{c.get('description') or 'No description provided.'}</p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            with col_action:
                st.markdown("<div style='height: 25px;'></div>", unsafe_allow_html=True)
                if is_enrolled:
                    st.success("Enrolled", icon="✅")
                else:
                    if st.button("Enroll Now", key=f"btn_enroll_{c_id}", type="primary"):
                        if not student_id:
                            st.error("Your user account is not linked to a student profile.")
                        else:
                            enroll_res = api_enroll_student(student_id, c_id)
                            if enroll_res.get("success"):
                                st.balloons()
                                st.success(f"🎉 Successfully enrolled in '{c.get('title')}'!")
                                st.rerun()
                            else:
                                st.error(f"Enrollment failed: {enroll_res.get('error')}")


def render_admin_course_management():
    render_section_title("📚 Course Management", "Add, update, or remove academic courses in MariaDB")

    tab_list, tab_add, tab_edit, tab_delete = st.tabs([
        "📋 All Courses", 
        "➕ Add New Course", 
        "✏️ Edit Course", 
        "🗑️ Delete Course"
    ])

    with st.spinner("Loading course records from MariaDB..."):
        courses_resp = api_get_courses()

    courses = courses_resp.get("data", []) if courses_resp.get("success") else []

    # 1. Course Listing
    with tab_list:
        if not courses:
            st.info("No courses found in database.")
        else:
            df = pd.DataFrame(courses)
            df_display = df.rename(columns={
                "id": "Course ID",
                "course_code": "Code",
                "title": "Course Title",
                "description": "Description",
                "enrolled_students_count": "Enrolled Students",
                "created_at": "Created Date"
            })[["Course ID", "Code", "Course Title", "Description", "Enrolled Students", "Created Date"]]
            st.dataframe(df_display, use_container_width=True, hide_index=True)

    # 2. Add New Course
    with tab_add:
        st.markdown("#### Create a New Course")
        with st.form("create_course_form", clear_on_submit=True):
            code = st.text_input("Course Code (e.g. CS-201, MATH-101)", placeholder="CS-102")
            title = st.text_input("Course Title *", placeholder="e.g. Cloud Computing & Virtualization")
            description = st.text_area("Course Description", placeholder="Outline course syllabus, learning outcomes, and prerequisites...")
            submit_create = st.form_submit_button("Create Course", type="primary", use_container_width=True)

            if submit_create:
                if not title.strip():
                    st.error("Course title is required.")
                else:
                    with st.spinner("Inserting into MariaDB..."):
                        res = api_create_course(code, title, description)
                    if res.get("success"):
                        st.success(f"✅ Course '{title}' created successfully!")
                        st.rerun()
                    else:
                        st.error(f"Failed to create course: {res.get('error')}")

    # 3. Edit Course
    with tab_edit:
        st.markdown("#### Edit Existing Course")
        if not courses:
            st.info("No courses to edit.")
        else:
            course_map = {f"[{c['id']}] {c.get('course_code', '')} - {c['title']}": c for c in courses}
            selected_choice = st.selectbox("Select course to modify:", list(course_map.keys()))
            selected_course = course_map[selected_choice]

            with st.form("edit_course_form"):
                edit_code = st.text_input("Course Code", value=selected_course.get("course_code", ""))
                edit_title = st.text_input("Course Title *", value=selected_course.get("title", ""))
                edit_desc = st.text_area("Course Description", value=selected_course.get("description", ""))
                submit_edit = st.form_submit_button("Save Changes", type="primary")

                if submit_edit:
                    if not edit_title.strip():
                        st.error("Course title cannot be empty.")
                    else:
                        with st.spinner("Updating MariaDB record..."):
                            up_res = api_update_course(selected_course["id"], edit_code, edit_title, edit_desc)
                        if up_res.get("success"):
                            st.success("✅ Course updated successfully!")
                            st.rerun()
                        else:
                            st.error(f"Failed to update course: {up_res.get('error')}")

    # 4. Delete Course
    with tab_delete:
        st.markdown("#### Remove a Course")
        st.warning("⚠️ Deleting a course will also remove all associated student enrollments.")
        if not courses:
            st.info("No courses to delete.")
        else:
            del_course_map = {f"[{c['id']}] {c.get('course_code', '')} - {c['title']}": c["id"] for c in courses}
            del_choice = st.selectbox("Select course to delete:", list(del_course_map.keys()))
            course_id_to_del = del_course_map[del_choice]
            confirm = st.checkbox(f"I confirm that I want to permanently delete Course ID {course_id_to_del} from MariaDB.")

            if st.button("Permanently Delete Course", type="primary", disabled=not confirm):
                with st.spinner("Deleting from MariaDB..."):
                    del_res = api_delete_course(course_id_to_del)
                if del_res.get("success"):
                    st.success(f"Course ID {course_id_to_del} deleted successfully.")
                    st.rerun()
                else:
                    st.error(f"Failed to delete course: {del_res.get('error')}")

