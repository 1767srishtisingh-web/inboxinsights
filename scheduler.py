"""
scheduler.py — Per-user timezone-aware delivery scheduler.

Scheduling rules:
- Runs in a background thread inside the Flask app.
- Every 30 seconds, checks each enabled user who has at least one Gmail account.
- If the current time in their timezone is at or past their delivery time
  and they haven't received today's report yet, mark today as sent and run their pipeline.
- Changing delivery time or timezone in the dashboard resets "last_report_date" so the new
  time takes effect the same day.
- A per-user lock prevents two runs at once.
- One user's failure never stops other users.
"""

import threading
import time
from datetime import datetime
import pytz

from modules.db import get_users_for_delivery, update_last_report_date
from modules.pipeline import run_for_user
from modules.logger import get_logger

log = get_logger(__name__)

# Per-user locks to prevent duplicate concurrent runs for the same user
_user_locks: dict[int, threading.Lock] = {}
_locks_mutex = threading.Lock()
_scheduler_thread = None
_stop_event = threading.Event()


def _get_user_lock(user_id: int) -> threading.Lock:
    with _locks_mutex:
        if user_id not in _user_locks:
            _user_locks[user_id] = threading.Lock()
        return _user_locks[user_id]


def _should_run(user: dict) -> tuple[bool, str]:
    """
    Check if user is due for today's delivery.
    Returns (should_run_bool, today_date_str).
    """
    tz_str = user.get("timezone", "Asia/Kolkata")
    try:
        user_tz = pytz.timezone(tz_str)
    except Exception:
        user_tz = pytz.timezone("Asia/Kolkata")

    now_local = datetime.now(user_tz)
    today_str = now_local.strftime("%Y-%m-%d")

    # Already sent today?
    if user.get("last_report_date") == today_str:
        return False, today_str

    # Time check (HH:MM 24-hour format)
    delivery_time_str = user.get("delivery_time", "08:00")
    current_time_str = now_local.strftime("%H:%M")

    if current_time_str >= delivery_time_str:
        return True, today_str

    return False, today_str


def check_and_deliver_all():
    """Single pass over all eligible users."""
    try:
        users = get_users_for_delivery()
    except Exception as exc:
        log.exception("Scheduler: failed to fetch users for delivery: %s", exc)
        return

    for user in users:
        try:
            should_run, today_str = _should_run(user)
            if not should_run:
                continue

            user_id = user["id"]
            user_lock = _get_user_lock(user_id)

            if user_lock.acquire(blocking=False):
                # Mark as sent immediately to avoid repeat triggers during 30s ticks
                update_last_report_date(user_id, today_str)

                def _worker(u_id=user_id, u_name=user.get("name", "User"), lock=user_lock):
                    try:
                        log.info("Scheduler: starting delivery for %s (id=%d)", u_name, u_id)
                        run_for_user(u_id, send_whatsapp=True)
                    except Exception as err:
                        log.exception("Scheduler: run_for_user failed for %s (id=%d): %s", u_name, u_id, err)
                    finally:
                        lock.release()

                t = threading.Thread(target=_worker, daemon=True, name=f"deliver-user-{user_id}")
                t.start()
            else:
                log.info("Scheduler: user %d is already running, skipping", user_id)

        except Exception as exc:
            log.exception("Scheduler: error processing user %s: %s", user.get("id"), exc)


def scheduler_loop():
    """Runs every 30 seconds in the background."""
    log.info("Background delivery scheduler loop started (interval=30s).")
    while not _stop_event.is_set():
        check_and_deliver_all()
        # Sleep in short increments so stop_event can exit cleanly
        for _ in range(30):
            if _stop_event.is_set():
                break
            time.sleep(1)


def start_scheduler():
    """Start the scheduler thread if not already running."""
    global _scheduler_thread
    if _scheduler_thread is not None and _scheduler_thread.is_alive():
        return
    _stop_event.clear()
    _scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True, name="InboxInsightsScheduler")
    _scheduler_thread.start()
    log.info("Scheduler thread launched.")


def stop_scheduler():
    """Signal the scheduler thread to stop."""
    _stop_event.set()
