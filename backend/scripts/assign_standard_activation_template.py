"""Set email_template_id for all products to the standard digital activation template."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "/app" if Path("/app/app").exists() else str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func

from app.database import SessionLocal
from app import models

TEMPLATE_NAME = "Стандартный шаблон активации (digital)"


def main() -> int:
    db = SessionLocal()
    tpl = (
        db.query(models.EmailTemplate)
        .filter(models.EmailTemplate.name == TEMPLATE_NAME)
        .order_by(models.EmailTemplate.id.asc())
        .first()
    )
    if not tpl:
        tpl = (
            db.query(models.EmailTemplate)
            .filter(models.EmailTemplate.name.ilike("%Стандартный шаблон активации%"))
            .order_by(models.EmailTemplate.id.asc())
            .first()
        )
    if not tpl:
        rows = db.query(models.EmailTemplate.id, models.EmailTemplate.name).limit(30).all()
        print("template not found; existing:", rows)
        return 1

    q = db.query(models.Product)
    if tpl.store_id:
        q = q.filter(models.Product.store_id == tpl.store_id)
    else:
        q = q.filter(models.Product.business_id == tpl.business_id)

    products = q.all()
    before = sum(1 for p in products if p.email_template_id == tpl.id)
    for p in products:
        p.email_template_id = tpl.id
    db.commit()
    print(f"template id={tpl.id} name={tpl.name!r}")
    print(f"updated {len(products)} products ({before} already had this template)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())