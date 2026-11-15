"""
Authentication and Authorization Utilities for Frontend (Streamlit)
Project: Xen-Based Dynamic Resource Allocation for Scalable E-Learning Services

Provides standardized, role-normalized session helpers across all frontend pages.
"""

import streamlit as st
from typing import Dict, Any, Optional

# Supported administrator role variations
ADMIN_ROLE_VARIANTS = {"admin", "administrator", "adm", "root"}

def normalize_role(role: Any) -> str:
    """Normalize a role string to lowercase with stripped whitespace."""
    if not role or not isinstance(role, str):
        return ""
    return role.strip().lower()

def is_admin_role(role: Any) -> bool:
    """Safely check if role matches any administrator variation."""
    return normalize_role(role) in ADMIN_ROLE_VARIANTS

def get_current_user() -> Optional[Dict[str, Any]]:
    """Retrieve the authenticated user dictionary from session state."""
    if not st.session_state.get("authenticated", False):
        return None
    user = st.session_state.get("user")
    if isinstance(user, dict):
        return user
    return None

def get_current_role() -> str:
    """Retrieve the current user's normalized role."""
    user = get_current_user()
    if user and "role" in user:
        return normalize_role(user.get("role"))
    raw_role = st.session_state.get("role")
    if raw_role:
        return normalize_role(raw_role)
    return ""

def is_authenticated() -> bool:
    """Check if the user has an active authenticated session with a token."""
    if not st.session_state.get("authenticated", False):
        return False
    user = get_current_user()
    if not user:
        return False
    return bool(user.get("token") or user.get("email"))

def is_admin_user() -> bool:
    """
    Check if the current authenticated user has administrator privileges.
    Evaluates:
    - user dict in session state (user.role)
    - role key in session state
    - role normalization: admin, administrator, Administrator, ADMIN
    """
    if not is_authenticated():
        return False
    return is_admin_role(get_current_role())

def sync_session_state():
    """Ensure session state keys are consistent across Streamlit reruns and page navigation."""
    user = st.session_state.get("user")
    if isinstance(user, dict):
        st.session_state["authenticated"] = True
        user_role = user.get("role")
        if user_role:
            st.session_state["role"] = user_role
        user_email = user.get("email")
        if user_email:
            st.session_state["email"] = user_email
        user_name = user.get("name")
        if user_name:
            st.session_state["name"] = user_name
    elif st.session_state.get("authenticated") and st.session_state.get("role"):
        # Synchronize backward if user dict was omitted
        st.session_state["user"] = {
            "email": st.session_state.get("email", ""),
            "role": st.session_state.get("role", ""),
            "name": st.session_state.get("name", "User")
        }
