"""
FNID Role-Based Access Control (RBAC)

Defines roles, permissions, and access control decorators for the
JCF case management system.
"""

from functools import wraps

from flask import abort, flash, redirect, url_for
from flask_login import current_user

# ---------------------------------------------------------------------------
# Role definitions
# ---------------------------------------------------------------------------
ROLES = {
    "admin": "System Administrator",
    "dco": "Divisional Crime Officer",
    "ddi": "Deputy Director of Investigations",
    "station_mgr": "Station Manager",
    "registrar": "Registrar",
    "io": "Investigating Officer",
    "plo": "Police Liaison Officer",
    "intel_officer": "Intelligence Officer",
    "transport_officer": "Transport Officer",
    "viewer": "Read-Only Viewer",
}

# Role hierarchy — higher roles inherit lower role permissions
ROLE_HIERARCHY = {
    "admin": 100,
    "ddi": 90,
    "dco": 80,
    "station_mgr": 70,
    "registrar": 60,
    "intel_officer": 55,
    "io": 50,
    "plo": 40,
    "transport_officer": 35,
    "viewer": 10,
}

# ---------------------------------------------------------------------------
# Permission matrix: {resource: {action: set_of_allowed_roles}}
# CONFIGURABLE — adjust per policy when FO 4032 field layouts are confirmed
# ---------------------------------------------------------------------------
PERMISSIONS = {
    "cases": {
        "create": {"admin", "dco", "ddi", "station_mgr", "registrar", "io"},
        "read": {"admin", "dco", "ddi", "station_mgr", "registrar", "io", "plo", "intel_officer", "viewer"},
        "update": {"admin", "dco", "ddi", "station_mgr", "registrar", "io"},
        "delete": {"admin", "dco"},
        "assign": {"admin", "dco", "ddi", "station_mgr"},
        "approve": {"admin", "dco", "ddi", "station_mgr"},
        "suspend": {"admin", "dco", "ddi"},
        "close": {"admin", "dco", "ddi", "station_mgr"},
        "reopen": {"admin", "dco", "ddi"},
    },
    "cr_forms": {
        "create": {"admin", "dco", "ddi", "station_mgr", "registrar", "io"},
        "read": {"admin", "dco", "ddi", "station_mgr", "registrar", "io", "plo", "viewer"},
        "update": {"admin", "dco", "ddi", "station_mgr", "registrar", "io"},
        "delete": {"admin", "dco"},
        "approve": {"admin", "dco", "ddi", "station_mgr"},
        "export_pdf": {"admin", "dco", "ddi", "station_mgr", "registrar", "io", "plo"},
    },
    "intel": {
        "create": {"admin", "dco", "ddi", "intel_officer"},
        "read": {"admin", "dco", "ddi", "intel_officer"},
        "update": {"admin", "dco", "ddi", "intel_officer"},
        "delete": {"admin", "dco"},
        "targets": {"admin", "dco", "ddi", "intel_officer"},
        "link_analysis": {"admin", "dco", "ddi", "intel_officer"},
    },
    "operations": {
        "create": {"admin", "dco", "ddi", "station_mgr", "io"},
        "read": {"admin", "dco", "ddi", "station_mgr", "io", "intel_officer", "viewer"},
        "update": {"admin", "dco", "ddi", "station_mgr", "io"},
        "delete": {"admin", "dco"},
    },
    "seizures": {
        "create": {"admin", "dco", "ddi", "station_mgr", "io"},
        "read": {"admin", "dco", "ddi", "station_mgr", "registrar", "io", "intel_officer", "plo", "viewer"},
        "update": {"admin", "dco", "ddi", "station_mgr", "io"},
        "delete": {"admin", "dco"},
    },
    "arrests": {
        "create": {"admin", "dco", "ddi", "station_mgr", "io"},
        "read": {"admin", "dco", "ddi", "station_mgr", "registrar", "io", "plo", "viewer"},
        "update": {"admin", "dco", "ddi", "station_mgr", "io"},
        "delete": {"admin", "dco"},
    },
    "forensics": {
        "create": {"admin", "dco", "ddi", "registrar", "io"},
        "read": {"admin", "dco", "ddi", "station_mgr", "registrar", "io", "plo", "viewer"},
        "update": {"admin", "dco", "ddi", "registrar", "io"},
        "delete": {"admin", "dco"},
    },
    "file_movement": {
        "create": {"admin", "dco", "ddi", "registrar", "io"},
        "read": {"admin", "dco", "ddi", "station_mgr", "registrar", "io", "viewer"},
        "update": {"admin", "dco", "ddi", "registrar"},
        "checkout_original": {"admin", "dco", "registrar"},
        "checkout_working": {"admin", "dco", "ddi", "station_mgr", "registrar", "io"},
    },
    "mcr": {
        "compile": {"admin", "dco", "ddi", "station_mgr", "registrar"},
        "read": {"admin", "dco", "ddi", "station_mgr", "registrar", "io", "intel_officer", "plo", "viewer"},
    },
    "admin": {
        "access": {"admin", "dco"},
        "users": {"admin"},
        "settings": {"admin", "dco"},
        "backup": {"admin"},
        "audit_log": {"admin", "dco", "ddi"},
    },
    "witnesses": {
        "read_identity": {"admin", "dco", "ddi", "io"},
        "read_pseudonym": {"admin", "dco", "ddi", "intel_officer", "io"},
    },
    "transport": {
        "create": {"admin", "dco", "transport_officer"},
        "read": {"admin", "dco", "ddi", "station_mgr", "transport_officer", "viewer"},
        "update": {"admin", "dco", "transport_officer"},
    },
}


def can_access(user, resource, action):
    """Check if a user has permission for a specific resource/action.

    Returns True if allowed, False otherwise.
    """
    if user is None or not user.is_authenticated:
        return False

    role = getattr(user, "role", "viewer")

    # Admin always has access
    if role == "admin":
        return True

    resource_perms = PERMISSIONS.get(resource, {})
    action_perms = resource_perms.get(action, set())
    return role in action_perms


def role_required(*roles):
    """Decorator: restrict route to users with one of the specified roles."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            user_role = getattr(current_user, "role", "viewer")
            if user_role not in roles and user_role != "admin":
                flash("You do not have permission to access this page.", "danger")
                return redirect(url_for("main.home"))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def permission_required(resource, action):
    """Decorator: restrict route based on the permission matrix."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            if not can_access(current_user, resource, action):
                flash("You do not have permission to perform this action.", "danger")
                return redirect(url_for("main.home"))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def is_supervisor(user):
    """Check if user has a supervisory role."""
    return getattr(user, "role", "viewer") in {
        "admin", "dco", "ddi", "station_mgr"
    }


def can_view_sensitive(user):
    """Check if user can view sensitive witness/source data."""
    return getattr(user, "role", "viewer") in {
        "admin", "dco", "ddi", "intel_officer"
    }
