# modules/gmail_fetcher.py
"""
Gmail OAuth 2.0 fetcher — multi-user, multi-account, today-only.

Bug fixes vs. the original prototype:
  * Was filtering "is:unread OR is:important" (could pull in emails from
    days/weeks ago). Now scopes every query to TODAY only, using Gmail's
    `after:<unix_epoch_seconds>` operator anchored to local midnight.
  * Token files were shared/global (token_<alias>.json). Now each
    user+account pair gets its own isolated token file so accounts never
    cross between users.
  * `invalid_grant` / expired-refresh-token errors used to crash the
    whole run. Now the stale token is deleted and re-auth is attempted
    once before giving up on that single account (other accounts/users
    still proceed).
"""

import os
import base64
import time
from datetime import datetime
from typing import List, Dict

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config.settings import (
    GMAIL_CREDENTIALS_FILE, GMAIL_SCOPES, MAX_EMAILS_PER_ACCOUNT,
    SKIP_LABELS, EMAIL_QUERY_FILTER, TOKENS_DIR, MAX_RETRIES, RETRY_BACKOFF_SECONDS,
)
from modules.user_manager import token_path_for
from modules.logger import get_logger

log = get_logger(__name__)


def _today_after_query() -> str:
    """Gmail `after:` wants a unix timestamp anchored to local midnight."""
    midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return f"after:{int(midnight.timestamp())}"


def _get_credentials(user_id: str, alias: str) -> Credentials:
    os.makedirs(TOKENS_DIR, exist_ok=True)
    token_path = token_path_for(user_id, alias, TOKENS_DIR)
    creds = None

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, GMAIL_SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(token_path, "w") as fh:
                fh.write(creds.to_json())
            return creds
        except RefreshError as e:
            # invalid_grant lands here — the refresh token was revoked/expired.
            log.warning(
                "[%s/%s] Refresh token invalid (%s). Deleting stale token, "
                "re-authenticating.", user_id, alias, e,
            )
            os.remove(token_path)

    # No usable token — run the interactive OAuth flow once.
    # In the cloud (GitHub Actions) there is no browser, so waiting for a
    # login would just hang until the job times out. Fail fast instead.
    if os.getenv("INBOX_HEADLESS") == "1":
        raise RuntimeError(
            f"[{user_id}/{alias}] No valid Gmail token in the cloud. Run "
            "`python main.py` on your laptop to log in again, then run "
            "`python tools/make_github_secrets.py` and update the "
            "GMAIL_TOKENS_B64 secret on GitHub."
        )
    if not os.path.exists(GMAIL_CREDENTIALS_FILE):
        raise FileNotFoundError(
            f"Gmail OAuth client file not found at {GMAIL_CREDENTIALS_FILE}. "
            "Download it from Google Cloud Console → APIs & Services → "
            "Credentials, and point GMAIL_CREDENTIALS_FILE at it in .env."
        )
    flow = InstalledAppFlow.from_client_secrets_file(GMAIL_CREDENTIALS_FILE, GMAIL_SCOPES)
    creds = flow.run_local_server(port=0)
    with open(token_path, "w") as fh:
        fh.write(creds.to_json())
    return creds


def _decode_body(payload: dict) -> str:
    body = ""
    if "parts" in payload:
        for part in payload["parts"]:
            body += _decode_body(part)
    elif payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            try:
                body = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
            except Exception:
                body = ""
    return body


def _categorize(labels: List[str]) -> str:
    s = set(labels)
    if s & {"CATEGORY_WORK"}:
        return "Work"
    if s & {"CATEGORY_PERSONAL"}:
        return "Personal"
    if s & {"CATEGORY_UPDATES", "CATEGORY_FINANCE"}:
        return "Finance"
    return "General"


def _with_retries(fn, *args, description: str, **kwargs):
    """Retry transient network/API errors with backoff; give up on the rest."""
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except HttpError as e:
            last_err = e
            status = getattr(e, "status_code", None) or getattr(e.resp, "status", None)
            if status and int(status) < 500 and int(status) != 429:
                raise  # non-retryable (auth/permission/bad request)
            log.warning("%s failed (attempt %d/%d): %s", description, attempt, MAX_RETRIES, e)
        except (ConnectionError, TimeoutError) as e:
            last_err = e
            log.warning("%s network error (attempt %d/%d): %s", description, attempt, MAX_RETRIES, e)
        time.sleep(RETRY_BACKOFF_SECONDS * attempt)
    raise last_err


def fetch_emails(user_id: str, alias: str) -> List[Dict]:
    """Fetch TODAY's emails for one Gmail account belonging to one user."""
    creds = _get_credentials(user_id, alias)
    service = build("gmail", "v1", credentials=creds)

    query = f"{EMAIL_QUERY_FILTER} {_today_after_query()}"
    results = _with_retries(
        lambda: service.users().messages().list(
            userId="me", q=query, maxResults=MAX_EMAILS_PER_ACCOUNT
        ).execute(),
        description=f"list messages [{user_id}/{alias}]",
    )

    emails = []
    for ref in results.get("messages", []):
        try:
            msg = _with_retries(
                lambda: service.users().messages().get(
                    userId="me", id=ref["id"], format="full"
                ).execute(),
                description=f"get message {ref['id']}",
            )
        except HttpError as e:
            log.error("[%s/%s] Could not fetch message %s: %s", user_id, alias, ref["id"], e)
            continue

        labels = msg.get("labelIds", [])
        if SKIP_LABELS & set(labels):
            continue

        hdrs = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        body = _decode_body(msg["payload"])

        emails.append({
            "id": msg["id"],
            "sender": hdrs.get("From", "Unknown"),
            "subject": hdrs.get("Subject", "(no subject)"),
            "date": hdrs.get("Date", ""),
            "snippet": msg.get("snippet", ""),
            "body": body[:3000],
            "category": _categorize(labels),
            "labels": labels,
            "account": alias,
        })
    return emails


def fetch_all_accounts(user_id: str, gmail_accounts: List[Dict]) -> List[Dict]:
    """Fetch today's emails from every Gmail account configured for one user."""
    all_emails = []
    for account in gmail_accounts:
        alias = account["alias"]
        log.info("[%s] Fetching account: %s (%s)", user_id, alias, account.get("label", alias))
        try:
            all_emails.extend(fetch_emails(user_id, alias))
        except FileNotFoundError as e:
            log.error("[%s/%s] %s", user_id, alias, e)
        except HttpError as e:
            log.error("[%s/%s] Gmail API error: %s", user_id, alias, e)
        except Exception as e:
            log.error("[%s/%s] Unexpected error: %s", user_id, alias, e)
    return all_emails
