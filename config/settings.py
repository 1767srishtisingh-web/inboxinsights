# config/settings.py
"""
Central configuration. Nothing here is hardcoded per-user — user data
lives in users/users.json. Everything else is driven by environment
variables so the app can move between machines without code changes.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─── Paths ───────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

USERS_CONFIG_FILE = os.getenv(
    "USERS_CONFIG_FILE", os.path.join(BASE_DIR, "users", "users.json")
)
TOKENS_DIR = os.getenv("TOKENS_DIR", os.path.join(BASE_DIR, "tokens"))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", os.path.join(BASE_DIR, "output"))
LOGS_DIR = os.getenv("LOGS_DIR", os.path.join(BASE_DIR, "logs"))

# ─── Gmail OAuth ─────────────────────────────────────────────────────
# One Google Cloud OAuth client (credentials.json) is shared across all
# users/accounts — each Gmail account still authorizes independently and
# gets its own token file under TOKENS_DIR.
GMAIL_CREDENTIALS_FILE = os.getenv(
    "GMAIL_CREDENTIALS_FILE", os.path.join(BASE_DIR, "credentials.json")
)
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Base query applied to every account, in ADDITION to the "today only"
# date filter that gmail_fetcher.py adds automatically.
EMAIL_QUERY_FILTER = os.getenv(
    "EMAIL_QUERY_FILTER", "in:inbox -in:spam -in:promotions"
)
SKIP_LABELS = {"CATEGORY_PROMOTIONS", "CATEGORY_SPAM", "SPAM"}
MAX_EMAILS_PER_ACCOUNT = int(os.getenv("MAX_EMAILS_PER_ACCOUNT", 50))

# ─── AI (Anthropic / Claude) ─────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")
AI_MAX_RETRIES = int(os.getenv("AI_MAX_RETRIES", 3))

# ─── WhatsApp (Twilio) ───────────────────────────────────────────────
# WhatsApp is the ONLY delivery channel. Telegram has been removed.
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

# Public file host used to give Twilio a media URL for the PDF.
# WARNING: this uploads the report (which contains email content) to a
# public, anonymous, unauthenticated host. Anyone with the link can open
# it until it expires. See README "Privacy note on WhatsApp delivery".
PDF_PUBLIC_HOST_ENABLED = os.getenv("PDF_PUBLIC_HOST_ENABLED", "true").lower() == "true"

# ─── Automation ───────────────────────────────────────────────────────
REPORT_TIME = os.getenv("REPORT_TIME", "17:00")  # 24h HH:MM, used by scheduler.py

# ─── Networking / retries ────────────────────────────────────────────
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", 30))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
RETRY_BACKOFF_SECONDS = int(os.getenv("RETRY_BACKOFF_SECONDS", 5))
