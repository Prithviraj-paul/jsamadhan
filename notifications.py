"""Background accountability worker for Jharkhand Samadhan.

Runs as a daemon thread alongside the server and enforces the citizen-facing
promises made on the site:

1. Notify within 24 hours  -> any open complaint older than 24h that has not
   been notified gets a demo "notification sent" entry in its timeline.
2. Action within 2-3 days  -> complaints whose action_due_at has passed while
   still open are escalated and moved to the higher-authority queue.

The worker opens its own sqlite connection (it runs outside Flask's request
context and flask.g).
"""

import sqlite3
import threading
import time
from datetime import datetime, timedelta

import db

NOTIFY_WINDOW_HOURS = 24
ACTION_DUE_DAYS = 3
CHECK_INTERVAL_SECONDS = 30
INITIAL_DELAY_SECONDS = 10


def _now():
    return datetime.utcnow()


def run_cycle():
    conn = sqlite3.connect(db.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        now = _now()
        due_notify = (now - timedelta(hours=NOTIFY_WINDOW_HOURS)).isoformat()
        notified = 0
        for row in db.list_due_notifications(conn, due_notify):
            db.mark_notified(conn, row["id"], now.isoformat())
            notified += 1

        escalated = 0
        for row in db.list_overdue_actions(conn, now.isoformat()):
            db.escalate_complaint(
                conn, row["id"],
                "Action was not completed within the promised 2\u20133 days. "
                "Complaint escalated to higher authority for immediate disposal.",
            )
            escalated += 1

        if notified or escalated:
            print(f"[notifications] cycle done \u2014 notified {notified}, escalated {escalated}")
    except Exception as exc:
        print(f"[notifications] cycle error: {exc}")
    finally:
        conn.close()


def _loop():
    time.sleep(INITIAL_DELAY_SECONDS)
    while True:
        try:
            run_cycle()
        except Exception:
            pass
        time.sleep(CHECK_INTERVAL_SECONDS)


def start_worker():
    threading.Thread(target=_loop, daemon=True, name="notify-escalate").start()
    print("[notifications] background worker started (notify <24h, action by 3 days, auto-escalate).")