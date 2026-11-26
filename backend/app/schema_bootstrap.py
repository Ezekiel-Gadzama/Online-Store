"""Post-create_all schema bits SQLAlchemy cannot express (indexes, enums). Safe on empty DB."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def ensure_database_schema(db: Session) -> None:
    """Idempotent extras after Base.metadata.create_all — new servers need no separate migration scripts."""
    db.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'finished'
                AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'orderstatus')
            ) THEN
                ALTER TYPE orderstatus ADD VALUE 'finished';
            END IF;
        END $$;
    """))

    db.execute(text("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_email_key"))
    db.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_admin_email_unique "
        "ON users (email) WHERE is_admin = true"
    ))
    db.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_staff_email_business_unique "
        "ON users (email, created_by_id) WHERE is_admin = false AND created_by_id IS NOT NULL"
    ))

    for con in (
        "app_settings_business_id_key",
        "uq_app_settings_business_id",
        "app_settings_business_id_unique",
    ):
        db.execute(text(f"ALTER TABLE app_settings DROP CONSTRAINT IF EXISTS {con}"))
    db.execute(text("DROP INDEX IF EXISTS ix_app_settings_business_id"))
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_app_settings_business_id ON app_settings (business_id)"
    ))
    db.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_app_settings_store_id "
        "ON app_settings (store_id) WHERE store_id IS NOT NULL"
    ))

    db.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_product_store_yandex_id "
        "ON products (store_id, yandex_market_id) "
        "WHERE yandex_market_id IS NOT NULL AND yandex_market_id <> ''"
    ))
    db.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_product_store_yandex_sku "
        "ON products (store_id, yandex_market_sku) "
        "WHERE yandex_market_sku IS NOT NULL AND yandex_market_sku <> ''"
    ))

    db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_products_yandex_market_id ON products(yandex_market_id)
    """))
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_products_yandex_market_sku ON products(yandex_market_sku)
    """))
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_products_store_id ON products (store_id)
    """))

    db.execute(text("""
        ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_yandex_order_id_key
    """))
    db.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE table_name = 'orders' AND constraint_name = 'uq_order_yandex_product'
            ) THEN
                ALTER TABLE orders
                ADD CONSTRAINT uq_order_yandex_product UNIQUE (yandex_order_id, product_id);
            END IF;
        END $$;
    """))

    db.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_msg_sender_biz_mid
        ON chat_message_senders (business_id, yandex_message_id)
    """))
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_chat_message_senders_order_id ON chat_message_senders(order_id)
    """))
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_chat_read_status_order_id ON chat_read_status(order_id)
    """))
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_product_cost_history_product_id ON product_cost_history(product_id)
    """))
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_product_cost_history_dates
        ON product_cost_history(product_id, start_date, end_date)
    """))

    db.commit()