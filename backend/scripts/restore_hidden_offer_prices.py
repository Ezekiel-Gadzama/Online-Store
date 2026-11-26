"""Restore Yandex prices from snapshot written by reveal_hidden_offers_5rub.py."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, List

import httpx

sys.path.insert(0, "/app" if Path("/app/app").exists() else str(Path(__file__).resolve().parents[1]))

BASE = "https://api.partner.market.yandex.ru"
BUSINESS = "217104046"
CAMPAIGN = "149339404"


def load_token() -> str:
    tok = os.environ.get("DEST_YANDEX_TOKEN") or os.environ.get("KATESKATE_TOKEN") or ""
    if tok:
        return tok
    try:
        from app.database import SessionLocal
        from app import models

        db = SessionLocal()
        row = (
            db.query(models.AppSettings)
            .filter(models.AppSettings.business_id == 2)
            .order_by(models.AppSettings.id.asc())
            .first()
        )
        if row and row.yandex_api_token:
            return row.yandex_api_token
    except Exception:
        pass
    return ""


def headers(token: str) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Api-Key": token,
        "X-Business-Id": BUSINESS,
    }


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: restore_hidden_offer_prices.py <snapshot.json>")
        return 1
    path = Path(sys.argv[1])
    if not path.is_file():
        print("file not found:", path)
        return 1
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    offers = snapshot.get("offers") or []
    token = load_token()
    if not token:
        print("No token")
        return 1

    updates: List[dict] = []
    offer_ids: List[str] = []
    for row in offers:
        oid = row.get("offerId")
        val = row.get("price_rub")
        if not oid or val is None:
            continue
        offer_ids.append(str(oid))
        updates.append({"offerId": str(oid), "price": {"value": float(val), "currencyId": "RUR"}})

    if not updates:
        print("no prices in snapshot")
        return 1

    with httpx.Client() as client:
        url = f"{BASE}/v2/businesses/{BUSINESS}/offer-prices/updates"
        chunk = 100
        for i in range(0, len(updates), chunk):
            batch = updates[i : i + chunk]
            r = client.post(url, headers=headers(token), json={"offers": batch}, timeout=120)
            print(f"restore batch {i + len(batch)}/{len(updates)}", r.status_code)
            if not r.is_success:
                print(r.text[:2000])
                return 1

        body = {"offerIds": offer_ids}
        for path in (
            f"/v2/businesses/{BUSINESS}/price-quarantine/confirm",
            f"/v2/campaigns/{CAMPAIGN}/price-quarantine/confirm",
        ):
            cr = client.post(BASE + path, headers=headers(token), json=body, timeout=120)
            print("quarantine confirm", path, cr.status_code)

    try:
        from app.database import SessionLocal
        from app import models

        db = SessionLocal()
        for row in offers:
            oid = row.get("offerId")
            val = row.get("price_rub")
            if oid is None or val is None:
                continue
            prod = (
                db.query(models.Product)
                .filter(
                    (models.Product.yandex_market_sku == oid)
                    | (models.Product.yandex_market_id == oid)
                )
                .first()
            )
            if prod:
                prod.selling_price = float(val)
        db.commit()
        print("local db prices restored")
    except Exception as e:
        print("local db skip:", e)

    print(f"restored {len(updates)} offers from {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())