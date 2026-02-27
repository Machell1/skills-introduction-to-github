#!/usr/bin/env python3
"""
FNID Area 3 Operational Portal - Flask Web Application

Professional web-based portal for the Jamaica Constabulary Force
Firearms & Narcotics Investigation Division, Area 3
(Manchester, St. Elizabeth, Clarendon).

Architecture centered on:
  - Investigations & Case Management
  - Standard Operating Procedures (SOP) compliance
  - DPP file preparation per Prosecution Protocol (2012)
  - Disclosure Protocol (2013) compliance
  - Statutory requirements: Firearms Act 2022, DDA, POCA 2007, Bail Act 2023
"""

import os
import json
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, jsonify, send_file
)
from models import get_db, init_db, generate_id, log_audit
import config as cfg

app = Flask(__name__)
app.secret_key = cfg.SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB upload limit

os.makedirs(cfg.UPLOAD_DIR, exist_ok=True)
os.makedirs(cfg.EXPORT_DIR, exist_ok=True)


@app.context_processor
def inject_globals():
    """Inject global template variables."""
    return {
        "portals": cfg.UNIT_PORTALS,
        "now": datetime.now(),
    }


# =================================================================
#  AUTHENTICATION (simplified - badge number + name)
# =================================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        badge = request.form.get("badge_number", "").strip()
        name = request.form.get("full_name", "").strip()
        rank = request.form.get("rank", "").strip()
        section = request.form.get("section", "").strip()

        if not badge or not name or not rank:
            flash("Badge number, name, and rank are required.", "danger")
            return redirect(url_for("login"))

        conn = get_db()
        officer = conn.execute(
            "SELECT * FROM officers WHERE badge_number = ?", (badge,)
        ).fetchone()

        if not officer:
            conn.execute(
                "INSERT INTO officers (badge_number, full_name, rank, section) VALUES (?,?,?,?)",
                (badge, name, rank, section)
            )
            conn.commit()

        conn.close()

        session["officer_badge"] = badge
        session["officer_name"] = name
        session["officer_rank"] = rank
        session["officer_section"] = section
        log_audit("officers", badge, "LOGIN", badge, name)
        flash(f"Welcome, {rank} {name}.", "success")
        return redirect(url_for("home"))

    return render_template("login.html",
                           ranks=cfg.JCF_RANKS,
                           sections=cfg.FNID_SECTIONS)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# =================================================================
#  HOME - Portal Selection
# =================================================================
@app.route("/")
def home():
    if not session.get("officer_badge"):
        return redirect(url_for("login"))

    conn = get_db()
    stats = {}
    for unit_key in cfg.UNIT_PORTALS:
        table_map = {
            "intel": "intel_reports",
            "operations": "operations",
            "seizures": "firearm_seizures",
            "arrests": "arrests",
            "forensics": "chain_of_custody",
            "registry": "cases",
        }
        table = table_map.get(unit_key, "cases")
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        stats[unit_key] = count

    conn.close()
    return render_template("home.html", stats=stats)


# =================================================================
#  UNIT HOME & DASHBOARD
# =================================================================
@app.route("/unit/<unit>")
def unit_home(unit):
    if unit not in cfg.UNIT_PORTALS:
        flash("Invalid unit.", "danger")
        return redirect(url_for("home"))
    session["unit"] = unit
    portal = cfg.UNIT_PORTALS[unit]

    conn = get_db()
    data = {}

    if unit == "intel":
        data["records"] = conn.execute(
            "SELECT * FROM intel_reports ORDER BY id DESC"
        ).fetchall()
    elif unit == "operations":
        data["records"] = conn.execute(
            "SELECT * FROM operations ORDER BY id DESC"
        ).fetchall()
    elif unit == "seizures":
        data["firearms"] = conn.execute(
            "SELECT * FROM firearm_seizures ORDER BY id DESC"
        ).fetchall()
        data["narcotics"] = conn.execute(
            "SELECT * FROM narcotics_seizures ORDER BY id DESC"
        ).fetchall()
    elif unit == "arrests":
        data["records"] = conn.execute(
            "SELECT * FROM arrests ORDER BY id DESC"
        ).fetchall()
    elif unit == "forensics":
        data["custody"] = conn.execute(
            "SELECT * FROM chain_of_custody ORDER BY id DESC"
        ).fetchall()
        data["lab"] = conn.execute(
            "SELECT * FROM lab_tracking ORDER BY id DESC"
        ).fetchall()
    elif unit == "registry":
        data["cases"] = conn.execute(
            "SELECT * FROM cases ORDER BY id DESC"
        ).fetchall()
        data["dpp"] = conn.execute(
            "SELECT * FROM dpp_pipeline ORDER BY id DESC"
        ).fetchall()
        data["sop"] = conn.execute(
            "SELECT * FROM sop_checklists ORDER BY id DESC"
        ).fetchall()

    conn.close()
    return render_template(f"{unit}/home.html", portal=portal, data=data, unit=unit)


@app.route("/unit/<unit>/dashboard")
def unit_dashboard(unit):
    if unit not in cfg.UNIT_PORTALS:
        return redirect(url_for("home"))

    conn = get_db()
    charts = {}

    if unit == "intel":
        charts["by_source"] = conn.execute(
            "SELECT source, COUNT(*) as cnt FROM intel_reports GROUP BY source ORDER BY cnt DESC"
        ).fetchall()
        charts["by_priority"] = conn.execute(
            "SELECT priority, COUNT(*) as cnt FROM intel_reports GROUP BY priority"
        ).fetchall()
        charts["by_parish"] = conn.execute(
            "SELECT parish, COUNT(*) as cnt FROM intel_reports GROUP BY parish"
        ).fetchall()
        charts["total"] = conn.execute("SELECT COUNT(*) FROM intel_reports").fetchone()[0]
        charts["critical"] = conn.execute(
            "SELECT COUNT(*) FROM intel_reports WHERE priority='Critical'"
        ).fetchone()[0]
        charts["actioned"] = conn.execute(
            "SELECT COUNT(*) FROM intel_reports WHERE triage_decision LIKE 'Action%'"
        ).fetchone()[0]

    elif unit == "operations":
        charts["by_type"] = conn.execute(
            "SELECT op_type, COUNT(*) as cnt FROM operations GROUP BY op_type ORDER BY cnt DESC"
        ).fetchall()
        charts["by_outcome"] = conn.execute(
            "SELECT outcome, COUNT(*) as cnt FROM operations GROUP BY outcome"
        ).fetchall()
        charts["total"] = conn.execute("SELECT COUNT(*) FROM operations").fetchone()[0]
        charts["successful"] = conn.execute(
            "SELECT COUNT(*) FROM operations WHERE outcome LIKE 'Successful%'"
        ).fetchone()[0]
        charts["firearms_total"] = conn.execute(
            "SELECT COALESCE(SUM(firearms_seized),0) FROM operations"
        ).fetchone()[0]

    elif unit == "seizures":
        charts["fa_by_type"] = conn.execute(
            "SELECT firearm_type, COUNT(*) as cnt FROM firearm_seizures GROUP BY firearm_type ORDER BY cnt DESC"
        ).fetchall()
        charts["na_by_type"] = conn.execute(
            "SELECT drug_type, COUNT(*) as cnt FROM narcotics_seizures GROUP BY drug_type ORDER BY cnt DESC"
        ).fetchall()
        charts["fa_total"] = conn.execute("SELECT COUNT(*) FROM firearm_seizures").fetchone()[0]
        charts["na_total"] = conn.execute("SELECT COUNT(*) FROM narcotics_seizures").fetchone()[0]
        charts["ibis_hits"] = conn.execute(
            "SELECT COUNT(*) FROM firearm_seizures WHERE ibis_status LIKE 'Hit%'"
        ).fetchone()[0]

    elif unit == "arrests":
        charts["by_bail"] = conn.execute(
            "SELECT bail_status, COUNT(*) as cnt FROM arrests GROUP BY bail_status"
        ).fetchall()
        charts["total"] = conn.execute("SELECT COUNT(*) FROM arrests").fetchone()[0]
        charts["compliant_48"] = conn.execute(
            "SELECT COUNT(*) FROM arrests WHERE charge_within_48hr='Yes'"
        ).fetchone()[0]

    elif unit == "forensics":
        charts["by_type"] = conn.execute(
            "SELECT exhibit_type, COUNT(*) as cnt FROM chain_of_custody GROUP BY exhibit_type ORDER BY cnt DESC"
        ).fetchall()
        charts["by_cert"] = conn.execute(
            "SELECT certificate_status, COUNT(*) as cnt FROM lab_tracking GROUP BY certificate_status"
        ).fetchall()
        charts["total_exhibits"] = conn.execute("SELECT COUNT(*) FROM chain_of_custody").fetchone()[0]
        charts["certs_issued"] = conn.execute(
            "SELECT COUNT(*) FROM lab_tracking WHERE certificate_status LIKE '%Issued%'"
        ).fetchone()[0]

    elif unit == "registry":
        charts["by_status"] = conn.execute(
            "SELECT case_status, COUNT(*) as cnt FROM cases GROUP BY case_status ORDER BY cnt DESC"
        ).fetchall()
        charts["by_classification"] = conn.execute(
            "SELECT classification, COUNT(*) as cnt FROM cases GROUP BY classification ORDER BY cnt DESC"
        ).fetchall()
        charts["by_compliance"] = conn.execute(
            "SELECT sop_compliance, COUNT(*) as cnt FROM cases GROUP BY sop_compliance"
        ).fetchall()
        charts["by_dpp"] = conn.execute(
            "SELECT dpp_status, COUNT(*) as cnt FROM cases WHERE dpp_status IS NOT NULL GROUP BY dpp_status"
        ).fetchall()
        charts["total"] = conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
        charts["compliant"] = conn.execute(
            "SELECT COUNT(*) FROM cases WHERE sop_compliance LIKE 'Fully%' OR sop_compliance LIKE 'Substantially%'"
        ).fetchone()[0]
        charts["at_dpp"] = conn.execute(
            "SELECT COUNT(*) FROM cases WHERE case_status LIKE 'Referred to DPP%'"
        ).fetchone()[0]

    conn.close()
    return render_template(f"{unit}/dashboard.html",
                           portal=cfg.UNIT_PORTALS[unit],
                           charts=charts, unit=unit)


# =================================================================
#  COMMAND DASHBOARD (aggregated cross-unit)
# =================================================================
@app.route("/command")
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


# =================================================================
#  CRUD OPERATIONS - Generic record entry/edit
# =================================================================
@app.route("/unit/<unit>/new", methods=["GET", "POST"])
@app.route("/unit/<unit>/new/<subtype>", methods=["GET", "POST"])
def new_record(unit, subtype=None):
    if unit not in cfg.UNIT_PORTALS:
        return redirect(url_for("home"))

    if request.method == "POST":
        return _save_record(unit, subtype, is_new=True)

    return render_template(f"{unit}/form.html",
                           portal=cfg.UNIT_PORTALS[unit],
                           unit=unit, subtype=subtype,
                           record=None, cfg=cfg, is_new=True)


@app.route("/unit/<unit>/edit/<int:record_id>", methods=["GET", "POST"])
@app.route("/unit/<unit>/edit/<int:record_id>/<subtype>", methods=["GET", "POST"])
def edit_record(unit, record_id, subtype=None):
    if unit not in cfg.UNIT_PORTALS:
        return redirect(url_for("home"))

    conn = get_db()
    table = _get_table(unit, subtype)
    record = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (record_id,)).fetchone()
    conn.close()

    if not record:
        flash("Record not found.", "danger")
        return redirect(url_for("unit_home", unit=unit))

    if request.method == "POST":
        return _save_record(unit, subtype, is_new=False, record_id=record_id)

    return render_template(f"{unit}/form.html",
                           portal=cfg.UNIT_PORTALS[unit],
                           unit=unit, subtype=subtype,
                           record=record, cfg=cfg, is_new=False)


def _get_table(unit, subtype=None):
    """Map unit/subtype to database table name."""
    tables = {
        "intel": "intel_reports",
        "operations": "operations",
        "seizures": {
            "firearms": "firearm_seizures",
            "narcotics": "narcotics_seizures",
            None: "firearm_seizures",
        },
        "arrests": "arrests",
        "forensics": {
            "custody": "chain_of_custody",
            "lab": "lab_tracking",
            None: "chain_of_custody",
        },
        "registry": {
            "cases": "cases",
            "dpp": "dpp_pipeline",
            "sop": "sop_checklists",
            "witness": "witness_statements",
            "disclosure": "disclosure_log",
            None: "cases",
        },
    }
    mapping = tables.get(unit, "cases")
    if isinstance(mapping, dict):
        return mapping.get(subtype, mapping.get(None, "cases"))
    return mapping


def _get_id_prefix(unit, subtype=None):
    """Map unit/subtype to ID prefix."""
    prefixes = {
        "intel": "INT",
        "operations": "OP",
        "seizures": {"firearms": "FS", "narcotics": "NS", None: "FS"},
        "arrests": "AR",
        "forensics": {"custody": "EXH", "lab": "LAB", None: "EXH"},
        "registry": {"cases": "CR", "dpp": "DPP", "sop": "SOP",
                      "witness": "WIT", "disclosure": "DISC", None: "CR"},
    }
    mapping = prefixes.get(unit, "REC")
    if isinstance(mapping, dict):
        return mapping.get(subtype, mapping.get(None, "REC"))
    return mapping


def _get_id_column(unit, subtype=None):
    """Map unit/subtype to the ID column name."""
    columns = {
        "intel": "intel_id",
        "operations": "op_id",
        "seizures": "seizure_id",
        "arrests": "arrest_id",
        "forensics": {"custody": "exhibit_tag", "lab": "lab_ref", None: "exhibit_tag"},
        "registry": {"cases": "case_id", "dpp": "linked_case_id",
                      "sop": "linked_case_id", "witness": "statement_id",
                      "disclosure": "disclosure_id", None: "case_id"},
    }
    mapping = columns.get(unit, "id")
    if isinstance(mapping, dict):
        return mapping.get(subtype, mapping.get(None, "id"))
    return mapping


def _save_record(unit, subtype, is_new, record_id=None):
    """Save a new or edited record from form data."""
    table = _get_table(unit, subtype)
    form = request.form.to_dict()

    officer_badge = session.get("officer_badge", "")
    officer_name = session.get("officer_name", "")

    if is_new:
        id_col = _get_id_column(unit, subtype)
        prefix = _get_id_prefix(unit, subtype)
        new_id = generate_id(prefix, table, id_col)
        form[id_col] = new_id
        form["created_by"] = officer_name
        form["record_status"] = form.get("record_status", "Draft")
        if form.get("record_status") == "Submitted":
            form["submitted_by"] = officer_name
            form["submitted_date"] = datetime.now().strftime("%Y-%m-%d")
    else:
        form["updated_at"] = datetime.now().isoformat()
        if form.get("record_status") == "Submitted" and not form.get("submitted_by"):
            form["submitted_by"] = officer_name
            form["submitted_date"] = datetime.now().strftime("%Y-%m-%d")

    # Remove empty strings, keep actual values
    form = {k: (v if v != "" else None) for k, v in form.items()}

    conn = get_db()
    try:
        if is_new:
            cols = ", ".join(form.keys())
            placeholders = ", ".join(["?"] * len(form))
            conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
                         list(form.values()))
            log_audit(table, form.get(_get_id_column(unit, subtype), ""),
                      "CREATE", officer_badge, officer_name)
            flash(f"Record {form.get(_get_id_column(unit, subtype), '')} created successfully.", "success")
        else:
            set_clause = ", ".join([f"{k} = ?" for k in form.keys()])
            conn.execute(f"UPDATE {table} SET {set_clause} WHERE id = ?",
                         list(form.values()) + [record_id])
            log_audit(table, str(record_id), "UPDATE", officer_badge, officer_name)
            flash("Record updated successfully.", "success")
        conn.commit()
    except Exception as e:
        conn.rollback()
        flash(f"Error saving record: {str(e)}", "danger")
    finally:
        conn.close()

    return redirect(url_for("unit_home", unit=unit))


# =================================================================
#  DATA IMPORT (Word/Excel upload)
# =================================================================
@app.route("/import", methods=["GET", "POST"])
def import_data():
    if request.method == "POST":
        if "file" not in request.files:
            flash("No file selected.", "danger")
            return redirect(url_for("import_data"))

        file = request.files["file"]
        if file.filename == "":
            flash("No file selected.", "danger")
            return redirect(url_for("import_data"))

        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in (".docx", ".xlsx"):
            flash("Only .docx and .xlsx files are supported.", "danger")
            return redirect(url_for("import_data"))

        filepath = os.path.join(cfg.UPLOAD_DIR, file.filename)
        file.save(filepath)

        unit = request.form.get("target_unit", "")
        flash(f"File '{file.filename}' uploaded. Use the data import CLI tool to process: "
              f"python fnid_data_import.py --source {filepath} --unit {unit}", "info")
        return redirect(url_for("import_data"))

    return render_template("import.html")


# =================================================================
#  EXPORT TO EXCEL
# =================================================================
@app.route("/export/<unit>")
def export_unit(unit):
    try:
        from openpyxl import Workbook as XlWorkbook
    except ImportError:
        flash("openpyxl required for export.", "danger")
        return redirect(url_for("unit_home", unit=unit))

    table = _get_table(unit, None)
    conn = get_db()
    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    columns = [desc[0] for desc in conn.execute(f"SELECT * FROM {table} LIMIT 0").description]
    conn.close()

    wb = XlWorkbook()
    ws = wb.active
    ws.title = unit.title()
    ws.append(columns)
    for row in rows:
        ws.append(list(row))

    filename = f"FNID_{unit}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    filepath = os.path.join(cfg.EXPORT_DIR, filename)
    wb.save(filepath)

    return send_file(filepath, as_attachment=True, download_name=filename)


# =================================================================
#  API ENDPOINTS (for AJAX chart data)
# =================================================================
@app.route("/api/stats/<unit>")
def api_stats(unit):
    conn = get_db()
    result = {}

    if unit == "command":
        result = {
            "intel": conn.execute("SELECT COUNT(*) FROM intel_reports").fetchone()[0],
            "operations": conn.execute("SELECT COUNT(*) FROM operations").fetchone()[0],
            "firearms": conn.execute("SELECT COUNT(*) FROM firearm_seizures").fetchone()[0],
            "narcotics": conn.execute("SELECT COUNT(*) FROM narcotics_seizures").fetchone()[0],
            "arrests": conn.execute("SELECT COUNT(*) FROM arrests").fetchone()[0],
            "cases": conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0],
        }

    conn.close()
    return jsonify(result)


# =================================================================
#  TEMPLATE PAGES
# =================================================================

# --- Login ---
# (handled above)

# --- Import ---
# (handled above)

# =================================================================
#  INITIALIZE & RUN
# =================================================================
if __name__ == "__main__":
    init_db()
    print("=" * 60)
    print("FNID Area 3 Operational Portal")
    print("Jamaica Constabulary Force")
    print("Firearms & Narcotics Investigation Division")
    print("=" * 60)
    print(f"Database: {cfg.DB_PATH}")
    print(f"Starting server on http://127.0.0.1:5000")
    print("=" * 60)
    app.run(debug=True, host="0.0.0.0", port=5000)
