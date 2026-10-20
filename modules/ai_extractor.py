"""
Claude AI deadline extractor — batched, with regex fallback.

Sends emails in batches of AI_BATCH_SIZE.
Returns a list of deadline strings (or None) in the same order as input.
"""
import json
import re
import time
from typing import Optional

from config.settings import (
    AI_BATCH_SIZE,
    AI_MAX_RETRIES,
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    RETRY_BACKOFF_SECONDS,
)
from modules.logger import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# System / user prompt templates
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a deadline extraction assistant. "
    "Extract only actionable deadlines from emails — things the recipient must do: "
    "submit, pay, reply, register, apply, renew, attend, or confirm. "
    "Ignore newsletters, delivery estimates, past dates, and marketing messages. "
    "Never invent a deadline. "
    "Format: 'DD Mon YYYY' or 'DD Mon YYYY, h:mm AM/PM – action (max 6 words)'. "
    "Return null when there is no actionable deadline."
)

_USER_TEMPLATE = (
    "Today: {today_date}\n\n"
    "Extract deadlines from these emails. Return ONLY a JSON array:\n"
    '[{{"i": 0, "deadline": "24 Oct 2026 – fee payment"}}, {{"i": 1, "deadline": null}}]\n\n'
    "Emails:\n{emails_json}"
)

# ---------------------------------------------------------------------------
# Regex fallback helpers
# ---------------------------------------------------------------------------

_DEADLINE_KEYWORDS = re.compile(
    r"\b(due|submit|deadline|by|before|expires?|register by|apply by|"
    r"confirm by|attend|pay by|response by|respond by)\b",
    re.IGNORECASE,
)

_DATE_PATTERNS = [
    # DD/MM/YYYY or DD-MM-YYYY
    r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b",
    # "January 15" or "Jan 15"
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})(?:st|nd|rd|th)?\b",
    # "15 January" or "15th Jan"
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|"
    r"September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b",
    # "Jan 15, 2026"
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b",
]

_COMPILED_DATES = [re.compile(p, re.IGNORECASE) for p in _DATE_PATTERNS]


def _find_date_near_keyword(text: str) -> Optional[str]:
    """Find a date within 30 characters after a deadline keyword."""
    for kw_match in _DEADLINE_KEYWORDS.finditer(text):
        window_start = kw_match.end()
        window_end = min(len(text), window_start + 60)
        window = text[window_start:window_end]
        for date_re in _COMPILED_DATES:
            dm = date_re.search(window)
            if dm:
                return dm.group(0)
    return None


def _regex_fallback(emails: list[dict]) -> list[Optional[str]]:
    """
    Regex-based deadline extraction as a last resort.

    Scans subject + body for deadline keywords followed by a date.
    Returns a list of date strings or None, same length as emails.
    """
    results: list[Optional[str]] = []
    for email in emails:
        text = f"{email.get('subject', '')} {email.get('body_text', '')}"
        date_str = _find_date_near_keyword(text)
        results.append(date_str)
    return results


# ---------------------------------------------------------------------------
# Claude extraction
# ---------------------------------------------------------------------------

def _call_claude(batch: list[dict], today_date: str, attempt: int = 0) -> Optional[list[dict]]:
    """
    Call Claude API for one batch of emails.
    Returns a list of {i, deadline} dicts, or None on failure.
    """
    try:
        import anthropic  # lazy import — only needed if API key is set
        import os

        headers = {}
        workspace_id = os.getenv("ANTHROPIC_WORKSPACE_ID", "")
        if workspace_id:
            headers["anthropic-workspace-id"] = workspace_id

        client = anthropic.Anthropic(
            api_key=ANTHROPIC_API_KEY,
            default_headers=headers if headers else None,
        )

        user_message = _USER_TEMPLATE.format(
            today_date=today_date,
            emails_json=json.dumps(batch, ensure_ascii=False),
        )

        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        raw = response.content[0].text.strip()

        # Extract JSON array even if wrapped in markdown code blocks
        json_match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not json_match:
            log.warning("Claude response missing JSON array: %s", raw[:200])
            return None

        parsed = json.loads(json_match.group(0))
        if isinstance(parsed, list):
            return parsed
        return None

    except json.JSONDecodeError as e:
        log.warning("Claude JSON parse error (attempt %d): %s", attempt + 1, e)
        return None
    except Exception as e:
        log.warning("Claude API error (attempt %d): %s", attempt + 1, e)
        err_str = str(e)
        if any(term in err_str for term in ("invalid_request_error", "workspace", "400", "401", "403")):
            return "NON_RETRYABLE"
        return None


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def extract_deadlines(emails: list[dict], today_date: str) -> list[Optional[str]]:
    """
    Extract deadlines for a list of emails using Claude (with regex fallback).

    Args:
        emails:     List of email dicts with at least {subject, sender, body_text}.
        today_date: Today's date string, e.g. "20 Oct 2026".

    Returns:
        A list of deadline strings or None, one per email, in the same order.
    """
    if not emails:
        return []

    results: list[Optional[str]] = [None] * len(emails)

    if not ANTHROPIC_API_KEY:
        log.warning("No ANTHROPIC_API_KEY — using regex fallback for all emails.")
        return _regex_fallback(emails)

    # Process in batches
    for batch_start in range(0, len(emails), AI_BATCH_SIZE):
        batch_slice = emails[batch_start : batch_start + AI_BATCH_SIZE]
        batch_input = [
            {
                "i": idx,
                "subject": e.get("subject", ""),
                "sender": e.get("sender", ""),
                "body": e.get("body_text", "")[:1500],
            }
            for idx, e in enumerate(batch_slice)
        ]

        response_items = None
        for attempt in range(AI_MAX_RETRIES):
            response_items = _call_claude(batch_input, today_date, attempt)
            if response_items == "NON_RETRYABLE":
                response_items = None
                break
            if response_items is not None:
                break
            if attempt < AI_MAX_RETRIES - 1:
                wait = RETRY_BACKOFF_SECONDS * (2 ** attempt)
                log.info("Retrying Claude in %ds (attempt %d/%d)…", wait, attempt + 1, AI_MAX_RETRIES)
                time.sleep(wait)

        if response_items is None:
            log.warning(
                "Claude failed for batch %d–%d; falling back to regex.",
                batch_start, batch_start + len(batch_slice) - 1,
            )
            fallback = _regex_fallback(batch_slice)
            for local_i, deadline in enumerate(fallback):
                results[batch_start + local_i] = deadline
            continue

        # Map Claude's batch-local indices back to global list
        deadline_map: dict[int, Optional[str]] = {}
        for item in response_items:
            if isinstance(item, dict):
                local_i = item.get("i")
                deadline = item.get("deadline")
                if isinstance(local_i, int):
                    deadline_map[local_i] = deadline if isinstance(deadline, str) else None

        for local_i, email in enumerate(batch_slice):
            results[batch_start + local_i] = deadline_map.get(local_i)

    return results
