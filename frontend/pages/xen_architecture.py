import os
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
    vms_info = xen_data.get("vms", [])
    
    # Read dynamic configuration with fallback
    app_vm_info = next((v for v in vms_info if "app" in v.get("role", "").lower() or "application" in v.get("role", "").lower()), {})
    db_vm_info = next((v for v in vms_info if "database" in v.get("role", "").lower() or "db" in v.get("role", "").lower()), {})

    app_name = app_vm_info.get("name") or os.getenv("APP_VM_NAME", "Alpine-Linux")
    app_ip = app_vm_info.get("ip") or os.getenv("APP_VM_IP", "10.189.191.51")
    db_name = db_vm_info.get("name") or os.getenv("DB_VM_NAME", "Alpine-DB")
    db_ip = db_vm_info.get("ip") or os.getenv("DB_VM_IP", "10.189.191.248")
    db_port = db_vm_info.get("port") or os.getenv("DB_PORT", "3306")
    xcp_host = xen_data.get("virtualization", {}).get("host_management_ip") or os.getenv("XCP_NG_HOST", "10.189.191.175")

    st.markdown(
        f"""
        <div style="background:#EFF6FF; border-left:4px solid #2563EB; padding:15px; border-radius:6px; margin-bottom:15px;">
            <b style="color:#1E40AF;">College Project Objective:</b>
            Demonstrate how an e-learning platform operates across a virtualized infrastructure using XCP-ng/Xen (Host: <code>{xcp_host}</code>),
            with separate application ({app_name}) and database ({db_name}) VMs, structured for dynamic CPU and RAM elasticity.
        </div>
        """,
        unsafe_allow_html=True
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(f"### 🖥️ **Application VM ({app_name})**")
        st.markdown(
            f"""
            - **Operating System:** Alpine Linux 3.24
            - **IP Address:** `{app_ip}`
            - **Python Version:** 3.14.x
            - **Services Running:**
              - **Streamlit Frontend:** Port `8501`
              - **Flask REST API:** Port `5000`
              - **Nginx Reverse Proxy:** Port `80` (Optional)
            - **Virtual Hardware:**
              - Configured vCPUs: 2 (Elastic scale range: 1 - 4)
              - Memory: Dynamic Ballooning Target
            """
        )

    with col2:
        st.markdown(f"### 🗄️ **Database VM ({db_name})**")
        st.markdown(
            f"""
            - **Operating System:** Alpine Linux 3.24
            - **IP Address:** `{db_ip}`
            - **Database Engine:** MariaDB 11.8.9
            - **Database Name:** `elearning`
            - **Listening Port:** `{db_port}` (TCP)
            - **Preserved Tables:**
              - `students` (Student One)
              - `courses` (Introduction to E-Learning)
              - `users` (Role-based authentication)
              - `enrollments` (Unique constraint)
              - `vm_metrics_history` (Phase 2 telemetry)
              - `allocation_decisions_history` (Elasticity log)
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

