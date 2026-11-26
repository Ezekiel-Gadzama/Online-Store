"""Yandex review-campaign price backup, discount, fix loop, restore."""
from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

from app.database import SessionLocal
from app import models
from app.services.yandex_api import YandexMarketAPI

BASE_URL = "https://api.partner.market.yandex.ru"
DEFAULT_WAREHOUSE = int(os.environ.get("YANDEX_WAREHOUSE_ID", "2528107"))
PUBLISHED_OK = {"PUBLISHED", "READY"}
DISABLED_STATUS = "DISABLED_AUTOMATICALLY"
BACKUP_KIND = "review_price_backup"
DEFAULT_TEMPLATE_NAME = os.environ.get(
    "REVIEW_ACTIVATION_TEMPLATE_NAME",
    "Стандартный шаблон активации (digital)",
)
DEFAULT_PLACEHOLDER_KEY = os.environ.get("REVIEW_DEFAULT_ACTIVATION_KEY", "REVIEW-DEFAULT-KEY")


@dataclass
class StoreYandex:
    store_id: int
    store_name: str
    business_id: str
    campaign_id: str
    token: str
    owner_business_id: int


def headers(token: str, business_id: str) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Api-Key": token,
        "X-Business-Id": business_id,
    }


def load_store(store_id: Optional[int] = None) -> StoreYandex:
    db = SessionLocal()
    store_q = db.query(models.MarketStore)
    if store_id is not None:
        store = store_q.filter(models.MarketStore.id == store_id).first()
    else:
        store = store_q.order_by(models.MarketStore.id.asc()).first()
    if not store:
        raise RuntimeError("No market store found")
    settings = (
        db.query(models.AppSettings)
        .filter(models.AppSettings.store_id == store.id)
        .first()
    )
    if not settings or not settings.yandex_api_token:
        settings = (
            db.query(models.AppSettings)
            .filter(models.AppSettings.business_id == store.owner_id)
            .order_by(models.AppSettings.id.asc())
            .first()
        )
    if not settings or not settings.yandex_api_token:
        raise RuntimeError(f"No Yandex token for store {store.id}")
    business = (settings.yandex_business_id or store.yandex_business_id or "").strip()
    campaign = (settings.yandex_campaign_id or store.yandex_campaign_id or "").strip()
    if not business or not campaign:
        raise RuntimeError(f"Store {store.id} missing yandex business/campaign ids")
    return StoreYandex(
        store_id=store.id,
        store_name=store.name,
        business_id=business,
        campaign_id=campaign,
        token=settings.yandex_api_token,
        owner_business_id=store.owner_id,
    )


def backup_dir() -> Path:
    root = Path("/app/media") if Path("/app/media").exists() else Path(__file__).resolve().parents[1] / "data"
    path = root / "review_price_backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def latest_pointer(store_id: int) -> Path:
    return backup_dir() / f"store_{store_id}_latest.json"


def product_offer_ids(store_id: int) -> List[str]:
    db = SessionLocal()
    ids: List[str] = []
    for p in db.query(models.Product).filter(models.Product.store_id == store_id).all():
        oid = (p.yandex_market_sku or p.yandex_market_id or "").strip()
        if oid:
            ids.append(oid)
    return sorted(set(ids))


def product_for_offer(store_id: int, offer_id: str) -> Optional[models.Product]:
    db = SessionLocal()
    return (
        db.query(models.Product)
        .filter(
            models.Product.store_id == store_id,
            (
                (models.Product.yandex_market_sku == offer_id)
                | (models.Product.yandex_market_id == offer_id)
            ),
        )
        .first()
    )


def unused_key_count(db, product_id: int) -> int:
    return (
        db.query(models.ActivationKey)
        .filter(
            models.ActivationKey.product_id == product_id,
            models.ActivationKey.is_used.is_(False),
        )
        .count()
    )


def default_activation_template(db, store: StoreYandex) -> Optional[models.EmailTemplate]:
    tid = (os.environ.get("REVIEW_ACTIVATION_TEMPLATE_ID") or "").strip()
    if tid:
        return (
            db.query(models.EmailTemplate)
            .filter(
                models.EmailTemplate.id == int(tid),
                models.EmailTemplate.business_id == store.owner_business_id,
            )
            .first()
        )
    q = db.query(models.EmailTemplate).filter(
        models.EmailTemplate.business_id == store.owner_business_id,
        models.EmailTemplate.name == DEFAULT_TEMPLATE_NAME,
    )
    if store.store_id:
        scoped = q.filter(models.EmailTemplate.store_id == store.store_id).first()
        if scoped:
            return scoped
    return q.order_by(models.EmailTemplate.id.asc()).first()


def activation_snapshot_for_offers(store: StoreYandex, offer_ids: List[str]) -> List[Dict[str, Any]]:
    db = SessionLocal()
    rows: List[Dict[str, Any]] = []
    for oid in offer_ids:
        prod = (
            db.query(models.Product)
            .filter(
                models.Product.store_id == store.store_id,
                (
                    (models.Product.yandex_market_sku == oid)
                    | (models.Product.yandex_market_id == oid)
                ),
            )
            .first()
        )
        if not prod:
            rows.append({"offerId": oid, "product_id": None})
            continue
        rows.append(
            {
                "offerId": oid,
                "product_id": prod.id,
                "email_template_id": prod.email_template_id,
                "unused_keys_at_backup": unused_key_count(db, prod.id),
            }
        )
    return rows


def _unique_placeholder_key(db, product_id: int) -> str:
    base = DEFAULT_PLACEHOLDER_KEY
    for candidate in (base, f"{base}-{product_id}", f"{base}-{product_id}-{secrets.token_hex(4)}"):
        exists = db.query(models.ActivationKey).filter(models.ActivationKey.key == candidate).first()
        if not exists:
            return candidate
    return f"{base}-{product_id}-{secrets.token_urlsafe(8)}"


def apply_activation_for_review(store: StoreYandex, offer_ids: List[str], backup_path: Path) -> Dict[str, Any]:
    """Assign default template / placeholder key only where missing; record changes in backup file."""
    data = json.loads(backup_path.read_text(encoding="utf-8"))
    snapshot = {row["offerId"]: row for row in (data.get("product_activation") or []) if row.get("offerId")}
    db = SessionLocal()
    tpl = default_activation_template(db, store)
    if not tpl:
        raise RuntimeError(
            "No default activation template; set REVIEW_ACTIVATION_TEMPLATE_ID or create "
            f"{DEFAULT_TEMPLATE_NAME!r}"
        )
    templates_assigned: List[int] = []
    keys_created: List[int] = []
    for oid in offer_ids:
        row = snapshot.get(oid) or {}
        product_id = row.get("product_id")
        if not product_id:
            continue
        prod = db.query(models.Product).filter(models.Product.id == product_id).first()
        if not prod:
            continue
        if prod.email_template_id is None:
            prod.email_template_id = tpl.id
            templates_assigned.append(product_id)
        if unused_key_count(db, product_id) == 0:
            key_str = _unique_placeholder_key(db, product_id)
            ak = models.ActivationKey(product_id=product_id, key=key_str, is_used=False)
            db.add(ak)
            db.flush()
            keys_created.append(ak.id)
    db.commit()
    data["activation_setup"] = {
        "default_template_id": tpl.id,
        "templates_assigned_product_ids": templates_assigned,
        "created_activation_key_ids": keys_created,
    }
    backup_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data["activation_setup"]


def restore_activation_from_backup(store: StoreYandex, path: Path) -> Tuple[int, int]:
    """Revert template/key changes made during review setup; leave unchanged products alone."""
    data = json.loads(path.read_text(encoding="utf-8"))
    snapshot_by_id: Dict[int, Dict[str, Any]] = {}
    for row in data.get("product_activation") or []:
        pid = row.get("product_id")
        if pid is not None:
            snapshot_by_id[int(pid)] = row
    setup = data.get("activation_setup") or {}
    db = SessionLocal()
    templates_restored = 0
    keys_removed = 0
    for product_id in setup.get("templates_assigned_product_ids") or []:
        prod = db.query(models.Product).filter(
            models.Product.id == product_id,
            models.Product.store_id == store.store_id,
        ).first()
        if not prod:
            continue
        snap = snapshot_by_id.get(product_id, {})
        prod.email_template_id = snap.get("email_template_id")
        templates_restored += 1
    for key_id in setup.get("created_activation_key_ids") or []:
        ak = db.query(models.ActivationKey).filter(models.ActivationKey.id == key_id).first()
        if not ak:
            continue
        prod = db.query(models.Product).filter(models.Product.id == ak.product_id).first()
        if not prod or prod.store_id != store.store_id:
            continue
        if ak.is_used:
            continue
        db.delete(ak)
        keys_removed += 1
    db.commit()
    return templates_restored, keys_removed


def review_count(store: StoreYandex, offer_id: str) -> int:
    api = YandexMarketAPI(
        business_id=store.owner_business_id,
        db=SessionLocal(),
        store_id=store.store_id,
    )
    try:
        rows = api.get_product_reviews(product_id=offer_id, limit=100)
        return len(rows or [])
    except Exception:
        return 0


def select_offers(
    store: StoreYandex,
    *,
    explicit: Optional[List[str]] = None,
    max_reviews: Optional[int] = None,
    no_reviews_only: bool = False,
) -> List[str]:
    if explicit:
        return sorted({str(x).strip() for x in explicit if str(x).strip()})
    catalog = product_offer_ids(store.store_id)
    if max_reviews is None and not no_reviews_only:
        return catalog
    selected: List[str] = []
    for oid in catalog:
        n = review_count(store, oid)
        if no_reviews_only and n > 0:
            continue
        if max_reviews is not None and n >= max_reviews:
            continue
        selected.append(oid)
    return selected


def fetch_prices(client: httpx.Client, store: StoreYandex, offer_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    url = f"{BASE_URL}/v2/businesses/{store.business_id}/offer-prices"
    for i in range(0, len(offer_ids), 100):
        batch = offer_ids[i : i + 100]
        r = client.post(url, headers=headers(store.token, store.business_id), json={"offerIds": batch}, timeout=120)
        r.raise_for_status()
        for row in (r.json().get("result") or {}).get("offers") or []:
            oid = row.get("offerId")
            if oid and row.get("price"):
                out[str(oid)] = row["price"]
    return out


def list_hidden(client: httpx.Client, store: StoreYandex) -> Set[str]:
    hidden: Set[str] = set()
    page_token: Optional[str] = None
    while True:
        params: Dict[str, Any] = {"limit": 500}
        if page_token:
            params["page_token"] = page_token
        r = client.get(
            f"{BASE_URL}/v2/campaigns/{store.campaign_id}/hidden-offers",
            headers=headers(store.token, store.business_id),
            params=params,
            timeout=120,
        )
        r.raise_for_status()
        result = r.json().get("result") or {}
        for row in result.get("hiddenOffers") or []:
            oid = row.get("offerId")
            if oid:
                hidden.add(str(oid))
        page_token = (result.get("paging") or {}).get("nextPageToken")
        if not page_token:
            break
    return hidden


def unhide(client: httpx.Client, store: StoreYandex, offer_ids: List[str]) -> None:
    url = f"{BASE_URL}/v2/campaigns/{store.campaign_id}/hidden-offers/delete"
    for i in range(0, len(offer_ids), 200):
        batch = offer_ids[i : i + 200]
        r = client.post(
            url,
            headers=headers(store.token, store.business_id),
            json={"hiddenOffers": [{"offerId": oid} for oid in batch]},
            timeout=120,
        )
        r.raise_for_status()


def set_prices(client: httpx.Client, store: StoreYandex, offer_ids: List[str], value: float) -> None:
    url = f"{BASE_URL}/v2/businesses/{store.business_id}/offer-prices/updates"
    for i in range(0, len(offer_ids), 100):
        batch = offer_ids[i : i + 100]
        body = {
            "offers": [
                {"offerId": oid, "price": {"value": value, "currencyId": "RUR"}}
                for oid in batch
            ]
        }
        r = client.post(url, headers=headers(store.token, store.business_id), json=body, timeout=120)
        r.raise_for_status()


def confirm_quarantine(client: httpx.Client, store: StoreYandex, offer_ids: List[str]) -> None:
    body = {"offerIds": offer_ids}
    for path in (
        f"/v2/businesses/{store.business_id}/price-quarantine/confirm",
        f"/v2/campaigns/{store.campaign_id}/price-quarantine/confirm",
    ):
        client.post(
            BASE_URL + path,
            headers=headers(store.token, store.business_id),
            json=body,
            timeout=120,
        )


def set_stocks(client: httpx.Client, store: StoreYandex, offer_ids: List[str], count: int) -> None:
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = f"{BASE_URL}/v3/businesses/{store.business_id}/offers/stocks/update"
    for i in range(0, len(offer_ids), 50):
        batch = offer_ids[i : i + 50]
        body = {
            "skuItems": [
                {
                    "sku": oid,
                    "partnerWarehouseId": DEFAULT_WAREHOUSE,
                    "count": count,
                    "updatedAt": updated_at,
                }
                for oid in batch
            ]
        }
        r = client.post(url, headers=headers(store.token, store.business_id), json=body, timeout=120)
        r.raise_for_status()


def campaign_status_map(
    client: httpx.Client, store: StoreYandex, offer_ids: List[str]
) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for i in range(0, len(offer_ids), 40):
        batch = offer_ids[i : i + 40]
        r = client.post(
            f"{BASE_URL}/v2/campaigns/{store.campaign_id}/offers",
            headers=headers(store.token, store.business_id),
            json={"offerIds": batch},
            params={"limit": len(batch)},
            timeout=120,
        )
        r.raise_for_status()
        for row in (r.json().get("result") or {}).get("offers") or []:
            oid = row.get("offerId")
            if oid:
                out[str(oid)] = str(row.get("status") or "")
    return out


def write_backup(store: StoreYandex, offer_ids: List[str], prices: Dict[str, Dict], hidden: Set[str]) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    payload = {
        "kind": BACKUP_KIND,
        "store_id": store.store_id,
        "store_name": store.store_name,
        "business_id": store.business_id,
        "campaign_id": store.campaign_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "product_activation": activation_snapshot_for_offers(store, offer_ids),
        "offers": [
            {
                "offerId": oid,
                "price_rub": prices.get(oid, {}).get("value"),
                "price": prices.get(oid),
                "was_hidden": oid in hidden,
            }
            for oid in offer_ids
        ],
    }
    path = backup_dir() / f"store_{store.store_id}_{ts}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_pointer(store.store_id).write_text(
        json.dumps({"snapshot": str(path), "created_at": payload["created_at"]}, indent=2),
        encoding="utf-8",
    )
    return path


def load_backup_path(store_id: int, snapshot: Optional[str]) -> Path:
    if snapshot:
        p = Path(snapshot)
        if not p.is_file():
            raise FileNotFoundError(snapshot)
        return p
    ptr = latest_pointer(store_id)
    if not ptr.is_file():
        raise FileNotFoundError(f"No backup pointer at {ptr}")
    data = json.loads(ptr.read_text(encoding="utf-8"))
    return Path(data["snapshot"])


def undo_review_backup(client: httpx.Client, store: StoreYandex, path: Path) -> Dict[str, Any]:
    n = restore_from_backup(client, store, path)
    t, k = restore_activation_from_backup(store, path)
    return {"prices_restored": n, "templates_restored": t, "placeholder_keys_removed": k}


def restore_from_backup(client: httpx.Client, store: StoreYandex, path: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("kind") != BACKUP_KIND:
        raise ValueError("Not a review price backup file")
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
    url = f"{BASE_URL}/v2/businesses/{store.business_id}/offer-prices/updates"
    for i in range(0, len(updates), 100):
        client.post(
            url,
            headers=headers(store.token, store.business_id),
            json={"offers": updates[i : i + 100]},
            timeout=120,
        ).raise_for_status()
    confirm_quarantine(client, store, offer_ids)
    db = SessionLocal()
    for row in offers:
        oid = row.get("offerId")
        val = row.get("price_rub")
        if oid is None or val is None:
            continue
        prod = (
            db.query(models.Product)
            .filter(
                models.Product.store_id == store.store_id,
                (models.Product.yandex_market_sku == oid) | (models.Product.yandex_market_id == oid),
            )
            .first()
        )
        if prod:
            prod.selling_price = float(val)
    db.commit()
    return len(updates)


def sync_local_prices(store: StoreYandex, offer_ids: List[str], value: float) -> None:
    sync_local_prices_map(store, {oid: value for oid in offer_ids})


def sync_local_prices_map(store: StoreYandex, price_by_offer: Dict[str, float]) -> None:
    db = SessionLocal()
    for oid, value in price_by_offer.items():
        prod = (
            db.query(models.Product)
            .filter(
                models.Product.store_id == store.store_id,
                (models.Product.yandex_market_sku == oid) | (models.Product.yandex_market_id == oid),
            )
            .first()
        )
        if prod:
            prod.selling_price = value
    db.commit()


def fix_until_clean(
    client: httpx.Client,
    store: StoreYandex,
    offer_ids: List[str],
    *,
    wait_sec: int,
    price_steps: List[float],
    max_rounds: int,
) -> Dict[str, Any]:
    price_by_offer = {oid: price_steps[0] for oid in offer_ids}
    rounds = 0
    history: List[Dict[str, Any]] = []
    while rounds < max_rounds:
        rounds += 1
        time.sleep(wait_sec)
        status = campaign_status_map(client, store, offer_ids)
        bad = [oid for oid in offer_ids if status.get(oid, "") not in PUBLISHED_OK]
        history.append({"round": rounds, "bad": len(bad), "statuses": {k: status[k] for k in bad[:5]}})
        if not bad:
            return {"ok": True, "rounds": rounds, "history": history, "prices": price_by_offer}
        set_stocks(client, store, bad, int(os.environ.get("STOCK_COUNT", "1000")))
        confirm_quarantine(client, store, bad)
        for oid in bad:
            cur = price_by_offer.get(oid, price_steps[0])
            if status.get(oid) == DISABLED_STATUS:
                for step in price_steps:
                    if step > cur:
                        cur = step
                        break
                price_by_offer[oid] = cur
                set_prices(client, store, [oid], cur)
                confirm_quarantine(client, store, [oid])
    status = campaign_status_map(client, store, offer_ids)
    bad = [oid for oid in offer_ids if status.get(oid, "") not in PUBLISHED_OK]
    return {
        "ok": len(bad) == 0,
        "rounds": rounds,
        "remaining": bad,
        "history": history,
        "prices": price_by_offer,
    }