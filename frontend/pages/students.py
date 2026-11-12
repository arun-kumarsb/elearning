import streamlit as st
import pandas as pd
from frontend.api import api_get_students, api_create_student, api_get_student, api_delete_student
from frontend.components.cards import render_section_title

def render_students_page():
    render_section_title("👥 Student Management", "Manage student profiles and view enrolled coursework")

    user = st.session_state.get("user", {})
    is_admin = user.get("role") == "admin"

    if not is_admin:
        st.warning("⚠️ Access restricted. Administrator privileges required to manage students.")
        return

    # Tabs for Student Management
    tab_list, tab_add = st.tabs(["📋 All Students", "➕ Register New Student"])

    with tab_list:
        with st.spinner("Loading student records from MariaDB..."):
            resp = api_get_students()

        if not resp.get("success"):
            st.error(f"Failed to fetch students: {resp.get('error')}")
            return

        students = resp.get("data", [])
        if not students:
            st.info("No students registered in the database.")
            return

        st.caption(f"Total registered students in MariaDB: **{len(students)}**")

        # Search filter
        search_term = st.text_input("🔍 Search by student name or email:", placeholder="Type to filter...")
        filtered = [
            s for s in students 
            if search_term.lower() in s["name"].lower() or search_term.lower() in s["email"].lower()
        ] if search_term else students

        # Display Students Table
        df = pd.DataFrame(filtered)
        display_df = df.rename(columns={
            "id": "ID",
            "name": "Full Name",
            "email": "Email Address",
            "enrollment_count": "Enrolled Courses",
            "created_at": "Registration Date"
        })[["ID", "Full Name", "Email Address", "Enrolled Courses", "Registration Date"]]
        st.dataframe(display_df, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("#### 🔍 **Inspect Student Details & Coursework**")
        
        student_options = {f"[ID {s['id']}] {s['name']} ({s['email']})": s["id"] for s in students}
        selected_label = st.selectbox("Select a student to inspect:", list(student_options.keys()))
        selected_id = student_options[selected_label]

        if st.button("View Student Details"):
            student_resp = api_get_student(selected_id)
            if student_resp.get("success"):
                student_data = student_resp.get("data", {})
                st.markdown(
                    f"""
                    <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-left:4px solid #2563EB; padding:15px; border-radius:8px; margin-top:10px;">
                        <h4 style="margin:0 0 5px 0; color:#1E3A8A;">{student_data.get('name')}</h4>
                        <div style="color:#64748B; font-size:0.9rem;">Email: <b>{student_data.get('email')}</b> | Student ID: <b>{student_data.get('id')}</b></div>
                        <div style="color:#64748B; font-size:0.85rem; margin-top:4px;">Enrolled Courses: <b>{student_data.get('enrollment_count', 0)}</b></div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                enrolled_courses = student_data.get("enrolled_courses", [])
                if enrolled_courses:
                    st.markdown("##### Enrolled Coursework:")
                    for c in enrolled_courses:
                        st.markdown(
                            f"- **{c.get('course_code')} - {c.get('title')}** (Enrolled: {c.get('enrolled_at', 'N/A')})"
                        )
                else:
                    st.info("This student is not enrolled in any courses yet.")
            else:
                st.error(f"Error: {student_resp.get('error')}")

        st.markdown("---")
        with st.expander("🗑️ Delete Student Account"):
            st.warning("Deleting a student will also remove their user credentials and course enrollments.")
            del_id = st.selectbox("Select student to permanently delete:", list(student_options.keys()), key="del_student")
            student_to_delete = student_options[del_id]
            confirm_del = st.checkbox(f"Yes, permanently delete Student ID {student_to_delete} from MariaDB")
            if st.button("Confirm Delete", type="primary", disabled=not confirm_del):
                del_resp = api_delete_student(student_to_delete)
                if del_resp.get("success"):
                    st.success(f"Student ID {student_to_delete} deleted successfully.")
                    st.rerun()
                else:
                    st.error(f"Failed to delete student: {del_resp.get('error')}")

    with tab_add:
        st.markdown("#### Register New Student Account")
        st.caption("New students will be stored in MariaDB `students` and `users` tables.")

        with st.form("add_student_form", clear_on_submit=True):
            name = st.text_input("Student Full Name *", placeholder="e.g. Alice Smith")
            email = st.text_input("Student Email Address *", placeholder="e.g. alice@example.com")
            password = st.text_input("Initial Password (Optional)", placeholder="Default: Student@123", type="password")
            submitted = st.form_submit_button("Register Student", use_container_width=True, type="primary")

            if submitted:
                if not name or not email:
                    st.error("Please fill in both name and email.")
                elif "@" not in email:
                    st.error("Please provide a valid email address.")
                else:
                    with st.spinner("Saving to MariaDB on Alpine-DB VM..."):
                        res = api_create_student(name, email, password if password else None)
                    if res.get("success"):
                        st.success(f"✅ Student '{name}' registered successfully in MariaDB!")
                        st.info(f"Student can log in using email: **{email}** and password: **{password or 'Student@123'}**")
                    else:
                        st.error(f"Failed to register student: {res.get('error')}")
