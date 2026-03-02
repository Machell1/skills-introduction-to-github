"""Main routes: home page and command dashboard."""

from functools import wraps

from flask import Blueprint, redirect, render_template, session, url_for

from ..constants import UNIT_PORTALS
from ..models import get_db

bp = Blueprint("main", __name__)


def login_required(f):
    """Decorator to require login for a route."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("officer_badge"):
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated_function


@bp.route("/")
@login_required
def home():
    conn = get_db()
    stats = {}
    table_map = {
        "intel": "intel_reports",
        "operations": "operations",
        "seizures": "firearm_seizures",
        "arrests": "arrests",
        "forensics": "chain_of_custody",
        "registry": "cases",
    }
    for unit_key in UNIT_PORTALS:
        table = table_map.get(unit_key, "cases")
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        stats[unit_key] = count

    conn.close()
    return render_template("home.html", stats=stats)


@bp.route("/command")
@login_required
def command_dashboard():
    conn = get_db()
    stats = {
        "intel": conn.execute("SELECT COUNT(*) FROM intel_reports").fetchone()[0],
        "operations": conn.execute("SELECT COUNT(*) FROM operations").fetchone()[0],
        "firearms": conn.execute("SELECT COUNT(*) FROM firearm_seizures").fetchone()[0],
        "narcotics": conn.execute("SELECT COUNT(*) FROM narcotics_seizures").fetchone()[0],
        "arrests": conn.execute("SELECT COUNT(*) FROM arrests").fetchone()[0],
        "exhibits": conn.execute("SELECT COUNT(*) FROM chain_of_custody").fetchone()[0],
        "cases": conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0],
        "compliant_48": conn.execute(
            "SELECT COUNT(*) FROM arrests WHERE charge_within_48hr='Yes'"
        ).fetchone()[0],
        "at_dpp": conn.execute(
            "SELECT COUNT(*) FROM cases WHERE case_status LIKE 'Referred to DPP%'"
        ).fetchone()[0],
        "sop_compliant": conn.execute(
            "SELECT COUNT(*) FROM cases WHERE sop_compliance LIKE 'Fully%'"
        ).fetchone()[0],
    }

    charts = {
        "cases_by_status": conn.execute(
            "SELECT case_status, COUNT(*) as cnt FROM cases GROUP BY case_status"
        ).fetchall(),
        "cases_by_parish": conn.execute(
            "SELECT parish, COUNT(*) as cnt FROM cases GROUP BY parish"
        ).fetchall(),
        "seizures_by_parish": conn.execute(
            "SELECT parish, COUNT(*) as cnt FROM firearm_seizures GROUP BY parish"
        ).fetchall(),
    }
    conn.close()
    return render_template("command/dashboard.html", stats=stats, charts=charts)
