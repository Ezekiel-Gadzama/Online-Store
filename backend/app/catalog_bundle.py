"""Merge Yandex catalog bundles by offerId (no duplicate SKUs)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

BUNDLE_VERSION = 2


def product_offer_id(product: Dict[str, Any]) -> str:
    oid = product.get("offerId")
    if oid:
        return str(oid)
    offer = product.get("offer") or {}
    oid = offer.get("offerId")
    return str(oid) if oid else ""


def load_bundle(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {"version": BUNDLE_VERSION, "products": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("products"), list):
        data["products"] = []
    return data


def save_bundle(path: Path, bundle: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    products = bundle.get("products") or []
    bundle["product_count"] = len(products)
    bundle.setdefault("version", BUNDLE_VERSION)
    path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")


def merge_products(
    existing: List[Dict[str, Any]],
    incoming: List[Dict[str, Any]],
    *,
    update_existing: bool = True,
) -> Tuple[List[Dict[str, Any]], int, int]:
    """Return merged list, added count, updated count."""
    by_id: Dict[str, Dict[str, Any]] = {}
    for p in existing:
        oid = product_offer_id(p)
        if oid:
            by_id[oid] = p
    added = updated = 0
    for p in incoming:
        oid = product_offer_id(p)
        if not oid:
            continue
        if oid in by_id:
            if update_existing:
                by_id[oid] = p
                updated += 1
        else:
            by_id[oid] = p
            added += 1
    merged = [by_id[k] for k in sorted(by_id)]
    return merged, added, updated


def append_bundle_file(
    catalog_path: Path,
    incoming: Dict[str, Any],
    *,
    update_existing: bool = True,
) -> Tuple[int, int, int]:
    """Merge incoming bundle into on-disk catalog. Returns (total, added, updated)."""
    current = load_bundle(catalog_path)
    merged, added, updated = merge_products(
        current.get("products") or [],
        incoming.get("products") or [],
        update_existing=update_existing,
    )
    if incoming.get("business_id"):
        current["business_id"] = incoming["business_id"]
    if incoming.get("campaign_id"):
        current["campaign_id"] = incoming["campaign_id"]
    current["products"] = merged
    save_bundle(catalog_path, current)
    return len(merged), added, updated