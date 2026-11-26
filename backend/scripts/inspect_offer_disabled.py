"""Debug one offer: campaign status, card errors, stock."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, "/app" if Path("/app/app").exists() else str(Path(__file__).resolve().parents[1]))

BASE = "https://api.partner.market.yandex.ru"
BUSINESS = "217104046"
CAMPAIGN = "149339404"


def load_token() -> str:
    tok = os.environ.get("DEST_YANDEX_TOKEN") or os.environ.get("KATESKATE_TOKEN") or ""
    if tok:
        return tok
    from app.database import SessionLocal
    from app import models

    db = SessionLocal()
    for bid in (2, 1):
        row = (
            db.query(models.AppSettings)
            .filter(models.AppSettings.business_id == bid)
            .order_by(models.AppSettings.id.asc())
            .first()
        )
        if row and row.yandex_api_token:
            return row.yandex_api_token
    return ""


def main() -> int:
    oid = sys.argv[1] if len(sys.argv) > 1 else "MRKT-179MV3NC"
    token = load_token()
    h = {"Content-Type": "application/json", "Api-Key": token, "X-Business-Id": BUSINESS}
    with httpx.Client() as c:
        r = c.post(
            f"{BASE}/v2/campaigns/{CAMPAIGN}/offers",
            headers=h,
            json={"offerIds": [oid]},
            params={"limit": 1},
            timeout=60,
        )
        offers = (r.json().get("result") or {}).get("offers") or []
        print("campaign offer:", json.dumps(offers[0] if offers else r.text, ensure_ascii=False, indent=2)[:8000])
        r2 = c.post(f"{BASE}/v2/businesses/{BUSINESS}/offer-cards", headers=h, json={"offerIds": [oid]}, timeout=60)
        cards = (r2.json().get("result") or {}).get("offerCards") or []
        if cards:
            print("offer-card:", json.dumps(cards[0], ensure_ascii=False, indent=2)[:4000])
        for path, body in (
            (f"{BASE}/v3/businesses/{BUSINESS}/offers/stocks", {"skuIds": [oid]}),
            (f"{BASE}/v2/campaigns/{CAMPAIGN}/offers/stocks", {"skuIds": [oid]}),
        ):
            r3 = c.post(path, headers=h, json=body, timeout=60)
            print(path, r3.status_code, r3.text[:1200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())