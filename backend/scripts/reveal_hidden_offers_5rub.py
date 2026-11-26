"""
KateSkate hidden offers: save current prices, set 5 RUR, unhide, wait, verify + confirm quarantine.

Restore later with restore_hidden_offer_prices.py using the written snapshot file.

  docker exec ... python scripts/reveal_hidden_offers_5rub.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import httpx

sys.path.insert(0, "/app" if Path("/app/app").exists() else str(Path(__file__).resolve().parents[1]))

BASE = "https://api.partner.market.yandex.ru"
BUSINESS = "217104046"
CAMPAIGN = "149339404"
TARGET_PRICE = 5.0
WAIT_SEC = 60


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


def headers(token: str) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Api-Key": token,
        "X-Business-Id": BUSINESS,
    }


def list_hidden_offer_ids(client: httpx.Client, token: str) -> List[str]:
    ids: List[str] = []
    page_token: str | None = None
    while True:
        params: Dict[str, Any] = {"limit": 500}
        if page_token:
            params["page_token"] = page_token
        r = client.get(
            f"{BASE}/v2/campaigns/{CAMPAIGN}/hidden-offers",
            headers=headers(token),
            params=params,
            timeout=120,
        )
        r.raise_for_status()
        result = r.json().get("result") or {}
        for row in result.get("hiddenOffers") or []:
            oid = row.get("offerId")
            if oid:
                ids.append(str(oid))
        page_token = (result.get("paging") or {}).get("nextPageToken")
        if not page_token:
            break
    return ids


def fetch_prices(client: httpx.Client, token: str, offer_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    chunk = 100
    url = f"{BASE}/v2/businesses/{BUSINESS}/offer-prices"
    for i in range(0, len(offer_ids), chunk):
        batch = offer_ids[i : i + chunk]
        r = client.post(url, headers=headers(token), json={"offerIds": batch}, timeout=120)
        r.raise_for_status()
        for row in (r.json().get("result") or {}).get("offers") or []:
            oid = row.get("offerId")
            if oid and row.get("price"):
                out[str(oid)] = row["price"]
    return out


def set_prices(client: httpx.Client, token: str, offer_ids: List[str], value: float) -> None:
    url = f"{BASE}/v2/businesses/{BUSINESS}/offer-prices/updates"
    chunk = 100
    for i in range(0, len(offer_ids), chunk):
        batch = offer_ids[i : i + chunk]
        body = {
            "offers": [
                {"offerId": oid, "price": {"value": value, "currencyId": "RUR"}}
                for oid in batch
            ]
        }
        r = client.post(url, headers=headers(token), json=body, timeout=120)
        print(f"price update batch {i + len(batch)}/{len(offer_ids)}", r.status_code)
        if not r.is_success:
            print(r.text[:2000])
            r.raise_for_status()


def unhide_offers(client: httpx.Client, token: str, offer_ids: List[str]) -> None:
    url = f"{BASE}/v2/campaigns/{CAMPAIGN}/hidden-offers/delete"
    chunk = 200
    for i in range(0, len(offer_ids), chunk):
        batch = offer_ids[i : i + chunk]
        r = client.post(
            url,
            headers=headers(token),
            json={"hiddenOffers": [{"offerId": oid} for oid in batch]},
            timeout=120,
        )
        print(f"unhide batch {i + len(batch)}/{len(offer_ids)}", r.status_code)
        if not r.is_success:
            print(r.text[:2000])
            r.raise_for_status()


def confirm_quarantine(client: httpx.Client, token: str, offer_ids: List[str]) -> None:
    body = {"offerIds": offer_ids}
    for path in (
        f"/v2/businesses/{BUSINESS}/price-quarantine/confirm",
        f"/v2/campaigns/{CAMPAIGN}/price-quarantine/confirm",
    ):
        r = client.post(BASE + path, headers=headers(token), json=body, timeout=120)
        print("quarantine confirm", path, r.status_code, r.text[:500])


def list_quarantine_ids(client: httpx.Client, token: str) -> List[str]:
    found: List[str] = []
    for path in (
        f"/v2/businesses/{BUSINESS}/price-quarantine",
        f"/v2/campaigns/{CAMPAIGN}/price-quarantine",
    ):
        r = client.post(BASE + path, headers=headers(token), json={}, timeout=120)
        print("quarantine list", path, r.status_code)
        if not r.is_success:
            continue
        data = r.json()
        for block in ("offers", "quarantineOffers", "result"):
            payload = data.get(block) if block != "result" else data.get("result")
            if isinstance(payload, dict):
                for key in ("offers", "quarantineOffers"):
                    for row in payload.get(key) or []:
                        oid = row.get("offerId") if isinstance(row, dict) else None
                        if oid:
                            found.append(str(oid))
            elif isinstance(payload, list):
                for row in payload:
                    oid = row.get("offerId") if isinstance(row, dict) else None
                    if oid:
                        found.append(str(oid))
        result = data.get("result") or {}
        for row in result.get("offers") or result.get("quarantineOffers") or []:
            oid = row.get("offerId")
            if oid:
                found.append(str(oid))
    return sorted(set(found))


def check_offer_cards(client: httpx.Client, token: str, offer_ids: List[str]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    url = f"{BASE}/v2/businesses/{BUSINESS}/offer-cards"
    chunk = 80
    for i in range(0, len(offer_ids), chunk):
        batch = offer_ids[i : i + chunk]
        r = client.post(url, headers=headers(token), json={"offerIds": batch}, timeout=120)
        if not r.is_success:
            issues.append({"batch": batch[:3], "http": r.status_code, "detail": r.text[:300]})
            continue
        for card in (r.json().get("result") or {}).get("offerCards") or []:
            oid = card.get("offerId")
            errs = card.get("errors") or card.get("error") or []
            warns = card.get("warnings") or []
            status = card.get("status") or card.get("cardStatus")
            ok_status = {"PUBLISHED", "OK", "ACTIVE", "HAS_CARD_CAN_UPDATE", "HAS_CARD_CAN_CREATE"}
            if errs or (status and str(status).upper() not in ok_status and str(status)):
                issues.append(
                    {
                        "offerId": oid,
                        "status": status,
                        "errors": errs,
                        "warnings": warns,
                    }
                )
    return issues


def check_campaign_offers(client: httpx.Client, token: str, offer_ids: List[str]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    chunk = 50
    for i in range(0, len(offer_ids), chunk):
        batch = offer_ids[i : i + chunk]
        r = client.post(
            f"{BASE}/v2/campaigns/{CAMPAIGN}/offers",
            headers=headers(token),
            json={"offerIds": batch},
            params={"limit": len(batch)},
            timeout=120,
        )
        if not r.is_success:
            issues.append({"http": r.status_code, "detail": r.text[:300]})
            continue
        for off in (r.json().get("result") or {}).get("offers") or []:
            oid = off.get("offerId")
            feed = off.get("feed") or {}
            errs = off.get("errors") or off.get("errorCodes") or feed.get("errors") or []
            st = off.get("status") or off.get("offerStatus")
            price = off.get("price") or off.get("basicPrice")
            if errs or (st and "REJECT" in str(st).upper()):
                issues.append({"offerId": oid, "status": st, "errors": errs, "price": price})
    return issues


def sync_local_db_prices(offer_ids: List[str], value: float) -> None:
    try:
        from app.database import SessionLocal
        from app import models

        db = SessionLocal()
        n = 0
        for oid in offer_ids:
            prod = (
                db.query(models.Product)
                .filter(
                    (models.Product.yandex_market_sku == oid)
                    | (models.Product.yandex_market_id == oid)
                )
                .first()
            )
            if prod:
                prod.selling_price = value
                n += 1
        db.commit()
        print(f"local db selling_price={value} updated for {n} products")
    except Exception as e:
        print("local db skip:", e)


def snapshot_path() -> Path:
    root = Path("/app/media") if Path("/app/media").exists() else Path(__file__).resolve().parents[1] / "data"
    root.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return root / f"kateskate_hidden_prices_before_5rub_{ts}.json"


def main() -> int:
    token = load_token()
    if not token:
        print("No Yandex API token")
        return 1

    with httpx.Client() as client:
        hidden = list_hidden_offer_ids(client, token)
        print(f"hidden offers count: {len(hidden)}")
        if not hidden:
            print("nothing to do")
            return 0

        prices = fetch_prices(client, token, hidden)
        snapshot = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "business_id": BUSINESS,
            "campaign_id": CAMPAIGN,
            "target_price_rub": TARGET_PRICE,
            "offers": [],
        }
        for oid in hidden:
            pr = prices.get(oid) or {}
            snapshot["offers"].append(
                {
                    "offerId": oid,
                    "price_rub": pr.get("value"),
                    "price": pr,
                }
            )

        out_file = snapshot_path()
        out_file.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"price snapshot written: {out_file}")
        print(json.dumps(snapshot, ensure_ascii=False)[:4000])

        set_prices(client, token, hidden, TARGET_PRICE)
        sync_local_db_prices(hidden, TARGET_PRICE)
        unhide_offers(client, token, hidden)

        print(f"waiting {WAIT_SEC}s before quarantine + error checks…")
        time.sleep(WAIT_SEC)

        in_quarantine = list_quarantine_ids(client, token)
        to_confirm = sorted(set(hidden) | set(in_quarantine))
        if to_confirm:
            confirm_quarantine(client, token, to_confirm)

        after_prices = fetch_prices(client, token, hidden)
        wrong_price = [
            oid
            for oid in hidden
            if after_prices.get(oid, {}).get("value") not in (TARGET_PRICE, TARGET_PRICE * 1.0, 5, 5.0)
        ]
        if wrong_price:
            print("WARNING: price not 5 RUR for:", wrong_price[:20], f"(+{max(0, len(wrong_price) - 20)} more)")
        else:
            print(f"all {len(hidden)} offers report price {TARGET_PRICE} RUR on business offer-prices")

        card_issues = check_offer_cards(client, token, hidden)
        camp_issues = check_campaign_offers(client, token, hidden)
        if card_issues:
            print("offer-cards issues:", json.dumps(card_issues[:30], ensure_ascii=False, indent=2))
        else:
            print("offer-cards: no blocking issues in sampled response")
        if camp_issues:
            print("campaign offers issues:", json.dumps(camp_issues[:30], ensure_ascii=False, indent=2))
        else:
            print("campaign offers: no obvious reject errors")

        latest = sorted(out_file.parent.glob("kateskate_hidden_prices_before_5rub_*.json"))[-1]
        print(f"restore with: python scripts/restore_hidden_offer_prices.py {latest}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())