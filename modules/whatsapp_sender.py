# modules/whatsapp_sender.py
"""
WhatsApp delivery via Twilio (free sandbox — no paid plan required).

Telegram support has been removed entirely per project requirements —
WhatsApp is now the only delivery channel.

PRIVACY NOTE (please read):
  Twilio needs a public URL to attach the PDF to a WhatsApp message.
  This module uploads the report to 0x0.st, a free, anonymous file
  host with NO authentication — anyone who obtains the link can open
  it until it expires. Since the PDF contains real email content, this
  is a genuine tradeoff of the "free resources only" requirement.
  Set PDF_PUBLIC_HOST_ENABLED=false in .env to disable delivery rather
  than risk that if your emails are sensitive; you'll then need a
  private file host (e.g. your own server, or a Twilio paid Media API)
  to send WhatsApp attachments safely.
"""

import time
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from config.settings import (
    TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM,
    PDF_PUBLIC_HOST_ENABLED, HTTP_TIMEOUT, MAX_RETRIES, RETRY_BACKOFF_SECONDS,
)
from modules.logger import get_logger

log = get_logger(__name__)


def send_whatsapp_pdf(pdf_path: str, whatsapp_to: str, message: str = None) -> bool:
    """Send a WhatsApp message with the PDF as a media attachment to one user."""
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, whatsapp_to]):
        log.warning("[WhatsApp] Twilio credentials or recipient number not set — skipping.")
        return False

    if not PDF_PUBLIC_HOST_ENABLED:
        log.warning(
            "[WhatsApp] PDF_PUBLIC_HOST_ENABLED=false — refusing to upload the report "
            "to a public host. Configure a private file host to enable delivery."
        )
        return False

    pdf_url = _upload_to_0x0(pdf_path)
    if not pdf_url:
        return False

    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    body = message or "Your Inbox Insights report is ready. See attached PDF."

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            msg = client.messages.create(
                from_=TWILIO_WHATSAPP_FROM,
                to=whatsapp_to,
                body=body,
                media_url=[pdf_url],
            )
            log.info("[WhatsApp] Sent to %s. SID: %s", whatsapp_to, msg.sid)
            return True
        except TwilioRestException as e:
            # Common cases: 21211 invalid 'To' number, 63016 template/session
            # window issues, 20003 auth failure. 4xx errors won't fix themselves.
            log.error("[WhatsApp] Twilio error %s: %s", e.code, e.msg)
            if 400 <= (e.status or 0) < 500:
                return False
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)
        except Exception as e:
            log.error("[WhatsApp] Unexpected error (attempt %d/%d): %s", attempt, MAX_RETRIES, e)
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    return False


def _upload_to_0x0(file_path: str) -> str:
    """Upload file to 0x0.st temp host and return its public URL."""
    import requests
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with open(file_path, "rb") as f:
                resp = requests.post("https://0x0.st", files={"file": f}, timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
            url = resp.text.strip()
            log.info("[WhatsApp] PDF uploaded to temporary public host: %s", url)
            return url
        except requests.RequestException as e:
            log.warning("[WhatsApp] Upload failed (attempt %d/%d): %s", attempt, MAX_RETRIES, e)
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)
    log.error("[WhatsApp] Giving up on PDF upload after %d attempts.", MAX_RETRIES)
    return ""
