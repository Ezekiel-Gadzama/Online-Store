"""Count campaign offer statuses."""
from __future__ import annotations

import sys
from pathlib import Path

import httpx

sys.path.insert(0, "/app" if Path("/app/app").exists() else str(Path(__file__).resolve().parents[1]))

from scripts.fix_kateskate_disabled_offers import campaign_offers  # noqa: E402
from scripts.fix_kateskate_offer_media import list_offer_ids, load_token  # noqa: E402


def main() -> int:
    with httpx.Client() as client:
        token = load_token()
        ids = list_offer_ids(client, token)
        m = campaign_offers(client, token, ids)
        by_status: dict[str, int] = {}
        for oid in ids:
            st = str((m.get(oid) or {}).get("status") or "?")
            by_status[st] = by_status.get(st, 0) + 1
        print("total", len(ids), by_status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())