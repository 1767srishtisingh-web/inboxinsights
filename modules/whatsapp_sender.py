"""
WhatsApp delivery via Twilio Sandbox for Inbox Insights.

PDF download links are served as signed URLs from this Flask app (/r/<token>).
"""
import time
from typing import Optional

from config.settings import (
    MAX_RETRIES,
    RETRY_BACKOFF_SECONDS,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_WHATSAPP_FROM,
)
from modules.logger import get_logger

log = get_logger(__name__)


def _get_twilio_client():
    """Lazily instantiate the Twilio client."""
    from twilio.rest import Client  # type: ignore
    return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def _send_with_retry(
    to: str,
    body: str,
    media_url: Optional[str] = None,
) -> bool:
    """
    Send a WhatsApp message via Twilio with exponential back-off on 5xx errors.

    Returns True if the message was accepted.
    """
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        log.error("Twilio credentials not configured; cannot send WhatsApp message.")
        return False

    client = _get_twilio_client()

    for attempt in range(MAX_RETRIES):
        try:
            kwargs = {
                "from_": TWILIO_WHATSAPP_FROM,
                "to":    f"whatsapp:{to}" if not to.startswith("whatsapp:") else to,
                "body":  body,
            }
            if media_url:
                kwargs["media_url"] = [media_url]

            message = client.messages.create(**kwargs)
            log.info(
                "WhatsApp message sent to %s | SID=%s | status=%s",
                to, message.sid, message.status,
            )
            return True

        except Exception as exc:
            error_msg = str(exc)
            # Retry on 5xx errors
            is_retryable = any(
                code in error_msg for code in ("500", "503", "502", "429")
            )
            if is_retryable and attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF_SECONDS * (2 ** attempt)
                log.warning(
                    "Twilio retryable error (attempt %d/%d): %s — retrying in %ds",
                    attempt + 1, MAX_RETRIES, exc, wait,
                )
                time.sleep(wait)
            else:
                log.error(
                    "Twilio send failed (attempt %d/%d): %s",
                    attempt + 1, MAX_RETRIES, exc,
                )
                return False

    return False


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def send_report(user: dict, report: dict, base_url: str) -> bool:
    """
    Send the daily digest WhatsApp message to the user.

    Args:
        user:     User dict (must contain 'whatsapp', 'name').
        report:   Report dict with keys:
                    report_date, email_count, deadline_count,
                    pdf_token, pdf_token_expires, deadlines_list (list[str|None])
        base_url: Public base URL (e.g. https://yourdomain.com)

    Returns:
        True if message was sent successfully.
    """
    whatsapp_to  = user["whatsapp"]
    report_date  = report.get("report_date", "")
    email_count  = report.get("email_count", 0)
    deadline_count = report.get("deadline_count", 0)
    pdf_token    = report.get("pdf_token", "")
    deadlines    = report.get("deadlines_list", [])

    # Format date nicely if possible
    try:
        from datetime import datetime
        dt = datetime.strptime(report_date, "%Y-%m-%d")
        display_date = f"{dt.day} {dt.strftime('%b %Y')}"
    except Exception:
        display_date = report_date

    # Build deadlines bullet list (max 10 items to stay under 1600 chars)
    dl_lines = []
    for dl in deadlines:
        if dl:
            dl_lines.append(f"• {dl}")
    dl_section = "\n".join(dl_lines[:10]) if dl_lines else "  (none)"

    # Build body
    use_https = base_url.startswith("https://")
    pdf_url   = f"{base_url}/r/{pdf_token}" if use_https and pdf_token else None

    body_parts = [
        f"📊 *Inbox Insights — {display_date}*",
        f"{email_count} email{'s' if email_count != 1 else ''} · {deadline_count} deadline{'s' if deadline_count != 1 else ''}",
        "",
        "Deadlines:",
        dl_section,
    ]

    if pdf_url:
        body_parts += [
            "",
            f"📎 Report: {pdf_url}",
            "⚠️ Link expires in 48h",
        ]
    else:
        body_parts += [
            "",
            "(PDF available on dashboard)",
        ]

    body = "\n".join(body_parts)

    # Truncate if over 1600 chars (Twilio limit)
    if len(body) > 1600:
        body = body[:1597] + "…"

    media_url = pdf_url if use_https else None
    return _send_with_retry(whatsapp_to, body, media_url=media_url)


def send_no_emails_message(whatsapp_to: str, date_str: str) -> bool:
    """
    Notify the user that no new emails were found today.

    Args:
        whatsapp_to: E.164 number e.g. "+919876543210"
        date_str:    Human-readable date string.

    Returns:
        True if sent successfully.
    """
    body = (
        f"📭 No new emails today ({date_str}). "
        "Inbox Insights will check again tomorrow."
    )
    return _send_with_retry(whatsapp_to, body)


def send_reconnect_warning(whatsapp_to: str, account_labels: list[str]) -> bool:
    """
    Warn the user that one or more Gmail accounts need re-authorisation.

    Args:
        whatsapp_to:    E.164 number.
        account_labels: List of account label strings needing reconnection.

    Returns:
        True if sent successfully.
    """
    label_list = "\n".join(f"• {lbl}" for lbl in account_labels)
    body = (
        "⚠️ *Inbox Insights — Action Required*\n\n"
        "The following Gmail account(s) need to be reconnected:\n"
        f"{label_list}\n\n"
        "Please log in to Inbox Insights and re-authorise these accounts."
    )
    return _send_with_retry(whatsapp_to, body)
