"""
FNID Database Models - SQLite

Central schema designed around Investigations and Case Management.
All tables link back to the Case (investigation) as the core entity.
"""

import sqlite3
import os
from datetime import datetime
from config import DB_PATH


def get_db():
    """Get database connection with row factory."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db():
    """Initialize database schema."""
    conn = get_db()
    c = conn.cursor()

    # --- Officers / Users ---
    c.execute("""
    CREATE TABLE IF NOT EXISTS officers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        badge_number TEXT UNIQUE NOT NULL,
        full_name TEXT NOT NULL,
        rank TEXT NOT NULL,
        section TEXT NOT NULL,
        unit_access TEXT NOT NULL DEFAULT 'all',
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now'))
    )""")

    # --- CASES (Central Entity) ---
    # Every investigation is a Case. All other records link here.
    c.execute("""
    CREATE TABLE IF NOT EXISTS cases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id TEXT UNIQUE NOT NULL,
        registration_date TEXT NOT NULL,
        classification TEXT NOT NULL,
        oic_badge TEXT NOT NULL,
        oic_name TEXT NOT NULL,
        oic_rank TEXT NOT NULL,
        parish TEXT NOT NULL,
        division TEXT DEFAULT 'FNID Area 3',
        offence_description TEXT NOT NULL,
        law_and_section TEXT NOT NULL,
        suspect_name TEXT,
        suspect_dob TEXT,
        suspect_address TEXT,
        suspect_occupation TEXT,
        victim_name TEXT,
        victim_address TEXT,
        linked_intel_id TEXT,
        linked_op_id TEXT,
        linked_arrest_id TEXT,
        case_status TEXT NOT NULL DEFAULT 'Open - Active Investigation',
        file_completeness TEXT DEFAULT 'Not Started',
        sop_compliance TEXT DEFAULT 'Under Review',
        dpp_submission_date TEXT,
        dpp_status TEXT,
        dpp_ruling TEXT,
        court_type TEXT,
        next_court_date TEXT,
        trial_date TEXT,
        verdict TEXT,
        sentence TEXT,
        poca_referred TEXT DEFAULT 'No',
        poca_status TEXT DEFAULT 'Not Applicable',
        record_status TEXT DEFAULT 'Draft',
        submitted_by TEXT,
        submitted_date TEXT,
        notes TEXT,
        created_by TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""")

    # --- INTELLIGENCE ---
    c.execute("""
    CREATE TABLE IF NOT EXISTS intel_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        intel_id TEXT UNIQUE NOT NULL,
        date_received TEXT NOT NULL,
        time_received TEXT,
        source TEXT NOT NULL,
        source_ref TEXT,
        priority TEXT NOT NULL,
        subject_matter TEXT NOT NULL,
        firearms_related TEXT DEFAULT 'No',
        narcotics_related TEXT DEFAULT 'No',
        trafficking_related TEXT DEFAULT 'No',
        target_person TEXT,
        target_location TEXT,
        parish TEXT NOT NULL,
        substance_of_intel TEXT,
        triage_decision TEXT,
        triage_by TEXT,
        triage_date TEXT,
        linked_op_id TEXT,
        linked_case_id TEXT,
        outcome TEXT,
        outcome_notes TEXT,
        record_status TEXT DEFAULT 'Draft',
        submitted_by TEXT,
        submitted_date TEXT,
        created_by TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""")

    # --- OPERATIONS ---
    c.execute("""
    CREATE TABLE IF NOT EXISTS operations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        op_id TEXT UNIQUE NOT NULL,
        op_name TEXT NOT NULL,
        op_date TEXT NOT NULL,
        op_type TEXT NOT NULL,
        warrant_basis TEXT,
        warrant_number TEXT,
        issuing_jp TEXT,
        parish TEXT NOT NULL,
        target_location TEXT,
        target_person TEXT,
        team_lead TEXT NOT NULL,
        team_lead_rank TEXT,
        team_size INTEGER,
        joint_agency TEXT,
        linked_intel_id TEXT,
        start_time TEXT,
        end_time TEXT,
        duration_hrs REAL,
        firearms_seized INTEGER DEFAULT 0,
        narcotics_seized INTEGER DEFAULT 0,
        ammo_seized INTEGER DEFAULT 0,
        cash_seized REAL DEFAULT 0,
        arrests_made INTEGER DEFAULT 0,
        outcome TEXT,
        outcome_notes TEXT,
        risk_assessment TEXT,
        body_cam TEXT DEFAULT 'No',
        evidence_tagged TEXT DEFAULT 'No',
        record_status TEXT DEFAULT 'Draft',
        submitted_by TEXT,
        submitted_date TEXT,
        created_by TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""")

    # --- FIREARM SEIZURES ---
    c.execute("""
    CREATE TABLE IF NOT EXISTS firearm_seizures (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seizure_id TEXT UNIQUE NOT NULL,
        seizure_date TEXT NOT NULL,
        linked_op_id TEXT,
        linked_case_id TEXT,
        parish TEXT NOT NULL,
        location TEXT,
        firearm_type TEXT NOT NULL,
        make TEXT,
        model TEXT,
        serial_number TEXT,
        calibre TEXT,
        country_of_origin TEXT,
        ammo_count INTEGER DEFAULT 0,
        magazine_count INTEGER DEFAULT 0,
        ibis_status TEXT DEFAULT 'Not Submitted',
        etrace_status TEXT DEFAULT 'Not Submitted',
        exhibit_tag TEXT,
        storage_location TEXT,
        seized_by TEXT NOT NULL,
        witness_officer TEXT,
        record_status TEXT DEFAULT 'Draft',
        submitted_by TEXT,
        submitted_date TEXT,
        notes TEXT,
        created_by TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""")

    # --- NARCOTICS SEIZURES ---
    c.execute("""
    CREATE TABLE IF NOT EXISTS narcotics_seizures (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seizure_id TEXT UNIQUE NOT NULL,
        seizure_date TEXT NOT NULL,
        linked_op_id TEXT,
        linked_case_id TEXT,
        parish TEXT NOT NULL,
        location TEXT,
        drug_type TEXT NOT NULL,
        quantity REAL,
        unit TEXT,
        est_street_value REAL,
        packaging_method TEXT,
        concealment_method TEXT,
        field_test_result TEXT,
        lab_cert_status TEXT DEFAULT 'Not Yet Submitted to Lab',
        exhibit_tag TEXT,
        storage_location TEXT,
        seized_by TEXT NOT NULL,
        witness_officer TEXT,
        record_status TEXT DEFAULT 'Draft',
        submitted_by TEXT,
        submitted_date TEXT,
        notes TEXT,
        created_by TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""")

    # --- ARRESTS ---
    c.execute("""
    CREATE TABLE IF NOT EXISTS arrests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        arrest_id TEXT UNIQUE NOT NULL,
        arrest_date TEXT NOT NULL,
        arrest_time TEXT,
        linked_op_id TEXT,
        linked_case_id TEXT,
        suspect_name TEXT NOT NULL,
        suspect_dob TEXT,
        suspect_address TEXT,
        suspect_occupation TEXT,
        parish TEXT NOT NULL,
        arrest_location TEXT,
        arresting_officer TEXT NOT NULL,
        arresting_officer_rank TEXT,
        offence_1 TEXT NOT NULL,
        law_section_1 TEXT,
        offence_2 TEXT,
        law_section_2 TEXT,
        deadline_48hr TEXT,
        charge_date TEXT,
        charge_within_48hr TEXT,
        bail_status TEXT,
        court_type TEXT,
        first_court_date TEXT,
        remand_location TEXT,
        legal_representation TEXT,
        statements_taken TEXT DEFAULT 'No',
        witness_count INTEGER DEFAULT 0,
        record_status TEXT DEFAULT 'Draft',
        submitted_by TEXT,
        submitted_date TEXT,
        notes TEXT,
        created_by TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""")

    # --- CHAIN OF CUSTODY ---
    c.execute("""
    CREATE TABLE IF NOT EXISTS chain_of_custody (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exhibit_tag TEXT NOT NULL,
        exhibit_type TEXT NOT NULL,
        description TEXT,
        linked_case_id TEXT,
        linked_seizure_id TEXT,
        seized_date TEXT,
        seized_by TEXT,
        seized_location TEXT,
        current_custodian TEXT,
        storage_location TEXT,
        transfer_date TEXT,
        transfer_from TEXT,
        transfer_to TEXT,
        transfer_reason TEXT,
        condition TEXT,
        photos_taken TEXT DEFAULT 'No',
        seal_intact TEXT DEFAULT 'Yes',
        disposal_status TEXT DEFAULT 'Held - Active Case (court proceedings)',
        record_status TEXT DEFAULT 'Draft',
        submitted_by TEXT,
        submitted_date TEXT,
        notes TEXT,
        created_by TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""")

    # --- LAB TRACKING ---
    c.execute("""
    CREATE TABLE IF NOT EXISTS lab_tracking (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lab_ref TEXT UNIQUE NOT NULL,
        exhibit_tag TEXT NOT NULL,
        linked_case_id TEXT,
        submission_date TEXT NOT NULL,
        lab_type TEXT,
        exam_type TEXT,
        analyst TEXT,
        expected_date TEXT,
        completion_date TEXT,
        certificate_number TEXT,
        certificate_status TEXT DEFAULT 'Not Yet Submitted to Lab',
        result TEXT,
        collected_by TEXT,
        collection_date TEXT,
        ibis_status TEXT,
        etrace_status TEXT,
        record_status TEXT DEFAULT 'Draft',
        submitted_by TEXT,
        submitted_date TEXT,
        notes TEXT,
        created_by TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""")

    # --- DPP PIPELINE ---
    c.execute("""
    CREATE TABLE IF NOT EXISTS dpp_pipeline (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        linked_case_id TEXT NOT NULL,
        classification TEXT,
        oic_name TEXT,
        suspect_name TEXT,
        offence_summary TEXT,
        dpp_file_date TEXT,
        crown_counsel TEXT,
        dpp_status TEXT NOT NULL,
        evidential_sufficiency TEXT DEFAULT 'No',
        public_interest_met TEXT DEFAULT 'No',
        ruling_date TEXT,
        ruling_outcome TEXT,
        ruling_notes TEXT,
        voluntary_bill TEXT DEFAULT 'No',
        prelim_exam TEXT DEFAULT 'No',
        returned_for_investigation TEXT DEFAULT 'No',
        return_reason TEXT,
        resubmission_date TEXT,
        record_status TEXT DEFAULT 'Draft',
        submitted_by TEXT,
        submitted_date TEXT,
        notes TEXT,
        created_by TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""")

    # --- SOP CHECKLIST ---
    c.execute("""
    CREATE TABLE IF NOT EXISTS sop_checklists (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        linked_case_id TEXT NOT NULL,
        oic_name TEXT,
        checklist_date TEXT,
        station_diary_entry TEXT DEFAULT 'No',
        crime_report_filed TEXT DEFAULT 'No',
        offence_register_updated TEXT DEFAULT 'No',
        occurrence_book_entry TEXT DEFAULT 'No',
        scene_log_started TEXT DEFAULT 'No',
        suspect_cautioned TEXT DEFAULT 'No',
        rights_advised TEXT DEFAULT 'No',
        attorney_access TEXT DEFAULT 'No',
        detainee_book_entry TEXT DEFAULT 'No',
        property_book_entry TEXT DEFAULT 'No',
        lockup_time_recorded TEXT DEFAULT 'No',
        forty_eight_hr_compliance TEXT DEFAULT 'No',
        charge_sheet_prepared TEXT DEFAULT 'No',
        exhibit_register_updated TEXT DEFAULT 'No',
        exhibits_photographed TEXT DEFAULT 'No',
        exhibits_sealed_tagged TEXT DEFAULT 'No',
        chain_of_custody_started TEXT DEFAULT 'No',
        forensic_submissions_made TEXT DEFAULT 'No',
        ballistic_submission TEXT DEFAULT 'No',
        drug_field_test TEXT DEFAULT 'No',
        ibis_etrace_submitted TEXT DEFAULT 'No',
        victim_statement TEXT DEFAULT 'No',
        witness_statements TEXT DEFAULT 'No',
        suspect_statement_cautioned TEXT DEFAULT 'No',
        officer_statements TEXT DEFAULT 'No',
        expert_statements TEXT DEFAULT 'No',
        scene_photographed TEXT DEFAULT 'No',
        scene_sketch TEXT DEFAULT 'No',
        scene_video TEXT DEFAULT 'No',
        id_parade_required TEXT DEFAULT 'N/A',
        id_parade_conducted TEXT DEFAULT 'N/A',
        cctv_canvass TEXT DEFAULT 'No',
        neighbourhood_enquiry TEXT DEFAULT 'No',
        forensic_certs_received TEXT DEFAULT 'No',
        ballistic_cert_received TEXT DEFAULT 'No',
        post_mortem_received TEXT DEFAULT 'N/A',
        all_statements_compiled TEXT DEFAULT 'No',
        exhibit_list_complete TEXT DEFAULT 'No',
        case_summary_prepared TEXT DEFAULT 'No',
        evidential_sufficiency_met TEXT DEFAULT 'No',
        public_interest_assessed TEXT DEFAULT 'No',
        dpp_file_complete TEXT DEFAULT 'No',
        disclosure_schedule TEXT DEFAULT 'No',
        unused_material_listed TEXT DEFAULT 'No',
        disclosure_served TEXT DEFAULT 'No',
        pii_application TEXT DEFAULT 'N/A',
        supplementary_disclosure TEXT DEFAULT 'N/A',
        overall_compliance TEXT DEFAULT 'Under Review',
        compliance_notes TEXT,
        record_status TEXT DEFAULT 'Draft',
        submitted_by TEXT,
        submitted_date TEXT,
        created_by TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""")

    # --- WITNESS STATEMENTS ---
    c.execute("""
    CREATE TABLE IF NOT EXISTS witness_statements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        statement_id TEXT UNIQUE NOT NULL,
        linked_case_id TEXT NOT NULL,
        witness_name TEXT NOT NULL,
        witness_type TEXT,
        witness_address TEXT,
        witness_phone TEXT,
        relation_to_case TEXT,
        statement_date TEXT,
        statement_taken_by TEXT,
        statement_pages INTEGER,
        statement_signed TEXT DEFAULT 'No',
        witness_willing TEXT DEFAULT 'Yes',
        special_measures_needed TEXT DEFAULT 'No',
        special_measures_type TEXT,
        available_for_court TEXT DEFAULT 'Yes',
        record_status TEXT DEFAULT 'Draft',
        submitted_by TEXT,
        submitted_date TEXT,
        notes TEXT,
        created_by TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""")

    # --- DISCLOSURE LOG ---
    c.execute("""
    CREATE TABLE IF NOT EXISTS disclosure_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        disclosure_id TEXT UNIQUE NOT NULL,
        linked_case_id TEXT NOT NULL,
        disclosure_date TEXT,
        disclosure_type TEXT,
        material_disclosed TEXT,
        served_on_defence TEXT DEFAULT 'No',
        defence_solicitor TEXT,
        service_method TEXT,
        service_date TEXT,
        acknowledgement_received TEXT DEFAULT 'No',
        pii_application TEXT DEFAULT 'No',
        pii_outcome TEXT,
        supplementary_needed TEXT DEFAULT 'No',
        supplementary_date TEXT,
        disclosure_status TEXT DEFAULT 'Not Required Yet (pre-charge)',
        prepared_by TEXT,
        record_status TEXT DEFAULT 'Draft',
        submitted_by TEXT,
        submitted_date TEXT,
        notes TEXT,
        created_by TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""")

    # --- AUDIT LOG ---
    c.execute("""
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        table_name TEXT NOT NULL,
        record_id TEXT NOT NULL,
        action TEXT NOT NULL,
        officer_badge TEXT,
        officer_name TEXT,
        details TEXT,
        timestamp TEXT DEFAULT (datetime('now'))
    )""")

    conn.commit()

    # Insert default admin officer if none exist
    existing = c.execute("SELECT COUNT(*) FROM officers").fetchone()[0]
    if existing == 0:
        c.execute("""
            INSERT INTO officers (badge_number, full_name, rank, section, unit_access)
            VALUES (?, ?, ?, ?, ?)
        """, ("ADMIN", "System Administrator", "Superintendent of Police",
              "FNID Headquarters - Area 3", "all"))
        conn.commit()

    conn.close()


def log_audit(table_name, record_id, action, officer_badge=None,
              officer_name=None, details=None):
    """Log an action to the audit trail."""
    conn = get_db()
    conn.execute("""
        INSERT INTO audit_log (table_name, record_id, action,
                               officer_badge, officer_name, details)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (table_name, record_id, action, officer_badge, officer_name, details))
    conn.commit()
    conn.close()


def generate_id(prefix, table, id_column):
    """Generate the next sequential ID for a table."""
    conn = get_db()
    year = datetime.now().year
    pattern = f"{prefix}-{year}-%"
    row = conn.execute(
        f"SELECT {id_column} FROM {table} WHERE {id_column} LIKE ? ORDER BY id DESC LIMIT 1",
        (pattern,)).fetchone()
    conn.close()

    if row:
        try:
            num = int(str(row[0]).split("-")[-1]) + 1
        except (ValueError, IndexError):
            num = 1
    else:
        num = 1
    return f"{prefix}-{year}-{str(num).zfill(3)}"


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at: {DB_PATH}")
