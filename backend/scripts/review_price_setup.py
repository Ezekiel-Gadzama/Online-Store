"""
Review campaign: backup prices, set lowest publishable price, fix errors in a loop, restore later.

  python scripts/review_price_setup.py setup [--store-id N] [--offers id1,id2]
      [--max-reviews 10] [--no-reviews-only] [--price 5] [--wait 60]
  python scripts/review_price_setup.py undo [--store-id N] [--snapshot path]
  python scripts/review_price_setup.py status [--store-id N]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

_ROOT = "/app" if Path("/app/app").exists() else str(Path(__file__).resolve().parents[1])
_SCRIPTS = str(Path(__file__).resolve().parent)
sys.path.insert(0, _ROOT)
sys.path.insert(0, _SCRIPTS)

import review_price_lib as lib  # noqa: E402

# KateSkate digital: 5 RUR often -> DISABLED_AUTOMATICALLY; 10 RUR publishes.
DEFAULT_PRICE_STEPS = [float(x) for x in os.environ.get("REVIEW_PRICE_STEPS", "5,10").split(",") if x.strip()]


def cmd_setup(args: argparse.Namespace) -> int:
    store = lib.load_store(args.store_id)
    explicit = [x.strip() for x in (args.offers or "").split(",") if x.strip()] or None
    offer_ids = lib.select_offers(
        store,
        explicit=explicit,
        max_reviews=args.max_reviews,
        no_reviews_only=args.no_reviews_only,
    )
    if not offer_ids:
        print("No offers matched filters")
        return 1
    print(f"store={store.store_name} ({store.store_id}) offers={len(offer_ids)}")

    with httpx.Client() as client:
        hidden = lib.list_hidden(client, store)
        prices = lib.fetch_prices(client, store, offer_ids)
        backup = lib.write_backup(store, offer_ids, prices, hidden)
        print(f"backup: {backup}")
        setup_act = lib.apply_activation_for_review(store, offer_ids, backup)
        print(
            "activation setup:",
            f"templates_assigned={len(setup_act.get('templates_assigned_product_ids') or [])}",
            f"keys_created={len(setup_act.get('created_activation_key_ids') or [])}",
        )

        targets_hidden = [oid for oid in offer_ids if oid in hidden]
        if targets_hidden:
            lib.unhide(client, store, targets_hidden)
            print(f"unhid {len(targets_hidden)} offers")

        start_price = args.price if args.price is not None else DEFAULT_PRICE_STEPS[0]
        lib.set_prices(client, store, offer_ids, start_price)
        lib.confirm_quarantine(client, store, offer_ids)
        lib.set_stocks(client, store, offer_ids, int(os.environ.get("STOCK_COUNT", "1000")))
        lib.sync_local_prices(store, offer_ids, start_price)

        result = lib.fix_until_clean(
            client,
            store,
            offer_ids,
            wait_sec=args.wait,
            price_steps=DEFAULT_PRICE_STEPS if args.price is None else [args.price, 10.0],
            max_rounds=args.max_rounds,
        )
        final_prices = result.get("prices") or {}
        if final_prices:
            lib.sync_local_prices_map(store, final_prices)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("ok"):
        print("Some offers still not published; see remaining list")
        return 1
    print("Review price setup complete. Undo:", f"python scripts/review_price_setup.py undo --store-id {store.store_id}")
    return 0


def cmd_undo(args: argparse.Namespace) -> int:
    store = lib.load_store(args.store_id)
    path = lib.load_backup_path(store.store_id, args.snapshot)
    with httpx.Client() as client:
        result = lib.undo_review_backup(client, store, path)
    print(
        f"restored prices for {result['prices_restored']} offers; "
        f"templates cleared on {result['templates_restored']} products; "
        f"removed {result['placeholder_keys_removed']} placeholder keys — from {path}"
    )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    store = lib.load_store(args.store_id)
    try:
        ptr = lib.load_backup_path(store.store_id, None)
        print("latest backup:", ptr)
    except FileNotFoundError:
        print("no backup on file")
    offer_ids = lib.product_offer_ids(store.store_id)
    with httpx.Client() as client:
        status = lib.campaign_status_map(client, store, offer_ids)
    counts: dict[str, int] = {}
    for st in status.values():
        counts[st] = counts.get(st, 0) + 1
    print(f"offers={len(offer_ids)} status={counts}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Review campaign price setup / undo")
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("setup", help="Backup, lower prices, unhide, fix until published")
    ps.add_argument("--store-id", type=int, default=None)
    ps.add_argument("--offers", type=str, default="", help="Comma-separated offerIds")
    ps.add_argument("--max-reviews", type=int, default=None, help="Only SKUs with review count < N")
    ps.add_argument("--no-reviews-only", action="store_true")
    ps.add_argument("--price", type=float, default=None, help="Starting RUR (default first REVIEW_PRICE_STEPS)")
    ps.add_argument("--wait", type=int, default=60, help="Seconds between error checks")
    ps.add_argument("--max-rounds", type=int, default=8)
    ps.set_defaults(func=cmd_setup)

    pu = sub.add_parser("undo", help="Restore prices from latest backup")
    pu.add_argument("--store-id", type=int, default=None)
    pu.add_argument("--snapshot", type=str, default=None)
    pu.set_defaults(func=cmd_undo)

    pst = sub.add_parser("status", help="Show backup pointer and campaign statuses")
    pst.add_argument("--store-id", type=int, default=None)
    pst.set_defaults(func=cmd_status)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())