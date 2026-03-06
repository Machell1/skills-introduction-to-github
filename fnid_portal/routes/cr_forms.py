"""
Case Reference (CR) Form Management Routes

Digital handling for JCF Case Reference forms per Case Management Policy
(JCF/FW/PL/C&S/0001/2024 Section 11.0).

NB: All related forms must be referred to as Case Reference Form
(not Crime Reference Form) per policy.

Forms: CR 1 (Investigator's Worksheet), CR 2 (Action Sheet),
CR 3 (Witness Bio-Data), CR 4 (Stolen Property), CR 5 (Exhibit Chain of Custody),
CR 6 (Investigator Index Card), CR 7 (Morning Crime Report),
CR 8 (Q&A Suspect), CR 9 (Q&A Accused), CR 10 (Customer Reference Form),
CR 11 (Confession Statement), CR 12 (Major & Minor Case Report),
CR 13 (Court Case File Checklist), CR 14 (JCF Profile Form),
CR 15 (Application for Remand of Accused or Bail Conditions).

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

# Case Reference (CR) Form definitions — per JCF Case Management Policy
# JCF/FW/PL/C&S/0001/2024 Section 11.0
# NB: Forms are Case Reference Forms (not Crime Reference Forms)
CR_FORM_DEFINITIONS = {
    "CR1": {
        "name": "Investigator's Worksheet",
        "description": "Investigator's Worksheet (Appendix 9) - tracks investigator actions and case progress",
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
        "name": "Action Sheet",
        "description": "Action Sheet (Appendix 10) - tasks generated during vetting, reviews and conferences",
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
        "name": "Witness Bio-Data Form",
        "description": "Witness Bio-Data Form (Appendix 8) - completed for all major crimes and attached to front of statement",
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
        "name": "Stolen Property Form",
        "description": "Stolen Property Form (Appendix 7) - completed in triplicate for all stolen/recovered property",
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
        "name": "Exhibit Chain of Custody Schedule",
        "description": "Exhibit Chain of Custody Schedule (Appendix 16) - documents exhibit handling and transfers",
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
        "name": "Investigator Index Card",
        "description": "Investigator Index Card (Appendix 17) - records IO information and assigned cases",
        "sections": [
            {"title": "Investigator Information", "fields": [
                {"name": "officer_name", "label": "Investigator Name", "type": "text", "required": True},
                {"name": "officer_badge", "label": "Badge Number", "type": "text", "required": True},
                {"name": "officer_rank", "label": "Rank", "type": "select", "options": "JCF_RANKS"},
                {"name": "unit_section", "label": "Unit/Section", "type": "text"},
            ]},
            {"title": "Assigned Cases", "fields": [
                {"name": "case_reference", "label": "Case Reference Number", "type": "text"},
                {"name": "offence", "label": "Offence", "type": "text"},
                {"name": "assigned_date", "label": "Date Assigned", "type": "date"},
                {"name": "case_status", "label": "Case Status", "type": "text"},
                {"name": "last_review_date", "label": "Last Review Date", "type": "date"},
                {"name": "next_review_date", "label": "Next Review Date", "type": "date"},
                {"name": "remarks", "label": "Remarks", "type": "textarea"},
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
    "CR8": {
        "name": "Question and Answer Suspect Form",
        "description": "Question and Answer Suspect Form (Appendix 18) - recording of suspect interview",
        "sections": [
            {"title": "Suspect Interview", "fields": [
                {"name": "interview_date", "label": "Date of Interview", "type": "date", "required": True},
                {"name": "interview_time", "label": "Time of Interview", "type": "time"},
                {"name": "interview_location", "label": "Place of Interview", "type": "text", "required": True},
                {"name": "suspect_name", "label": "Name of Suspect", "type": "text", "required": True},
                {"name": "suspect_address", "label": "Address", "type": "text"},
                {"name": "suspect_dob", "label": "Date of Birth", "type": "date"},
                {"name": "suspect_occupation", "label": "Occupation", "type": "text"},
                {"name": "cautioned", "label": "Suspect Cautioned", "type": "select",
                 "options_list": ["Yes", "No"]},
                {"name": "rights_advised", "label": "Constitutional Rights Advised", "type": "select",
                 "options_list": ["Yes", "No"]},
                {"name": "attorney_access", "label": "Access to Attorney Offered", "type": "select",
                 "options_list": ["Yes", "No"]},
                {"name": "questions_answers", "label": "Questions and Answers", "type": "textarea", "required": True},
                {"name": "interviewer_name", "label": "Interviewer Name", "type": "text"},
                {"name": "interviewer_rank", "label": "Interviewer Rank", "type": "select", "options": "JCF_RANKS"},
                {"name": "witness_officer", "label": "Witness Officer", "type": "text"},
                {"name": "audio_visual_recorded", "label": "Audio-Visually Recorded", "type": "select",
                 "options_list": ["Yes", "No"]},
            ]},
        ],
    },
    "CR9": {
        "name": "Question and Answer Accused Form",
        "description": "Question and Answer Accused Form (Appendix 19) - recording of accused interview",
        "sections": [
            {"title": "Accused Interview", "fields": [
                {"name": "interview_date", "label": "Date of Interview", "type": "date", "required": True},
                {"name": "interview_time", "label": "Time of Interview", "type": "time"},
                {"name": "interview_location", "label": "Place of Interview", "type": "text", "required": True},
                {"name": "accused_name", "label": "Name of Accused", "type": "text", "required": True},
                {"name": "accused_address", "label": "Address", "type": "text"},
                {"name": "accused_dob", "label": "Date of Birth", "type": "date"},
                {"name": "charge", "label": "Charge(s)", "type": "textarea", "required": True},
                {"name": "cautioned", "label": "Accused Cautioned", "type": "select",
                 "options_list": ["Yes", "No"]},
                {"name": "questions_answers", "label": "Questions and Answers", "type": "textarea", "required": True},
                {"name": "interviewer_name", "label": "Interviewer Name", "type": "text"},
                {"name": "interviewer_rank", "label": "Interviewer Rank", "type": "select", "options": "JCF_RANKS"},
                {"name": "witness_officer", "label": "Witness Officer", "type": "text"},
                {"name": "audio_visual_recorded", "label": "Audio-Visually Recorded", "type": "select",
                 "options_list": ["Yes", "No"]},
            ]},
        ],
    },
    "CR10": {
        "name": "Customer Reference Form",
        "description": "Customer Reference Form (Appendix 6) - issued to complainant upon making a report",
        "sections": [
            {"title": "Customer Reference Details", "fields": [
                {"name": "customer_name", "label": "Name", "type": "text", "required": True},
                {"name": "customer_address", "label": "Address", "type": "text"},
                {"name": "customer_tel", "label": "Tel.", "type": "text"},
                {"name": "customer_email", "label": "Email", "type": "text"},
                {"name": "police_station", "label": "Police Station", "type": "text", "required": True},
                {"name": "station_tel", "label": "Station's Tel. # (876)", "type": "text"},
                {"name": "station_email", "label": "Station's Email", "type": "text"},
                {"name": "date_of_report", "label": "Date of Report", "type": "date", "required": True},
                {"name": "time_of_report", "label": "Time of Report", "type": "time"},
                {"name": "nature_of_report", "label": "Nature of Report", "type": "textarea", "required": True},
                {"name": "diary_entry", "label": "D/E #", "type": "text"},
                {"name": "crime_ref", "label": "Crime Ref.#", "type": "text"},
                {"name": "recording_officer", "label": "Name of Recording Officer", "type": "text"},
                {"name": "officer_rank", "label": "Rank", "type": "select", "options": "JCF_RANKS"},
                {"name": "officer_reg", "label": "Reg.#", "type": "text"},
                {"name": "recording_officer_signature", "label": "Signature of Recording Officer", "type": "text"},
            ]},
        ],
    },
    "CR11": {
        "name": "Confession Statement Form",
        "description": "Confession Statement Form (Appendix 20) - recording of confession per Section 9.3.4",
        "sections": [
            {"title": "Confession Details", "fields": [
                {"name": "confession_date", "label": "Date of Confession", "type": "date", "required": True},
                {"name": "confession_time", "label": "Time", "type": "time"},
                {"name": "confession_location", "label": "Place of Confession", "type": "text", "required": True},
                {"name": "person_name", "label": "Name of Person", "type": "text", "required": True},
                {"name": "person_address", "label": "Address", "type": "text"},
                {"name": "cautioned", "label": "Person Cautioned", "type": "select",
                 "options_list": ["Yes", "No"]},
                {"name": "rights_advised", "label": "Constitutional Rights Advised", "type": "select",
                 "options_list": ["Yes", "No"]},
                {"name": "offence_confessed", "label": "Offence(s) Confessed To", "type": "textarea", "required": True},
                {"name": "confession_body", "label": "Confession Statement", "type": "textarea", "required": True},
                {"name": "audio_visual_recorded", "label": "Audio-Visually Recorded", "type": "select",
                 "options_list": ["Yes", "No"]},
                {"name": "recording_device", "label": "Recording Device Used", "type": "text"},
                {"name": "transcript_prepared", "label": "Transcript Prepared", "type": "select",
                 "options_list": ["Yes", "No"]},
                {"name": "recorded_by", "label": "Recorded By", "type": "text"},
                {"name": "recorded_by_rank", "label": "Rank", "type": "select", "options": "JCF_RANKS"},
                {"name": "witness_officer", "label": "Witness Officer", "type": "text"},
            ]},
        ],
    },
    "CR12": {
        "name": "Major and Minor Case Report Form",
        "description": "Major and Minor Case Report Form (Appendix 21) - completed for case closure or court submission",
        "sections": [
            {"title": "Case Report Details", "fields": [
                {"name": "case_reference", "label": "Case Reference Number", "type": "text", "required": True},
                {"name": "report_date", "label": "Date", "type": "date", "required": True},
                {"name": "crime_type", "label": "Crime Type", "type": "select",
                 "options_list": ["Major", "Minor"]},
                {"name": "classification", "label": "Classification", "type": "select", "options": "CASE_CLASSIFICATIONS"},
                {"name": "offence", "label": "Offence", "type": "text", "required": True},
                {"name": "complainant_name", "label": "Complainant Name", "type": "text"},
                {"name": "suspect_name", "label": "Suspect Name", "type": "text"},
                {"name": "investigating_officer", "label": "Investigating Officer", "type": "text"},
                {"name": "case_status", "label": "Case Status", "type": "select",
                 "options_list": ["Case Open", "Case Cleared", "Case Closed", "Case Suspended", "Cold Case"]},
                {"name": "closure_reason", "label": "Closure/Clearance Reason (per Section 6.3)", "type": "textarea"},
                {"name": "court_submission_date", "label": "Date Submitted to Court", "type": "date"},
                {"name": "remarks", "label": "Remarks", "type": "textarea"},
                {"name": "prepared_by", "label": "Prepared By", "type": "text"},
                {"name": "reviewed_by", "label": "Reviewed By", "type": "text"},
            ]},
        ],
    },
    "CR13": {
        "name": "Court Case File Checklist",
        "description": "Court Case File Checklist (Appendix 22) - ensures all documents accompany case file to court",
        "sections": [
            {"title": "Case File Checklist", "fields": [
                {"name": "case_reference", "label": "Case Reference Number", "type": "text", "required": True},
                {"name": "accused_name", "label": "Accused Name", "type": "text", "required": True},
                {"name": "offence", "label": "Offence", "type": "text", "required": True},
                {"name": "court", "label": "Court", "type": "select", "options": "COURT_TYPES"},
                {"name": "court_date", "label": "Court Date", "type": "date"},
                {"name": "charge_sheet", "label": "Charge Sheet", "type": "select",
                 "options_list": ["Yes", "No", "N/A"]},
                {"name": "complainant_statement", "label": "Complainant Statement", "type": "select",
                 "options_list": ["Yes", "No", "N/A"]},
                {"name": "witness_statements", "label": "Witness Statements", "type": "select",
                 "options_list": ["Yes", "No", "N/A"]},
                {"name": "arresting_officer_statement", "label": "Arresting Officer Statement", "type": "select",
                 "options_list": ["Yes", "No", "N/A"]},
                {"name": "first_responder_statement", "label": "First Responder Statement", "type": "select",
                 "options_list": ["Yes", "No", "N/A"]},
                {"name": "forensic_certificates", "label": "Forensic Certificate(s)", "type": "select",
                 "options_list": ["Yes", "No", "N/A"]},
                {"name": "ballistic_certificate", "label": "Ballistic Certificate", "type": "select",
                 "options_list": ["Yes", "No", "N/A"]},
                {"name": "exhibit_list", "label": "Exhibit List", "type": "select",
                 "options_list": ["Yes", "No", "N/A"]},
                {"name": "chain_of_custody", "label": "Chain of Custody Schedule (CR 5)", "type": "select",
                 "options_list": ["Yes", "No", "N/A"]},
                {"name": "jcf_profile_form", "label": "JCF Profile Form (CR 14)", "type": "select",
                 "options_list": ["Yes", "No", "N/A"]},
                {"name": "photos_videos", "label": "Photographs/Video Evidence", "type": "select",
                 "options_list": ["Yes", "No", "N/A"]},
                {"name": "other_documents", "label": "Other Documents", "type": "textarea"},
                {"name": "verified_by", "label": "Verified By (Registrar/DCR)", "type": "text"},
                {"name": "verification_date", "label": "Verification Date", "type": "date"},
            ]},
        ],
    },
    "CR14": {
        "name": "JCF Profile Form",
        "description": "JCF Profile Form (Appendix 24) - completed by arresting/investigating officer for all case files",
        "sections": [
            {"title": "Accused Profile", "fields": [
                {"name": "accused_name", "label": "Name of Accused", "type": "text", "required": True},
                {"name": "accused_alias", "label": "Alias", "type": "text"},
                {"name": "accused_dob", "label": "Date of Birth", "type": "date"},
                {"name": "accused_address", "label": "Address", "type": "text"},
                {"name": "accused_occupation", "label": "Occupation", "type": "text"},
                {"name": "accused_nationality", "label": "Nationality", "type": "text"},
                {"name": "accused_description", "label": "Physical Description", "type": "textarea"},
                {"name": "charge", "label": "Charge(s)", "type": "textarea", "required": True},
                {"name": "law_section", "label": "Law & Section", "type": "text"},
                {"name": "previous_convictions", "label": "Previous Convictions", "type": "textarea"},
                {"name": "arresting_officer", "label": "Arresting Officer", "type": "text"},
                {"name": "arresting_officer_badge", "label": "Badge No.", "type": "text"},
                {"name": "investigating_officer", "label": "Investigating Officer", "type": "text"},
                {"name": "station", "label": "Station", "type": "text"},
            ]},
        ],
    },
    "CR15": {
        "name": "Application for Remand of Accused or Bail Conditions",
        "description": "Application for Remand of Accused or Bail Conditions (Appendix 25) - submitted in case file to DCR",
        "sections": [
            {"title": "Remand/Bail Application", "fields": [
                {"name": "application_date", "label": "Date", "type": "date", "required": True},
                {"name": "accused_name", "label": "Name of Accused", "type": "text", "required": True},
                {"name": "accused_address", "label": "Address", "type": "text"},
                {"name": "offence", "label": "Offence Charged", "type": "text", "required": True},
                {"name": "law_section", "label": "Law & Section", "type": "text"},
                {"name": "application_type", "label": "Application Type", "type": "select",
                 "options_list": ["Remand in Custody", "Bail with Conditions"]},
                {"name": "grounds", "label": "Grounds for Application", "type": "textarea", "required": True},
                {"name": "bail_conditions_requested", "label": "Bail Conditions Requested (if applicable)", "type": "textarea"},
                {"name": "bail_amount_suggested", "label": "Bail Amount Suggested (JMD)", "type": "number"},
                {"name": "surety_required", "label": "Surety Required", "type": "select",
                 "options_list": ["Yes", "No"]},
                {"name": "risk_of_flight", "label": "Risk of Flight", "type": "select",
                 "options_list": ["Yes", "No"]},
                {"name": "risk_to_witnesses", "label": "Risk to Witnesses", "type": "select",
                 "options_list": ["Yes", "No"]},
                {"name": "previous_convictions", "label": "Previous Convictions", "type": "textarea"},
                {"name": "court", "label": "Court", "type": "select", "options": "COURT_TYPES"},
                {"name": "investigating_officer", "label": "Investigating Officer", "type": "text"},
                {"name": "io_badge", "label": "Badge No.", "type": "text"},
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
