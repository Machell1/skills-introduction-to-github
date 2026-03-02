"""
FNID Area 3 Operational Portal

Flask application factory for the Jamaica Constabulary Force
Firearms & Narcotics Investigation Division, Area 3.
"""

import os
from datetime import datetime

from flask import Flask

from . import models
from .config import config_by_name
from .constants import UNIT_PORTALS


def create_app(config_name=None):
    """Create and configure the Flask application.

    Args:
        config_name: Configuration name ('development', 'production', 'testing').
                     Defaults to FLASK_ENV environment variable or 'development'.
    """
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")

    app = Flask(__name__)

    # Load configuration
    config_cls = config_by_name.get(config_name)
    if config_cls is None:
        raise ValueError(f"Unknown config: {config_name}. Use: {list(config_by_name.keys())}")

    # For production, instantiate to trigger validation
    if config_name == "production":
        config_obj = config_cls()
        app.config.from_object(config_obj)
    else:
        app.config.from_object(config_cls)

    # Store custom paths in app config for easy access
    app.config.setdefault("UPLOAD_DIR", config_cls.UPLOAD_DIR)
    app.config.setdefault("EXPORT_DIR", config_cls.EXPORT_DIR)

    # Ensure data directories exist
    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)
    os.makedirs(app.config["EXPORT_DIR"], exist_ok=True)

    # Configure database
    db_path = getattr(config_cls, "DB_PATH", None)
    if config_name == "production":
        db_path = config_obj.DB_PATH
    models.configure(db_path)

    # Initialize database
    models.init_db()

    # Register context processor
    @app.context_processor
    def inject_globals():
        return {
            "portals": UNIT_PORTALS,
            "now": datetime.now(),
        }

    # Register blueprints
    from .routes.api import bp as api_bp
    from .routes.auth import bp as auth_bp
    from .routes.data import bp as data_bp
    from .routes.main import bp as main_bp
    from .routes.units import bp as units_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(units_bp)
    app.register_blueprint(data_bp)
    app.register_blueprint(api_bp)

    return app
