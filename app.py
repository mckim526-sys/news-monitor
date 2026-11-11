"""Compatibility entry point for existing Render start commands.

The application lives in main.py.  This wrapper supports deployments
configured to launch app.py without duplicating the application.
"""
import os

from main import app, start_worker

if __name__ == "__main__":
    start_worker()
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        use_reloader=False,
    )
