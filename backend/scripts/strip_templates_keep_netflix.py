"""Clear activation templates on all store products except Netflix Full HD; keep that SKU visible."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, "/app" if Path("/app/app").exists() else str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app import models

KEEP_SKUS = frozenset({"NFLX-Full-HD-1M-RU"})


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--store-id", type=int, default=1)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    db = SessionLocal()
    products = db.query(models.Product).filter(models.Product.store_id == args.store_id).all()
    cleared = 0
    kept = 0
    for prod in products:
        sku = (prod.yandex_market_sku or prod.yandex_market_id or "").strip()
        if sku in KEEP_SKUS:
            kept += 1
            continue
        if prod.email_template_id is not None:
            if not args.dry_run:
                prod.email_template_id = None
            cleared += 1
    if not args.dry_run:
        db.commit()
    print(f"store_id={args.store_id} templates_cleared={cleared} netflix_kept={kept} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())