"""Tests for the FNID Morning Crime Report engine."""

from datetime import datetime, timedelta

import pytest

from fnid_portal.mcr_engine import (
    FNID_KEYWORDS,
    _get_mcr_window,
    _is_fnid_relevant,
    compile_mcr,
    generate_leads_report,
)


def test_get_mcr_window_default(app):
    """MCR window spans 24 hours ending at 05:30 on the target date."""
    with app.app_context():
        today = datetime.now().date()
        window_start, window_end = _get_mcr_window(today)

        assert window_end.hour == 5
        assert window_end.minute == 30
        assert window_end.date() == today
        assert window_start == window_end - timedelta(days=1)


def test_get_mcr_window_with_string_date(app):
    """MCR window accepts a date string in YYYY-MM-DD format."""
    with app.app_context():
        window_start, window_end = _get_mcr_window("2026-03-01")
        assert window_end.date() == datetime(2026, 3, 1).date()
        assert window_end.hour == 5
        assert window_end.minute == 30


def test_is_fnid_relevant_matches_firearm_keywords():
    """_is_fnid_relevant returns True for firearm-related text."""
    assert _is_fnid_relevant("Recovered a firearm from suspect") is True
    assert _is_fnid_relevant("Illegal gun possession") is True
    assert _is_fnid_relevant("Ammunition found in vehicle") is True
    assert _is_fnid_relevant("SHOOTING incident reported") is True


def test_is_fnid_relevant_matches_narcotics_keywords():
    """_is_fnid_relevant returns True for narcotics-related text."""
    assert _is_fnid_relevant("Cocaine seized at checkpoint") is True
    assert _is_fnid_relevant("Cannabis cultivation found") is True
    assert _is_fnid_relevant("Narcotics trafficking ring") is True
    assert _is_fnid_relevant("ganja found in vehicle") is True


def test_is_fnid_relevant_returns_false_for_unrelated():
    """_is_fnid_relevant returns False for non-FNID text."""
    assert _is_fnid_relevant("Traffic accident on Highway 2000") is False
    assert _is_fnid_relevant("Missing person report filed") is False
    assert _is_fnid_relevant("Domestic dispute resolved") is False
    assert _is_fnid_relevant("") is False
    assert _is_fnid_relevant(None) is False


def test_compile_mcr_collects_entries(app):
    """compile_mcr collects entries from source tables within the window."""
    with app.app_context():
        from fnid_portal.models import get_db

        # Calculate window for tomorrow so we can insert data inside it
        target = (datetime.now() + timedelta(days=1)).date()
        window_start, window_end = _get_mcr_window(target)

        # Insert a case within the window
        mid_window = (window_start + timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")
        conn = get_db()
        conn.execute("""
            INSERT INTO cases (
                case_id, registration_date, classification, oic_badge,
                oic_name, oic_rank, parish, offence_description,
                law_and_section, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("MCR/SD/A3/FNID/2026/0001", "2026-03-01",
              "Firearms - Possession", "T001", "Test Officer", "Inspector",
              "Manchester", "Illegal firearm seized during search warrant",
              "s.5 Firearms Act", "Test Officer", mid_window))
        conn.commit()
        conn.close()

        mcr_date, entries = compile_mcr(
            target_date=target.strftime("%Y-%m-%d"),
            compiled_by="Test Officer"
        )

        assert mcr_date == target.strftime("%Y-%m-%d")
        assert len(entries) >= 1
        # The firearm case should be flagged as FNID-relevant
        relevant = [e for e in entries if e["fnid_relevant"]]
        assert len(relevant) >= 1


def test_compile_mcr_idempotent(app):
    """Calling compile_mcr twice for the same date returns existing data."""
    with app.app_context():
        from fnid_portal.models import get_db

        target = (datetime.now() + timedelta(days=2)).date()
        window_start, window_end = _get_mcr_window(target)
        mid_window = (window_start + timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S")

        conn = get_db()
        conn.execute("""
            INSERT INTO cases (
                case_id, registration_date, classification, oic_badge,
                oic_name, oic_rank, parish, offence_description,
                law_and_section, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("MCR/SD/A3/FNID/2026/0002", "2026-03-02",
              "Narcotics - Trafficking (Import/Export)", "T001",
              "Test Officer", "Inspector", "St. Elizabeth",
              "Cocaine trafficking intercept",
              "s.8 DDA", "Test Officer", mid_window))
        conn.commit()
        conn.close()

        target_str = target.strftime("%Y-%m-%d")
        date1, entries1 = compile_mcr(target_date=target_str, compiled_by="A")
        date2, entries2 = compile_mcr(target_date=target_str, compiled_by="B")

        assert date1 == date2
        assert len(entries1) == len(entries2)


def test_generate_leads_report_structure(app):
    """generate_leads_report returns a dict with expected keys."""
    with app.app_context():
        from fnid_portal.models import get_db

        # Insert MCR entries directly
        conn = get_db()
        conn.execute("""
            INSERT INTO mcr_entries
            (mcr_date, window_start, window_end, source_table, source_id,
             classification, parish, summary, fnid_relevant, compiled_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("2026-04-01", "2026-03-31 05:30:00", "2026-04-01 05:30:00",
              "cases", "RPT/001", "Firearms - Possession", "Manchester",
              "Case RPT/001: Firearm recovered", 1, "Test"))
        conn.commit()
        conn.close()

        report = generate_leads_report("2026-04-01")

        assert "mcr_date" in report
        assert report["mcr_date"] == "2026-04-01"
        assert "total_entries" in report
        assert report["total_entries"] >= 1
        assert "follow_up_lines" in report
        assert "hotspot_trends" in report
        assert "briefing_topics" in report


def test_generate_leads_report_empty_date(app):
    """generate_leads_report for a date with no entries returns a message."""
    with app.app_context():
        report = generate_leads_report("1999-01-01")
        assert "message" in report
