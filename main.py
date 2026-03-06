"""One-click entry point for the FNID Portal."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from fnid_portal import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
