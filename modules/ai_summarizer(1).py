# modules/ai_summarizer.py
"""
AI Email Summarizer using Claude (Anthropic).

Bug fix vs. the original prototype: the spec calls for a High/Medium/Low
priority on every email, but the old SYSTEM_PROMPT / JSON schema never
asked Claude for one, so it was silently missing from every report.
That's added here, plus retries on transient/rate-limit failures.
"""

import json
import re
import time
from typing import List, Dict

import anthropic
from config.settings import ANTHROPIC_API_KEY, CLAUDE_MODEL, AI_MAX_RETRIES
from modules.logger import get_logger

log = get_logger(__name__)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

SYSTEM_PROMPT = """You are an executive email assistant. Summarize the email concisely.

Return ONLY this exact JSON structure (no markdown, no preamble):
{
  "summary": "2-3 sentence overview",
  "tasks": ["task 1", "task 2"],
  "deadlines": ["deadline 1"],
  "key_points": ["point 1", "point 2", "point 3"],
  "priority": "High" | "Medium" | "Low"
}

Priority guide:
- High: needs action today, a deadline, or is time-sensitive/financial.
- Medium: worth reading soon but no immediate deadline.
- Low: informational, newsletters, receipts, FYI.

If a field has nothing, use an empty list []. Keep each bullet under 15 words."""

_FALLBACK = {
    "summary": None,  # filled in per-call
    "tasks": [],
    "deadlines": [],
    "key_points": [],
    "priority": "Medium",
}


def summarize_email(email: dict) -> dict:
    """Summarize a single email using Claude. Never raises — always returns a dict."""
    if client is None:
        return {**_FALLBACK, "summary": "AI summarization skipped: ANTHROPIC_API_KEY not set.",
                 "key_points": ["[AI error: missing API key]"]}

    content = f"""
From: {email['sender']}
Subject: {email['subject']}
Date: {email['date']}

Body:
{email['body'] or email['snippet']}
""".strip()

    last_error = None
    for attempt in range(1, AI_MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=512,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content}],
            )
            raw = response.content[0].text.strip()
            raw = re.sub(r"```json|```", "", raw).strip()
            parsed = json.loads(raw)
            # Fill any missing keys defensively rather than trusting the model 100%.
            for key, default in _FALLBACK.items():
                parsed.setdefault(key, default if default is not None else "")
            if parsed.get("priority") not in ("High", "Medium", "Low"):
                parsed["priority"] = "Medium"
            return parsed

        except anthropic.RateLimitError as e:
            last_error = e
            wait = 2 ** attempt
            log.warning("Rate limited, retrying in %ss (attempt %d/%d)", wait, attempt, AI_MAX_RETRIES)
            time.sleep(wait)
        except anthropic.APIStatusError as e:
            last_error = e
            if e.status_code and e.status_code < 500:
                break  # bad request / auth error — retrying won't help
            time.sleep(2 ** attempt)
        except (json.JSONDecodeError, IndexError, KeyError) as e:
            last_error = e
            log.warning("Malformed AI response for '%s': %s", email.get("subject", "")[:50], e)
            break
        except Exception as e:
            last_error = e
            break

    log.error("Summarization failed for '%s': %s", email.get("subject", "")[:50], last_error)
    return {
        **_FALLBACK,
        "summary": email.get("snippet", "Could not summarize."),
        "key_points": [f"[AI error: {str(last_error)[:60]}]"],
    }


def summarize_all(emails: List[Dict]) -> List[Dict]:
    """Add an AI summary (including priority) to every email dict in-place."""
    for i, email in enumerate(emails):
        log.info("Summarizing %d/%d: %s", i + 1, len(emails), email["subject"][:50])
        email["ai"] = summarize_email(email)
    return emails
