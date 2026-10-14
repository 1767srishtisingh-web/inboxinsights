# modules/user_manager.py
"""
Loads and validates user configuration from users/users.json.

Supports an UNLIMITED number of users (not hardcoded to 5) — add or
remove entries in users.json and no source code changes are needed.
Each user's Gmail accounts and WhatsApp number are kept fully isolated
from every other user.
"""

import json
import os
from typing import List, Dict

from config.settings import USERS_CONFIG_FILE
from modules.logger import get_logger

log = get_logger(__name__)


class ConfigError(Exception):
    """Raised when users.json is missing or malformed."""


def load_users(enabled_only: bool = True) -> List[Dict]:
    """
    Load all configured users.

    Each user dict looks like:
    {
        "user_id": "user1",
        "name": "John Doe",
        "enabled": true,
        "whatsapp_to": "whatsapp:+91XXXXXXXXXX",
        "gmail_accounts": [
            {"alias": "personal", "label": "Personal Gmail"},
            {"alias": "work", "label": "Work Gmail"}
        ]
    }
    """
    if not os.path.exists(USERS_CONFIG_FILE):
        raise ConfigError(
            f"users.json not found at {USERS_CONFIG_FILE}. "
            "Copy users/users.example.json to users/users.json and fill it in."
        )

    try:
        with open(USERS_CONFIG_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as e:
        raise ConfigError(f"users.json is not valid JSON: {e}") from e

    users = data.get("users", [])
    if not users:
        raise ConfigError("users.json contains no users.")

    valid_users, seen_ids = [], set()
    for u in users:
        problems = _validate_user(u)
        if problems:
            log.warning("Skipping invalid user entry %s: %s", u.get("user_id", "?"), problems)
            continue
        if u["user_id"] in seen_ids:
            log.warning("Duplicate user_id '%s' — skipping duplicate.", u["user_id"])
            continue
        seen_ids.add(u["user_id"])
        valid_users.append(u)

    if enabled_only:
        valid_users = [u for u in valid_users if u.get("enabled", True)]

    log.info("Loaded %d user(s) from %s", len(valid_users), USERS_CONFIG_FILE)
    return valid_users


def _validate_user(user: Dict) -> List[str]:
    problems = []
    for field in ("user_id", "name", "whatsapp_to", "gmail_accounts"):
        if not user.get(field):
            problems.append(f"missing '{field}'")
    if user.get("gmail_accounts") and not isinstance(user["gmail_accounts"], list):
        problems.append("'gmail_accounts' must be a list")
    return problems


def token_path_for(user_id: str, alias: str, tokens_dir: str) -> str:
    """Every user+account pair gets its own isolated token file."""
    safe_user = user_id.replace(os.sep, "_")
    safe_alias = alias.replace(os.sep, "_")
    return os.path.join(tokens_dir, f"{safe_user}__{safe_alias}_token.json")
