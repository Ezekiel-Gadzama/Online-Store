"""
Move all business-scoped rows from one admin user to another, then remove the old admin.

  docker compose -f docker-compose.vps.yml exec backend python scripts/transfer_business_owner.py \
    --from-email ezekiel.setup@local \
    --to-email genx10limited@gmail.com

Dry-run: add --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, "/app" if Path("/app/app").exists() else str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from app.database import SessionLocal
from app import models


TABLES_WITH_BUSINESS_ID = (
    models.Product,
    models.Order,
    models.Client,
    models.EmailTemplate,
    models.MarketingEmailTemplate,
    models.Documentation,
    models.ExtraCost,
    models.AppSettings,
)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--from-email", required=True)
    p.add_argument("--to-email", required=True)
    p.add_argument("--business-name", default="")
    p.add_argument("--business-username", default="")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    db = SessionLocal()
    try:
        old = (
            db.query(models.User)
            .filter(models.User.email == args.from_email.strip(), models.User.is_admin.is_(True))
            .first()
        )
        new = db.query(models.User).filter(models.User.email == args.to_email.strip()).first()
        if not old:
            print("Old admin not found:", args.from_email)
            return 1
        if not new:
            print("Target user not found:", args.to_email)
            return 1
        if old.id == new.id:
            print("Same user — nothing to do")
            return 0

        old_id, new_id = old.id, new.id
        counts = {}
        for model in TABLES_WITH_BUSINESS_ID:
            counts[model.__tablename__] = (
                db.query(model).filter(model.business_id == old_id).count()
            )

        print(f"transfer business_id {old_id} ({old.email}) -> {new_id} ({new.email})")
        for name, n in counts.items():
            print(f"  {name}: {n} rows")

        if args.dry_run:
            print("dry-run — no changes")
            return 0

        new.is_admin = True
        new.is_active = True
        new.created_by_id = None
        if args.business_name:
            new.business_name = args.business_name
        if args.business_username:
            un = args.business_username.strip()
            if not un.startswith("@"):
                un = "@" + un
            new.business_username = un
        perms = dict(new.permissions or {})
        for k in (
            "view_staff",
            "view_settings",
            "client_right",
            "view_marketing_emails",
            "dashboard_right",
        ):
            perms[k] = True
        perms.setdefault("view_product_prices", True)
        new.permissions = perms

        dest_settings = (
            db.query(models.AppSettings).filter(models.AppSettings.business_id == new_id).first()
        )
        if dest_settings:
            db.delete(dest_settings)
            db.flush()

        for model in TABLES_WITH_BUSINESS_ID:
            db.query(model).filter(model.business_id == old_id).update(
                {model.business_id: new_id}, synchronize_session=False
            )

        db.query(models.User).filter(
            models.User.created_by_id == old_id
        ).update({models.User.created_by_id: new_id}, synchronize_session=False)

        db.delete(old)
        db.commit()
        print("done — removed old admin", args.from_email)
        print(
            "new login: business",
            new.business_username or new.email,
            "| owner email",
            new.email,
        )
        s = db.query(models.AppSettings).filter(models.AppSettings.business_id == new_id).first()
        if s:
            print(
                "yandex business",
                s.yandex_business_id,
                "campaign",
                s.yandex_campaign_id,
            )
        return 0
    except Exception as e:
        db.rollback()
        print("error:", e)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())