"""Yandex offer card content recommendations/errors."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import httpx

sys.path.insert(0, "/app" if Path("/app/app").exists() else str(Path(__file__).resolve().parents[1]))

from scripts.fix_kateskate_offer_media import (  # noqa: E402
    BUSINESS,
    DEFAULT_BASE,
    headers,
    list_offer_ids,
    load_token,
)

BASE = DEFAULT_BASE


def main() -> int:
    token = load_token()
    if not token:
        return 1
    with httpx.Client() as client:
        ids = list_offer_ids(client, token)
        problems: List[Dict[str, Any]] = []
        chunk = 50
        for i in range(0, len(ids), chunk):
            batch = ids[i : i + chunk]
            r = client.post(
                f"{BASE}/v2/businesses/{BUSINESS}/offer-cards",
                headers=headers(token),
                json={"offerIds": batch, "withRecommendations": True},
                timeout=120,
            )
            r.raise_for_status()
            for card in (r.json().get("result") or {}).get("offerCards") or []:
                oid = card.get("offerId")
                recs = card.get("recommendations") or []
                errs = card.get("errors") or []
                warns = card.get("warnings") or []
                rating = card.get("contentRating")
                if recs or errs or warns or (rating is not None and rating < 70):
                    problems.append(
                        {
                            "offerId": oid,
                            "contentRating": rating,
                            "cardStatus": card.get("cardStatus"),
                            "errors": errs,
                            "warnings": warns,
                            "recommendations": recs[:8],
                        }
                    )
        print("content problems", len(problems))
        print(json.dumps(problems, ensure_ascii=False, indent=2)[:50000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())