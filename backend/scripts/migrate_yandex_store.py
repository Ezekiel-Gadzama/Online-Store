"""
Export / import marketplace catalog bundles. Prefer scripts/store_setup.py and data/store_templates/.

Does not copy app users, clients, orders, or SMTP secrets (owner/ops data).
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

sys.path.insert(0, "/app" if Path("/app/app").exists() else str(Path(__file__).resolve().parents[1]))

DEFAULT_BASE = "https://api.partner.market.yandex.ru"

# Offer fields safe to copy to another business catalog
_OFFER_COPY_KEYS = (
    "offerId",
    "name",
    "description",
    "pictures",
    "videos",
    "vendor",
    "vendorCode",
    "barcodes",
    "category",
    "parameterValues",
    "weightDimensions",
    "dimensions",
    "adult",
    "age",
    "type",
    "downloadable",
    "basicPrice",
    "purchasePrice",
    "additionalExpenses",
    "campaignPrice",
    "sellingProgram",
    "tags",
    "manufacturerCountries",
    "shelfLife",
    "lifeTime",
    "guaranteePeriod",
    "customsCommodityCode",
    "commodityCodes",
)


def _headers(api_token: str, business_id: str) -> Dict[str, str]:
    h: Dict[str, str] = {"Content-Type": "application/json"}
    if api_token.startswith("ACMA:"):
        h["Api-Key"] = api_token
    else:
        h["Authorization"] = api_token if api_token.startswith("OAuth ") else f"OAuth {api_token}"
    h["X-Business-Id"] = str(business_id)
    return h


def _post_json(
    client: httpx.Client,
    url: str,
    headers: Dict[str, str],
    *,
    params: Optional[Dict] = None,
    body: Optional[Dict] = None,
) -> Dict[str, Any]:
    r = client.post(url, headers=headers, params=params or {}, json=body or {}, timeout=120.0)
    if not r.is_success:
        raise RuntimeError(f"{r.request.method} {url} -> {r.status_code}: {r.text[:800]}")
    return r.json()


def fetch_all_offer_mappings(
    client: httpx.Client, base_url: str, business_id: str, token: str
) -> List[Dict]:
    url = f"{base_url.rstrip('/')}/v2/businesses/{business_id}/offer-mappings"
    headers = _headers(token, business_id)
    all_rows: List[Dict] = []
    page_token: Optional[str] = None
    while True:
        params: Dict[str, Any] = {"limit": 100}
        if page_token:
            params["page_token"] = page_token
        data = _post_json(client, url, headers, params=params, body={})
        rows = data.get("result", {}).get("offerMappings", [])
        all_rows.extend(rows)
        page_token = (data.get("result", {}).get("paging") or {}).get("nextPageToken")
        if not page_token:
            break
    return all_rows


def fetch_offer_cards(
    client: httpx.Client, base_url: str, business_id: str, token: str, offer_ids: List[str]
) -> Dict[str, Dict]:
    if not offer_ids:
        return {}
    url = f"{base_url.rstrip('/')}/v2/businesses/{business_id}/offer-cards"
    headers = _headers(token, business_id)
    out: Dict[str, Dict] = {}
    chunk = 80
    for i in range(0, len(offer_ids), chunk):
        batch = offer_ids[i : i + chunk]
        data = _post_json(client, url, headers, body={"offerIds": batch})
        for card in data.get("result", {}).get("offerCards", []):
            oid = card.get("offerId")
            if oid:
                out[oid] = card
    return out


def fetch_offer_prices(
    client: httpx.Client, base_url: str, business_id: str, token: str, offer_ids: List[str]
) -> Dict[str, Dict]:
    url = f"{base_url.rstrip('/')}/v2/businesses/{business_id}/offer-prices"
    headers = _headers(token, business_id)
    prices: Dict[str, Dict] = {}
    chunk = 100
    for i in range(0, len(offer_ids), chunk):
        batch = offer_ids[i : i + chunk]
        data = _post_json(client, url, headers, body={"offerIds": batch})
        for row in data.get("result", {}).get("offers", []):
            oid = row.get("offerId")
            if oid and row.get("price"):
                prices[oid] = row["price"]
    return prices


def sanitize_offer_for_target(
    offer: Dict[str, Any],
    card: Optional[Dict[str, Any]],
    price: Optional[Dict[str, Any]],
    *,
    strip_foreign_business_id: Optional[str] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key in _OFFER_COPY_KEYS:
        if key in offer and offer[key] is not None:
            out[key] = copy.deepcopy(offer[key])
    if card and card.get("parameterValues"):
        out["parameterValues"] = copy.deepcopy(card["parameterValues"])
    mapping = (card or {}).get("mapping") or offer.get("mapping") or {}
    if mapping.get("marketCategoryId"):
        out["marketCategoryId"] = mapping["marketCategoryId"]
    if price:
        out["_price"] = {
            "value": price.get("value"),
            "currencyId": price.get("currencyId", "RUR"),
        }
    out.pop("type", None)
    out.setdefault("downloadable", True)
    videos = out.get("videos") or []
    if strip_foreign_business_id:
        needle = f"/business/{strip_foreign_business_id}/"
        out["videos"] = [v for v in videos if isinstance(v, str) and needle not in v]
    return out


def _offer_for_yandex_push(offer: Dict[str, Any]) -> Dict[str, Any]:
    o = copy.deepcopy(offer)
    o.pop("_price", None)
    o.pop("basicPrice", None)
    o.pop("type", None)
    if o.get("categoryId") and not o.get("marketCategoryId"):
        o["marketCategoryId"] = o.pop("categoryId")
    return o


def default_partner_warehouse_id(
    client: httpx.Client, base_url: str, business_id: str, token: str
) -> int:
    url = f"{base_url.rstrip('/')}/v2/businesses/{business_id}/warehouses"
    data = _post_json(client, url, _headers(token, business_id), body={})
    warehouses = data.get("result", {}).get("warehouses", [])
    if not warehouses:
        raise RuntimeError("No warehouses returned for stock update")
    wid = warehouses[0].get("id")
    if wid is None:
        raise RuntimeError("Warehouse id missing in API response")
    return int(wid)


def push_stocks(
    client: httpx.Client,
    base_url: str,
    business_id: str,
    token: str,
    offer_ids: List[str],
    *,
    count: int = 100,
    warehouse_id: Optional[int] = None,
) -> None:
    if not offer_ids:
        return
    partner_wh = warehouse_id or default_partner_warehouse_id(
        client, base_url, business_id, token
    )
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = f"{base_url.rstrip('/')}/v3/businesses/{business_id}/offers/stocks/update"
    headers = _headers(token, business_id)
    batch = 50
    for i in range(0, len(offer_ids), batch):
        chunk = offer_ids[i : i + batch]
        body = {
            "skuItems": [
                {
                    "sku": oid,
                    "partnerWarehouseId": partner_wh,
                    "count": count,
                    "updatedAt": updated_at,
                }
                for oid in chunk
            ]
        }
        _post_json(client, url, headers, body=body)
    print(f"Set stock={count} for {len(offer_ids)} offers (warehouse {partner_wh})")


def build_update_payload(products: List[Dict[str, Any]]) -> Dict[str, Any]:
    entries = []
    for p in products:
        entries.append({"offer": _offer_for_yandex_push(p["offer"])})
    return {"offerMappings": entries}


def _resolve_token(cli_token: str) -> str:
    if cli_token:
        return cli_token
    _scripts = str(Path(__file__).resolve().parent)
    if _scripts not in sys.path:
        sys.path.insert(0, _scripts)
    from yandex_token import load_yandex_token

    return load_yandex_token()


def fetch_catalog_bundle(
    client: httpx.Client,
    base_url: str,
    business_id: str,
    token: str,
    *,
    campaign_id: str = "",
) -> Dict[str, Any]:
    mappings = fetch_all_offer_mappings(client, base_url, business_id, token)
    offer_ids = [
        (row.get("offer") or {}).get("offerId") or row.get("offerId") for row in mappings
    ]
    offer_ids = [x for x in offer_ids if x]
    cards = fetch_offer_cards(client, base_url, business_id, token, offer_ids)
    prices = fetch_offer_prices(client, base_url, business_id, token, offer_ids)

    bundle_products: List[Dict[str, Any]] = []
    for row in mappings:
        raw_offer = copy.deepcopy(row.get("offer") or row)
        oid = raw_offer.get("offerId")
        if not oid:
            continue
        sanitized = sanitize_offer_for_target(
            raw_offer,
            cards.get(oid),
            prices.get(oid),
            strip_foreign_business_id=None,
        )
        bundle_products.append(
            {
                "offerId": oid,
                "offer": sanitized,
                "source_mapping": row.get("mapping"),
                "source_card_status": (cards.get(oid) or {}).get("cardStatus"),
            }
        )

    return {
        "version": 2,
        "business_id": business_id,
        "campaign_id": campaign_id,
        "product_count": len(bundle_products),
        "products": bundle_products,
    }


def cmd_export(args: argparse.Namespace) -> int:
    token = _resolve_token(args.token)
    if not token:
        print("Missing --token or YANDEX_API_TOKEN / app settings")
        return 1
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with httpx.Client() as client:
        bundle = fetch_catalog_bundle(
            client,
            args.base_url,
            args.business,
            token,
            campaign_id=args.campaign or "",
        )
    out_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Exported {bundle['product_count']} products -> {out_path}")
    return 0


def cmd_push(args: argparse.Namespace) -> int:
    token = _resolve_token(args.token)
    if not token:
        print("Missing --token or YANDEX_API_TOKEN / app settings")
        return 1
    bundle = json.loads(Path(args.bundle).read_text(encoding="utf-8"))
    products = bundle.get("products", [])
    if not products:
        print("Bundle has no products")
        return 1
    src_bid = str(
        bundle.get("business_id") or bundle.get("source_business_id") or ""
    )
    strip_bid = src_bid if src_bid and src_bid != str(args.business) else None
    if strip_bid:
        for p in products:
            p["offer"] = sanitize_offer_for_target(
                p.get("offer") or {},
                None,
                None,
                strip_foreign_business_id=strip_bid,
            )

    url = f"{args.base_url.rstrip('/')}/v2/businesses/{args.business}/offer-mappings/update"
    headers = _headers(token, args.business)
    batch_size = args.batch_size
    updated = 0

    with httpx.Client() as client:
        for i in range(0, len(products), batch_size):
            chunk = products[i : i + batch_size]
            payload = build_update_payload(chunk)
            data = _post_json(client, url, headers, body=payload)
            updated += len(chunk)
            print(f"Pushed {updated}/{len(products)} status={data.get('status')}")

        price_url = (
            f"{args.base_url.rstrip('/')}/v2/businesses/{args.business}/offer-prices/updates"
        )
        price_offers = []
        for p in products:
            bp = p["offer"].get("_price") or p["offer"].get("basicPrice")
            if bp and p.get("offerId"):
                price_offers.append(
                    {
                        "offerId": p["offerId"],
                        "price": {
                            "value": bp["value"],
                            "currencyId": bp.get("currencyId", "RUR"),
                        },
                    }
                )
        for j in range(0, len(price_offers), batch_size):
            batch = price_offers[j : j + batch_size]
            _post_json(client, price_url, headers, body={"offers": batch})
        print(f"Updated prices for {len(price_offers)} offers")

        if args.campaign:
            camp_url = (
                f"{args.base_url.rstrip('/')}/v2/campaigns/{args.campaign}/offers/update"
            )
            camp_offers = []
            for p in products:
                o = _offer_for_yandex_push(p["offer"])
                oid = o.get("offerId") or p.get("offerId")
                if not oid:
                    continue
                o["offerId"] = oid
                camp_offers.append(o)
            for k in range(0, len(camp_offers), batch_size):
                batch = camp_offers[k : k + batch_size]
                try:
                    _post_json(client, camp_url, headers, body={"offers": batch})
                except RuntimeError as exc:
                    print(f"Campaign offers update note: {exc}")

        if not args.skip_stocks:
            offer_ids = [
                p.get("offerId") or (p.get("offer") or {}).get("offerId")
                for p in products
            ]
            offer_ids = [x for x in offer_ids if x]
            push_stocks(
                client,
                args.base_url,
                args.business,
                token,
                offer_ids,
                count=args.stock_count,
                warehouse_id=args.warehouse_id,
            )

    print("Push complete")
    return 0


def cmd_db_import(args: argparse.Namespace) -> int:
    from app.database import SessionLocal
    from app import models

    bundle = json.loads(Path(args.bundle).read_text(encoding="utf-8"))
    db = SessionLocal()
    try:
        admin = db.query(models.User).filter(models.User.id == args.admin_user_id).first()
        if not admin or not admin.is_admin:
            print(f"Admin user id {args.admin_user_id} not found")
            return 1
        created = updated = 0
        for p in bundle.get("products", []):
            offer = p["offer"]
            oid = p.get("offerId") or offer.get("offerId")
            if not oid:
                continue
            sku = oid
            name = offer.get("name") or oid
            price = float((offer.get("basicPrice") or {}).get("value") or 0)
            row = (
                db.query(models.Product)
                .filter(
                    models.Product.business_id == admin.id,
                    models.Product.yandex_market_id == oid,
                )
                .first()
            )
            if not row:
                row = models.Product(
                    business_id=admin.id,
                    store_id=args.store_id,
                    name=name,
                    description=offer.get("description") or "",
                    cost_price=max(price * 0.7, 0),
                    selling_price=price,
                    yandex_market_id=oid,
                    yandex_market_sku=sku,
                    product_type=models.ProductType.DIGITAL,
                    yandex_model="DBS",
                    is_synced=True,
                    yandex_full_data=offer,
                )
                db.add(row)
                created += 1
            else:
                row.name = name
                row.description = offer.get("description") or row.description
                row.selling_price = price
                row.yandex_full_data = offer
                row.is_synced = True
                if args.store_id is not None:
                    row.store_id = args.store_id
                updated += 1
        db.commit()
        print(f"DB import for business user {admin.id}: created={created} updated={updated}")
    finally:
        db.close()
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    from app.yandex_campaigns import fetch_campaigns_list

    token = args.token
    camps = fetch_campaigns_list(token, business_id=args.business)
    print(f"Business {args.business}: {len(camps)} campaign(s)")
    for c in camps:
        print(
            f"  campaignId={c.get('id')} domain={c.get('domain')} "
            f"placement={c.get('placementType')} api={c.get('apiAvailability')}"
        )
    if not camps:
        print(
            "No campaign yet — finish placement contract in Yandex, then check "
            "Settings → API and modules → Store integration for the campaign id."
        )
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default=DEFAULT_BASE)
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("export", help="Download catalog JSON (maintainers: refresh template bundle)")
    e.add_argument("--business", required=True)
    e.add_argument("--token", default="")
    e.add_argument("--campaign", default="")
    e.add_argument("--out", required=True)

    pu = sub.add_parser("push", help="Upload catalog bundle to Yandex business")
    pu.add_argument("--business", required=True)
    pu.add_argument("--token", default="")
    pu.add_argument("--campaign", default="", help="Campaign id for offer visibility + stocks")
    pu.add_argument("--bundle", required=True)
    pu.add_argument("--batch-size", type=int, default=20)
    pu.add_argument("--skip-stocks", action="store_true")
    pu.add_argument("--stock-count", type=int, default=1000)
    pu.add_argument("--warehouse-id", type=int, default=None)

    db = sub.add_parser("db-import", help="Import bundle into local Postgres for an admin user")
    db.add_argument("--bundle", required=True)
    db.add_argument("--admin-user-id", type=int, required=True)
    db.add_argument("--store-id", type=int, default=None)

    st = sub.add_parser("status", help="List campaigns for a business")
    st.add_argument("--business", required=True)
    st.add_argument("--token", required=True)

    args = p.parse_args()
    if args.cmd == "export":
        return cmd_export(args)
    if args.cmd == "push":
        return cmd_push(args)
    if args.cmd == "db-import":
        return cmd_db_import(args)
    if args.cmd == "status":
        return cmd_status(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())