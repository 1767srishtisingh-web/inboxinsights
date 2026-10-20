#!/usr/bin/env python3
"""
main.py — Run reports from the command line.

Usage:
    python main.py                  # Run report for all eligible users
    python main.py --user 1         # Run for specific user ID only
    python main.py --no-send        # Generate reports & PDFs without sending WhatsApp
    python main.py --user 1 --no-send
"""

import argparse
import sys
from datetime import datetime

from modules.db import init_db, get_users_for_delivery, get_user_by_id
from modules.pipeline import run_for_user
from modules.logger import get_logger

log = get_logger(__name__)


def run_cli():
    parser = argparse.ArgumentParser(
        description="Inbox Insights — CLI report generator & dispatcher"
    )
    parser.add_argument(
        "--user",
        type=int,
        metavar="USER_ID",
        help="Run pipeline only for a specific user ID",
    )
    parser.add_argument(
        "--no-send",
        action="store_true",
        help="Generate PDF reports but skip WhatsApp delivery",
    )
    args = parser.parse_args()

    init_db()

    send_whatsapp = not args.no_send
    start_time = datetime.now()

    print("\n" + "=" * 65)
    print("  Inbox Insights — Manual Report Runner")
    print(f"  Mode: {'Live WhatsApp send' if send_whatsapp else 'Dry-run (--no-send)'}")
    print(f"  Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    targets = []
    if args.user:
        user = get_user_by_id(args.user)
        if not user:
            print(f"\n[ERROR] User with ID {args.user} not found in database.")
            sys.exit(1)
        targets = [user]
    else:
        targets = get_users_for_delivery()
        if not targets:
            print("\nNo enabled users with connected Gmail accounts found.")
            sys.exit(0)

    print(f"\nProcessing {len(targets)} user(s)...\n")

    summary = []
    for user in targets:
        uid = user["id"]
        uname = user.get("name", f"User #{uid}")
        uphone = user.get("whatsapp", "")
        print(f"► Running for {uname} (ID: {uid}, {uphone})...")

        res = run_for_user(uid, send_whatsapp=send_whatsapp)
        summary.append(res)

        print(f"   • Emails found today:  {res.get('email_count', 0)}")
        print(f"   • Deadlines detected:  {res.get('deadline_count', 0)}")
        print(f"   • PDF generated:       {res.get('pdf_path') or 'None'}")
        print(f"   • WhatsApp delivery:   {res.get('whatsapp_status', 'skipped')}")
        if res.get("error"):
            print(f"   • Error:               {res['error']}")
        print()

    duration = datetime.now() - start_time
    print("=" * 65)
    print(f"  Completed in {duration.total_seconds():.1f}s")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    run_cli()
