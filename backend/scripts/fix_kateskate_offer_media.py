"""
Update KateSkate Yandex offers: replace broken mpic URLs with VPS-hosted media, set stocks.

  python scripts/fix_kateskate_offer_media.py spotify
  python scripts/fix_kateskate_offer_media.py stocks-all
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

sys.path.insert(0, "/app" if Path("/app/app").exists() else str(Path(__file__).resolve().parents[1]))

DEFAULT_BASE = "https://api.partner.market.yandex.ru"
BUSINESS = "217104046"
CAMPAIGN = "149339404"
WAREHOUSE = 2528107
PUBLIC_BASE = os.environ.get("PUBLIC_URL", "http://144.172.100.41:8010").rstrip("/")

SPOTIFY_OFFER = "MRKT-1G29S2OR"
SPOTIFY_PICTURES = [
    f"{PUBLIC_BASE}/api/media/files/store_migration/kateskate/spotify/spotify_lifestyle_listen.jpg",
    f"{PUBLIC_BASE}/api/media/files/store_migration/kateskate/spotify/spotify_listening_header.jpg",
    f"{PUBLIC_BASE}/api/media/files/store_migration/kateskate/spotify/spotify_nigeria_mood.png",
    f"{PUBLIC_BASE}/api/media/files/store_migration/kateskate/spotify/spotify_mobile_player.jpg",
]


def headers(token: str) -> Dict[str, str]:
    h: Dict[str, str] = {"Content-Type": "application/json", "X-Business-Id": BUSINESS}
    if token.startswith("ACMA:"):
        h["Api-Key"] = token
    else:
        h["Authorization"] = token if token.startswith("OAuth ") else f"OAuth {token}"
    return h


def post(client: httpx.Client, path: str, token: str, body: Dict) -> Dict[str, Any]:
    r = client.post(f"{DEFAULT_BASE}{path}", headers=headers(token), json=body, timeout=120)
    if not r.is_success:
        raise RuntimeError(f"{path} -> {r.status_code}: {r.text[:600]}")
    return r.json()


def update_spotify(client: httpx.Client, token: str) -> None:
    pics = SPOTIFY_PICTURES[:]
    try:
        r = httpx.get(pics[0], timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f"Picture not reachable: {pics[0]} ({r.status_code})")
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Picture not reachable: {pics[0]} ({exc})") from exc

    offer: Dict[str, Any] = {
        "offerId": SPOTIFY_OFFER,
        "pictures": pics,
        "downloadable": True,
    }
    offer["videos"] = None

    post(
        client,
        f"/v2/businesses/{BUSINESS}/offer-mappings/update",
        token,
        {"offerMappings": [{"offer": offer}]},
    )
    post(
        client,
        f"/v2/campaigns/{CAMPAIGN}/offers/update",
        token,
        {"offers": [offer]},
    )
    print(f"Updated {SPOTIFY_OFFER}: pictures={len(pics)} (videos cleared)")


def set_stocks(client: httpx.Client, token: str, offer_ids: List[str], count: int) -> None:
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    chunk = 50
    for i in range(0, len(offer_ids), chunk):
        batch = offer_ids[i : i + chunk]
        post(
            client,
            f"/v3/businesses/{BUSINESS}/offers/stocks/update",
            token,
            {
                "skuItems": [
                    {
                        "sku": oid,
                        "partnerWarehouseId": WAREHOUSE,
                        "count": count,
                        "updatedAt": updated_at,
                    }
                    for oid in batch
                ]
            },
        )
    print(f"Stock {count} for {len(offer_ids)} SKU(s), warehouse {WAREHOUSE}")


def list_offer_ids(client: httpx.Client, token: str) -> List[str]:
    ids: List[str] = []
    page_token: Optional[str] = None
    while True:
        params: Dict[str, Any] = {"limit": 100}
        if page_token:
            params["page_token"] = page_token
        r = client.post(
            f"{DEFAULT_BASE}/v2/businesses/{BUSINESS}/offer-mappings",
            headers=headers(token),
            json={},
            params=params,
            timeout=120,
        )
        if not r.is_success:
            raise RuntimeError(f"offer-mappings -> {r.status_code}: {r.text[:400]}")
        data = r.json()
        for row in data.get("result", {}).get("offerMappings", []):
            oid = (row.get("offer") or {}).get("offerId")
            if oid:
                ids.append(oid)
        page_token = (data.get("result", {}).get("paging") or {}).get("nextPageToken")
        if not page_token:
            break
    return ids


def load_token() -> str:
    _scripts = str(Path(__file__).resolve().parent)
    if _scripts not in sys.path:
        sys.path.insert(0, _scripts)
    from yandex_token import load_yandex_token

    return load_yandex_token()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=("spotify", "stocks-all"))
    args = p.parse_args()
    token = load_token()
    if not token:
        print("Set YANDEX_API_TOKEN or store token in app settings")
        return 1
    with httpx.Client() as client:
        if args.cmd == "spotify":
            update_spotify(client, token)
            set_stocks(client, token, [SPOTIFY_OFFER], int(os.environ.get("STOCK_COUNT", "1000")))
        elif args.cmd == "stocks-all":
            count = int(os.environ.get("STOCK_COUNT", "1000"))
            set_stocks(client, token, list_offer_ids(client, token), count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())