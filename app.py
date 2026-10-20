# app.py — Inbox Insights Flask web application
"""
Full-featured Flask web app for Inbox Insights.

Routes
------
GET  /                        Landing page
GET  /register                Registration form
POST /register                Create account
GET  /login                   Login form
POST /login                   Authenticate user
GET  /logout                  Clear session
GET  /dashboard               User dashboard (login required)
GET  /connect-gmail           Start Gmail OAuth flow (login required)
GET  /oauth/callback          Gmail OAuth callback
POST /gmail/remove/<id>       Remove a Gmail account (login required)
POST /gmail/reconnect/<id>    Re-initiate OAuth for an account (login required)
POST /settings/delivery       Update delivery settings (login required)
POST /send-now                Trigger immediate report (login required)
GET  /r/<token>               Serve signed PDF (public, token-gated)
POST /delete-account          Delete account with password confirmation (login required)
"""

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, send_file, abort,
)
from flask_wtf.csrf import CSRFProtect
from functools import wraps
import threading
import secrets
import os
from datetime import datetime, timezone, timedelta

import pytz
from werkzeug.security import generate_password_hash, check_password_hash

from config.settings import SECRET_KEY, BASE_URL, OUTPUT_DIR
from modules.db import (
    init_db,
    create_user,
    get_user_by_whatsapp,
    get_user_by_id,
    update_delivery_settings,
    update_last_report_date,
    delete_user,
    record_login_attempt,
    is_locked_out,
    add_gmail_account,
    update_gmail_token,
    set_gmail_status,
    get_gmail_accounts,
    get_gmail_account_by_id,
    remove_gmail_account,
    create_report,
    update_report_status,
    get_reports,
    get_report_by_token,
    save_oauth_state,
    get_oauth_state,
    delete_oauth_state,
)
from modules.gmail_fetcher import get_auth_url, exchange_code_for_token, build_credentials_from_token
from modules.pipeline import run_for_user
from modules.logger import get_logger
from scheduler import start_scheduler

# ─── App Setup ───────────────────────────────────────────────────────────────

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["WTF_CSRF_TIME_LIMIT"] = 3600

csrf = CSRFProtect(app)
log = get_logger(__name__)

# ─── Helpers ─────────────────────────────────────────────────────────────────

import re

WHATSAPP_RE = re.compile(r"^\+[1-9]\d{7,14}$")


def login_required(f):
    """Decorator: redirect to /login if the user is not authenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def current_user():
    """Return the row for the currently logged-in user, or None."""
    uid = session.get("user_id")
    if uid is None:
        return None
    return get_user_by_id(uid)


@app.context_processor
def inject_globals():
    """Make commonly-needed values available in every template."""
    return {
        "current_user": current_user(),
        "base_url": BASE_URL,
        "twilio_sandbox_number": "+14155238886",
        "twilio_sandbox_word": os.getenv("TWILIO_SANDBOX_WORD", "your-sandbox-word"),
    }


@app.template_filter("pastel_color")
def pastel_color_filter(n):
    """Cycle 0, 1, 2 to pink, peach, lavender."""
    try:
        idx = int(n)
    except (ValueError, TypeError):
        idx = 0
    return {0: "pink", 1: "peach", 2: "lavender"}[idx % 3]


# ─── Authentication ───────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Landing / marketing page."""
    return render_template("index.html")


@app.route("/register", methods=["GET"])
def register():
    """Show the registration form."""
    return render_template("register.html")


@app.route("/register", methods=["POST"])
def register_post():
    """Process the registration form and create a new user account."""
    name          = request.form.get("name", "").strip()
    whatsapp      = request.form.get("whatsapp", "").strip()
    password      = request.form.get("password", "")
    confirm_pw    = request.form.get("confirm_password", "")
    delivery_time = request.form.get("delivery_time", "08:00").strip()
    tz_name       = request.form.get("timezone", "UTC").strip()

    errors = []

    if not name:
        errors.append("Name is required.")
    if not whatsapp:
        errors.append("WhatsApp number is required.")
    elif not WHATSAPP_RE.match(whatsapp):
        errors.append(
            "WhatsApp number must start with a country code (e.g. +91…) "
            "and be 8–15 digits total."
        )
    if not password:
        errors.append("Password is required.")
    elif len(password) < 8:
        errors.append("Password must be at least 8 characters.")
    elif password != confirm_pw:
        errors.append("Passwords do not match.")

    # Validate delivery time format HH:MM
    try:
        datetime.strptime(delivery_time, "%H:%M")
    except ValueError:
        errors.append("Delivery time must be in HH:MM format (24-hour).")

    # Validate timezone
    try:
        pytz.timezone(tz_name)
    except pytz.exceptions.UnknownTimeZoneError:
        errors.append(f"Unknown timezone: {tz_name!r}.")

    # Check for duplicate WhatsApp number
    if not errors and get_user_by_whatsapp(whatsapp):
        errors.append("An account with that WhatsApp number already exists.")

    if errors:
        for err in errors:
            flash(err, "danger")
        return render_template(
            "register.html",
            form_data={
                "name": name,
                "whatsapp": whatsapp,
                "delivery_time": delivery_time,
                "timezone": tz_name,
            },
        )

    password_hash = generate_password_hash(password)
    try:
        user_id = create_user(
            name=name,
            whatsapp=whatsapp,
            password_hash=password_hash,
            delivery_time=delivery_time,
            timezone=tz_name,
        )
    except TypeError:
        try:
            user_id = create_user(
                name=name,
                whatsapp=whatsapp,
                password_hash=password_hash,
                delivery_time=delivery_time,
                timezone_str=tz_name,
            )
        except TypeError:
            user_id = create_user(name, whatsapp, password_hash, delivery_time, tz_name)

    session["user_id"] = user_id
    flash(f"Welcome, {name}! Your account has been created.", "success")
    return redirect(url_for("dashboard"))


@app.route("/login", methods=["GET"])
def login():
    """Show the login form."""
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login_post():
    """Authenticate the user and open a session."""
    whatsapp = request.form.get("whatsapp", "").strip()
    password = request.form.get("password", "")

    # Check account lockout before anything else
    try:
        lockout = is_locked_out(whatsapp)
        if isinstance(lockout, (tuple, list)):
            locked = bool(lockout[0])
            wait_minutes = lockout[1] if len(lockout) > 1 else 15
        else:
            locked = bool(lockout)
            wait_minutes = 15
    except Exception:
        locked, wait_minutes = False, 0

    if locked:
        flash(
            f"Too many failed attempts. Please try again in {wait_minutes} minute(s).",
            "danger",
        )
        return render_template("login.html", form_data={"whatsapp": whatsapp})

    user = get_user_by_whatsapp(whatsapp)
    if user and check_password_hash(user["password_hash"], password):
        record_login_attempt(whatsapp, success=True)
        session["user_id"] = user["id"]
        flash(f"Welcome back, {user['name']}!", "success")
        return redirect(url_for("dashboard"))

    # Failed attempt
    record_login_attempt(whatsapp, success=False)
    flash("Invalid credentials. Please check your number and password.", "danger")
    return render_template("login.html", form_data={"whatsapp": whatsapp})


@app.route("/logout")
def logout():
    """Destroy the session and redirect to the landing page."""
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


# ─── Dashboard ────────────────────────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    """Main user dashboard: connected accounts, recent reports, delivery settings."""
    user           = current_user()
    gmail_accounts = get_gmail_accounts(user["id"])
    reports        = get_reports(user["id"], limit=30)

    # Compute time of day in user's timezone
    user_tz_str = user.get("timezone", "Asia/Kolkata")
    try:
        user_tz = pytz.timezone(user_tz_str)
    except Exception:
        user_tz = pytz.utc
    hour = datetime.now(user_tz).hour
    if 5 <= hour < 12:
        time_of_day = "morning"
    elif 12 <= hour < 17:
        time_of_day = "afternoon"
    elif 17 <= hour < 21:
        time_of_day = "evening"
    else:
        time_of_day = "night"

    last_email_count = reports[0]["email_count"] if reports else 0

    sandbox_join = (
        f"join {os.getenv('TWILIO_SANDBOX_WORD', 'your-sandbox-word')}"
    )

    return render_template(
        "dashboard.html",
        user=user,
        gmail_accounts=gmail_accounts,
        reports=reports,
        recent_reports=reports,
        last_email_count=last_email_count,
        time_of_day=time_of_day,
        sandbox_join=sandbox_join,
        timezones=pytz.common_timezones,
    )


# ─── Gmail OAuth ──────────────────────────────────────────────────────────────

@app.route("/connect-gmail")
@login_required
def connect_gmail():
    """Begin the Gmail OAuth 2.0 PKCE flow for the current user."""
    label = request.args.get("label", "Gmail").strip() or "Gmail"
    user  = current_user()

    try:
        auth_url, state, code_verifier = get_auth_url(user["id"], label)
    except Exception as exc:
        log.exception("Could not build Gmail auth URL: %s", exc)
        flash("Could not start Gmail authorisation. Check server logs.", "danger")
        return redirect(url_for("dashboard"))

    # Persist state so the callback can retrieve the code_verifier
    save_oauth_state(
        state=state,
        user_id=user["id"],
        code_verifier=code_verifier,
        label=label,
    )

    return redirect(auth_url)


@app.route("/oauth/callback")
def oauth_callback():
    """Handle the redirect back from Google after the user grants permission."""
    state = request.args.get("state")
    code  = request.args.get("code")
    error = request.args.get("error")

    if error:
        flash(f"Google authorisation denied: {error}", "danger")
        return redirect(url_for("dashboard"))

    if not state or not code:
        flash("Invalid OAuth callback — missing state or code.", "danger")
        return redirect(url_for("dashboard"))

    # Load the saved state row
    state_row = get_oauth_state(state)
    if not state_row:
        flash("OAuth state not found or expired. Please try connecting again.", "danger")
        return redirect(url_for("dashboard"))

    user_id       = state_row["user_id"]
    code_verifier = state_row["code_verifier"]
    label         = state_row.get("label", "Gmail")

    # Ensure the callback belongs to the logged-in user (if a session exists)
    if "user_id" in session and session["user_id"] != user_id:
        flash("OAuth session mismatch. Please log in and try again.", "danger")
        delete_oauth_state(state)
        return redirect(url_for("dashboard"))

    try:
        token_data = exchange_code_for_token(code, code_verifier)
    except Exception as exc:
        log.exception("Token exchange failed: %s", exc)
        flash("Failed to exchange authorisation code for token.", "danger")
        delete_oauth_state(state)
        return redirect(url_for("dashboard"))

    # Retrieve the Gmail address from the token
    try:
        creds   = build_credentials_from_token(token_data)
        from googleapiclient.discovery import build as gbuild
        service = gbuild("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        gmail_address = profile.get("emailAddress", "")
    except Exception as exc:
        log.exception("Could not fetch Gmail profile: %s", exc)
        flash("Connected but could not retrieve Gmail address.", "warning")
        gmail_address = ""

    # Check for duplicate connection
    existing_accounts = get_gmail_accounts(user_id)
    for acct in existing_accounts:
        if acct.get("email") == gmail_address:
            flash(
                f"{gmail_address} is already connected to your account.",
                "warning",
            )
            delete_oauth_state(state)
            # Restore session if it was missing (e.g. mobile redirect)
            session["user_id"] = user_id
            return redirect(url_for("dashboard"))

    # Encrypt token and store the account
    try:
        from modules.crypto import encrypt_token  # noqa: WPS433 — lazy import
        encrypted_token = encrypt_token(token_data)
    except ImportError:
        # Fallback: store as JSON string if no crypto module available
        import json
        encrypted_token = json.dumps(token_data)

    add_gmail_account(
        user_id=user_id,
        email=gmail_address,
        label=label,
        token=encrypted_token,
    )

    delete_oauth_state(state)
    session["user_id"] = user_id
    flash(
        f"Gmail account {gmail_address or label!r} connected successfully!",
        "success",
    )
    return redirect(url_for("dashboard"))


@app.route("/gmail/remove/<int:account_id>", methods=["POST"])
@login_required
def gmail_remove(account_id):
    """Disconnect and delete a Gmail account from this user's profile."""
    user    = current_user()
    account = get_gmail_account_by_id(account_id)

    if not account or account["user_id"] != user["id"]:
        flash("Gmail account not found or access denied.", "danger")
        return redirect(url_for("dashboard"))

    remove_gmail_account(account_id)
    flash(
        f"Gmail account {account.get('email', account_id)!r} has been removed.",
        "success",
    )
    return redirect(url_for("dashboard"))


@app.route("/gmail/reconnect/<int:account_id>", methods=["POST"])
@login_required
def gmail_reconnect(account_id):
    """Re-initiate OAuth for an existing Gmail account (e.g. token expired)."""
    user    = current_user()
    account = get_gmail_account_by_id(account_id)

    if not account or account["user_id"] != user["id"]:
        flash("Gmail account not found or access denied.", "danger")
        return redirect(url_for("dashboard"))

    # Re-use the stored label so the account slot is preserved
    label = account.get("label", "Gmail")
    return redirect(url_for("connect_gmail", label=label))


# ─── Settings ─────────────────────────────────────────────────────────────────

@app.route("/settings/delivery", methods=["POST"])
@login_required
def settings_delivery():
    """Update delivery time, timezone, and enabled flag for the current user."""
    user             = current_user()
    delivery_time    = request.form.get("delivery_time", "").strip()
    tz_name          = request.form.get("timezone", "").strip()
    delivery_enabled = request.form.get("delivery_enabled") == "on"

    errors = []

    # Validate HH:MM format
    try:
        datetime.strptime(delivery_time, "%H:%M")
    except ValueError:
        errors.append("Delivery time must be in HH:MM (24-hour) format.")

    # Validate timezone
    try:
        pytz.timezone(tz_name)
    except pytz.exceptions.UnknownTimeZoneError:
        errors.append(f"Unknown timezone: {tz_name!r}.")

    if errors:
        for err in errors:
            flash(err, "danger")
        return redirect(url_for("dashboard"))

    try:
        update_delivery_settings(
            user_id=user["id"],
            delivery_time=delivery_time,
            timezone=tz_name,
            delivery_enabled=delivery_enabled,
        )
    except TypeError:
        try:
            update_delivery_settings(
                user_id=user["id"],
                delivery_time=delivery_time,
                timezone_str=tz_name,
                delivery_enabled=delivery_enabled,
            )
        except TypeError:
            update_delivery_settings(user["id"], delivery_time, tz_name, delivery_enabled)
    # Reset last_report_date so the scheduler can fire today at the new time
    update_last_report_date(user["id"], None)

    flash("Delivery settings saved.", "success")
    return redirect(url_for("dashboard"))


# ─── Reports ──────────────────────────────────────────────────────────────────

@app.route("/send-now", methods=["POST"])
@login_required
def send_now():
    """Trigger an immediate report generation in a background daemon thread."""
    user_id = session["user_id"]

    def _run():
        try:
            run_for_user(user_id, send_whatsapp=True)
        except Exception as exc:
            log.exception("Background send-now failed for user %s: %s", user_id, exc)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    flash(
        "Your report is being generated and will be sent to WhatsApp shortly!",
        "success",
    )
    return redirect(url_for("dashboard"))


@app.route("/r/<token>")
def serve_report(token):
    """
    Serve a signed PDF report by its short-lived token.

    No login is required — the token itself authorises access.
    Returns 404 if the token does not exist, 410 if it has expired.
    """
    report = get_report_by_token(token)
    if not report:
        abort(404)

    # Check expiry (stored as ISO-8601 UTC string)
    try:
        expires = datetime.fromisoformat(report["pdf_token_expires"])
        # Make timezone-aware if it isn't already
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
    except (KeyError, ValueError, TypeError):
        log.warning("Could not parse pdf_token_expires for token %s", token)
        abort(404)

    if datetime.now(timezone.utc) > expires:
        abort(410)  # Gone — link has expired

    pdf_path = report.get("pdf_path", "")
    if not pdf_path or not os.path.exists(pdf_path):
        abort(404)

    return send_file(
        pdf_path,
        mimetype="application/pdf",
        download_name=f"inbox_insights_{report.get('report_date', 'report')}.pdf",
    )


# ─── Account Management ───────────────────────────────────────────────────────

@app.route("/delete-account", methods=["POST"])
@login_required
def delete_account():
    """
    Permanently delete the current user's account.

    Requires the user to supply their password as confirmation.
    All PDF reports on disk are removed before the DB record is deleted.
    """
    user     = current_user()
    password = request.form.get("password", "")

    if not check_password_hash(user["password_hash"], password):
        flash("Incorrect password. Account was NOT deleted.", "danger")
        return redirect(url_for("dashboard"))

    # Remove all PDF files belonging to this user
    user_reports = get_reports(user["id"], limit=10_000)
    for report in user_reports:
        pdf_path = report.get("pdf_path", "")
        if pdf_path and os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
                log.info("Deleted PDF: %s", pdf_path)
            except OSError as exc:
                log.warning("Could not delete PDF %s: %s", pdf_path, exc)

    delete_user(user["id"])
    session.clear()
    flash("Your account and all associated data have been permanently deleted.", "info")
    return redirect(url_for("index"))


# ─── Error Handlers ───────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(exc):
    return render_template("error.html", error_code=404, code=404, error_message="Page not found.", message="Page not found."), 404


@app.errorhandler(410)
def gone(exc):
    return render_template(
        "error.html", error_code=410, code=410, error_message="This report link has expired.", message="This report link has expired."
    ), 410


@app.errorhandler(500)
def server_error(exc):
    log.exception("Internal server error: %s", exc)
    return render_template("error.html", error_code=500, code=500, error_message="Internal server error.", message="Internal server error."), 500


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", 5000))

    init_db()
    start_scheduler()

    from waitress import serve  # type: ignore[import]
    log.info("Starting Inbox Insights on http://%s:%s", HOST, PORT)
    serve(app, host=HOST, port=PORT)
