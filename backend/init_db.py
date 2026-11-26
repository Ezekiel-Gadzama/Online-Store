"""
Initialize database on a fresh server (Docker entrypoint / first deploy).

Schema lives in SQLAlchemy models + schema_bootstrap; no separate migration script folder required.
"""
import sys

from app.database import SessionLocal, engine, Base
from app.initial_data import (
    create_default_documentation,
    create_default_email_template,
    create_default_marketing_email_template,
    create_default_settings,
)
from app.schema_bootstrap import ensure_database_schema


def init_database() -> None:
    print("Ensuring base tables exist...")
    try:
        Base.metadata.create_all(bind=engine)
        print("✓ Base tables created/verified")
    except Exception as e:
        print(f"✗ Error creating base tables: {e}")
        sys.exit(1)

    db = SessionLocal()
    try:
        ensure_database_schema(db)
        db.commit()
        print("✓ Schema indexes and constraints ready")
    except Exception as e:
        db.rollback()
        print(f"✗ Schema bootstrap: {e}")
        sys.exit(1)
    finally:
        db.close()

    print("Creating default settings and templates...")
    try:
        create_default_settings()
        create_default_email_template()
        create_default_marketing_email_template()
        create_default_documentation()
        print("✓ Default business data ready")
    except Exception as e:
        print(f"⚠ Warning: default data: {e}")


if __name__ == "__main__":
    init_database()