#!/usr/bin/env python
"""
Cron job runner for Yandex Market Manager.

Usage:
  python -m app.jobs.runner orders   # Sync orders (run every 1-5 min)
  python -m app.jobs.runner products # Sync products (run every 15-60 min)
  python -m app.jobs.runner all      # Sync products + orders

Schedule with cron (Linux) or Task Scheduler (Windows):
  * * * * * cd /path/to/backend && python -m app.jobs.runner orders
"""
import sys
from app.jobs.sync_jobs import run_order_sync, run_product_sync, run_all_sync


def main():
    job = (sys.argv[1] if len(sys.argv) > 1 else "orders").lower()
    if job == "orders":
        run_order_sync()
    elif job == "products":
        run_product_sync()
    elif job == "all":
        run_all_sync()
    else:
        print(f"Unknown job: {job}. Use: orders | products | all")
        sys.exit(1)


if __name__ == "__main__":
    main()
