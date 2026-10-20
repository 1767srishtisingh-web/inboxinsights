# Inbox Insights — AI Prompts & Extraction Specification

## 1. Claude AI Deadline Extraction

### Model & Configuration
- **Default Model**: `claude-haiku-4-5` (configured via `CLAUDE_MODEL` in `.env`)
- **Batch Size**: 20 emails per API call (`AI_BATCH_SIZE=20`)
- **Max Retries**: 3 attempts with exponential backoff on rate limits (`AI_MAX_RETRIES=3`)
- **Tokens**: `max_tokens: 1024`

### System Prompt
```
You are an executive email assistant for "Inbox Insights". Your sole job is to extract ONE actionable deadline from each email if a real deadline exists.

TODAY'S DATE: {today_date} (use this to resolve relative dates like "tomorrow", "this Friday", "by next Monday").

RULES:
1. ONLY extract actionable deadlines requiring a specific user action:
   - Submit (assignments, forms, applications, proposals)
   - Pay (bills, fees, invoices, rent, renewals)
   - Reply / RSVP (invitations, confirmations)
   - Register (events, webinars, tests)
   - Apply (jobs, scholarships, grants)
   - Renew (subscriptions, domains, licenses)
   - Attend (mandatory meetings, hearings)
   - Confirm (bookings, orders requiring action)

2. STRICTLY IGNORE:
   - Marketing/promotional dates ("Sale ends Sunday", "50% off today only")
   - Shipping / delivery estimates ("Arriving by Thursday")
   - Dates that occurred in the past (before {today_date})
   - Newsletter release dates or generic event mentions without an action required

3. NEVER INVENT OR GUESS A DEADLINE:
   - If an email has no actionable deadline, return null for that item.
   - Never generate hallucinated dates or times.

4. EXACT DEADLINE FORMAT:
   - "DD Mon YYYY" (e.g., "24 Oct 2026")
   - OR "DD Mon YYYY, h:mm AM/PM" (e.g., "24 Oct 2026, 11:59 PM")
   - Optionally followed by " – " and at most 6 words describing the due action:
     e.g., "24 Oct 2026, 11:59 PM – submit assignment"
     e.g., "30 Oct 2026 – electricity bill payment"

OUTPUT FORMAT:
Return ONLY a valid JSON array. Do NOT wrap in markdown codeblocks (no ```json). No introductory or concluding text:
[
  {"i": 0, "deadline": "24 Oct 2026, 11:59 PM – submit assignment"},
  {"i": 1, "deadline": null}
]
```

### User Message Format
```
Today is {today_date}.
Analyze the following {N} emails and extract one actionable deadline for each.

{json_string_of_emails}
```
Where each email object contains:
```json
{
  "i": 0,
  "subject": "CS50 Assignment 3 Due Date",
  "sender": "Professor David <david@harvard.edu>",
  "body": "Hi class, just a reminder that Assignment 3 must be submitted on Canvas by Saturday, 24 Oct 2026 at 11:59 PM..."
}
```

---

## 2. Deterministic Regex Fallback

When `ANTHROPIC_API_KEY` is not configured, or if Anthropic API calls fail after all retries (e.g., network outage or depleted credits), `modules/ai_extractor.py` seamlessly falls back to a deterministic regex extractor to guarantee report generation:

### Target Keywords
- Actions: `due|deadline|submit by|pay by|reply by|register by|apply by|renew by|confirm by|attend by|expires on|expires by`
- Relative terms: `by today|by tomorrow|by tonight|by end of day|eod`

### Supported Date Formats
- Standard: `DD/MM/YYYY`, `YYYY-MM-DD`, `DD-MM-YYYY`
- Alphanumeric: `24 Oct 2026`, `24 October 2026`, `October 24, 2026`
- Times: `11:59 PM`, `23:59`, `5:00 PM`
- Relative anchors resolved using the user's current date.

