"""
Fresh VPS bootstrap: prune non-owner data, apply Yandex + SMTP settings from env.

Run inside backend container after init_db:
  docker compose -f docker-compose.vps.yml exec backend python scripts/vps_bootstrap.py
"""
import os
import sys

sys.path.insert(0, "/app")

from app.database import SessionLocal
from app import models


def _env(key: str) -> str:
    return (os.environ.get(key) or "").strip()


def prune_non_owner_data(db, keep_substring: str):
    """Remove business data for admins whose email does not contain keep_substring."""
    if not keep_substring:
        print("VPS_KEEP_EMAIL_SUBSTRING empty — skipping data prune")
        return

    keep_ids = {
        row[0]
        for row in db.query(models.User.id)
        .filter(
            models.User.is_admin == True,
            models.User.email.ilike(f"%{keep_substring}%"),
        )
        .all()
    }
    if not keep_ids:
        print(f"No admin users matching email %{keep_substring}% — skip prune")
        return

    remove_admin_ids = [
        row[0]
        for row in db.query(models.User.id)
        .filter(models.User.is_admin == True, ~models.User.id.in_(keep_ids))
        .all()
    ]

    def not_kept(model):
        return db.query(model).filter(
            model.business_id.isnot(None),
            ~model.business_id.in_(keep_ids),
        )

    for model in (
        models.Order,
        models.Product,
        models.Client,
        models.EmailTemplate,
        models.MarketingEmailTemplate,
        models.Documentation,
        models.AppSettings,
    ):
        if not hasattr(model, "business_id"):
            continue
        not_kept(model).delete(synchronize_session=False)

    if remove_admin_ids:
        db.query(models.User).filter(models.User.id.in_(remove_admin_ids)).delete(
            synchronize_session=False
        )
    db.query(models.User).filter(
        models.User.is_admin == False,
        models.User.created_by_id.isnot(None),
        ~models.User.created_by_id.in_(keep_ids),
    ).delete(synchronize_session=False)

    db.commit()
    print(f"Pruned data; kept business ids: {sorted(keep_ids)}")


def apply_settings_for_admins(db):
    from app.vps_env import apply_env_settings_for_business
    admins = db.query(models.User).filter(models.User.is_admin == True).all()
    if not admins:
        print("No admin users yet — sign up at the UI, then re-run bootstrap.")
        return

    for admin in admins:
        apply_env_settings_for_business(db, admin.id)  # noqa: used via import above
    print(f"Updated app_settings for {len(admins)} admin business(es)")


def main():
    keep = (_env("VPS_KEEP_EMAIL_SUBSTRING") or "ezekiel").lower()
    db = SessionLocal()
    try:
        prune_non_owner_data(db, keep)
        apply_settings_for_admins(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()