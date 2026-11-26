"""
Patch only broken media on KateSkate (business 217104046).

  PUBLIC_URL=http://144.172.100.41:8010 YANDEX_API_TOKEN=... VPS_PW=... \\
    python scripts/patch_broken_offer_media.py
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import paramiko

sys.path.insert(0, "/app" if Path("/app/app").exists() else str(Path(__file__).resolve().parents[1]))

from scripts.fix_kateskate_offer_media import (  # noqa: E402
    BUSINESS,
    CAMPAIGN,
    DEFAULT_BASE,
    PUBLIC_BASE,
    headers,
    post,
)

ROOT = Path(__file__).resolve().parents[2]
MEDIA_ROOT = ROOT / "media" / "offer_assets" / "patches"
VPS_HOST = os.environ.get("VPS_HOST", "144.172.100.41")
VPS_REMOTE = "/opt/online-store/media/offer_assets/patches"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
# Only these KateSkate-hosted assets are removed/replaced (not foreign partner URLs).
KATESKATE_BAD_VIDEO_URLS = (
    f"{PUBLIC_BASE}/api/media/files/offer_assets/spotify/spotify_nigeria.mp4",
)

NEW_IMAGE_SOURCE: Dict[str, str] = {
    "18820978/2a0000019c8abc43d1b5940dd4ab6296cb58": (
        "https://cdn.cloudflare.steamstatic.com/steam/apps/990080/library_600x900.jpg"
    ),
    "15593671/2a0000019cf2b83465d91e6eed61043acc0c": (
        "https://storage.googleapis.com/pr-newsroom-wp/1/2018/10/capcut_icon_128.png"
    ),
}


def is_foreign_partner_url(url: str) -> bool:
    if "frontend.vh.yandex.ru" in url:
        return True
    m = re.search(r"/business/(\d+)/", url)
    return bool(m and m.group(1) != BUSINESS)


def fetch_offers(client: httpx.Client, token: str) -> Dict[str, Dict[str, Any]]:
    r = client.post(
        f"{DEFAULT_BASE}/v2/businesses/{BUSINESS}/offer-mappings",
        headers=headers(token),
        json={},
        params={"limit": 100},
        timeout=60,
    )
    r.raise_for_status()
    out: Dict[str, Dict[str, Any]] = {}
    for row in r.json().get("result", {}).get("offerMappings", []):
        off = row.get("offer") or {}
        oid = off.get("offerId")
        if oid:
            out[oid] = off
    return out


def campaign_warnings(client: httpx.Client, token: str, offer_id: str) -> List[Dict]:
    r = client.post(
        f"{DEFAULT_BASE}/v2/campaigns/{CAMPAIGN}/offers",
        headers=headers(token),
        json={"offerIds": [offer_id]},
        timeout=60,
    )
    offers = (r.json().get("result") or {}).get("offers") or []
    if not offers:
        return []
    return offers[0].get("warnings") or []


def mpic_from_warning(comment: str) -> Optional[str]:
    m = re.search(r"get-mpic/[0-9a-f/]+/orig", comment)
    if not m:
        return None
    return f"https://avatars.mds.yandex.net/{m.group(0)}"


def failed_mpic_ids(offer: Dict[str, Any], warnings: List[Dict]) -> List[str]:
    ids: List[str] = []
    mf = offer.get("mediaFiles") or {}
    for pic in mf.get("pictures") or []:
        if pic.get("uploadState") == "FAILED":
            u = pic.get("url") or ""
            if "get-mpic/" in u and not is_foreign_partner_url(u):
                ids.append(u.split("get-mpic/")[-1].split("/orig")[0])
    for w in warnings:
        u = mpic_from_warning(w.get("comment") or "")
        if u and "get-mpic/" in u:
            ids.append(u.split("get-mpic/")[-1].split("/orig")[0])
    return list(dict.fromkeys(ids))


def download_replacement(mpic_id: str) -> Optional[Path]:
    MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    src = NEW_IMAGE_SOURCE.get(mpic_id)
    if not src:
        src = f"https://avatars.mds.yandex.net/get-mpic/{mpic_id}/orig"
    name = hashlib.md5(mpic_id.encode()).hexdigest()[:10]
    ext = ".png" if ".png" in src else ".jpg"
    dest = MEDIA_ROOT / f"{name}{ext}"
    try:
        r = httpx.get(src, headers=UA, follow_redirects=True, timeout=120)
        if not r.is_success or len(r.content) < 400:
            return None
        dest.write_bytes(r.content)
        return dest
    except httpx.HTTPError:
        return None


def push_vps(local: Path) -> str:
    pw = os.environ.get("VPS_PW", "")
    if not pw:
        raise RuntimeError("Set VPS_PW")
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(VPS_HOST, username="root", password=pw, timeout=25)
    c.exec_command(f"mkdir -p {VPS_REMOTE}")[1].read()
    sftp = c.open_sftp()
    sftp.put(str(local), f"{VPS_REMOTE}/{local.name}")
    sftp.close()
    c.close()
    return f"{PUBLIC_BASE}/api/media/files/offer_assets/patches/{local.name}"


def patch_pictures_only(
    pictures: List[str],
    broken_ids: List[str],
) -> tuple[List[str], int]:
    out = strip_accidental_patches(list(pictures))
    changes = 0
    missing_ids = [bid for bid in broken_ids if not any(bid in pic for pic in out)]
    for bid in broken_ids + missing_ids:
        local = download_replacement(bid)
        if not local:
            print("  could not download replacement for", bid[:40])
            continue
        new_url = push_vps(local)
        replaced = False
        for i, pic in enumerate(out):
            if bid in pic:
                out[i] = new_url
                replaced = True
                changes += 1
                break
        if not replaced:
            out.insert(0, new_url)
            changes += 1
        print("  kateskate image for mpic", bid.split("/")[0][:12])
    return out[:10], changes


def strip_accidental_patches(pictures: List[str]) -> List[str]:
    return [u for u in pictures if "/kateskate/patches/" not in u]


def kateskate_bad_videos(videos: List[str]) -> List[str]:
    return [v for v in videos if not is_foreign_partner_url(v) and v in KATESKATE_BAD_VIDEO_URLS]


def push_pictures(
    client: httpx.Client,
    token: str,
    offer_id: str,
    pictures: List[str],
) -> None:
    offer: Dict[str, Any] = {
        "offerId": offer_id,
        "pictures": pictures,
        "downloadable": True,
    }
    post(client, f"/v2/businesses/{BUSINESS}/offer-mappings/update", token, {"offerMappings": [{"offer": offer}]})
    post(client, f"/v2/campaigns/{CAMPAIGN}/offers/update", token, {"offers": [offer]})


def remove_kateskate_videos(
    client: httpx.Client,
    token: str,
    offer_id: str,
    pictures: List[str],
) -> None:
    offer: Dict[str, Any] = {
        "offerId": offer_id,
        "pictures": pictures,
        "downloadable": True,
        "videos": None,
    }
    post(client, f"/v2/businesses/{BUSINESS}/offer-mappings/update", token, {"offerMappings": [{"offer": offer}]})
    post(client, f"/v2/campaigns/{CAMPAIGN}/offers/update", token, {"offers": [offer]})


def main() -> int:
    token = os.environ.get("DEST_YANDEX_TOKEN", "") or os.environ.get("KATESKATE_TOKEN", "")
    if not token:
        print("Set DEST_YANDEX_TOKEN")
        return 1

    targets = ("MRKT-1G29S2OR", "MRKT-TWJYMMK0", "MRKT-Q321GLIY")
    with httpx.Client() as client:
        live = fetch_offers(client, token)
        for offer_id in targets:
            offer = live.get(offer_id)
            if not offer:
                continue
            print("===", offer_id, "(KateSkate only)")
            warnings = campaign_warnings(client, token, offer_id)
            pics = strip_accidental_patches(list(offer.get("pictures") or []))
            videos = list(offer.get("videos") or [])
            broken_ids = failed_mpic_ids(offer, warnings)
            bad_vid = kateskate_bad_videos(videos)

            new_pics, n_pic = patch_pictures_only(pics, broken_ids)
            if n_pic:
                push_pictures(client, token, offer_id, new_pics)
                print(f"  updated {n_pic} picture(s); partner-hosted videos untouched")

            if bad_vid and offer_id == "MRKT-1G29S2OR":
                remove_kateskate_videos(client, token, offer_id, new_pics if n_pic else list(offer.get("pictures") or []))
                print("  removed rejected KateSkate video only")

            if n_pic == 0 and not bad_vid:
                if broken_ids:
                    print("  broken mpic ids but download failed:", broken_ids)
                else:
                    print("  nothing to patch on KateSkate")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())