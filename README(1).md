# Inbox Insights

AI-powered, multi-user email dashboard that collects today's Gmail messages
across multiple accounts per user, summarizes them with Claude, builds a
professional PDF report, and delivers it to each user's WhatsApp number —
fully automated, on a daily schedule.

## Features

- **Unlimited users**, each fully isolated (own name, own Gmail accounts,
  own WhatsApp number, own tokens, own PDF report). Not hardcoded to 5 —
  just add rows to `users/users.json`.
- **Multiple Gmail accounts per user**, combined into one daily report.
- **Today-only fetching** — the Gmail query is anchored to local midnight,
  so old emails never leak into a report.
- **Claude AI summaries**: summary, action items, deadlines, key points,
  and a High/Medium/Low priority for every email.
- **Professional PDF report** per user via `fpdf2` (no paid rendering
  service).
- **WhatsApp-only delivery** via Twilio's free Sandbox. Telegram has been
  removed.
- **Configurable daily automation** (`scheduler.py`, time set in `.env`).
- **Structured logging** to `logs/application.log` (start/end time, users
  processed, email counts, AI/PDF/WhatsApp status, and errors).
- **Resilience**: expired/invalid Gmail tokens are detected and
  re-authenticated automatically; network and rate-limit errors are
  retried with backoff; one user's failure never blocks the others.

## Folder structure

```
Inbox_Insights/
├── config/
│   └── settings.py          # all configuration, env-driven
├── modules/
│   ├── logger.py             # centralized logging
│   ├── user_manager.py       # loads/validates users.json
│   ├── gmail_fetcher.py       # OAuth + today-only email fetch
│   ├── ai_summarizer.py       # Claude summaries + priority
│   ├── pdf_generator.py       # per-user PDF report
│   └── whatsapp_sender.py     # Twilio WhatsApp delivery
├── users/
│   └── users.example.json    # copy to users.json and edit
├── tokens/                    # per-user, per-account OAuth tokens (generated)
├── logs/                      # application.log (generated)
├── output/                    # generated PDF reports
├── templates/                 # reserved for future PDF/HTML templates
├── main.py                    # runs the pipeline for every enabled user
├── scheduler.py                # runs main.py daily at REPORT_TIME
├── requirements.txt
├── .env.example
└── SETUP_GUIDE.md              # step-by-step beginner setup
```

## Quick start

See **SETUP_GUIDE.md** for the full beginner walkthrough. Short version:

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env           # then fill in your keys
cp users/users.example.json users/users.json   # then fill in your users
python main.py                 # first run opens a browser per Gmail account for OAuth
python scheduler.py            # keep this running for daily automation
```

## Privacy note on WhatsApp delivery

Twilio's free WhatsApp Sandbox requires a **public URL** for any file
attachment. This project uploads the generated PDF (which contains real
email content) to `0x0.st`, a free anonymous file host with no login —
anyone who gets the link can open it until it expires. This is a direct
consequence of the "free resources only" requirement; there is no fully
free way to give Twilio a private, authenticated media URL without
running your own server. If your email content is sensitive, set
`PDF_PUBLIC_HOST_ENABLED=false` in `.env`, which disables WhatsApp
delivery rather than upload the file, and instead read the PDF straight
from `output/`.

## Free resources used

| Purpose         | Service                  | Free tier |
|------------------|---------------------------|-----------|
| Email fetching   | Gmail API                | Free |
| AI summarization | Anthropic Claude API      | Free signup credit |
| PDF generation   | fpdf2 (local library)     | Free, no service |
| WhatsApp delivery| Twilio WhatsApp Sandbox   | Free, no card required for sandbox |
| File hosting for attachments | 0x0.st        | Free, anonymous, temporary |

## Future improvements

- Per-user report times instead of one global `REPORT_TIME`.
- Optional private file storage (e.g. a small self-hosted server) to
  avoid the public-host privacy tradeoff above.
- Web UI for managing `users.json` instead of hand-editing JSON.
- Retry queue for failed WhatsApp deliveries instead of a single attempt
  per run.
