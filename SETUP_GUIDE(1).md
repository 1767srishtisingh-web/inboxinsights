# Setup Guide (Beginner-Friendly, Windows-focused)

## 1. Install software

- **Python 3.10+**: https://www.python.org/downloads/ — during install,
  check "Add python.exe to PATH".
- **Git** (optional, only if cloning from GitHub): https://git-scm.com

## 2. Get the project onto your PC

Unzip `Inbox_Insights.zip` anywhere, e.g. `C:\Projects\Inbox_Insights`.

## 3. Create and activate a virtual environment

```powershell
cd C:\Projects\Inbox_Insights
python -m venv venv
venv\Scripts\activate
```

You'll know it worked when your prompt shows `(venv)` at the start.

## 4. Install dependencies

```powershell
pip install -r requirements.txt
```

## 5. Create your `.env` file

```powershell
copy .env.example .env
```

Open `.env` in a text editor and fill in:
- `ANTHROPIC_API_KEY` — from https://console.anthropic.com
- `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` — from https://www.twilio.com

## 6. Enable the Gmail API and download OAuth credentials

1. Go to https://console.cloud.google.com and create (or select) a project.
2. APIs & Services → Library → search "Gmail API" → **Enable**.
3. APIs & Services → Credentials → **Create Credentials** → OAuth client ID.
4. Application type: **Desktop app**.
5. Download the JSON file it generates.
6. Rename it to `credentials.json` and place it in the project root
   (or point `GMAIL_CREDENTIALS_FILE` in `.env` at wherever you saved it).

**Important:** treat this file like a password. Never commit it to
GitHub or share it — anyone with it can request access to Gmail accounts
under your Google Cloud project. `.gitignore` already excludes it and
any `client_secret*.json` file, but double-check before pushing to a
public repo.

## 7. Authenticate each Gmail account

You don't do this manually ahead of time — the first time `main.py` runs,
it will open a browser window for **each** Gmail account listed in
`users.json` that doesn't already have a saved token. Log into that
Gmail account, approve access, and a token file is saved automatically
under `tokens/`. You won't be asked again unless that token expires or
is revoked.

## 8. Configure your users (unlimited, not just 5)

```powershell
copy users\users.example.json users\users.json
```

Edit `users/users.json`. Add one object per user:

```json
{
  "user_id": "user3",
  "name": "Alex Kumar",
  "enabled": true,
  "whatsapp_to": "whatsapp:+91ZZZZZZZZZZ",
  "gmail_accounts": [
    { "alias": "personal", "label": "Personal Gmail" }
  ]
}
```

- `user_id` must be unique.
- `whatsapp_to` must include the `whatsapp:` prefix and country code.
- Each user can list as many `gmail_accounts` as they want.
- Set `"enabled": false` to temporarily pause a user without deleting them.

### WhatsApp Sandbox: each user must opt in once

Twilio's free sandbox requires every recipient phone number to text
`join <your-sandbox-word>` to the Twilio sandbox number **once**, from
the phone that owns `whatsapp_to`. Find your sandbox word in the Twilio
Console under Messaging → Try it out → Send a WhatsApp message.

## 9. Schedule the daily run

Set your preferred time in `.env`:

```
REPORT_TIME=17:00
```

Then start the scheduler and leave it running:

```powershell
python scheduler.py
```

It runs once immediately, then every day at `REPORT_TIME`.

## 10. Run manually and verify each stage

```powershell
python main.py
```

Check the console output and `logs/application.log` for a per-user
breakdown of:
- Gmail authentication / fetch
- AI summarization
- PDF generation (saved under `output/`)
- WhatsApp delivery

## 11. Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `invalid_grant` | Gmail refresh token expired or was revoked | Delete the matching file in `tokens/` and re-run `main.py` to re-authenticate. |
| `Bad Request` from Gmail API | Malformed query or missing scope | Check `EMAIL_QUERY_FILTER` in `.env`; confirm Gmail API is enabled for your project. |
| WhatsApp message never arrives | User hasn't joined the sandbox | Have them text `join <sandbox-word>` to the Twilio number. |
| WhatsApp upload/send fails | Twilio credentials wrong, or `PDF_PUBLIC_HOST_ENABLED=false` | Check `.env` values; check `logs/application.log` for the exact Twilio error code. |
| `ModuleNotFoundError` | Dependencies not installed, or venv not activated | Run `venv\Scripts\activate` then `pip install -r requirements.txt` again. |
| No emails in report | No new mail matching filter today | Check `EMAIL_QUERY_FILTER`; confirm the Gmail account actually has mail from today. |

## 12. Updating user configuration later

Just edit `users/users.json` — no code changes needed. Add, remove, or
disable users, or add more Gmail accounts to an existing user, at any
time. Restart `scheduler.py` (or wait for the next scheduled run) to
pick up the changes.

## 13. Running continuously on a Windows PC

Simplest option: keep a terminal window open running `python
scheduler.py`. For something more durable:

- Use **Task Scheduler** to run `python main.py` once daily at your
  chosen time instead of running `scheduler.py` continuously (skips the
  need to keep a terminal open).
- Or wrap `scheduler.py` as a Windows service using a tool like
  `nssm` (Non-Sucking Service Manager), which is free.
