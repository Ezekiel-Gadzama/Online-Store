# Backend scripts (kept on purpose)

Fresh servers rely on **app startup** (`schema_bootstrap`, `store_bootstrap`, `initial_data`) and **Docker `init_db.py`** — not one-off patch scripts.

| Script | Use |
|--------|-----|
| `store_setup.py` | Digital (and future) store-type catalog: append, push, db-import |
| `migrate_yandex_store.py` | Low-level catalog export/push/import |
| `yandex_token.py` | Resolve API token from env or DB |
| `vps_bootstrap.py` | Optional VPS: prune sandbox data, apply env to `app_settings` |
| `test_yandex_setup.py` | Smoke-test Yandex credentials after deploy |
| `review_price_lib.py` / `review_price_setup.py` | Optional review-campaign price workflow (see `.cursor/rules/review-setup-prices.mdc`) |

Deploy from repo root: `scripts/deploy_vps.py`.