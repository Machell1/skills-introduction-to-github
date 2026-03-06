"""
CR Form Management Routes

Digital handling for JCF Crime Report forms: CR 1–7, CR 10, CR 12–15.
Forms are stored as JSON data linked to cases.

Field layouts are CONFIGURABLE — derived from JCF policy language.
"""

import json
from datetime import datetime

from flask import Blueprint, Response, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..case_numbers import generate_form_id
from ..models import get_db, log_audit
from ..pdf_export import pdf_base_css, pdf_header_html, render_pdf
from ..rbac import permission_required
from . import _cfg_module

bp = Blueprint("cr_forms", __name__)

# CR Form definitions — CONFIGURABLE field layouts
# Derived from JCF policy language; adjust when FO 4032 layouts are available
CR_FORM_DEFINITIONS = {
    "CR1": {
        "name": "Crime Report",
        "description": "Initial crime report details",
        "sections": [
            {"title": "Report Details", "fields": [
                {"name": "report_date", "label": "Date of Report", "type": "date", "required": True},
                {"name": "report_time", "label": "Time of Report", "type": "time"},
                {"name": "station", "label": "Station", "type": "text", "required": True},
                {"name": "diary_number", "label": "Station Diary Number", "type": "text"},
                {"name": "offence_date", "label": "Date of Offence", "type": "date", "required": True},
                {"name": "offence_time", "label": "Time of Offence", "type": "time"},
                {"name": "offence_location", "label": "Location of Offence", "type": "text", "required": True},
                {"name": "parish", "label": "Parish", "type": "select", "options": "ALL_PARISHES"},
            ]},
            {"title": "Offence Classification", "fields": [
                {"name": "classification", "label": "Classification", "type": "select", "options": "CASE_CLASSIFICATIONS"},
                {"name": "offence", "label": "Offence", "type": "select", "options": "ALL_OFFENCES"},
                {"name": "law_section", "label": "Law & Section", "type": "text"},
                {"name": "crime_type", "label": "Crime Type", "type": "select",
                 "options_list": ["Major", "Minor"]},
            ]},
            {"title": "Complainant/Victim", "fields": [
                {"name": "complainant_name", "label": "Complainant Name", "type": "text"},
                {"name": "complainant_address", "label": "Address", "type": "text"},
                {"name": "complainant_phone", "label": "Telephone", "type": "text"},
                {"name": "complainant_occupation", "label": "Occupation", "type": "text"},
            ]},
            {"title": "Suspect Details", "fields": [
                {"name": "suspect_name", "label": "Suspect Name", "type": "text"},
                {"name": "suspect_alias", "label": "Alias", "type": "text"},
                {"name": "suspect_dob", "label": "Date of Birth", "type": "date"},
                {"name": "suspect_address", "label": "Address", "type": "text"},
                {"name": "suspect_description", "label": "Description", "type": "textarea"},
            ]},
            {"title": "Particulars of Offence", "fields": [
                {"name": "particulars", "label": "Particulars of Offence", "type": "textarea", "required": True},
                {"name": "stolen_property", "label": "Stolen Property Description", "type": "textarea"},
                {"name": "property_value", "label": "Estimated Value (JMD)", "type": "number"},
                {"name": "weapons_used", "label": "Weapons Used", "type": "text"},
                {"name": "modus_operandi", "label": "Modus Operandi", "type": "textarea"},
            ]},
            {"title": "Investigating Officer", "fields": [
                {"name": "oic_name", "label": "OIC Name", "type": "text"},
                {"name": "oic_rank", "label": "OIC Rank", "type": "select", "options": "JCF_RANKS"},
                {"name": "oic_badge", "label": "OIC Badge No.", "type": "text"},
            ]},
        ],
    },
    "CR2": {
        "name": "Supplementary Report",
        "description": "Additional information supplementing the initial CR 1",
        "sections": [
            {"title": "Supplementary Details", "fields": [
                {"name": "supplement_date", "label": "Date", "type": "date", "required": True},
                {"name": "supplement_number", "label": "Supplement Number", "type": "number"},
                {"name": "additional_info", "label": "Additional Information", "type": "textarea", "required": True},
                {"name": "new_evidence", "label": "New Evidence Discovered", "type": "textarea"},
                {"name": "new_witnesses", "label": "New Witnesses Identified", "type": "textarea"},
                {"name": "suspect_update", "label": "Suspect Update", "type": "textarea"},
                {"name": "prepared_by", "label": "Prepared By", "type": "text"},
            ]},
        ],
    },
    "CR3": {
        "name": "Statement Form",
        "description": "Witness/suspect statement template",
        "sections": [
            {"title": "Statement Details", "fields": [
                {"name": "statement_date", "label": "Date", "type": "date", "required": True},
                {"name": "statement_time", "label": "Time", "type": "time"},
                {"name": "deponent_name", "label": "Name of Deponent", "type": "text", "required": True},
                {"name": "deponent_address", "label": "Address", "type": "text"},
                {"name": "deponent_occupation", "label": "Occupation", "type": "text"},
                {"name": "deponent_age", "label": "Age", "type": "number"},
                {"name": "statement_type", "label": "Type", "type": "select",
                 "options_list": ["Witness", "Complainant", "Suspect (under caution)", "Expert"]},
                {"name": "cautioned", "label": "Cautioned (if suspect)", "type": "select",
                 "options_list": ["N/A", "Yes", "No"]},
                {"name": "statement_body", "label": "Statement", "type": "textarea", "required": True},
                {"name": "taken_by", "label": "Statement Taken By", "type": "text"},
                {"name": "signed", "label": "Signed by Deponent", "type": "select",
                 "options_list": ["Yes", "No"]},
            ]},
        ],
    },
    "CR4": {
        "name": "Property/Exhibit Register",
        "description": "Seized/found property listing",
        "sections": [
            {"title": "Exhibit Details", "fields": [
                {"name": "exhibit_number", "label": "Exhibit Number", "type": "text", "required": True},
                {"name": "exhibit_description", "label": "Description", "type": "textarea", "required": True},
                {"name": "exhibit_type", "label": "Type", "type": "select", "options": "EXHIBIT_TYPES"},
                {"name": "quantity", "label": "Quantity", "type": "number"},
                {"name": "seized_from", "label": "Seized From (person/location)", "type": "text"},
                {"name": "seizure_date", "label": "Date of Seizure", "type": "date"},
                {"name": "seized_by", "label": "Seized By", "type": "text"},
                {"name": "witness_officer", "label": "Witness Officer", "type": "text"},
                {"name": "seal_number", "label": "Seal Number", "type": "text"},
                {"name": "storage_location", "label": "Storage Location", "type": "text"},
                {"name": "condition", "label": "Condition", "type": "text"},
                {"name": "photos_taken", "label": "Photographs Taken", "type": "select",
                 "options_list": ["Yes", "No"]},
            ]},
        ],
    },
    "CR5": {
        "name": "Investigation Diary",
        "description": "Investigator's daily log of activities",
        "sections": [
            {"title": "Diary Entry", "fields": [
                {"name": "entry_date", "label": "Date", "type": "date", "required": True},
                {"name": "entry_time", "label": "Time", "type": "time"},
                {"name": "activity", "label": "Activity/Action Taken", "type": "textarea", "required": True},
                {"name": "persons_contacted", "label": "Persons Contacted", "type": "textarea"},
                {"name": "locations_visited", "label": "Locations Visited", "type": "text"},
                {"name": "evidence_obtained", "label": "Evidence Obtained", "type": "textarea"},
                {"name": "next_steps", "label": "Next Steps Planned", "type": "textarea"},
                {"name": "hours_spent", "label": "Hours Spent", "type": "number"},
            ]},
        ],
    },
    "CR6": {
        "name": "Case Summary",
        "description": "Summary for supervisor/DPP review",
        "sections": [
            {"title": "Case Summary", "fields": [
                {"name": "summary_date", "label": "Date", "type": "date", "required": True},
                {"name": "case_synopsis", "label": "Synopsis of Case", "type": "textarea", "required": True},
                {"name": "evidence_summary", "label": "Summary of Evidence", "type": "textarea", "required": True},
                {"name": "witness_summary", "label": "Summary of Witnesses", "type": "textarea"},
                {"name": "exhibits_summary", "label": "Summary of Exhibits", "type": "textarea"},
                {"name": "forensic_summary", "label": "Forensic Evidence Summary", "type": "textarea"},
                {"name": "recommendation", "label": "Recommendation", "type": "textarea", "required": True},
                {"name": "prepared_by", "label": "Prepared By", "type": "text"},
                {"name": "reviewed_by", "label": "Reviewed By (Supervisor)", "type": "text"},
            ]},
        ],
    },
    "CR7": {
        "name": "Morning Crime Report",
        "description": "Daily crime summary (typically auto-generated by MCR engine)",
        "sections": [
            {"title": "MCR Summary", "fields": [
                {"name": "mcr_date", "label": "Report Date", "type": "date", "required": True},
                {"name": "window_start", "label": "Period From", "type": "text"},
                {"name": "window_end", "label": "Period To", "type": "text"},
                {"name": "total_matters", "label": "Total Matters", "type": "number"},
                {"name": "fnid_matters", "label": "FNID-Relevant Matters", "type": "number"},
                {"name": "firearms_seized", "label": "Firearms Seized", "type": "number"},
                {"name": "narcotics_seized", "label": "Narcotics Seized", "type": "text"},
                {"name": "arrests_made", "label": "Arrests Made", "type": "number"},
                {"name": "summary_narrative", "label": "Summary Narrative", "type": "textarea", "required": True},
                {"name": "lead_items", "label": "Lead Items for Follow-Up", "type": "textarea"},
                {"name": "compiled_by", "label": "Compiled By", "type": "text"},
            ]},
        ],
    },
    "CR10": {
        "name": "Scene of Crime Report",
        "description": "Crime scene documentation",
        "sections": [
            {"title": "Scene Details", "fields": [
                {"name": "scene_date", "label": "Date of Examination", "type": "date", "required": True},
                {"name": "scene_time", "label": "Time of Examination", "type": "time"},
                {"name": "scene_location", "label": "Scene Location", "type": "text", "required": True},
                {"name": "scene_type", "label": "Scene Type", "type": "select",
                 "options_list": ["Indoor", "Outdoor", "Vehicle", "Mixed"]},
                {"name": "weather_conditions", "label": "Weather/Conditions", "type": "text"},
                {"name": "scene_description", "label": "Scene Description", "type": "textarea", "required": True},
                {"name": "evidence_found", "label": "Evidence Found at Scene", "type": "textarea"},
                {"name": "photographs_taken", "label": "Photographs Taken", "type": "number"},
                {"name": "sketches_drawn", "label": "Sketches/Diagrams Made", "type": "select",
                 "options_list": ["Yes", "No"]},
                {"name": "video_recorded", "label": "Video Recorded", "type": "select",
                 "options_list": ["Yes", "No"]},
                {"name": "forensic_processing", "label": "Forensic Processing Done", "type": "textarea"},
                {"name": "examined_by", "label": "Examined By", "type": "text"},
            ]},
        ],
    },
    "CR12": {
        "name": "Charge Sheet",
        "description": "Formal charge details",
        "sections": [
            {"title": "Charge Details", "fields": [
                {"name": "charge_date", "label": "Date of Charge", "type": "date", "required": True},
                {"name": "accused_name", "label": "Name of Accused", "type": "text", "required": True},
                {"name": "accused_address", "label": "Address", "type": "text"},
                {"name": "accused_dob", "label": "Date of Birth", "type": "date"},
                {"name": "accused_occupation", "label": "Occupation", "type": "text"},
                {"name": "charge_1", "label": "Charge 1", "type": "text", "required": True},
                {"name": "law_section_1", "label": "Law & Section (Charge 1)", "type": "text"},
                {"name": "charge_2", "label": "Charge 2", "type": "text"},
                {"name": "law_section_2", "label": "Law & Section (Charge 2)", "type": "text"},
                {"name": "charge_3", "label": "Charge 3", "type": "text"},
                {"name": "law_section_3", "label": "Law & Section (Charge 3)", "type": "text"},
                {"name": "particulars", "label": "Particulars of Charge", "type": "textarea", "required": True},
                {"name": "charging_officer", "label": "Charging Officer", "type": "text"},
                {"name": "charging_officer_badge", "label": "Badge No.", "type": "text"},
            ]},
        ],
    },
    "CR13": {
        "name": "Bail Record",
        "description": "Bail decision documentation",
        "sections": [
            {"title": "Bail Details", "fields": [
                {"name": "bail_date", "label": "Date", "type": "date", "required": True},
                {"name": "accused_name", "label": "Accused Name", "type": "text", "required": True},
                {"name": "offence", "label": "Offence Charged", "type": "text", "required": True},
                {"name": "bail_decision", "label": "Bail Decision", "type": "select", "options": "BAIL_STATUS"},
                {"name": "bail_amount", "label": "Bail Amount (JMD)", "type": "number"},
                {"name": "surety_required", "label": "Surety Required", "type": "select",
                 "options_list": ["Yes", "No"]},
                {"name": "conditions", "label": "Bail Conditions", "type": "textarea"},
                {"name": "court", "label": "Court", "type": "select", "options": "COURT_TYPES"},
                {"name": "next_court_date", "label": "Next Court Date", "type": "date"},
                {"name": "remand_location", "label": "Remand Location (if denied)", "type": "select",
                 "options": "REMAND_LOCATIONS"},
                {"name": "recording_officer", "label": "Recording Officer", "type": "text"},
            ]},
        ],
    },
    "CR14": {
        "name": "Court Result Sheet",
        "description": "Court outcome recording",
        "sections": [
            {"title": "Court Result", "fields": [
                {"name": "court_date", "label": "Court Date", "type": "date", "required": True},
                {"name": "court", "label": "Court", "type": "select", "options": "COURT_TYPES"},
                {"name": "accused_name", "label": "Accused Name", "type": "text", "required": True},
                {"name": "charges", "label": "Charges Before Court", "type": "textarea", "required": True},
                {"name": "plea", "label": "Plea", "type": "select",
                 "options_list": ["Not Guilty", "Guilty", "Mixed", "No Plea Entered"]},
                {"name": "verdict", "label": "Verdict", "type": "select",
                 "options_list": ["Guilty", "Not Guilty", "Nolle Prosequi", "Dismissed",
                                  "Adjourned", "Committal to Circuit Court", "Pending"]},
                {"name": "sentence", "label": "Sentence (if convicted)", "type": "textarea"},
                {"name": "next_date", "label": "Next Court Date (if adjourned)", "type": "date"},
                {"name": "crown_counsel", "label": "Crown Counsel", "type": "text"},
                {"name": "defence_counsel", "label": "Defence Counsel", "type": "text"},
                {"name": "plo_present", "label": "PLO Present", "type": "text"},
                {"name": "result_notes", "label": "Notes", "type": "textarea"},
            ]},
        ],
    },
    "CR15": {
        "name": "Case Closure Report",
        "description": "Final case disposition and closure documentation",
        "sections": [
            {"title": "Closure Details", "fields": [
                {"name": "closure_date", "label": "Date of Closure", "type": "date", "required": True},
                {"name": "closure_reason", "label": "Reason for Closure", "type": "select",
                 "options_list": [
                     "Convicted — Sentence Imposed",
                     "Acquitted — Verdict of Not Guilty",
                     "No Charge — DPP Ruling",
                     "Withdrawn by Prosecution",
                     "Dismissed by Court",
                     "Nolle Prosequi",
                     "Deceased Accused",
                     "Merged with Another Case",
                     "Administrative Closure",
                 ]},
                {"name": "case_synopsis", "label": "Final Case Synopsis", "type": "textarea", "required": True},
                {"name": "investigation_summary", "label": "Investigation Summary", "type": "textarea"},
                {"name": "court_outcome", "label": "Court Outcome", "type": "textarea"},
                {"name": "exhibits_disposition", "label": "Exhibits Disposition", "type": "textarea"},
                {"name": "lessons_learned", "label": "Lessons Learned / Observations", "type": "textarea"},
                {"name": "closed_by", "label": "Closed By", "type": "text"},
                {"name": "approved_by", "label": "Approved By (Supervisor)", "type": "text"},
            ]},
        ],
    },
}


@bp.route("/cases/<case_id>/forms")
@login_required
@permission_required("cr_forms", "read")
def form_list(case_id):
    """List all CR forms for a case."""
    conn = get_db()
    try:
        case = conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
        if not case:
            flash("Case not found.", "danger")
            return redirect(url_for("cases.case_list"))

        forms = conn.execute(
            "SELECT * FROM cr_forms WHERE case_id = ? ORDER BY form_type, created_at",
            (case_id,)
        ).fetchall()

        return render_template("cr_forms/form_list.html",
                             case=case, forms=forms,
                             form_definitions=CR_FORM_DEFINITIONS)
    finally:
        conn.close()


@bp.route("/cases/<case_id>/forms/new/<form_type>", methods=["GET", "POST"])
@login_required
@permission_required("cr_forms", "create")
def new_form(case_id, form_type):
    """Create a new CR form."""
    form_def = CR_FORM_DEFINITIONS.get(form_type)
    if not form_def:
        flash(f"Unknown form type: {form_type}", "danger")
        return redirect(url_for("cr_forms.form_list", case_id=case_id))

    conn = get_db()
    try:
        case = conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
        if not case:
            flash("Case not found.", "danger")
            return redirect(url_for("cases.case_list"))

        if request.method == "POST":
            form_id = generate_form_id(form_type, case_id)
            form_data = {}
            for section in form_def["sections"]:
                for field in section["fields"]:
                    val = request.form.get(field["name"], "")
                    if val:
                        form_data[field["name"]] = val

            status = request.form.get("form_status", "Draft")
            name = current_user.full_name
            now = datetime.now().isoformat()

            conn.execute("""
                INSERT INTO cr_forms (form_id, case_id, form_type, form_data,
                                      status, created_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (form_id, case_id, form_type, json.dumps(form_data),
                  status, name, now, now))

            if status == "Submitted":
                conn.execute("""
                    UPDATE cr_forms SET submitted_by = ?, submitted_at = ?
                    WHERE form_id = ?
                """, (name, now, form_id))

            conn.commit()
            log_audit("cr_forms", form_id, "CREATE", current_user.badge_number,
                     name, f"{form_type} for case {case_id}")
            flash(f"{form_def['name']} ({form_id}) created.", "success")
            return redirect(url_for("cr_forms.form_list", case_id=case_id))

        cfg = _cfg_module()
        return render_template("cr_forms/form_edit.html",
                             case=case, form_type=form_type,
                             form_def=form_def, form_data={},
                             is_new=True, cfg=cfg)
    finally:
        conn.close()


@bp.route("/cases/<case_id>/forms/<form_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("cr_forms", "update")
def edit_form(case_id, form_id):
    """Edit an existing CR form."""
    conn = get_db()
    try:
        form_rec = conn.execute(
            "SELECT * FROM cr_forms WHERE form_id = ? AND case_id = ?",
            (form_id, case_id)
        ).fetchone()
        if not form_rec:
            flash("Form not found.", "danger")
            return redirect(url_for("cr_forms.form_list", case_id=case_id))

        case = conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
        form_type = form_rec["form_type"]
        form_def = CR_FORM_DEFINITIONS.get(form_type)
        if not form_def:
            flash(f"Unknown form type: {form_type}", "danger")
            return redirect(url_for("cr_forms.form_list", case_id=case_id))

        existing_data = json.loads(form_rec["form_data"]) if form_rec["form_data"] else {}

        if request.method == "POST":
            form_data = {}
            for section in form_def["sections"]:
                for field in section["fields"]:
                    val = request.form.get(field["name"], "")
                    if val:
                        form_data[field["name"]] = val

            status = request.form.get("form_status", "Draft")
            now = datetime.now().isoformat()
            name = current_user.full_name

            conn.execute("""
                UPDATE cr_forms SET form_data = ?, status = ?, updated_at = ?
                WHERE form_id = ?
            """, (json.dumps(form_data), status, now, form_id))

            if status == "Submitted" and not form_rec["submitted_by"]:
                conn.execute("""
                    UPDATE cr_forms SET submitted_by = ?, submitted_at = ?
                    WHERE form_id = ?
                """, (name, now, form_id))

            conn.commit()
            log_audit("cr_forms", form_id, "UPDATE", current_user.badge_number, name)
            flash("Form updated.", "success")
            return redirect(url_for("cr_forms.form_list", case_id=case_id))

        cfg = _cfg_module()
        return render_template("cr_forms/form_edit.html",
                             case=case, form_type=form_type,
                             form_def=form_def, form_data=existing_data,
                             form_rec=form_rec, is_new=False, cfg=cfg)
    finally:
        conn.close()


@bp.route("/cases/<case_id>/forms/<form_id>/pdf")
@login_required
@permission_required("cr_forms", "export_pdf")
def export_form_pdf(case_id, form_id):
    """Export a CR form as PDF."""
    conn = get_db()
    try:
        form_rec = conn.execute(
            "SELECT * FROM cr_forms WHERE form_id = ? AND case_id = ?",
            (form_id, case_id)
        ).fetchone()
        if not form_rec:
            flash("Form not found.", "danger")
            return redirect(url_for("cr_forms.form_list", case_id=case_id))

        form_type = form_rec["form_type"]
        form_def = CR_FORM_DEFINITIONS.get(form_type, {})
        form_data = json.loads(form_rec["form_data"]) if form_rec["form_data"] else {}

        # Build HTML for PDF
        html = f"""<!DOCTYPE html><html><head>{pdf_base_css()}</head><body>
        {pdf_header_html(f'{form_def.get("name", form_type)} ({form_type})', case_id, form_id)}
        """

        for section in form_def.get("sections", []):
            html += f'<div class="section"><div class="section-title">{section["title"]}</div>'
            html += '<table>'
            for field in section["fields"]:
                val = form_data.get(field["name"], "—")
                html += f'<tr><td class="field-label" style="width:35%">{field["label"]}</td>'
                html += f'<td class="field-value">{val}</td></tr>'
            html += '</table></div>'

        html += f"""
        <div class="footer">
            Form ID: {form_id} | Status: {form_rec['status']} |
            Created by: {form_rec['created_by']} | Date: {form_rec['created_at']}
        </div>
        </body></html>"""

        pdf_buffer = render_pdf(html)
        if pdf_buffer:
            log_audit("cr_forms", form_id, "EXPORT_PDF",
                     current_user.badge_number, current_user.full_name)
            return Response(
                pdf_buffer.read(),
                mimetype="application/pdf",
                headers={"Content-Disposition": f"attachment; filename={form_type}_{case_id}.pdf"}
            )
        else:
            flash("PDF generation unavailable. Showing print view.", "warning")
            return redirect(url_for("cr_forms.print_form", case_id=case_id, form_id=form_id))
    finally:
        conn.close()


@bp.route("/cases/<case_id>/forms/<form_id>/print")
@login_required
@permission_required("cr_forms", "read")
def print_form(case_id, form_id):
    """Print-optimized view of a CR form."""
    conn = get_db()
    try:
        form_rec = conn.execute(
            "SELECT * FROM cr_forms WHERE form_id = ? AND case_id = ?",
            (form_id, case_id)
        ).fetchone()
        if not form_rec:
            flash("Form not found.", "danger")
            return redirect(url_for("cr_forms.form_list", case_id=case_id))

        case = conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
        form_type = form_rec["form_type"]
        form_def = CR_FORM_DEFINITIONS.get(form_type, {})
        form_data = json.loads(form_rec["form_data"]) if form_rec["form_data"] else {}

        return render_template("cr_forms/form_print.html",
                             case=case, form_rec=form_rec,
                             form_def=form_def, form_data=form_data)
    finally:
        conn.close()
