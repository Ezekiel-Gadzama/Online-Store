"""
Scheduled jobs (cron) for Yandex Market Manager.

Run via: python -m app.jobs.runner [job_name]
Example: python -m app.jobs.runner orders
         python -m app.jobs.runner products
         python -m app.jobs.runner all

Configure system cron (Linux) or Task Scheduler (Windows) to run every minute:
  * * * * * cd /path/to/project && python -m app.jobs.runner orders
"""
