"""Restore prices from reveal snapshot and re-hide offers listed in that snapshot."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List

import httpx

_SCRIPTS = str(Path(__file__).resolve().parent)
_ROOT = "/app" if Path("/app/app").exists() else str(Path(__file__).resolve().parents[1])
sys.path.insert(0, _ROOT)
sys.path.insert(0, _SCRIPTS)

from fix_kateskate_offer_media import DEFAULT_BASE, headers, load_token  # noqa: E402
from restore_hidden_offer_prices import BUSINESS, CAMPAIGN  # noqa: E402

DEFAULT_SNAPSHOT = Path("/app/media/kateskate_hidden_prices_before_5rub_20261126_000058.json")


def hide_offers(client: httpx.Client, token: str, offer_ids: List[str]) -> None:
    url = f"{DEFAULT_BASE}/v2/campaigns/{CAMPAIGN}/hidden-offers"
    for i in range(0, len(offer_ids), 200):
        batch = offer_ids[i : i + 200]
        r = client.post(
            url,
            headers=headers(token),
            json={"hiddenOffers": [{"offerId": oid} for oid in batch]},
            timeout=120,
        )
        r.raise_for_status()
        print(f"hidden {i + len(batch)}/{len(offer_ids)}")


def restore_prices(client: httpx.Client, token: str, snapshot: Path) -> int:
    data = json.loads(snapshot.read_text(encoding="utf-8"))
    offers = data.get("offers") or []
    updates = []
    offer_ids: List[str] = []
    for row in offers:
        oid = row.get("offerId")
        val = row.get("price_rub")
        if not oid or val is None:
            continue
        offer_ids.append(str(oid))
        updates.append({"offerId": str(oid), "price": {"value": float(val), "currencyId": "RUR"}})
    url = f"{DEFAULT_BASE}/v2/businesses/{BUSINESS}/offer-prices/updates"
    for i in range(0, len(updates), 100):
        client.post(
            url,
            headers=headers(token),
            json={"offers": updates[i : i + 100]},
            timeout=120,
        ).raise_for_status()
    body = {"offerIds": offer_ids}
    for path in (
        f"/v2/businesses/{BUSINESS}/price-quarantine/confirm",
        f"/v2/campaigns/{CAMPAIGN}/price-quarantine/confirm",
    ):
        client.post(DEFAULT_BASE + path, headers=headers(token), json=body, timeout=120)
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
                (models.Product.yandex_market_sku == oid) | (models.Product.yandex_market_id == oid),
            )
            .first()
        )
        if prod:
            prod.selling_price = float(val)
    db.commit()
    return len(updates)


def main() -> int:
    snapshot = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SNAPSHOT
    if not snapshot.is_file():
        print("snapshot not found:", snapshot)
        return 1
    data = json.loads(snapshot.read_text(encoding="utf-8"))
    offer_ids = [str(row["offerId"]) for row in data.get("offers") or [] if row.get("offerId")]
    token = load_token()
    if not token:
        print("no token")
        return 1
    with httpx.Client() as client:
        n = restore_prices(client, token, snapshot)
        print(f"restored {n} offer prices from {snapshot}")
        hide_offers(client, token, offer_ids)
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())