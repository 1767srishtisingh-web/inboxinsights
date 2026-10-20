# ☕ Inbox Insights

> **A public, multi-user web dashboard that automatically delivers a clean, table-only PDF report of your daily emails directly to your WhatsApp every morning.**

![Python 3.10+](https://img.shields.io/badge/Python-3.10+-4A2A26?style=for-the-badge&logo=python&logoColor=FBF7F1)
![Flask](https://img.shields.io/badge/Flask-3.0.3-A3807E?style=for-the-badge&logo=flask&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-WAL_Mode-CFB6C5?style=for-the-badge&logo=sqlite&logoColor=4A2A26)
![Claude AI](https://img.shields.io/badge/Claude-Haiku_4.5-9A3440?style=for-the-badge&logo=anthropic&logoColor=white)
![Twilio WhatsApp](https://img.shields.io/badge/Twilio-WhatsApp_Sandbox-F2D0CB?style=for-the-badge&logo=twilio&logoColor=4A2A26)

---

## 📖 Overview

Inbox Insights solves email overwhelm with extreme minimalism:
1. **Sign Up & Log In**: Create an account with your WhatsApp number and password.
2. **Connect Multiple Gmail Accounts**: Connect your personal, work, and college accounts using secure OAuth 2.0 with PKCE and the read-only `gmail.readonly` scope.
3. **Choose Your Time & Timezone**: Set your preferred delivery time (e.g. 08:00 AM) and timezone (e.g. `Asia/Kolkata`, `America/New_York`).
4. **Automated WhatsApp Delivery**: Every day at your chosen time, the system:
   - Fetches **only** emails received today (00:00:00 to 23:59:59 in your timezone) across all connected Gmail accounts.
   - Extracts one critical actionable deadline per email using **Claude AI** (`claude-haiku-4-5`) with a regex fallback.
   - Compiles an elegant, minimal, 3-column PDF (`#`, `Subject`, `Deadline`).
   - Sends the PDF to your WhatsApp number via Twilio, with a self-hosted private signed expiring link (`/r/<token>`).
5. **On-Demand Dispatch**: Click **"Send today's report now"** on the dashboard anytime.

---

## 🎨 Visual Design — Café & Dessert Aesthetic

Inbox Insights features a bespoke café-themed visual identity across both the web dashboard and generated PDF reports:
- **Cream & Paper**: `#F6EFE6` page background, `#FBF7F1` paper cards.
- **Dusty Mauve**: `#A3807E` hero banner and footer with authentic torn-paper edges.
- **Espresso & Cocoa**: `#4A2A26` dark roast headers & buttons, `#7A5650` warm body text.
- **Pastel Accent Cards**: Soft pink (`#F2D0CB`), peach (`#F3DFCF`), and lavender (`#CFB6C5`).
- **Raspberry Accent**: `#9A3440` highlights actionable deadlines and primary alerts.
- **Typography**: Self-hosted **Playfair Display** (classic high-contrast serif) & **Jost** (geometric sans).
- **Subtle Details**: Animated coffee cup steam (respects `prefers-reduced-motion`), soft shadows, and paper grain.

---

## 📄 PDF Report Specification

The generated PDF report is strictly minimal, organized, and tabular:
- **Header**: Report date (e.g. `Tuesday, 20 October 2026`), followed by `Name · N emails · N deadlines` in the mauve band with torn-paper zigzag.
- **One Table, Three Columns**:
  1. `#` — Row number (1, 2, 3...)
  2. `Subject` — Email subject wrapped inside cell (Devanagari supported, emoji stripped)
  3. `Deadline` — Actionable deadline highlighted in raspberry (e.g. `24 Oct 2026, 11:59 PM – submit assignment`), or `—`
- **Chronological Order**: Emails are strictly sorted in the order received (oldest first).
- **Repeating Header & Pagination**: Table headers repeat across page breaks; "Page X of Y" footer.
- **No Spam / No Clutter**: No summaries, body text, sender clutter, or priority tags.

---

## 🏗️ Architecture & Directory Tree

```
inboxinsights/
├── app.py                  # Flask web dashboard (Waitress WSGI, routes, OAuth, CSRF)
├── main.py                 # Manual CLI report runner (--user N, --no-send)
├── scheduler.py            # Per-user timezone delivery engine (30s interval thread)
├── requirements.txt        # Python package dependencies
├── .env.example            # Environment template with full documentation
├── SETUP_GUIDE.md          # Beginner-friendly setup instructions
├── PROMPT.md               # Claude AI extraction prompt & regex spec
├── config/
│   └── settings.py         # Central configuration & Fernet encryption key derivation
├── modules/
│   ├── db.py               # SQLite database with thread-local connections & WAL mode
│   ├── crypto.py           # Fernet encryption for Google OAuth refresh tokens
│   ├── gmail_fetcher.py    # Gmail OAuth (PKCE) + strict today-only message fetcher
│   ├── ai_extractor.py     # Batched Claude deadline extraction + regex fallback
│   ├── pdf_generator.py    # fpdf2 generator with torn-paper header & 3-column table
│   ├── whatsapp_sender.py  # Twilio WhatsApp sender with private expiring /r/<token> links
│   ├── pipeline.py         # End-to-end pipeline orchestrator for a single user
│   └── logger.py           # Rotating file logger (logs/application.log)
├── templates/
│   ├── base.html           # Master layout with nav, flash notifications & footer
│   ├── index.html          # Café-themed landing page with SVG illustrations & cards
│   ├── register.html       # Sign-up page with WhatsApp validation & timezone selector
│   ├── login.html          # Sign-in page with login throttling protection
│   ├── dashboard.html      # User dashboard with account cards, settings & report history
│   └── error.html          # Custom error page (404, 410, 500) with illustration
└── static/
    ├── css/
    │   └── style.css       # Full café-theme CSS with responsive design (390px+)
    ├── fonts/              # Self-hosted Playfair Display and Jost fonts
    └── img/                # Favicon and coffee cup SVGs
```

---

## 🔒 Security & Privacy Features

- **Passwords**: Hashed with Werkzeug `scrypt`.
- **Login Throttling**: Automatically locks out an account after 8 failed attempts for 15 minutes.
- **CSRF Protection**: All forms protected with Flask-WTF CSRF tokens.
- **Secure Sessions**: `HttpOnly`, `SameSite=Lax` cookies (and `Secure` on HTTPS).
- **OAuth Security**: PKCE (`S256`), `access_type=offline`, state verification, and encrypted token storage (`Fernet` key derived from `SECRET_KEY`).
- **Private PDF Delivery**: Reports are **never** uploaded to third-party public hosts. They are served directly from the application through private, signed URLs (`/r/<token>`) that expire after 48 hours.
- **Scoped Permissions**: Requests strictly `gmail.readonly` — never send or delete privileges.
- **Full Account Deletion**: Users can delete their account at any time, wiping credentials, tokens, and all generated PDFs from disk.

---

## 🚀 Quick Start

### 1. Clone & Setup Environment
```bash
git clone https://github.com/your-username/inboxinsights.git
cd inboxinsights
py -3.12 -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate  # macOS / Linux
pip install -r requirements.txt
```

### 2. Configure Settings
```bash
cp .env.example .env
```
Open `.env` and fill in your values (Google OAuth, Twilio Sandbox, Anthropic API Key).

### 3. Run the Application
```bash
python app.py
```
Visit `http://localhost:5000` in your web browser.

### 4. Run CLI On Demand
```bash
python main.py             # Run all users
python main.py --user 1    # Run specific user
python main.py --no-send   # Test run without dispatching WhatsApp messages
```

---

## 📄 License
MIT License. Built with ☕ and Python.
