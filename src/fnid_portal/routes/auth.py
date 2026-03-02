"""Authentication routes."""

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from ..constants import FNID_SECTIONS, JCF_RANKS
from ..models import get_db, log_audit

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        badge = request.form.get("badge_number", "").strip()
        name = request.form.get("full_name", "").strip()
        rank = request.form.get("rank", "").strip()
        section = request.form.get("section", "").strip()

        if not badge or not name or not rank:
            flash("Badge number, name, and rank are required.", "danger")
            return redirect(url_for("auth.login"))

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
        return redirect(url_for("main.home"))

    return render_template("login.html",
                           ranks=JCF_RANKS,
                           sections=FNID_SECTIONS)


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
