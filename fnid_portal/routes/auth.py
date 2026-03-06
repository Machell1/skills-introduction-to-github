"""Authentication routes — password-based with Flask-Login."""

from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..auth import User, set_password
from ..constants import FNID_SECTIONS, JCF_RANKS
from ..models import get_db, get_setting, log_audit
from ..rbac import ROLES

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    if request.method == "POST":
        badge = request.form.get("badge_number", "").strip()
        password = request.form.get("password", "").strip()
        name = request.form.get("full_name", "").strip()
        rank = request.form.get("rank", "").strip()
        section = request.form.get("section", "").strip()

        if not badge:
            flash("Badge number is required.", "danger")
            return redirect(url_for("auth.login"))

        conn = get_db()
        try:
            row = conn.execute(
                "SELECT * FROM officers WHERE badge_number = ?", (badge,)
            ).fetchone()

            allow_legacy = get_setting("allow_legacy_login", "true") == "true"

            if row:
                user = User.from_row(row)

                # Check if account is active
                if not user.is_active:
                    flash("Account is deactivated. Contact your administrator.", "danger")
                    return redirect(url_for("auth.login"))

                # Password-based auth
                if user.has_password():
                    if not password:
                        flash("Password is required.", "danger")
                        return redirect(url_for("auth.login"))
                    if not user.check_password(password):
                        # Increment failed attempts
                        conn.execute("""
                            UPDATE officers SET failed_attempts = failed_attempts + 1
                            WHERE badge_number = ?
                        """, (badge,))
                        conn.commit()
                        log_audit("officers", badge, "LOGIN_FAILED", badge, "")
                        flash("Invalid credentials.", "danger")
                        return redirect(url_for("auth.login"))
                    # Reset failed attempts on success
                    conn.execute("""
                        UPDATE officers SET failed_attempts = 0, last_login = ?
                        WHERE badge_number = ?
                    """, (datetime.now().isoformat(), badge))
                    conn.commit()
                elif allow_legacy:
                    # Legacy: badge-only login (no password set)
                    conn.execute("""
                        UPDATE officers SET last_login = ? WHERE badge_number = ?
                    """, (datetime.now().isoformat(), badge))
                    conn.commit()
                else:
                    flash("Password required. Contact admin to set one.", "danger")
                    return redirect(url_for("auth.login"))

                login_user(user)

                # Set session values for template compatibility
                session["officer_badge"] = badge
                session["officer_name"] = user.full_name
                session["officer_rank"] = user.rank
                session["officer_section"] = user.section
                session["officer_role"] = user.role

                log_audit("officers", badge, "LOGIN", badge, user.full_name)
                flash(f"Welcome, {user.rank} {user.full_name}.", "success")

                # Check if password change required
                if user.must_change_password:
                    flash("You must change your password.", "warning")
                    return redirect(url_for("auth.change_password"))

                return redirect(url_for("main.home"))
            else:
                # New user — create during legacy login period
                if allow_legacy and name and rank:
                    conn.execute("""
                        INSERT INTO officers
                        (badge_number, full_name, rank, section, role, last_login)
                        VALUES (?, ?, ?, ?, 'io', ?)
                    """, (badge, name, rank, section, datetime.now().isoformat()))
                    conn.commit()

                    row = conn.execute(
                        "SELECT * FROM officers WHERE badge_number = ?", (badge,)
                    ).fetchone()
                    user = User.from_row(row)
                    login_user(user)

                    session["officer_badge"] = badge
                    session["officer_name"] = name
                    session["officer_rank"] = rank
                    session["officer_section"] = section
                    session["officer_role"] = "io"

                    log_audit("officers", badge, "LOGIN_NEW", badge, name)
                    flash(f"Welcome, {rank} {name}. Account created.", "success")
                    return redirect(url_for("main.home"))
                else:
                    flash("Account not found. Contact administrator.", "danger")
                    return redirect(url_for("auth.login"))
        finally:
            conn.close()

    allow_legacy = get_setting("allow_legacy_login", "true") == "true"
    return render_template("login.html",
                         ranks=JCF_RANKS,
                         sections=FNID_SECTIONS,
                         allow_legacy=allow_legacy)


@bp.route("/logout")
def logout():
    badge = session.get("officer_badge", "")
    name = session.get("officer_name", "")
    if badge:
        log_audit("officers", badge, "LOGOUT", badge, name)
    logout_user()
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    """Change current user's password."""
    if request.method == "POST":
        current_pw = request.form.get("current_password", "")
        new_pw = request.form.get("new_password", "")
        confirm_pw = request.form.get("confirm_password", "")

        if new_pw != confirm_pw:
            flash("New passwords do not match.", "danger")
            return redirect(url_for("auth.change_password"))

        if len(new_pw) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return redirect(url_for("auth.change_password"))

        # If user has an existing password, verify it
        if current_user.has_password() and not current_user.must_change_password:
            if not current_user.check_password(current_pw):
                flash("Current password is incorrect.", "danger")
                return redirect(url_for("auth.change_password"))

        set_password(current_user.badge_number, new_pw)
        log_audit("officers", current_user.badge_number, "PASSWORD_CHANGE",
                 current_user.badge_number, current_user.full_name)
        flash("Password changed successfully.", "success")
        return redirect(url_for("main.home"))

    return render_template("change_password.html")
