"""
FNID Authentication - Flask-Login integration with password hashing.

Provides the User model, login manager setup, and password utilities.
"""

from flask_login import LoginManager, UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .models import get_db

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "warning"
login_manager.login_message = "Please sign in to access this page."


class User(UserMixin):
    """Flask-Login compatible user wrapping the officers table."""

    def __init__(self, badge_number, full_name, rank, section, role="io",
                 password_hash=None, email=None, is_active=True,
                 unit_access="all", must_change_password=False):
        self.id = badge_number  # Flask-Login uses .id
        self.badge_number = badge_number
        self.full_name = full_name
        self.rank = rank
        self.section = section
        self.role = role or "io"
        self.password_hash = password_hash
        self.email = email
        self._is_active = is_active
        self.unit_access = unit_access
        self.must_change_password = must_change_password

    @property
    def is_active(self):
        return bool(self._is_active)

    @staticmethod
    def from_row(row):
        """Create a User from a sqlite3.Row."""
        if row is None:
            return None
        return User(
            badge_number=row["badge_number"],
            full_name=row["full_name"],
            rank=row["rank"],
            section=row["section"],
            role=row["role"] if "role" in row.keys() else "io",
            password_hash=row["password_hash"] if "password_hash" in row.keys() else None,
            email=row["email"] if "email" in row.keys() else None,
            is_active=bool(row["is_active"]) if "is_active" in row.keys() else True,
            unit_access=row["unit_access"] if "unit_access" in row.keys() else "all",
            must_change_password=(
                row["must_change_password"]
                if "must_change_password" in row.keys() else False
            ),
        )

    def check_password(self, password):
        """Verify password against stored hash."""
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    def has_password(self):
        """Check if the user has set a password."""
        return bool(self.password_hash)


@login_manager.user_loader
def load_user(badge_number):
    """Flask-Login user loader callback."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM officers WHERE badge_number = ?", (badge_number,)
        ).fetchone()
        return User.from_row(row)
    finally:
        conn.close()


def set_password(badge_number, password):
    """Set (or reset) password for an officer."""
    pw_hash = generate_password_hash(password)
    conn = get_db()
    try:
        conn.execute(
            "UPDATE officers SET password_hash = ?, must_change_password = 0 WHERE badge_number = ?",
            (pw_hash, badge_number),
        )
        conn.commit()
    finally:
        conn.close()


def create_officer(badge_number, full_name, rank, section, role="io",
                   password=None, email=None):
    """Create a new officer account."""
    pw_hash = generate_password_hash(password) if password else None
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO officers (badge_number, full_name, rank, section, role,
                                  password_hash, email, must_change_password)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (badge_number, full_name, rank, section, role, pw_hash, email,
              1 if password else 0))
        conn.commit()
    finally:
        conn.close()
