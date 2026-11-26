"""
Re-enable KateSkate offers stuck at DISABLED_AUTOMATICALLY (stock + ACTIVE).

  python scripts/fix_kateskate_disabled_offers.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import httpx

sys.path.insert(0, "/app" if Path("/app/app").exists() else str(Path(__file__).resolve().parents[1]))

from scripts.fix_kateskate_offer_media import (  # noqa: E402
    BUSINESS,
    CAMPAIGN,
    DEFAULT_BASE,
    WAREHOUSE,
    headers,
    list_offer_ids,
    load_token,
    post,
    set_stocks,
)

STATUSES_OK = {"PUBLISHED", "READY", "ACTIVE", "PENDING"}
DISABLED = "DISABLED_AUTOMATICALLY"


def campaign_offers(client: httpx.Client, token: str, offer_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    chunk = 40
    for i in range(0, len(offer_ids), chunk):
        batch = offer_ids[i : i + chunk]
        r = client.post(
            f"{DEFAULT_BASE}/v2/campaigns/{CAMPAIGN}/offers",
            headers=headers(token),
            json={"offerIds": batch},
            params={"limit": len(batch)},
            timeout=120,
        )
        r.raise_for_status()
        for row in (r.json().get("result") or {}).get("offers") or []:
            oid = row.get("offerId")
            if oid:
                out[str(oid)] = row
    return out


def fetch_mapping(client: httpx.Client, token: str, offer_id: str) -> Dict[str, Any]:
    r = client.post(
        f"{DEFAULT_BASE}/v2/businesses/{BUSINESS}/offer-mappings",
        headers=headers(token),
        json={"offerIds": [offer_id]},
        params={"limit": 1},
        timeout=60,
    )
    r.raise_for_status()
    rows = (r.json().get("result") or {}).get("offerMappings") or []
    if not rows:
        return {}
    return rows[0].get("offer") or {}


def push_active(client: httpx.Client, token: str, offer_id: str, offer: Dict[str, Any]) -> None:
    body_offer: Dict[str, Any] = {
        "offerId": offer_id,
        "downloadable": True,
        "pictures": offer.get("pictures") or [],
    }
    if offer.get("videos"):
        body_offer["videos"] = offer.get("videos")
    post(
        client,
        f"/v2/businesses/{BUSINESS}/offer-mappings/update",
        token,
        {"offerMappings": [{"offer": body_offer}]},
    )
    camp_offer: Dict[str, Any] = {
        "offerId": offer_id,
        "downloadable": True,
        "pictures": body_offer["pictures"],
    }
    post(client, f"/v2/campaigns/{CAMPAIGN}/offers/update", token, {"offers": [camp_offer]})


def main() -> int:
    token = load_token()
    if not token:
        print("No Yandex token")
        return 1

    with httpx.Client() as client:
        all_ids = list_offer_ids(client, token)
        by_id = campaign_offers(client, token, all_ids)
        disabled = [
            oid
            for oid in all_ids
            if str((by_id.get(oid) or {}).get("status", "")).upper() == DISABLED
        ]
        print(f"total={len(all_ids)} disabled={len(disabled)}")
        if not disabled:
            print("nothing disabled")
            return 0

        set_stocks(client, token, disabled, int(os.environ.get("STOCK_COUNT", "1000")))

        fixed = 0
        for oid in disabled:
            offer = fetch_mapping(client, token, oid)
            if not offer:
                print("skip mapping missing", oid)
                continue
            try:
                push_active(client, token, oid, offer)
                fixed += 1
                print("pushed ACTIVE/downloadable", oid)
            except Exception as exc:
                print("failed", oid, exc)

        by_id2 = campaign_offers(client, token, disabled)
        still = [
            oid
            for oid in disabled
            if str((by_id2.get(oid) or {}).get("status", "")).upper() == DISABLED
        ]
        print(f"still {DISABLED}: {len(still)}")
        if still:
            print(json.dumps([by_id2.get(o) for o in still[:5]], ensure_ascii=False, indent=2)[:3000])

    return 0 if not still else 1


if __name__ == "__main__":
    raise SystemExit(main())