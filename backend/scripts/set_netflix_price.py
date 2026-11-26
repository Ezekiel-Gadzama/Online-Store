"""Set Netflix offer price on Yandex and confirm price quarantine if needed."""
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
OFFER = "NFLX-Full-HD-1M-RU"


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
    except Exception as e:
        print("token from db failed:", e)
    return ""


def headers(token: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Api-Key": token,
        "X-Business-Id": BUSINESS,
    }


def main() -> int:
    price_rub = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
    token = load_token()
    if not token:
        print("No Yandex API token")
        return 1

    with httpx.Client() as client:
        url = f"{BASE}/v2/businesses/{BUSINESS}/offer-prices/updates"
        body = {"offers": [{"offerId": OFFER, "price": {"value": price_rub, "currencyId": "RUR"}}]}
        r = client.post(url, headers=headers(token), json=body, timeout=60)
        print("price update", r.status_code)
        print(r.text[:4000])
        if not r.is_success:
            return 1

        for path in (
            f"/v2/businesses/{BUSINESS}/price-quarantine",
            f"/v2/campaigns/{CAMPAIGN}/price-quarantine",
        ):
            lr = client.post(BASE + path, headers=headers(token), json={}, timeout=60)
            print("quarantine list", path, lr.status_code)
            if lr.is_success:
                data = lr.json()
                print(json.dumps(data, ensure_ascii=False)[:4000])

        confirm = {"offerIds": [OFFER]}
        confirmed = False
        for path in (
            f"/v2/businesses/{BUSINESS}/price-quarantine/confirm",
            f"/v2/campaigns/{CAMPAIGN}/price-quarantine/confirm",
        ):
            cr = client.post(BASE + path, headers=headers(token), json=confirm, timeout=60)
            print("quarantine confirm", path, cr.status_code, cr.text[:800])
            if cr.is_success:
                confirmed = True

        off = client.post(
            f"{BASE}/v2/campaigns/{CAMPAIGN}/offers",
            headers=headers(token),
            json={"offerIds": [OFFER]},
            params={"limit": 5},
            timeout=60,
        )
        if off.is_success:
            offers = (off.json().get("result") or {}).get("offers") or []
            for o in offers:
                print("campaign offer:", json.dumps(o, ensure_ascii=False))
        else:
            print("offer fetch", off.status_code, off.text[:500])

        try:
            from app.database import SessionLocal
            from app import models

            db = SessionLocal()
            prod = db.query(models.Product).filter(models.Product.yandex_market_sku == OFFER).first()
            if prod:
                prod.selling_price = price_rub
                db.commit()
                print(f"local db product id={prod.id} selling_price={price_rub}")
        except Exception as e:
            print("local db skip:", e)

        print(f"done offer={OFFER} target={price_rub} RUR confirmed_quarantine={confirmed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())