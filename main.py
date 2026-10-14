#!/usr/bin/env python3
# main.py — Inbox Insights (multi-user)
# Run: python main.py

from datetime import datetime

from modules.user_manager import load_users, ConfigError
from modules.gmail_fetcher import fetch_all_accounts
from modules.ai_summarizer import summarize_all
from modules.pdf_generator import generate_pdf
from modules.whatsapp_sender import send_whatsapp_pdf
from modules.logger import get_logger

log = get_logger(__name__)


def process_user(user: dict) -> dict:
    """Run the full pipeline for a single user. Never lets one user's
    failure stop the others — errors are caught and logged per user."""
    user_id = user["user_id"]
    name = user["name"]
    accounts = user["gmail_accounts"]
    whatsapp_to = user["whatsapp_to"]

    status = {
        "user_id": user_id, "name": name, "emails_found": 0,
        "ai_status": "skipped", "pdf_status": "skipped",
        "whatsapp_status": "skipped", "error": None,
    }

    try:
        log.info("=== Processing user: %s (%s) ===", name, user_id)

        emails = fetch_all_accounts(user_id, accounts)
        status["emails_found"] = len(emails)
        if not emails:
            log.info("[%s] No emails found today. Nothing to summarize or send.", user_id)
            return status

        emails = summarize_all(emails)
        status["ai_status"] = "ok"

        pdf_path = generate_pdf(name, accounts, emails)
        status["pdf_status"] = "ok"
        status["pdf_path"] = pdf_path

        sent = send_whatsapp_pdf(pdf_path, whatsapp_to)
        status["whatsapp_status"] = "sent" if sent else "failed_or_skipped"

    except Exception as e:
        log.exception("[%s] Unhandled error while processing user: %s", user_id, e)
        status["error"] = str(e)

    return status


def run():
    start = datetime.now()
    log.info("Run started at %s", start.strftime("%Y-%m-%d %H:%M:%S"))

    try:
        users = load_users(enabled_only=True)
    except ConfigError as e:
        log.error("Cannot start: %s", e)
        return

    all_status = [process_user(user) for user in users]

    end = datetime.now()
    log.info("Run finished at %s (duration: %s)", end.strftime("%Y-%m-%d %H:%M:%S"), end - start)
    _print_summary(all_status)
    return all_status


def _print_summary(all_status):
    print("\n" + "=" * 60)
    print("  Inbox Insights — Run Summary")
    print("=" * 60)
    for s in all_status:
        print(f"\n  User: {s['name']} ({s['user_id']})")
        print(f"    Emails found:  {s['emails_found']}")
        print(f"    AI summary:    {s['ai_status']}")
        print(f"    PDF report:    {s['pdf_status']}")
        print(f"    WhatsApp:      {s['whatsapp_status']}")
        if s.get("error"):
            print(f"    Error:         {s['error']}")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    run()
