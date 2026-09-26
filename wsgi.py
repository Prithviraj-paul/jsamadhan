"""Production entrypoint (gunicorn / Render / any WSGI server).

`gunicorn app:app` alone never creates the SQLite schema, seeds demo
users, or starts the notification worker — those live in run_server.py,
which gunicorn bypasses. Importing this module performs the same
boot steps, then exposes the Flask app.

Start command:  gunicorn wsgi:app
"""

import logging
import os

import db

logger = logging.getLogger("jsamadhan.wsgi")

# 1. Schema (idempotent — safe on every boot, preserves existing data).
db.init_db()

# 2. Demo users (skipped when SEED_DEMO_USERS=0, e.g. production).
if os.environ.get("SEED_DEMO_USERS", "1") == "1":
    try:
        from app import seed_demo_users

        seed_demo_users()
    except Exception:
        logger.exception("Demo-user seeding failed; continuing without it")

# 3. Import the app (registers routes), then background worker.
from app import app  # noqa: E402  (after init so tables exist)

try:
    import notifications

    notifications.start_worker()
except Exception:
    logger.exception("Notification worker failed to start; continuing")
