"""Raise 5 RUR offers to 10 RUR and confirm quarantine so Yandex republishes them."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import List

import httpx

sys.path.insert(0, "/app" if Path("/app/app").exists() else str(Path(__file__).resolve().parents[1]))

from scripts.fix_kateskate_offer_media import (  # noqa: E402
    BUSINESS,
    CAMPAIGN,
    DEFAULT_BASE,
    headers,
    list_offer_ids,
    load_token,
    post,
    set_stocks,
)
from scripts.reveal_hidden_offers_5rub import confirm_quarantine, fetch_prices  # noqa: E402
from scripts.fix_kateskate_disabled_offers import campaign_offers  # noqa: E402

NEW_PRICE = float(os.environ.get("REPUBLISH_PRICE", "10"))
DISABLED = "DISABLED_AUTOMATICALLY"


def set_price(client: httpx.Client, token: str, offer_ids: List[str], value: float) -> None:
    chunk = 100
    for i in range(0, len(offer_ids), chunk):
        batch = offer_ids[i : i + chunk]
        post(
            client,
            f"/v2/businesses/{BUSINESS}/offer-prices/updates",
            token,
            {
                "offers": [
                    {"offerId": oid, "price": {"value": value, "currencyId": "RUR"}}
                    for oid in batch
                ]
            },
        )
    print(f"prices -> {value} RUR for {len(offer_ids)} offers")


def main() -> int:
    token = load_token()
    if not token:
        return 1
    with httpx.Client() as client:
        ids = list_offer_ids(client, token)
        by_id = campaign_offers(client, token, ids)
        disabled = [
            oid for oid in ids if str((by_id.get(oid) or {}).get("status", "")).upper() == DISABLED
        ]
        print("disabled before", len(disabled))
        if not disabled:
            return 0
        set_price(client, token, disabled, NEW_PRICE)
        confirm_quarantine(client, token, disabled)
        set_stocks(client, token, disabled, 1000)
        print("wait 45s for Yandex…")
        time.sleep(45)
        by2 = campaign_offers(client, token, disabled)
        still = [
            oid for oid in disabled if str((by2.get(oid) or {}).get("status", "")).upper() == DISABLED
        ]
        pub = [
            oid
            for oid in disabled
            if str((by2.get(oid) or {}).get("status", "")).upper() in ("PUBLISHED", "READY")
        ]
        print(f"published/recovered: {len(pub)} still disabled: {len(still)}")
        if still:
            print("still disabled sample", still[:10])
    return 0 if len(still) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())