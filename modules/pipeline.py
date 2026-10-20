"""
Full pipeline orchestrator for one user:
  fetch emails → extract deadlines → generate PDF → send WhatsApp.

Never raises — all exceptions are caught and logged.
"""
import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

import pytz

from config.settings import OUTPUT_DIR, BASE_URL, PDF_LINK_EXPIRY_HOURS
from modules import db as database
from modules.ai_extractor import extract_deadlines
from modules.gmail_fetcher import fetch_today_emails
from modules.logger import get_logger
from modules.pdf_generator import generate_pdf
from modules import whatsapp_sender

log = get_logger(__name__)


def run_for_user(user_id: int, send_whatsapp: bool = True) -> dict:
    """
    Run the complete pipeline for a single user.

    Returns a status dict with keys:
        user_id, name, email_count, deadline_count,
        pdf_path, pdf_token, whatsapp_status, error
    """
    result: dict = {
        "user_id":        user_id,
        "name":           "",
        "email_count":    0,
        "deadline_count": 0,
        "pdf_path":       None,
        "pdf_token":      None,
        "whatsapp_status": "pending",
        "error":          None,
    }

    # ── Step 1: Load user ──────────────────────────────────────────────
    try:
        user = database.get_user_by_id(user_id)
        if not user:
            result["error"] = f"User {user_id} not found."
            log.error(result["error"])
            return result
        result["name"] = user["name"]
    except Exception as exc:
        result["error"] = f"DB error loading user: {exc}"
        log.exception(result["error"])
        return result

    user_tz_str = user.get("timezone", "Asia/Kolkata")
    try:
        user_tz = pytz.timezone(user_tz_str)
    except pytz.UnknownTimeZoneError:
        user_tz = pytz.timezone("Asia/Kolkata")

    # Today's date in user's local timezone
    today_local = datetime.now(user_tz).date()
    date_str     = today_local.strftime("%Y-%m-%d")
    today_display = today_local.strftime("%d %b %Y")

    # ── Step 2: Load Gmail accounts ────────────────────────────────────
    try:
        accounts = database.get_gmail_accounts(user_id)
        ok_accounts = [a for a in accounts if a.get("status") == "ok"]
    except Exception as exc:
        result["error"] = f"DB error loading accounts: {exc}"
        log.exception(result["error"])
        return result

    if not accounts:
        log.info("No Gmail accounts configured for user %d (%s)", user_id, user.get("name"))
        if send_whatsapp:
            try:
                whatsapp_sender.send_no_accounts_message(user["whatsapp"], BASE_URL)
            except Exception as exc:
                log.warning("Failed to send no-accounts message: %s", exc)
        result["error"] = "No Gmail accounts connected yet. Please connect an inbox from your dashboard."
        return result

    # Warn about accounts needing reconnection
    bad_accounts = [a for a in accounts if a.get("status") != "ok"]
    if bad_accounts and send_whatsapp:
        try:
            whatsapp_sender.send_reconnect_warning(
                user["whatsapp"],
                [a["label"] for a in bad_accounts],
            )
        except Exception as exc:
            log.warning("Failed to send reconnect warning: %s", exc)

    if not ok_accounts:
        result["error"] = "All connected Gmail accounts need reconnection."
        return result

    # ── Step 3: Fetch emails ───────────────────────────────────────────
    all_emails: list[dict] = []
    for account in ok_accounts:
        try:
            fetched = fetch_today_emails(account, user_tz_str)
            all_emails.extend(fetched)
        except Exception as exc:
            log.error(
                "Failed to fetch emails for account %s (%s): %s",
                account.get("id"), account.get("email"), exc,
            )

    # Sort oldest-first by internalDate
    all_emails.sort(key=lambda e: e.get("internal_date_ms", 0))

    result["email_count"] = len(all_emails)

    # ── Step 4: No emails ─────────────────────────────────────────────
    if not all_emails:
        log.info("No emails for user %d on %s", user_id, date_str)
        try:
            report_id = database.create_report(
                user_id         = user_id,
                report_date     = date_str,
                email_count     = 0,
                deadline_count  = 0,
                pdf_path        = None,
                pdf_token       = None,
                pdf_token_expires = None,
            )
            if send_whatsapp:
                sent = whatsapp_sender.send_no_emails_message(
                    user["whatsapp"], today_display
                )
                status = "no_emails" if sent else "failed"
            else:
                status = "no_emails"
            database.update_report_status(report_id, status)
            database.update_last_report_date(user_id, date_str)
            result["whatsapp_status"] = status
        except Exception as exc:
            result["error"] = f"Error handling no-email case: {exc}"
            log.exception(result["error"])
        return result

    # ── Step 5: Extract deadlines ──────────────────────────────────────
    deadlines: list[Optional[str]] = [None] * len(all_emails)
    try:
        deadlines = extract_deadlines(all_emails, today_display)
    except Exception as exc:
        log.error("Deadline extraction failed: %s — proceeding without deadlines.", exc)

    deadline_count = sum(1 for d in deadlines if d)
    result["deadline_count"] = deadline_count

    # Attach deadlines to email dicts
    emails_with_deadlines = []
    for email, dl in zip(all_emails, deadlines):
        emails_with_deadlines.append({**email, "deadline": dl})

    # ── Step 6: Generate PDF ───────────────────────────────────────────
    pdf_path: Optional[str] = None
    try:
        output_filename = f"report_{user_id}_{date_str}.pdf"
        pdf_path = os.path.join(OUTPUT_DIR, output_filename)
        generate_pdf(
            user_name   = user["name"],
            report_date = date_str,
            emails      = emails_with_deadlines,
            output_path = pdf_path,
        )
        result["pdf_path"] = pdf_path
    except Exception as exc:
        log.error("PDF generation failed for user %d: %s", user_id, exc)
        pdf_path = None

    # ── Step 7: Signed token ───────────────────────────────────────────
    pdf_token: Optional[str] = None
    pdf_token_expires: Optional[str] = None
    if pdf_path:
        try:
            pdf_token = secrets.token_hex(32)
            expires_dt = datetime.now(timezone.utc) + timedelta(hours=PDF_LINK_EXPIRY_HOURS)
            pdf_token_expires = expires_dt.isoformat()
            result["pdf_token"] = pdf_token
        except Exception as exc:
            log.error("Failed to generate PDF token: %s", exc)

    # ── Step 8: Save report to DB ──────────────────────────────────────
    report_id: Optional[int] = None
    try:
        report_id = database.create_report(
            user_id           = user_id,
            report_date       = date_str,
            email_count       = len(all_emails),
            deadline_count    = deadline_count,
            pdf_path          = pdf_path,
            pdf_token         = pdf_token,
            pdf_token_expires = pdf_token_expires,
        )
    except Exception as exc:
        log.error("Failed to save report to DB: %s", exc)

    # ── Step 9 & 10: Send WhatsApp ─────────────────────────────────────
    whatsapp_status = "skipped"
    if send_whatsapp:
        try:
            report_payload = {
                "report_date":    date_str,
                "email_count":    len(all_emails),
                "deadline_count": deadline_count,
                "pdf_token":      pdf_token or "",
                "pdf_token_expires": pdf_token_expires or "",
                "deadlines_list": deadlines,
            }
            sent = whatsapp_sender.send_report(user, report_payload, BASE_URL)
            whatsapp_status = "sent" if sent else "failed"
        except Exception as exc:
            log.error("WhatsApp send failed for user %d: %s", user_id, exc)
            whatsapp_status = "failed"

        if report_id is not None:
            try:
                database.update_report_status(report_id, whatsapp_status)
            except Exception as exc:
                log.error("Failed to update report status: %s", exc)

    result["whatsapp_status"] = whatsapp_status

    # ── Step 11: Update last_report_date ──────────────────────────────
    try:
        database.update_last_report_date(user_id, date_str)
    except Exception as exc:
        log.error("Failed to update last_report_date for user %d: %s", user_id, exc)

    log.info(
        "Pipeline complete for user %d (%s): %d emails, %d deadlines, WA=%s",
        user_id, user["name"], len(all_emails), deadline_count, whatsapp_status,
    )
    return result
