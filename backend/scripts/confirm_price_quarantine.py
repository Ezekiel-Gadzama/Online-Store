"""Confirm Yandex price quarantine for offer IDs (sharp price drop)."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import List

import httpx

ROOT = Path(__file__).resolve().parents[2]
BASE = "https://api.partner.market.yandex.ru"
BUSINESS = "217104046"
CAMPAIGN = "149339404"


def load_token() -> str:
    tok = os.environ.get("DEST_YANDEX_TOKEN") or os.environ.get("KATESKATE_TOKEN") or ""
    if tok:
        return tok
    for name in (".env", "backend/.env"):
        p = ROOT / name
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            m = re.match(
                r"^(?:YANDEX_(?:MARKET_)?API_?KEY|VPS_YANDEX_TOKEN|DEST_YANDEX_TOKEN)=(.+)$",
                line.strip(),
                re.I,
            )
            if m:
                return m.group(1).strip().strip('"').strip("'")
    return ""


def main() -> int:
    offer_ids = sys.argv[1:] or ["NFLX-Full-HD-1M-RU"]
    token = load_token()
    if not token:
        print("Set DEST_YANDEX_TOKEN or YANDEX token in .env")
        return 1
    headers = {
        "Content-Type": "application/json",
        "Api-Key": token,
        "X-Business-Id": BUSINESS,
    }
    with httpx.Client() as client:
        for path in (
            f"/v2/businesses/{BUSINESS}/price-quarantine",
            f"/v2/campaigns/{CAMPAIGN}/price-quarantine",
        ):
            r = client.post(BASE + path, headers=headers, json={}, timeout=60)
            print("quarantine list", path, r.status_code)
            if r.is_success:
                print(json.dumps(r.json(), ensure_ascii=False)[:3000])
        body = {"offerIds": offer_ids}
        for path in (
            f"/v2/businesses/{BUSINESS}/price-quarantine/confirm",
            f"/v2/campaigns/{CAMPAIGN}/price-quarantine/confirm",
        ):
            r = client.post(BASE + path, headers=headers, json=body, timeout=60)
            print("confirm", path, r.status_code, r.text[:400])
        r = client.post(
            f"{BASE}/v2/campaigns/{CAMPAIGN}/offers",
            headers=headers,
            json={"offerIds": offer_ids},
            params={"limit": 10},
            timeout=60,
        )
        if r.is_success:
            offers = (r.json().get("result") or {}).get("offers") or []
            for o in offers:
                print("campaign offer:", json.dumps(o, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())