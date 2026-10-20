"""Central configuration — all values from .env."""
import os
import hashlib
import base64
from dotenv import load_dotenv
from cryptography.fernet import Fernet

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Flask
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production-32-chars!!")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 5000))
BASE_URL = os.getenv("BASE_URL", f"http://localhost:{PORT}")  # public https URL for signed links

# Database
DB_PATH = os.getenv("DB_PATH", os.path.join(BASE_DIR, "data", "inbox_insights.db"))

# Paths
OUTPUT_DIR = os.getenv("OUTPUT_DIR", os.path.join(BASE_DIR, "output"))
LOGS_DIR = os.getenv("LOGS_DIR", os.path.join(BASE_DIR, "logs"))
TOKENS_DIR = os.getenv("TOKENS_DIR", os.path.join(BASE_DIR, "tokens"))

# Gmail OAuth (Web Application type)
GMAIL_CLIENT_ID = os.getenv("GMAIL_CLIENT_ID", "")
GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET", "")
GMAIL_REDIRECT_URI = os.getenv("GMAIL_REDIRECT_URI", f"{BASE_URL}/oauth/callback")
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Claude AI
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")
AI_MAX_RETRIES = int(os.getenv("AI_MAX_RETRIES", 3))
AI_BATCH_SIZE = int(os.getenv("AI_BATCH_SIZE", 20))

# Twilio WhatsApp
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

# PDF signed links (served by this Flask app)
PDF_LINK_EXPIRY_HOURS = int(os.getenv("PDF_LINK_EXPIRY_HOURS", 48))

# Retry / network
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", 30))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
RETRY_BACKOFF_SECONDS = int(os.getenv("RETRY_BACKOFF_SECONDS", 5))

# Gmail fetch
EMAIL_QUERY_FILTER = os.getenv("EMAIL_QUERY_FILTER", "in:inbox -in:spam -in:promotions")
SKIP_LABELS = {"CATEGORY_PROMOTIONS", "CATEGORY_SPAM", "SPAM"}
MAX_EMAILS_PER_ACCOUNT = int(os.getenv("MAX_EMAILS_PER_ACCOUNT", 50))

# Security
LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", 8))
LOGIN_LOCKOUT_MINUTES = int(os.getenv("LOGIN_LOCKOUT_MINUTES", 15))

# Fernet encryption key derived from SECRET_KEY (for storing OAuth tokens)
_key_material = hashlib.sha256(SECRET_KEY.encode()).digest()
FERNET_KEY = base64.urlsafe_b64encode(_key_material)

# Ensure directories exist
for _d in [OUTPUT_DIR, LOGS_DIR, TOKENS_DIR, os.path.dirname(DB_PATH)]:
    os.makedirs(_d, exist_ok=True)
