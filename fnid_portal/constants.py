"""
FNID Controlled Input Definitions

Based on Jamaica Constabulary Force terminology, Firearms Act 2022,
Dangerous Drugs Act, POCA 2007, Bail Act 2023, Gun Court Act 1974,
and DPP protocols.
"""

# FNID Area 3 covers these parishes
FNID_PARISHES = ["Manchester", "St. Elizabeth", "Clarendon"]

# --- Ranks (JCF rank structure) ---
JCF_RANKS = [
    "Commissioner of Police",
    "Deputy Commissioner of Police",
    "Assistant Commissioner of Police",
    "Senior Superintendent of Police",
    "Superintendent of Police",
    "Deputy Superintendent of Police",
    "Assistant Superintendent of Police",
    "Inspector of Police",
    "Sergeant of Police",
    "Corporal of Police",
    "District Constable",
    "Constable",
    "Detective Superintendent",
    "Detective Inspector",
    "Detective Sergeant",
    "Detective Corporal",
    "Detective Constable",
]

# --- FNID Divisions/Sections ---
FNID_SECTIONS = [
    "FNID Headquarters - Area 3",
    "Intelligence Section",
    "Operations Section",
    "Firearms Investigation Section",
    "Narcotics Investigation Section",
    "Forensic Liaison Section",
    "Case Management & Registry",
    "Manchester Division",
    "St. Elizabeth Division",
    "Clarendon Division",
]

# --- Intelligence Sources (per JCF intelligence gathering protocols) ---
INTEL_SOURCES = [
    "Crime Stop (311)",
    "NIB (811)",
    "Registered Informant",
    "Unregistered Informant",
    "DEA (US Drug Enforcement Administration)",
    "ATF (US Bureau of Alcohol, Tobacco, Firearms)",
    "HSI (Homeland Security Investigations)",
    "MOCA (Major Organised Crime & Anti-Corruption Agency)",
    "JCA Detection (Jamaica Customs Agency)",
    "Divisional CIB (Criminal Investigation Branch)",
    "Patrol Intercept",
    "C-TOC (Counter-Terrorism and Organised Crime)",
    "SIB (Special Investigations Branch)",
    "INTERPOL",
    "Walk-In Report",
    "FNID Direct (923-6184)",
    "UK NCA (National Crime Agency)",
    "US Marshals Service",
    "CARICOM IMPACS",
    "Anonymous Tip",
    "Social Media Monitoring",
    "Station Diary Entry",
]

INTEL_PRIORITIES = ["Critical", "High", "Medium", "Low"]

TRIAGE_DECISIONS = [
    "Action - Mount Operation",
    "Action - Surveillance Only",
    "Action - Port Alert (JCA/Immigration)",
    "Action - Airport Alert",
    "Refer to Divisional CIB",
    "Refer to MOCA",
    "Refer to SIB (Special Investigations Branch)",
    "Refer to C-TOC",
    "Intel Filed - Active Monitoring",
    "Intel Filed - Passive Monitoring",
    "Closed - Insufficient Information",
    "Closed - Duplicate Report",
]

# --- Operation Types ---
OPERATION_TYPES = [
    "Search Warrant Execution (s.91 Firearms Act)",
    "Search Warrant Execution (s.21 DDA)",
    "Search Warrant Execution (s.14 POCA)",
    "Snap Raid (Exigent Circumstances)",
    "Port/Cargo Interdiction",
    "Airport Interdiction",
    "Vehicle Interception / Stop & Search",
    "Coastal/Maritime Operation",
    "Checkpoint (Authorised)",
    "ZOSO Checkpoint (s.5 ZOSO Act)",
    "Surveillance Operation",
    "Controlled Delivery",
    "Joint Operation - JCA",
    "Joint Operation - JDF (Jamaica Defence Force)",
    "Joint Operation - MOCA",
    "Joint Operation - DEA",
    "Joint Operation - ATF",
    "Fugitive Apprehension",
    "Follow-Up / Secondary Operation",
    "SOE Operation (State of Emergency)",
    "Courier/Parcel Investigation",
    "Undercover Operation",
]

WARRANT_BASIS = [
    "Section 91 - Firearms (Prohibition, Restriction & Regulation) Act, 2022",
    "Section 21 - Dangerous Drugs Act",
    "Section 14 - Proceeds of Crime Act (POCA), 2007",
    "ZOSO - Warrantless Search (s.5 ZOSO Act)",
    "SOE - Warrantless Search (Emergency Powers)",
    "Sergeant Written Directive (DDA s.21(2))",
    "Justice of the Peace Warrant",
    "Supreme Court Order",
    "Consent Search",
    "Plain View Doctrine / Exigent Circumstances",
]

OPERATION_OUTCOMES = [
    "Successful - Seizure and Arrest",
    "Successful - Seizure Only (no suspect present)",
    "Successful - Arrest Only",
    "Partial Success - Intelligence Developed",
    "Negative - No Finds",
    "Aborted - Operation Compromised",
    "Aborted - Safety Concern / Threat to Life",
    "Ongoing - Surveillance Continuing",
    "Ongoing - Controlled Delivery in Progress",
]

# --- Firearm Classifications (per Firearms Act 2022) ---
FIREARM_TYPES = [
    "Pistol - Semi-Automatic",
    "Pistol - Revolver",
    "Rifle - Semi-Automatic",
    "Rifle - Bolt Action",
    "Rifle - Assault / Select Fire",
    "Shotgun - Pump Action",
    "Shotgun - Semi-Automatic",
    "Shotgun - Break Action",
    "Submachine Gun",
    "Machine Pistol",
    "Improvised / Homemade (Slam Gun)",
    "3D-Printed Firearm",
    "Imitation / Replica Firearm",
    "Component - Frame / Receiver",
    "Component - Barrel",
    "Component - Slide",
    "Component - Trigger Assembly",
    "Magazine (detachable)",
    "Silencer / Suppressor",
    "Ammunition Only",
]

FIREARM_CALIBRES = [
    "9mm Luger/Parabellum", ".40 S&W", ".45 ACP", ".380 ACP (9mm Short)",
    ".22 LR", ".25 ACP", ".32 ACP", ".38 Special", ".357 Magnum",
    ".44 Magnum", "5.56x45mm NATO / .223 Remington",
    "7.62x39mm (AK pattern)", "7.62x51mm NATO / .308 Winchester",
    "12 Gauge", "20 Gauge", ".410 Bore", "Other / Unknown",
]

# --- Narcotics Classifications (per DDA schedules) ---
DRUG_TYPES = [
    "Cannabis / Ganja - Compressed (brick)",
    "Cannabis / Ganja - Loose (cured)",
    "Cannabis / Ganja - Oil / Concentrate",
    "Cannabis / Ganja - Edibles",
    "Cocaine Hydrochloride (powder)",
    "Cocaine - Crack / Freebase",
    "Heroin (diamorphine)",
    "MDMA / Ecstasy (tablets/crystals)",
    "Methamphetamine",
    "Synthetic Cannabinoids (K2/Spice)",
    "Fentanyl / Synthetic Opioids",
    "Prescription Opioids (unauthorised)",
    "Psilocybin (mushrooms)",
    "Other Controlled Substance",
]

DRUG_UNITS = ["kg", "g", "lbs", "oz", "plants", "tablets", "capsules", "ml", "litres"]

# --- Offences (Firearms Act 2022 - key sections) ---
FIREARMS_ACT_OFFENCES = [
    "s.5 - Possession of Prohibited Weapon (mandatory 15yr; max 25yr)",
    "s.6 - Stockpiling (3+ firearms or 50+ rounds; 15yr min)",
    "s.7 - Trafficking in Prohibited Weapon (20yr min; life max)",
    "s.8 - Possession with Intent to Traffic",
    "s.9 - Manufacture of Prohibited Weapon (20yr min)",
    "s.10 - Dealing in Prohibited Weapon",
    "s.11 - Importing / Exporting Prohibited Weapon",
    "s.12 - Diversion of Lawful Firearm",
    "s.22 - Possession of Prohibited Ammunition",
    "s.29 - Possession of Unmarked Firearm",
    "s.30 - Obliterating Serial Number / Markings",
    "s.42 - Use of Firearm in Commission of Offence",
    "s.43 - Shooting with Intent (wounding / grievous bodily harm)",
    "s.48 - Conspiracy to Commit Firearms Offence",
    "Illegal Possession of Firearm (general)",
    "Illegal Possession of Ammunition (general)",
]

# --- Offences (Dangerous Drugs Act - key sections) ---
DDA_OFFENCES = [
    "s.7C - Import/Export Cannabis (DDA Part IIIA; 5yr-life)",
    "s.7D - Dealing/Trafficking Cannabis",
    "s.7E - Possession of Cannabis (>2oz = deemed dealing)",
    "s.7F - Cultivation of Cannabis (>5 plants = trafficking)",
    "s.8 - Import/Export Cocaine/Heroin (DDA Part IV; 10yr-life)",
    "s.8 - Dealing/Trafficking Cocaine/Heroin",
    "s.8 - Possession of Cocaine (any quantity)",
    "s.8 - Possession of Heroin (>1/10 oz = deemed dealing)",
    "s.21 - Search & Seizure under DDA",
    "Deemed Dealing - Possession near School Premises",
    "Conspiracy to Import/Export Controlled Drug",
    "Money Laundering (drug proceeds)",
]

# --- Offences (Other relevant statutes) ---
OTHER_OFFENCES = [
    "Murder (committed with firearm)",
    "Attempted Murder (firearm)",
    "Wounding with Intent (s.20 Offences Against the Person Act)",
    "Robbery with Aggravation (firearm)",
    "POCA - Dealing in Property of Criminal Origin (s.4)",
    "POCA - Money Laundering (s.5)",
    "POCA - Failure to Report Suspicious Transaction (s.6)",
    "Conspiracy (general)",
    "Accessory Before/After the Fact",
    "Harbouring an Offender",
]

ALL_OFFENCES = FIREARMS_ACT_OFFENCES + DDA_OFFENCES + OTHER_OFFENCES

# --- Seizure Locations ---
SEIZURE_LOCATIONS = [
    "Port Bustamante (Kingston)",
    "Kingston Logistics Centre",
    "Newport West Container Terminal",
    "Norman Manley International Airport",
    "Sangster International Airport",
    "Ian Fleming International Airport",
    "Roadway / Vehicle (Highway)",
    "Residential Premises",
    "Commercial Premises",
    "Beach / Coastal Landing Point",
    "Open Land / Bushes",
    "Wharf / Fishing Village",
    "Courier / Postal Facility",
    "ZOSO Checkpoint",
    "Police Station (surrendered)",
    "Other Location",
]

# --- Arrest & Detention ---
BAIL_STATUS = [
    "Bail Granted (conditions set)",
    "Bail Denied (opposed by Crown)",
    "Remanded in Custody (lockup)",
    "Remanded in Custody (correctional centre)",
    "Released - No Charge (insufficient evidence)",
    "Released - Station Bail",
    "Stop Order Issued (s.5 Bail Act 2023)",
    "Electronic Monitoring (s.8 Bail Act 2023)",
    "Bail Revoked",
]

COURT_TYPES = [
    "Gun Court - High Court Division (judge alone, in camera)",
    "Gun Court - Circuit Court Division (jury, murder/treason)",
    "Gun Court - Resident Magistrate Division (preliminary enquiry)",
    "Parish Court (summary drug offence)",
    "Circuit Court (indictable drug offence)",
    "Supreme Court",
    "Court of Appeal",
    "Privy Council",
]

REMAND_LOCATIONS = [
    "Tower Street Adult Correctional Centre",
    "St. Catherine Adult Correctional Centre",
    "Horizon Adult Remand Centre",
    "Mandeville Police Lock-Up",
    "Santa Cruz Police Lock-Up",
    "May Pen Police Lock-Up",
    "Christiana Police Lock-Up",
    "Black River Police Lock-Up",
    "Other Police Lock-Up",
]

# --- DPP File & Case Management ---
DPP_FILE_STATUS = [
    "File Being Prepared by OIC",
    "File Under Review by Unit Commander",
    "File Submitted to DPP",
    "Awaiting Forensic Certificate (Chemistry - IFSLM)",
    "Awaiting Ballistic Certificate (IFSLM)",
    "Awaiting Post Mortem Report (FMO)",
    "Crown Counsel Assigned",
    "Crown Counsel Reviewing",
    "Additional Investigation Requested",
    "Ruling - Charge Approved",
    "Ruling - No Charge (Insufficient Evidence)",
    "Ruling - No Charge (Public Interest)",
    "Voluntary Bill of Indictment Filed",
    "Preliminary Enquiry Ordered",
    "Returned for Further Investigation",
    "Nolle Prosequi Entered",
]

# --- Case Status per JCF Case Management Policy Section 6.3 ---
# (JCF/FW/PL/C&S/0001/2024)
CASE_STATUS = [
    # 6.3.1 Case Open — actively under investigation
    "Case Open - Active Investigation",
    "Case Open - Pending Forensic Results",
    "Case Open - Pending Witness Statements",
    "Case Open - Pending ID Parade",
    "Case Open - Surveillance Phase",
    "Case Open - Pending DPP File Submission",
    "Referred to DPP - Awaiting Ruling",
    "Before Court - Preliminary Enquiry",
    "Before Court - Committal Proceedings",
    "Before Court - Trial Pending",
    "Before Court - Trial in Progress",
    # 6.3.2 Case Suspended — all investigative leads exhausted
    "Case Suspended - Leads Exhausted",
    # 6.3.3 Case Cleared (per policy Section 6.3.3 a-i)
    "Case Cleared - Charge(s) Laid",
    "Case Cleared - Suspect Dead",
    "Case Cleared - Warrant Issued (Life Sentence Abroad)",
    "Case Cleared - Extradition Denied",
    "Case Cleared - Victim Will Not Prosecute",
    "Case Cleared - Submitted to Coroners Court",
    "Case Cleared - Child Diversion",
    "Case Cleared - Suspect Summoned",
    "Case Cleared - Report Contrived",
    # 6.3.4 Case Closed (per policy Section 6.3.4 a-i)
    "Case Closed - Charge(s) Preferred, No Other Suspect",
    "Case Closed - Suspect Dead, No Other Suspect",
    "Case Closed - Life Sentence Abroad (No Parole/Deported)",
    "Case Closed - Extradition Denied",
    "Case Closed - Victim Will Not Prosecute",
    "Case Closed - Coroners Court (No Criminal Liability)",
    "Case Closed - Child Diversion Completed",
    "Case Closed - Report Contrived",
    "Case Closed - ACP CIB Direction",
    "Case Closed - Convicted (Sentence Imposed)",
    "Case Closed - Acquitted (Not Guilty)",
    "Case Closed - No Charge (DPP Ruling)",
    "Case Closed - Withdrawn by Prosecution",
    "Case Closed - Dismissed by Court",
    # 6.3.5 Cold Case — suspended for 3+ years
    "Cold Case - Under Periodic Review",
    "Cold Case - Dormant",
    # Other
    "Case Reopened",
    "Merged - See Linked Case",
]

CASE_CLASSIFICATIONS = [
    "Firearms - Possession",
    "Firearms - Trafficking",
    "Firearms - Stockpiling",
    "Firearms - Manufacturing",
    "Narcotics - Possession with Intent",
    "Narcotics - Trafficking (Import/Export)",
    "Narcotics - Cultivation",
    "Narcotics - Distribution/Dealing",
    "Firearms + Narcotics (Combined)",
    "Trafficking - Multi-Commodity",
    "POCA / Financial Investigation",
    "Murder with Firearm",
    "Attempted Murder with Firearm",
    "Shooting with Intent",
    "Robbery with Aggravation (firearm)",
    "Gang / Organised Crime Network",
]

# --- Forensic / Evidence ---
EXHIBIT_TYPES = [
    "Firearm (complete weapon)",
    "Firearm Component (frame/receiver/barrel/slide)",
    "Ammunition (live rounds)",
    "Magazine (detachable)",
    "Drug Sample (for lab analysis)",
    "Drug Bulk (for weighing/destruction)",
    "Cash / Currency (JMD)",
    "Cash / Currency (USD/other foreign)",
    "Electronic Device (phone/laptop/tablet)",
    "SIM Card / Memory Card",
    "Vehicle (motor car/truck/boat)",
    "Document (passport/licence/papers)",
    "Clothing / Personal Item",
    "Biological Sample (DNA/blood)",
    "CCTV / Video Footage",
    "Photographs",
    "Other Physical Evidence",
]

IBIS_STATUS = [
    "Not Submitted",
    "Submitted to IFSLM - Pending Entry",
    "Entered - No Match",
    "Hit - Confirmed Match (linked to other case)",
    "Hit - Unconfirmed (further analysis needed)",
    "Serial Obliterated (cannot enter)",
    "N/A (not a firearm)",
]

ETRACE_STATUS = [
    "Not Submitted",
    "Submitted to ATF - Pending",
    "Traced - US Origin (state/dealer identified)",
    "Traced - Non-US Origin (country identified)",
    "Untraceable - No Serial Number",
    "Untraceable - Serial Obliterated",
    "Trace Complete - Report Filed",
    "N/A (not a firearm)",
]

FORENSIC_CERT_STATUS = [
    "Not Yet Submitted to Lab",
    "Submitted to IFSLM (Institute of Forensic Science & Legal Medicine)",
    "Analysis In Progress",
    "Certificate Issued - Collected",
    "Certificate Issued - Not Yet Collected",
    "Certificate Overdue (>8 weeks)",
    "Inconclusive Result",
    "Re-examination Requested",
    "N/A",
]

EXHIBIT_DISPOSAL = [
    "Held - Active Case (court proceedings)",
    "Held - Court Order (preservation order)",
    "Destroyed - Commissioner's Order (s.97 Firearms Act)",
    "Destroyed - Court Order",
    "Returned to Lawful Owner",
    "Forfeited to Crown (POCA order)",
    "Transferred to JDF/Military",
    "Pending Disposal Authorization",
]

# --- SOP Compliance Checklist Items ---
SOP_CHECKLIST_CATEGORIES = {
    "Initial Response & Recording": [
        ("station_diary_entry", "Station Diary Entry Made"),
        ("crime_report_filed", "Crime Report Form Filed (CRF)"),
        ("offence_register_updated", "Offence Register Updated"),
        ("occurrence_book_entry", "Occurrence Book Entry"),
        ("scene_log_started", "Scene Log / Cordon Log Started"),
    ],
    "Suspect Processing (Constabulary Force Act s.15)": [
        ("suspect_cautioned", "Suspect Cautioned (Judges' Rules)"),
        ("rights_advised", "Constitutional Rights Advised (Ch. III)"),
        ("attorney_access", "Access to Attorney Facilitated"),
        ("detainee_book_entry", "Detainee Book Entry"),
        ("property_book_entry", "Charge & Prisoners' Property Book Entry"),
        ("lockup_time_recorded", "Lock-Up Time Recorded"),
        ("48hr_compliance", "48-Hour Rule Compliance (s.15 CFA)"),
        ("charge_sheet_prepared", "Charge Sheet Prepared"),
    ],
    "Evidence & Exhibit Management": [
        ("exhibit_register_updated", "Exhibit Register Updated"),
        ("exhibits_photographed", "Exhibits Photographed (in situ)"),
        ("exhibits_sealed_tagged", "Exhibits Sealed and Tagged"),
        ("chain_of_custody_started", "Chain of Custody Form Started"),
        ("forensic_submissions_made", "Forensic Lab Submissions Made (IFSLM)"),
        ("ballistic_submission", "Ballistic Submission (if firearm)"),
        ("drug_field_test", "Drug Field Test Conducted (if narcotics)"),
        ("ibis_etrace_submitted", "IBIS/eTrace Submission (if firearm)"),
    ],
    "Statements & Witnesses": [
        ("victim_statement", "Victim Statement Taken"),
        ("witness_statements", "Witness Statements Taken"),
        ("suspect_statement_cautioned", "Suspect Statement (under caution)"),
        ("officer_statements", "Investigating Officer Statements"),
        ("expert_statements", "Expert / Forensic Analyst Statement"),
    ],
    "Scene & Investigation": [
        ("scene_photographed", "Crime Scene Photographed"),
        ("scene_sketch", "Scene Sketch / Diagram Drawn"),
        ("scene_video", "Video Recording of Scene"),
        ("id_parade_required", "ID Parade Required (Y/N assessed)"),
        ("id_parade_conducted", "ID Parade Conducted (if required)"),
        ("cctv_canvass", "CCTV Canvass Conducted"),
        ("neighbourhood_enquiry", "Neighbourhood Enquiry Conducted"),
    ],
    "DPP File Readiness (per Prosecution Protocol 2012)": [
        ("forensic_certs_received", "Forensic Certificate(s) Received"),
        ("ballistic_cert_received", "Ballistic Certificate Received"),
        ("post_mortem_received", "Post Mortem Report Received (if applicable)"),
        ("all_statements_compiled", "All Statements Compiled"),
        ("exhibit_list_complete", "Exhibit List Complete"),
        ("case_summary_prepared", "Case Summary Prepared for DPP"),
        ("evidential_sufficiency_met", "Evidential Sufficiency Test Met"),
        ("public_interest_assessed", "Public Interest Test Assessed"),
        ("dpp_file_complete", "DPP File Package Complete"),
    ],
    "Disclosure (per Disclosure Protocol 2013)": [
        ("disclosure_schedule", "Disclosure Schedule Prepared"),
        ("unused_material_listed", "Unused Material Listed"),
        ("disclosure_served", "Primary Disclosure Served on Defence"),
        ("pii_application", "PII Application Made (if applicable)"),
        ("supplementary_disclosure", "Supplementary Disclosure Provided"),
    ],
}

# --- POCA (Proceeds of Crime Act 2007) ---
POCA_STATUS = [
    "Not Applicable",
    "Referred to Financial Investigations Division (FID)",
    "Restraint Order Applied For",
    "Restraint Order Granted",
    "Civil Recovery Action Filed",
    "Forfeiture Order - Post Conviction",
    "Consent Order Obtained",
    "Dismissed / Lifted",
    "Ongoing Financial Investigation",
]

DISCLOSURE_STATUS = [
    "Not Required Yet (pre-charge)",
    "Disclosure Schedule Being Prepared",
    "Primary Disclosure Package Prepared",
    "Primary Disclosure Served on Defence",
    "Partial Disclosure (PII application pending)",
    "Supplementary Disclosure Pending",
    "All Disclosure Complete",
]

FILE_COMPLETENESS = [
    "Complete (all documents present)",
    "Substantially Complete (>80% - minor items outstanding)",
    "Incomplete - Missing Forensic Certificates",
    "Incomplete - Missing Ballistic Certificate",
    "Incomplete - Missing Witness Statements",
    "Incomplete - Missing Exhibit Register",
    "Incomplete - Missing Officer Statements",
    "Incomplete - Multiple Documents Outstanding",
    "Not Started",
]

SOP_COMPLIANCE_OVERALL = [
    "Fully Compliant",
    "Substantially Compliant (minor deficiencies)",
    "Non-Compliant - Missing Statements",
    "Non-Compliant - Missing Forensic Certificates",
    "Non-Compliant - Missing Exhibit Documentation",
    "Non-Compliant - 48-Hour Rule Breach",
    "Non-Compliant - Overdue DPP Submission",
    "Non-Compliant - Multiple Deficiencies",
    "Under Review",
]

# --- Parishes (all Jamaica, FNID Area 3 first) ---
ALL_PARISHES = [
    "Manchester", "St. Elizabeth", "Clarendon",
    "Kingston", "St. Andrew", "St. Thomas", "Portland",
    "St. Mary", "St. Ann", "Trelawny", "St. James",
    "Hanover", "Westmoreland", "St. Catherine",
]

YES_NO = ["Yes", "No"]
YES_NO_NA = ["Yes", "No", "N/A"]
RECORD_STATUS = ["Draft", "Submitted", "Edited", "Approved", "Rejected"]

# --- JCF Case Management Policy Abbreviations & Acronyms ---
# Per JCF/FW/PL/C&S/0001/2024 Section 5.0
JCF_ABBREVIATIONS = {
    "ACO": "Area Crime Officer",
    "ACP": "Assistant Commissioner of Police",
    "CIB": "Criminal Investigation Branch",
    "CMS": "Case Management System",
    "CR": "Case Reference",
    "C-TOC": "Counter Terrorism and Organized Crime Investigation Branch",
    "DCR": "Division Case Registry",
    "DCRR": "Divisional Case Report Register",
    "DDI": "Divisional Detective Inspector",
    "DI": "Detective Inspector",
    "DIM": "Division Intelligence Manager",
    "DIU": "Division Intelligence Unit",
    "DPP": "Director of Public Prosecutions",
    "IB": "Intelligence Branch",
    "IO": "Investigating Officer",
    "LO": "Legal Officer",
    "MCR": "Morning Crime Report",
    "MID": "Major Investigation Division",
    "ODPP": "Office of the Director of Public Prosecutions",
    "PLO": "Prosecution Liaison Officer",
    "SIO": "Senior Investigation Officer",
    "SOP": "Standard Operating Procedures",
    "SRMS": "Station Records Management System",
    "CISOCA": "Centre for Investigation of Sexual Offences and Child Abuse",
    "IFSLM": "Institute of Forensic Science and Legal Medicine",
    "INDECOM": "Independent Commission of Investigations",
    "FID": "Financial Investigations Division",
    "PSTEB": "Public Safety and Traffic Enforcement Branch",
    "SIMU": "Statistics and Information Management Unit",
    "CRO": "Criminal Records Office",
}

# --- Case Reference (CR) Forms per JCF Case Management Policy Section 11.0 ---
# NB: All related forms must be referred to as Case Reference Form (not Crime Reference Form)
CR_FORM_TYPES = {
    "CR1": "Investigator's Worksheet",
    "CR2": "Action Sheet",
    "CR3": "Witness Bio-Data Form",
    "CR4": "Stolen Property Form",
    "CR5": "Exhibit Chain of Custody Schedule",
    "CR6": "Investigator Index Card",
    "CR7": "Morning Crime Report",
    "CR8": "Question & Answer (Suspect/Witness Interview) Form",
    "CR9": "Question & Answer (Accused Written Interview) Form",
    "CR10": "Customer Reference Form",
    "CR11": "Confession Statement of Suspect/Accused",
    "CR12": "Major and Minor Case Report Form",
    "CR13": "Court Case File Checklist",
    "CR14": "JCF Profile Form",
    "CR15": "Application for Remand of Accused or Bail Conditions",
    "CFSR": "Case File Submission Register for Court",
}

# --- Case Lifecycle Stages per Policy ---
CASE_LIFECYCLE_STAGES = [
    "intake",
    "appreciation",       # Section 9.1 - Appreciating Customer's Report
    "vetting",            # Section 9.2.1 - Preliminary Vetting
    "assignment",         # Section 9.2.2 - Assignment of Cases
    "investigation",      # Section 9.3 - Management of Cases
    "follow_up",          # Section 9.3.1 - Ongoing vetting and follow-up
    "review",             # Section 9.3.3 - Case Reviews and Conferences
    "court_preparation",  # Section 9.3.6 - Submission of Cases
    "before_court",       # Before court proceedings
    "suspended",          # Section 9.3.9 - Case Suspended
    "reopened",           # Case reopened with new leads
    "cold_case",          # Section 9.3.10 - Cold Case (suspended 3+ years)
    "cleared",            # Section 6.3.3 - Case Cleared
    "closed",             # Section 6.3.4 - Case Closed
]

# --- Crime Types per Policy ---
CRIME_TYPE_INVESTIGATORS = {
    "major_non_uniformed": "Major crimes to be investigated by non-uniformed personnel",
    "major_uniformed": "Major crimes to be investigated by uniformed personnel",
    "minor_uniformed": "Minor crimes investigated by uniformed personnel",
}

# --- Case Review Timeline per Policy Section 9.3.3 ---
REVIEW_TIMELINES = {
    "homicide_preliminary": "24 hours",
    "homicide_first_review": "72 hours",
    "major_crime_first_review": "7 days",
    "minor_crime_first_review": "7 days",
    "follow_up_review": "14 days after first review",
    "subsequent_reviews": "Every 28 days",
    "suspended_case_review": "Every 90 days",
}

# --- Vetting Submission Timelines per Policy Section 9.1.12 ---
VETTING_TIMELINES = {
    "non_uniformed_to_dcr": "72 hours",
    "uniformed_to_station_mgr": "48 hours",
    "station_mgr_to_dcr": "48 hours (major crimes)",
    "documents_to_dcr": "48 hours upon receipt",
    "court_file_receipt": "48 hours prior to court deadline",
}

# --- Unit Portal Definitions ---
UNIT_PORTALS = {
    "intel": {
        "name": "Intelligence Unit",
        "icon": "bi-eye",
        "color": "#BF8F00",
        "description": "Intelligence gathering, triage, and dissemination",
    },
    "operations": {
        "name": "Operations Unit",
        "icon": "bi-bullseye",
        "color": "#C00000",
        "description": "Operation planning, execution, and outcome tracking",
    },
    "seizures": {
        "name": "Seizures Unit",
        "icon": "bi-shield-lock",
        "color": "#00B0F0",
        "description": "Firearms, narcotics, and other seizure documentation",
    },
    "arrests": {
        "name": "Arrests & Court Unit",
        "icon": "bi-person-badge",
        "color": "#7030A0",
        "description": "Arrest processing, bail, and court tracking",
    },
    "forensics": {
        "name": "Forensics & Evidence Unit",
        "icon": "bi-fingerprint",
        "color": "#538135",
        "description": "Chain of custody, lab submissions, and exhibit management",
    },
    "registry": {
        "name": "Case Registry & SOP Compliance",
        "icon": "bi-journal-check",
        "color": "#8B4513",
        "description": "Case file management, DPP pipeline, SOP compliance, disclosure",
    },
}
