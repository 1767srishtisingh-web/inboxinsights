"""
Gmail OAuth (PKCE web flow) and email fetching for Inbox Insights.

- Web OAuth flow using PKCE (RFC 7636)
- Token encrypted at rest via modules.crypto
- Automatic token refresh; sets status='reconnect_needed' on failure
- fetch_today_emails: returns emails received today in user's local timezone
"""
import base64
import email as email_lib
import hashlib
import json
import os
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

import pytz
import requests
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from config.settings import (
    AI_BATCH_SIZE,
    EMAIL_QUERY_FILTER,
    GMAIL_CLIENT_ID,
    GMAIL_CLIENT_SECRET,
    GMAIL_REDIRECT_URI,
    GMAIL_SCOPES,
    HTTP_TIMEOUT,
    MAX_EMAILS_PER_ACCOUNT,
    MAX_RETRIES,
    RETRY_BACKOFF_SECONDS,
    SKIP_LABELS,
)
from modules import crypto
from modules import db as database
from modules.logger import get_logger

log = get_logger(__name__)

_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"

# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------

def _generate_code_verifier() -> str:
    """Generate a PKCE code verifier (43–128 unreserved chars)."""
    # unreserved = ALPHA / DIGIT / "-" / "." / "_" / "~"
    alphabet = (
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    )
    return "".join(secrets.choice(alphabet) for _ in range(96))


def _code_challenge(verifier: str) -> str:
    """SHA-256 hash of verifier, base64url-encoded (no padding)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# ---------------------------------------------------------------------------
# Auth URL / token exchange
# ---------------------------------------------------------------------------

def get_auth_url(user_id: int, label: str) -> tuple[str, str, str]:
    """
    Build a Google OAuth consent URL using PKCE.

    Returns:
        (auth_url, state, code_verifier)
    """
    state = secrets.token_urlsafe(32)
    code_verifier = _generate_code_verifier()
    challenge = _code_challenge(code_verifier)

    params = {
        "client_id": GMAIL_CLIENT_ID,
        "redirect_uri": GMAIL_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(GMAIL_SCOPES),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = f"{_GOOGLE_AUTH_URL}?{urlencode(params)}"

    # Persist state for callback verification
    database.save_oauth_state(state, user_id, code_verifier, label=label)

    return auth_url, state, code_verifier


def exchange_code_for_token(
    code: str,
    code_verifier: str,
    redirect_uri: str = GMAIL_REDIRECT_URI,
) -> dict:
    """
    Exchange an authorization code for a token dict.

    Returns the JSON token dict from Google.
    Raises requests.HTTPError on failure.
    """
    payload = {
        "code": code,
        "client_id": GMAIL_CLIENT_ID,
        "client_secret": GMAIL_CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
    }
    resp = requests.post(_GOOGLE_TOKEN_URL, data=payload, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Credentials helpers
# ---------------------------------------------------------------------------

def build_credentials_from_token(token_dict: dict) -> Credentials:
    """Build a google.oauth2.credentials.Credentials from a token dict."""
    return Credentials(
        token=token_dict.get("access_token"),
        refresh_token=token_dict.get("refresh_token"),
        token_uri=_GOOGLE_TOKEN_URL,
        client_id=GMAIL_CLIENT_ID,
        client_secret=GMAIL_CLIENT_SECRET,
        scopes=GMAIL_SCOPES,
    )


def get_gmail_service(account: dict):
    """
    Decrypt the stored token, refresh if expired, return (service, updated_json_or_None).

    If refresh fails, marks account status='reconnect_needed' and raises RuntimeError.
    """
    token_bytes = account.get("token_encrypted")
    if not token_bytes:
        database.set_gmail_status(account["id"], "reconnect_needed")
        raise RuntimeError(f"No token stored for account {account['id']}")

    token_json = crypto.decrypt_token(bytes(token_bytes))
    token_dict = json.loads(token_json)

    creds = build_credentials_from_token(token_dict)

    updated_json = None
    if creds.expired or not creds.valid:
        try:
            creds.refresh(Request())
            new_token_dict = {
                "access_token": creds.token,
                "refresh_token": creds.refresh_token,
                "token_type": "Bearer",
                "scope": " ".join(creds.scopes or []),
            }
            new_json = json.dumps(new_token_dict)
            encrypted = crypto.encrypt_token(new_json)
            database.update_gmail_token(account["id"], encrypted)
            database.set_gmail_status(account["id"], "ok")
            updated_json = new_json
        except Exception as exc:
            log.error("Token refresh failed for account %s: %s", account["id"], exc)
            database.set_gmail_status(account["id"], "reconnect_needed")
            raise RuntimeError(f"Token refresh failed: {exc}") from exc

    service = build("gmail", "v1", credentials=creds)
    return service, updated_json


# ---------------------------------------------------------------------------
# Email body decoding
# ---------------------------------------------------------------------------

def _strip_emoji(text: str) -> str:
    """Remove emoji characters from a string."""
    emoji_re = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002700-\U000027BF"
        "\U0001F900-\U0001F9FF"
        "\U00002600-\U000026FF"
        "\U00002B50-\U00002B55"
        "\U000025AA-\U000025FE"
        "\u200d"
        "\ufe0f"
        "]+",
        flags=re.UNICODE,
    )
    return emoji_re.sub("", text).strip()


def _decode_payload(payload: dict) -> str:
    """Recursively decode text from a Gmail message payload."""
    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data", "")
    parts = payload.get("parts", [])

    if mime_type == "text/plain" and body_data:
        try:
            return base64.urlsafe_b64decode(body_data + "==").decode("utf-8", errors="replace")
        except Exception:
            return ""

    if mime_type == "text/html" and body_data and not parts:
        try:
            raw = base64.urlsafe_b64decode(body_data + "==").decode("utf-8", errors="replace")
            # Strip HTML tags
            return re.sub(r"<[^>]+>", " ", raw)
        except Exception:
            return ""

    # Multipart — prefer text/plain parts
    plain_text = ""
    html_fallback = ""
    for part in parts:
        if part.get("mimeType") == "text/plain":
            plain_text += _decode_payload(part)
        elif part.get("mimeType") == "text/html":
            html_fallback += _decode_payload(part)
        elif part.get("mimeType", "").startswith("multipart/"):
            plain_text += _decode_payload(part)

    return plain_text or html_fallback


def _extract_header(headers: list[dict], name: str) -> str:
    """Extract a header value by name (case-insensitive)."""
    name_lower = name.lower()
    for h in headers:
        if h.get("name", "").lower() == name_lower:
            return h.get("value", "")
    return ""


# ---------------------------------------------------------------------------
# Main fetch function
# ---------------------------------------------------------------------------

def _retry_request(fn, retries: int = MAX_RETRIES, backoff: int = RETRY_BACKOFF_SECONDS):
    """Execute fn() with exponential backoff on 429/5xx errors."""
    for attempt in range(retries):
        try:
            return fn()
        except Exception as exc:
            msg = str(exc)
            is_retryable = "429" in msg or "500" in msg or "503" in msg
            if is_retryable and attempt < retries - 1:
                wait = backoff * (2 ** attempt)
                log.warning("Retryable error (attempt %d/%d): %s — sleeping %ds",
                            attempt + 1, retries, exc, wait)
                time.sleep(wait)
            else:
                raise


def fetch_today_emails(account: dict, user_timezone: str) -> list[dict]:
    """
    Fetch emails received today (in user_timezone) for a single Gmail account.

    Returns a list of dicts:
        {id, subject, sender, date_str, body_text, internal_date_ms,
         account_label, account_email}
    """
    try:
        service, _ = get_gmail_service(account)
    except RuntimeError as e:
        log.error("Cannot get Gmail service for account %s: %s", account.get("email"), e)
        return []

    # Compute today's local midnight as UTC epoch seconds
    try:
        tz = pytz.timezone(user_timezone)
    except pytz.UnknownTimeZoneError:
        tz = pytz.utc

    now_local = datetime.now(tz)
    today_local = now_local.date()
    midnight_local = tz.localize(
        datetime(today_local.year, today_local.month, today_local.day, 0, 0, 0)
    )
    tomorrow_local = tz.localize(
        datetime(today_local.year, today_local.month, today_local.day, 23, 59, 59)
    )

    start_epoch = int(midnight_local.astimezone(pytz.utc).timestamp())
    end_epoch = int(tomorrow_local.astimezone(pytz.utc).timestamp())
    start_ms = start_epoch * 1000
    end_ms = end_epoch * 1000

    query = f"{EMAIL_QUERY_FILTER} after:{start_epoch} before:{end_epoch}"

    log.info(
        "Fetching emails for %s | tz=%s | query=%s",
        account.get("email"), user_timezone, query,
    )

    # List message IDs
    def _list():
        result = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=MAX_EMAILS_PER_ACCOUNT,
        ).execute()
        return result.get("messages", [])

    try:
        messages_meta = _retry_request(_list)
    except Exception as e:
        log.error("Failed to list messages for %s: %s", account.get("email"), e)
        return []

    if not messages_meta:
        return []

    emails = []
    for meta in messages_meta:
        msg_id = meta["id"]

        def _get_msg(mid=msg_id):
            return service.users().messages().get(
                userId="me",
                id=mid,
                format="full",
            ).execute()

        try:
            msg = _retry_request(_get_msg)
        except Exception as e:
            log.warning("Failed to fetch message %s: %s", msg_id, e)
            continue

        # Double-filter by internalDate
        internal_date_ms = int(msg.get("internalDate", 0))
        if internal_date_ms < start_ms or internal_date_ms >= end_ms:
            continue

        # Skip unwanted labels
        label_ids = set(msg.get("labelIds", []))
        if label_ids & SKIP_LABELS:
            continue

        headers = msg.get("payload", {}).get("headers", [])
        subject = _strip_emoji(_extract_header(headers, "Subject") or "(No Subject)")
        sender = _extract_header(headers, "From") or ""
        date_str = _extract_header(headers, "Date") or ""

        body_text = _decode_payload(msg.get("payload", {}))
        body_text = re.sub(r"\s+", " ", body_text).strip()[:1500]

        emails.append(
            {
                "id": msg_id,
                "subject": subject,
                "sender": sender,
                "date_str": date_str,
                "body_text": body_text,
                "internal_date_ms": internal_date_ms,
                "account_label": account.get("label", ""),
                "account_email": account.get("email", ""),
            }
        )

    log.info(
        "Fetched %d emails for %s", len(emails), account.get("email")
    )
    return emails
