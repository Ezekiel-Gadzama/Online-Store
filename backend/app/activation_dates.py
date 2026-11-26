"""Yandex digital goods activate_till (YYYY-MM-DD)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def yandex_activate_till_date(days: int | None, *, default_days: int = 30) -> str:
    """Expiry calendar date sent to Yandex; always at least one full day from today (UTC)."""
    n = int(days) if days is not None else default_days
    if n < 1:
        n = default_days if default_days >= 1 else 30
    expiry = datetime.now(timezone.utc).date() + timedelta(days=n)
    return expiry.strftime("%Y-%m-%d")