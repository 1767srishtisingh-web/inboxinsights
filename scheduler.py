#!/usr/bin/env python3
# scheduler.py — Run the dashboard automatically every day.
# Usage: python scheduler.py
# Time is configurable via REPORT_TIME in .env (24h "HH:MM", default 17:00).

import time
import schedule

from config.settings import REPORT_TIME
from modules.logger import get_logger
from main import run

log = get_logger(__name__)


def job():
    log.info("Scheduler triggered a run.")
    try:
        run()
    except Exception as e:
        log.exception("Scheduled run failed: %s", e)


def main():
    schedule.every().day.at(REPORT_TIME).do(job)
    log.info("Scheduler started. Will run daily at %s. Running once now.", REPORT_TIME)
    job()  # run immediately on startup too

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
