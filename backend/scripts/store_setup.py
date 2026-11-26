"""
Store-type default catalogs: push / db-import from git, append from any live Yandex store.

  python scripts/store_setup.py list
  python scripts/store_setup.py append-catalog digital --store-id 1
  python scripts/store_setup.py append-catalog digital --business ... --campaign ...
  python scripts/store_setup.py push digital --store-id 1
  python scripts/store_setup.py db-import digital --admin-user-id 1 --store-id 1
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

_SCRIPTS = str(Path(__file__).resolve().parent)
_ROOT = "/app" if Path("/app/app").exists() else str(Path(__file__).resolve().parents[1])
sys.path.insert(0, _ROOT)
sys.path.insert(0, _SCRIPTS)

from app.catalog_bundle import append_bundle_file  # noqa: E402
from app.store_templates import TEMPLATES, get_template  # noqa: E402

import migrate_yandex_store as mig  # noqa: E402


def _resolve_yandex(
    args: argparse.Namespace,
) -> tuple[str, str, str]:
    token = (getattr(args, "yandex_token", None) or "").strip()
    business = (getattr(args, "business", None) or "").strip()
    campaign = (getattr(args, "campaign", None) or "").strip()
    store_id = getattr(args, "store_id", None)

    if store_id:
        from yandex_token import load_store_yandex  # noqa: E402

        stok, sbiz, scamp, _name = load_store_yandex(int(store_id))
        token = token or (stok or "")
        business = business or (sbiz or "")
        campaign = campaign or (scamp or "")

    if not token:
        from yandex_token import load_yandex_token  # noqa: E402

        token = load_yandex_token()

    if not token:
        raise SystemExit("Missing Yandex token (--yandex-token, YANDEX_API_TOKEN, or store settings)")
    if not business:
        raise SystemExit("Missing --business or --store-id with yandex_business_id")
    return token, business, campaign


def cmd_list(_: argparse.Namespace) -> int:
    for tid, tpl in TEMPLATES.items():
        print(json.dumps(tpl.manifest(), ensure_ascii=False, indent=2))
    return 0


def _write_manifest(tpl) -> None:
    tpl.manifest_path().write_text(
        json.dumps(tpl.manifest(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def cmd_append(args: argparse.Namespace) -> int:
    tpl = get_template(args.template)
    token, business, campaign = _resolve_yandex(args)
    base = "https://api.partner.market.yandex.ru"

    with httpx.Client() as client:
        incoming = mig.fetch_catalog_bundle(client, base, business, token, campaign_id=campaign)

    total, added, updated = append_bundle_file(
        tpl.catalog_path,
        incoming,
        update_existing=not args.new_only,
    )
    _write_manifest(tpl)
    skipped = incoming["product_count"] - added - updated
    print(
        f"Template {tpl.template_id}: {incoming['product_count']} exported from business {business}; "
        f"catalog now {total} offers (+{added} new, {updated} updated, {skipped} unchanged)"
    )
    return 0


def cmd_refresh(args: argparse.Namespace) -> int:
    """Replace template catalog entirely from one live store export."""
    tpl = get_template(args.template)
    token, business, campaign = _resolve_yandex(args)
    tpl.catalog_path.parent.mkdir(parents=True, exist_ok=True)
    ns = argparse.Namespace(
        business=business,
        campaign=campaign,
        token=token,
        base_url="https://api.partner.market.yandex.ru",
        out=str(tpl.catalog_path),
    )
    code = mig.cmd_export(ns)
    _write_manifest(tpl)
    return code


def cmd_push(args: argparse.Namespace) -> int:
    tpl = get_template(args.template)
    token, business, campaign = _resolve_yandex(args)
    ns = argparse.Namespace(
        bundle=str(tpl.catalog_path),
        business=business,
        campaign=campaign,
        token=token,
        base_url="https://api.partner.market.yandex.ru",
        batch_size=args.batch_size,
        skip_stocks=args.skip_stocks,
        stock_count=args.stock_count,
        warehouse_id=args.warehouse_id,
    )
    return mig.cmd_push(ns)


def cmd_db_import(args: argparse.Namespace) -> int:
    tpl = get_template(args.template)
    ns = argparse.Namespace(
        bundle=str(tpl.catalog_path),
        admin_user_id=args.admin_user_id,
        store_id=args.store_id,
    )
    return mig.cmd_db_import(ns)


def main() -> int:
    p = argparse.ArgumentParser(description="Store-type default product catalogs")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="Show built-in templates").set_defaults(func=cmd_list)

    pa = sub.add_parser(
        "append-catalog",
        help="Export a live store and merge into template file (dedupe by offerId)",
    )
    pa.add_argument("template", choices=list(TEMPLATES))
    pa.add_argument("--store-id", type=int, default=None)
    pa.add_argument("--business", default="")
    pa.add_argument("--campaign", default="")
    pa.add_argument("--yandex-token", default="")
    pa.add_argument(
        "--new-only",
        action="store_true",
        help="Do not overwrite existing offerIds in the template",
    )
    pa.set_defaults(func=cmd_append)

    pr = sub.add_parser("refresh-catalog", help="Replace template catalog from one live export")
    pr.add_argument("template", choices=list(TEMPLATES))
    pr.add_argument("--store-id", type=int, default=None)
    pr.add_argument("--business", default="")
    pr.add_argument("--campaign", default="")
    pr.add_argument("--yandex-token", default="")
    pr.set_defaults(func=cmd_refresh)

    pu = sub.add_parser("push", help="Push template catalog to a Yandex business")
    pu.add_argument("template", choices=list(TEMPLATES))
    pu.add_argument("--store-id", type=int, default=None)
    pu.add_argument("--business", default="")
    pu.add_argument("--campaign", default="")
    pu.add_argument("--yandex-token", default="")
    pu.add_argument("--batch-size", type=int, default=20)
    pu.add_argument("--skip-stocks", action="store_true")
    pu.add_argument("--stock-count", type=int, default=100)
    pu.add_argument("--warehouse-id", type=int, default=None)
    pu.set_defaults(func=cmd_push)

    pi = sub.add_parser("db-import", help="Import template catalog into app DB")
    pi.add_argument("template", choices=list(TEMPLATES))
    pi.add_argument("--admin-user-id", type=int, required=True)
    pi.add_argument("--store-id", type=int, default=None)
    pi.set_defaults(func=cmd_db_import)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())