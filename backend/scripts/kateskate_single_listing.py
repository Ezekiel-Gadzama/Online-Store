"""
KateSkate: hide all campaign offers except one; set its price.

  DEST_YANDEX_TOKEN=... python scripts/kateskate_single_listing.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import httpx

sys.path.insert(0, "/app" if Path("/app/app").exists() else str(Path(__file__).resolve().parents[1]))

BASE = "https://api.partner.market.yandex.ru"
BUSINESS = "217104046"
CAMPAIGN = "149339404"
WAREHOUSE = 2528107
KEEP_OFFER = "NFLX-Full-HD-1M-RU"
KEEP_MSKU = 251403882771935232
PRICE_RUB = 30


def headers(token: str) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Api-Key": token,
        "X-Business-Id": BUSINESS,
    }


def list_offer_ids(client: httpx.Client, token: str) -> List[str]:
    r = client.post(
        f"{BASE}/v2/businesses/{BUSINESS}/offer-mappings",
        headers=headers(token),
        json={},
        params={"limit": 100},
        timeout=60,
    )
    r.raise_for_status()
    ids: List[str] = []
    for row in r.json().get("result", {}).get("offerMappings", []):
        off = row.get("offer") or {}
        oid = off.get("offerId")
        msku = (row.get("mapping") or {}).get("marketSku")
        if oid == KEEP_OFFER or msku == KEEP_MSKU:
            continue
        if oid:
            ids.append(oid)
    return ids


def hide_offers(client: httpx.Client, token: str, offer_ids: List[str]) -> None:
    url = f"{BASE}/v2/campaigns/{CAMPAIGN}/hidden-offers"
    chunk = 200
    for i in range(0, len(offer_ids), chunk):
        batch = offer_ids[i : i + chunk]
        body = {"hiddenOffers": [{"offerId": oid} for oid in batch]}
        r = client.post(url, headers=headers(token), json=body, timeout=120)
        r.raise_for_status()
        print(f"hidden {i + len(batch)}/{len(offer_ids)}")


def unhide_keep(client: httpx.Client, token: str) -> None:
    url = f"{BASE}/v2/campaigns/{CAMPAIGN}/hidden-offers/delete"
    r = client.post(
        url,
        headers=headers(token),
        json={"hiddenOffers": [{"offerId": KEEP_OFFER}]},
        timeout=60,
    )
    if r.is_success:
        print("ensure visible:", KEEP_OFFER)


def set_price(client: httpx.Client, token: str) -> None:
    url = f"{BASE}/v2/businesses/{BUSINESS}/offer-prices/updates"
    body = {
        "offers": [
            {
                "offerId": KEEP_OFFER,
                "price": {"value": PRICE_RUB, "currencyId": "RUR"},
            }
        ]
    }
    r = client.post(url, headers=headers(token), json=body, timeout=60)
    r.raise_for_status()
    print(f"price {KEEP_OFFER} = {PRICE_RUB} RUR")


def confirm_price_quarantine(client: httpx.Client, token: str) -> None:
    body = {"offerIds": [KEEP_OFFER]}
    for path in (
        f"/v2/businesses/{BUSINESS}/price-quarantine/confirm",
        f"/v2/campaigns/{CAMPAIGN}/price-quarantine/confirm",
    ):
        r = client.post(BASE + path, headers=headers(token), json=body, timeout=60)
        r.raise_for_status()
    print("price quarantine confirmed:", KEEP_OFFER)


def set_stocks(client: httpx.Client, token: str) -> None:
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = f"{BASE}/v3/businesses/{BUSINESS}/offers/stocks/update"
    r = client.post(
        url,
        headers=headers(token),
        json={
            "skuItems": [
                {
                    "sku": KEEP_OFFER,
                    "partnerWarehouseId": WAREHOUSE,
                    "count": 1000,
                    "updatedAt": updated_at,
                }
            ]
        },
        timeout=60,
    )
    r.raise_for_status()
    print(f"stock {KEEP_OFFER} = 1000")


def main() -> int:
    token = os.environ.get("DEST_YANDEX_TOKEN", "") or os.environ.get("KATESKATE_TOKEN", "")
    if not token:
        print("Set DEST_YANDEX_TOKEN")
        return 1
    with httpx.Client() as client:
        hide = list_offer_ids(client, token)
        unhide_keep(client, token)
        hide_offers(client, token, hide)
        set_price(client, token)
        confirm_price_quarantine(client, token)
        set_stocks(client, token)
    print("done: only", KEEP_OFFER, "public; hidden", len(hide), "others")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())