# ☕ Inbox Insights — Complete Windows Setup Guide

A beginner-friendly, step-by-step walkthrough to get Inbox Insights up and running on Windows from scratch.

---

## 📋 Prerequisites

Before starting, make sure you have:
1. **Python 3.10+ (Recommended: Python 3.12)**: Download from [python.org](https://www.python.org/downloads/). Check "Add python.exe to PATH" during installation.
2. **A Google Account**: To access Google Cloud Console and set up OAuth credentials.
3. **A Free Twilio Account**: To send WhatsApp messages via the Twilio WhatsApp Sandbox ([twilio.com](https://www.twilio.com)).
4. **An Anthropic Account** *(Optional but recommended)*: To obtain a Claude API key for AI deadline extraction ([console.anthropic.com](https://console.anthropic.com)). If omitted, the app will automatically use the built-in regex fallback.

---

## 🛠️ Step 1: Open Terminal & Set Up Python Virtual Environment

1. Open PowerShell or Command Prompt.
2. Navigate to the project directory:
   ```powershell
   cd C:\Users\Asus\OneDrive\Desktop\inboxinsights
   ```
3. Create and activate a Python virtual environment:
   ```powershell
   py -3.12 -m venv venv
   .\venv\Scripts\Activate.ps1
   ```
   *(If PowerShell gives an execution policy error, run `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`, then try activating again).*

4. Install the required dependencies:
   ```powershell
   pip install -r requirements.txt
   ```

---

## 🔑 Step 2: Configure Google Cloud OAuth (Web Application)

To allow users to connect their Gmail accounts, you need an OAuth 2.0 Web Application client:

1. Visit the **[Google Cloud Console](https://console.cloud.google.com/)**.
2. Create a new project:
   - Click the project dropdown at the top left → **New Project**.
   - Name it `Inbox Insights` → click **Create**.
3. Enable the **Gmail API**:
   - Go to **APIs & Services** → **Library**.
   - Search for `Gmail API` → click on it → click **Enable**.
4. Configure the **OAuth Consent Screen**:
   - Go to **APIs & Services** → **OAuth consent screen**.
   - Choose **External** → click **Create**.
   - **App name**: `Inbox Insights`
   - **User support email**: Choose your email address.
   - **Developer contact information**: Enter your email address.
   - Click **Save and Continue**.
5. Add the Read-Only Scope:
   - Click **Add or Remove Scopes**.
   - In the filter box, type `gmail.readonly` and check `https://www.googleapis.com/auth/gmail.readonly`.
   - Click **Update** → **Save and Continue**.
6. **IMPORTANT: Add Test Users**:
   - While the app is in "Testing" mode, **only approved test users can log in**.
   - Under **Test users**, click **+ Add Users**.
   - Enter your Gmail address (and any friends' addresses you want to test with).
   - Click **Save and Continue**.
7. Create OAuth Client Credentials:
   - Go to **APIs & Services** → **Credentials**.
   - Click **+ Create Credentials** → **OAuth client ID**.
   - **Application type**: Select **Web application** (*NOT Desktop App*).
   - **Name**: `Inbox Insights Web Client`.
   - **Authorized redirect URIs**: Click **+ Add URI** and enter:
     ```
     http://localhost:5000/oauth/callback
     ```
   - Click **Create**.
   - A modal will appear with your **Client ID** and **Client Secret**. Copy both values for your `.env` file!

---

## 💬 Step 3: Set Up Twilio WhatsApp Sandbox

Twilio's free WhatsApp sandbox lets you send WhatsApp messages without business verification:

1. Sign up for a free account at **[twilio.com](https://www.twilio.com/)**.
2. Go to the **Twilio Console**.
3. Under **Account Info**, find and copy:
   - **Account SID** (e.g. `ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`)
   - **Auth Token**
4. Navigate to **Messaging** → **Try it out** → **Send a WhatsApp message**.
5. Look at the on-screen instructions:
   - Twilio will provide a phone number (e.g., `+1 415 523 8886`) and a unique code (e.g., `join purple-fox`).
6. From your phone's WhatsApp:
   - Send that exact message (`join <your-code>`) to `+1 415 523 8886`.
   - You will immediately receive a reply confirming: *"You are all set! The sandbox is joined."*

---

## 🤖 Step 4: Get an Anthropic API Key (Claude)

1. Sign up or log in at **[console.anthropic.com](https://console.anthropic.com/)**.
2. Go to **API Keys** → **Create Key**.
3. Give it a name like `Inbox Insights` and copy the secret key (`sk-ant-...`).

---

## ⚙️ Step 5: Configure `.env` File

1. In the project directory, copy `.env.example` to `.env`:
   ```powershell
   Copy-Item .env.example .env
   ```
2. Open `.env` in Notepad:
   ```powershell
   notepad .env
   ```
3. Fill in your credentials:
   ```ini
   SECRET_KEY=9f8e7d6c5b4a3210fedcba9876543210abcdef0123456789abcdef0123456789
   BASE_URL=http://localhost:5000

   GMAIL_CLIENT_ID=your-client-id.apps.googleusercontent.com
   GMAIL_CLIENT_SECRET=your-client-secret
   GMAIL_REDIRECT_URI=http://localhost:5000/oauth/callback

   ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   CLAUDE_MODEL=claude-haiku-4-5

   TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   TWILIO_AUTH_TOKEN=your-twilio-auth-token
   TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
   TWILIO_SANDBOX_WORD=join your-sandbox-word
   ```
4. Save and close Notepad.

---

## 🌐 Step 6: Making the App Public with ngrok (For WhatsApp PDF Attachments)

Twilio requires a public HTTPS URL to download media files (the PDF report) and attach them directly to WhatsApp messages. If your app is only running on `http://localhost:5000`, the report link will still be sent as text, but the PDF won't be attached directly.

To enable direct PDF attachments:
1. Install ngrok using winget:
   ```powershell
   winget install ngrok
   ```
   *(Or download from [ngrok.com](https://ngrok.com) and extract `ngrok.exe`).*
2. Start the tunnel in a separate command window:
   ```powershell
   ngrok http 5000
   ```
3. Copy the `Forwarding` HTTPS URL (e.g., `https://a1b2-c3d4.ngrok-free.app`).
4. Update `.env`:
   ```ini
   BASE_URL=https://a1b2-c3d4.ngrok-free.app
   GMAIL_REDIRECT_URI=https://a1b2-c3d4.ngrok-free.app/oauth/callback
   ```
5. In **Google Cloud Console** → **Credentials** → click your OAuth Web Client:
   - Add `https://a1b2-c3d4.ngrok-free.app/oauth/callback` to **Authorized redirect URIs**.
   - Click **Save**.

---

## ▶️ Step 7: Launch the Application

1. In your active virtual environment terminal, start the server:
   ```powershell
   python app.py
   ```
2. Open your web browser and navigate to:
   ```
   http://localhost:5000
   ```
   *(or your ngrok URL).*
3. Create your account with your WhatsApp number (e.g. `+919876543210`) and password.
4. On the dashboard:
   - Click **Add a Gmail account**.
   - Sign in with your Google Account and grant read-only access.
   - Adjust your delivery time or click **Send today's report now** to test immediately!

---

## 🩺 Troubleshooting Guide

| Problem | Root Cause | Solution |
| :--- | :--- | :--- |
| **`redirect_uri_mismatch`** | The redirect URI sent does not match what is registered in Google Cloud Console. | Open Google Cloud Console → Credentials → Web Client. Ensure `http://localhost:5000/oauth/callback` (or your ngrok callback) is listed **identically** under Authorized redirect URIs. |
| **`Access blocked: This app has not been verified`** | Google OAuth is in "Testing" mode and your email is not in the test list. | Go to Google Cloud Console → OAuth consent screen → **Test users** → Add your Gmail address. |
| **WhatsApp message not received** | You haven't joined the Twilio Sandbox from your phone. | Open WhatsApp on your phone and send `join <your-sandbox-word>` to `+1 415 523 8886`. |
| **PDF link says "Expired" (410 Gone)** | The 48-hour expiration window has elapsed. | Each report token is valid for 48 hours for privacy. Use the dashboard to view recent reports or regenerate a report. |
| **No emails in PDF** | You didn't receive any emails today or they were categorized as spam/promotions. | Inbox Insights strictly fetches emails received **today** (00:00 to 23:59:59 in your timezone). Send yourself a test email to your connected Gmail, then click "Send today's report now". |
| **Port 5000 in use** | Another service is using port 5000. | Change `PORT=5001` in `.env` and update your redirect URIs accordingly. |
| **Database error** | Corrupted SQLite database file. | Delete `data/inbox_insights.db`. The application will automatically regenerate clean tables on the next startup. |
