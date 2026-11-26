"""List Yandex campaign offer errors/warnings for all KateSkate SKUs."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import httpx

sys.path.insert(0, "/app" if Path("/app/app").exists() else str(Path(__file__).resolve().parents[1]))

BASE = "https://api.partner.market.yandex.ru"
BUSINESS = "217104046"
CAMPAIGN = "149339404"


def load_token() -> str:
    tok = os.environ.get("DEST_YANDEX_TOKEN") or os.environ.get("KATESKATE_TOKEN") or ""
    if tok:
        return tok
    try:
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
    except Exception:
        pass
    return ""


def headers(token: str) -> Dict[str, str]:
    return {"Content-Type": "application/json", "Api-Key": token, "X-Business-Id": BUSINESS}


def list_offer_ids(client: httpx.Client, token: str) -> List[str]:
    ids: List[str] = []
    page_token = None
    while True:
        params: Dict[str, Any] = {"limit": 100}
        if page_token:
            params["page_token"] = page_token
        r = client.post(
            f"{BASE}/v2/businesses/{BUSINESS}/offer-mappings",
            headers=headers(token),
            json={},
            params=params,
            timeout=120,
        )
        r.raise_for_status()
        data = r.json().get("result") or {}
        for row in data.get("offerMappings") or []:
            oid = (row.get("offer") or {}).get("offerId")
            if oid:
                ids.append(str(oid))
        page_token = (data.get("paging") or {}).get("nextPageToken")
        if not page_token:
            break
    return ids


def main() -> int:
    token = load_token()
    if not token:
        print("no token")
        return 1
    with httpx.Client() as client:
        ids = list_offer_ids(client, token)
        print("offers in catalog:", len(ids))
        problems: List[Dict[str, Any]] = []
        chunk = 30
        for i in range(0, len(ids), chunk):
            batch = ids[i : i + chunk]
            r = client.post(
                f"{BASE}/v2/campaigns/{CAMPAIGN}/offers",
                headers=headers(token),
                json={"offerIds": batch},
                params={"limit": len(batch)},
                timeout=120,
            )
            if not r.is_success:
                print("batch fail", r.status_code, r.text[:500])
                continue
            for off in (r.json().get("result") or {}).get("offers") or []:
                oid = off.get("offerId")
                errs = off.get("errors") or off.get("errorCodes") or []
                warns = off.get("warnings") or []
                st = off.get("status") or off.get("offerStatus")
                feed = off.get("feed") or {}
                if feed.get("errors"):
                    errs = list(errs) + list(feed.get("errors"))
                media = off.get("mediaFiles") or {}
                failed_pics = [
                    p for p in (media.get("pictures") or []) if p.get("uploadState") == "FAILED"
                ]
                if errs or warns or failed_pics or (st and "PUBLISHED" not in str(st).upper() and st):
                    problems.append(
                        {
                            "offerId": oid,
                            "status": st,
                            "errors": errs,
                            "warnings": warns,
                            "failedPictures": failed_pics,
                        }
                    )
        print("problems:", len(problems))
        print(json.dumps(problems, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())