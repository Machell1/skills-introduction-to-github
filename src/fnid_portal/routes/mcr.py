"""
Morning Crime Report (MCR) Routes

Views for MCR compilation, review, briefing, and leads reports.
"""

from datetime import datetime

from flask import Blueprint, Response, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..mcr_engine import compile_mcr, generate_leads_report
from ..models import get_db, log_audit
from ..pdf_export import pdf_base_css, pdf_header_html, render_pdf
from ..rbac import permission_required

bp = Blueprint("mcr", __name__, url_prefix="/mcr")


@bp.route("/")
@login_required
@permission_required("mcr", "read")
def mcr_dashboard():
    """MCR dashboard — latest report and history."""
    conn = get_db()
    try:
        # Get distinct MCR dates
        dates = conn.execute("""
            SELECT DISTINCT mcr_date, COUNT(*) as total,
                   SUM(fnid_relevant) as fnid_count,
                   compiled_by
            FROM mcr_entries
            GROUP BY mcr_date
            ORDER BY mcr_date DESC
            LIMIT 30
        """).fetchall()

        # Get today's entries if available
        today = datetime.now().strftime("%Y-%m-%d")
        today_entries = conn.execute("""
            SELECT * FROM mcr_entries WHERE mcr_date = ?
            ORDER BY fnid_relevant DESC, id
        """, (today,)).fetchall()

        return render_template("mcr/dashboard.html",
                             dates=dates, today_entries=today_entries,
                             today=today)
    finally:
        conn.close()


@bp.route("/compile", methods=["POST"])
@login_required
@permission_required("mcr", "compile")
def compile():
    """Manually trigger MCR compilation."""
    target_date = request.form.get("target_date")
    name = current_user.full_name

    try:
        mcr_date, entries = compile_mcr(target_date=target_date, compiled_by=name)
        log_audit("mcr_entries", mcr_date, "COMPILE",
                 current_user.badge_number, name,
                 f"Compiled {len(entries)} entries")
        flash(f"MCR compiled for {mcr_date}: {len(entries)} entries.", "success")
    except Exception as e:
        flash(f"Error compiling MCR: {e}", "danger")

    return redirect(url_for("mcr.mcr_dashboard"))


@bp.route("/<date>")
@login_required
@permission_required("mcr", "read")
def view_mcr(date):
    """View MCR for a specific date."""
    conn = get_db()
    try:
        entries = conn.execute("""
            SELECT * FROM mcr_entries WHERE mcr_date = ?
            ORDER BY fnid_relevant DESC, classification, id
        """, (date,)).fetchall()

        fnid_entries = [e for e in entries if e["fnid_relevant"]]
        general_entries = [e for e in entries if not e["fnid_relevant"]]

        return render_template("mcr/report.html",
                             mcr_date=date, entries=entries,
                             fnid_entries=fnid_entries,
                             general_entries=general_entries)
    finally:
        conn.close()


@bp.route("/<date>/briefing")
@login_required
@permission_required("mcr", "read")
def briefing(date):
    """Operational briefing view from MCR data."""
    conn = get_db()
    try:
        entries = conn.execute("""
            SELECT * FROM mcr_entries WHERE mcr_date = ? AND fnid_relevant = 1
            ORDER BY classification, id
        """, (date,)).fetchall()

        # Group by parish
        parish_groups = {}
        for e in entries:
            p = e["parish"] or "Unknown"
            parish_groups.setdefault(p, []).append(e)

        # Group by classification
        class_groups = {}
        for e in entries:
            c = e["classification"] or "Unknown"
            class_groups.setdefault(c, []).append(e)

        return render_template("mcr/briefing.html",
                             mcr_date=date, entries=entries,
                             parish_groups=parish_groups,
                             class_groups=class_groups)
    finally:
        conn.close()


@bp.route("/<date>/leads")
@login_required
@permission_required("mcr", "read")
def leads(date):
    """Leads report from MCR data."""
    report = generate_leads_report(date)
    return render_template("mcr/leads.html", mcr_date=date, report=report)


@bp.route("/<date>/pdf")
@login_required
@permission_required("mcr", "read")
def mcr_pdf(date):
    """Export MCR as PDF."""
    conn = get_db()
    try:
        entries = conn.execute("""
            SELECT * FROM mcr_entries WHERE mcr_date = ?
            ORDER BY fnid_relevant DESC, id
        """, (date,)).fetchall()

        html = f"""<!DOCTYPE html><html><head>{pdf_base_css()}</head><body>
        {pdf_header_html(f'Morning Crime Report — {date}')}
        <p><strong>FNID-Relevant Matters: {sum(1 for e in entries if e['fnid_relevant'])}</strong>
         | Total Matters: {len(entries)}</p>
        <table>
            <thead>
                <tr><th>Source</th><th>Classification</th><th>Parish</th><th>Summary</th><th>FNID</th></tr>
            </thead>
            <tbody>
        """
        for e in entries:
            fnid = "YES" if e["fnid_relevant"] else ""
            html += f"""<tr>
                <td>{e['source_table']}</td>
                <td>{e['classification'] or ''}</td>
                <td>{e['parish'] or ''}</td>
                <td>{e['summary'] or ''}</td>
                <td style="font-weight:bold; color:{'red' if e['fnid_relevant'] else '#999'}">{fnid}</td>
            </tr>"""

        html += """</tbody></table>
        <div class="footer">RESTRICTED — Morning Crime Report — FNID Area 3</div>
        </body></html>"""

        pdf_buffer = render_pdf(html)
        if pdf_buffer:
            log_audit("mcr_entries", date, "EXPORT_PDF",
                     current_user.badge_number, current_user.full_name)
            return Response(
                pdf_buffer.read(),
                mimetype="application/pdf",
                headers={"Content-Disposition": f"attachment; filename=MCR_{date}.pdf"}
            )
        else:
            flash("PDF generation unavailable.", "warning")
            return redirect(url_for("mcr.view_mcr", date=date))
    finally:
        conn.close()
