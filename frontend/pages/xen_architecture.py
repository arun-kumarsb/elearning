import streamlit as st
from frontend.api import api_get_xen_status
from frontend.components.cards import render_section_title

def render_xen_architecture_page():
    render_section_title(
        "🔬 Xen Virtualization Architecture & Resource Allocation",
        "Multi-VM decoupling and Phase 2 Dynamic CPU/RAM Allocation design"
    )

    with st.spinner("Fetching Xen virtualization metadata..."):
        resp = api_get_xen_status()

    xen_data = resp.get("data", {}) if resp.get("success") else {}

    st.markdown(
        """
        <div style="background:#EFF6FF; border-left:4px solid #2563EB; padding:15px; border-radius:6px; margin-bottom:15px;">
            <b style="color:#1E40AF;">College Project Objective:</b>
            Demonstrate how an e-learning platform operates across a virtualized infrastructure using XCP-ng/Xen,
            with separate application and database VMs, structured for future dynamic CPU and RAM elasticity.
        </div>
        """,
        unsafe_allow_html=True
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 🖥️ **Application VM (Alpine-Linux-New)**")
        st.markdown(
            """
            - **Operating System:** Alpine Linux 3.24
            - **IP Address:** `10.240.109.51`
            - **Python Version:** 3.14.x
            - **Services Running:**
              - **Streamlit Frontend:** Port `8501`
              - **Flask REST API:** Port `5000`
              - **Nginx Reverse Proxy:** Port `80` (Optional)
            - **Virtual Hardware:**
              - vCPUs: 2 (Scale target: 4)
              - Memory: 2048 MB Dynamic Target
            """
        )

    with col2:
        st.markdown("### 🗄️ **Database VM (Alpine-DB)**")
        st.markdown(
            """
            - **Operating System:** Alpine Linux 3.24
            - **IP Address:** `10.240.109.248`
            - **Database Engine:** MariaDB 11.8.9
            - **Database Name:** `elearning`
            - **Listening Port:** `3306` (TCP)
            - **Preserved Tables:**
              - `students` (Student One)
              - `courses` (Introduction to E-Learning)
              - `users` (Role-based authentication)
              - `enrollments` (Unique constraint)
            """
        )

    st.markdown("---")
    st.markdown("### ⚙️ **Phase 2: Dynamic Resource Allocation Design**")
    st.markdown(
        """
        In the upcoming Phase 2, a resource monitoring daemon will integrate with the XCP-ng XAPI hypervisor interface:
        """
    )

    p1, p2 = st.columns(2)
    with p1:
        st.markdown(
            """
            <div style="background:#FFFFFF; border:1px solid #E2E8F0; padding:14px; border-radius:8px;">
                <h4 style="margin:0 0 6px 0; color:#1E40AF;">📈 Dynamic CPU Allocation</h4>
                <p style="font-size:0.85rem; color:#475569;">
                    Monitors CPU load across VMs. When CPU utilization exceeds 80% during peak user activity,
                    the Xen hypervisor hot-plugs additional vCPUs via Xen Credit Scheduler:
                </p>
                <code>xe vm-vcpu-set uuid=&lt;UUID&gt; vcpus-number=4</code>
            </div>
            """,
            unsafe_allow_html=True
        )

    with p2:
        st.markdown(
            """
            <div style="background:#FFFFFF; border:1px solid #E2E8F0; padding:14px; border-radius:8px;">
                <h4 style="margin:0 0 6px 0; color:#1E40AF;">🧠 Dynamic RAM Allocation (Ballooning)</h4>
                <p style="font-size:0.85rem; color:#475569;">
                    Utilizes the Xen Balloon Driver (<code>xen-balloon</code>) in Alpine Linux kernel.
                    Dynamically expands memory ceiling when RAM exceeds 85%:
                </p>
                <code>xe vm-memory-limits-set uuid=&lt;UUID&gt; dynamic-max=3072MiB</code>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("🔍 View Raw Xen Cluster Telemetry & Specifications"):
        st.json(xen_data)

