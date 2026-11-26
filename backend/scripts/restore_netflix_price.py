"""Restore Netflix Full HD offer to 1200 RUR and keep it visible on KateSkate."""
from __future__ import annotations

import sys
from pathlib import Path

import httpx

_SCRIPTS = str(Path(__file__).resolve().parent)
_ROOT = "/app" if Path("/app/app").exists() else str(Path(__file__).resolve().parents[1])
sys.path.insert(0, _ROOT)
sys.path.insert(0, _SCRIPTS)

from fix_kateskate_offer_media import DEFAULT_BASE, BUSINESS, CAMPAIGN, headers, load_token  # noqa: E402

OFFER = "NFLX-Full-HD-1M-RU"
PRICE_RUB = 1200


def main() -> int:
    token = load_token()
    with httpx.Client() as client:
        url = f"{DEFAULT_BASE}/v2/businesses/{BUSINESS}/offer-prices/updates"
        body = {"offers": [{"offerId": OFFER, "price": {"value": PRICE_RUB, "currencyId": "RUR"}}]}
        client.post(url, headers=headers(token), json=body, timeout=60).raise_for_status()
        print(f"price {OFFER} = {PRICE_RUB} RUR")
        confirm = {"offerIds": [OFFER]}
        for path in (
            f"/v2/businesses/{BUSINESS}/price-quarantine/confirm",
            f"/v2/campaigns/{CAMPAIGN}/price-quarantine/confirm",
        ):
            cr = client.post(DEFAULT_BASE + path, headers=headers(token), json=confirm, timeout=60)
            if cr.is_success:
                print("quarantine confirmed:", path)
        unhide_url = f"{DEFAULT_BASE}/v2/campaigns/{CAMPAIGN}/hidden-offers/delete"
        client.post(
            unhide_url,
            headers=headers(token),
            json={"hiddenOffers": [{"offerId": OFFER}]},
            timeout=60,
        ).raise_for_status()
        print(f"unhid {OFFER}")
        from app.database import SessionLocal
        from app import models

        db = SessionLocal()
        prod = (
            db.query(models.Product)
            .filter(
                (models.Product.yandex_market_sku == OFFER) | (models.Product.yandex_market_id == OFFER),
            )
            .first()
        )
        if prod:
            prod.selling_price = float(PRICE_RUB)
            db.commit()
            print(f"local selling_price -> {PRICE_RUB}")
        else:
            print("local product row not found")
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())