# Online Store

Multi-store operations platform for digital (and future physical) sellers. Connect one or more **marketplaces** per store (Yandex Market today; more channels over time), fulfill orders, manage staff, and bootstrap catalogs from versioned templates.

## What it does

- **Stores** — Owners create multiple `market_stores`; staff access is scoped per store.
- **Marketplaces** — Per-store connections (API token, business/campaign ids). Yandex is the first supported marketplace.
- **Products** — Synced from the marketplace; optional push/import from store-type defaults (`digital` → see [STORE_SETUP.md](STORE_SETUP.md)).
- **Orders & activation** — Digital fulfillment, templates, chat with buyers (Yandex partner chat).
- **Team** — Owner vs staff roles, permissions, SMTP and settings per store where applicable.

## Repo layout

```
backend/           FastAPI, PostgreSQL, marketplace adapters
frontend/          React + TypeScript admin UI
backend/data/store_templates/   Default product bundles by store type (e.g. digital)
```

## Quick start (Docker)

```bash
cp .env.example .env
# Set DATABASE_URL / Yandex credentials for your store connection

docker compose up -d
# UI: http://localhost:3000   API: http://localhost:8000   Docs: /docs
```

See [DOCKER.md](DOCKER.md), [SETUP.md](SETUP.md), [RUN_WINDOWS.md](RUN_WINDOWS.md), [DEPLOY_VPS.md](DEPLOY_VPS.md).

## Store-type default catalogs

New servers do not copy catalog data from another live business. Use committed JSON templates:

```bash
python scripts/store_setup.py append-catalog digital --store-id <id>
python scripts/store_setup.py push digital --store-id <id>
python scripts/store_setup.py db-import digital --admin-user-id <id> --store-id <id>
```

Details: [STORE_SETUP.md](STORE_SETUP.md).

## Configuration

- **Per store:** name, store types (`digital`, …), Yandex business/campaign ids, API token (Settings or `app_settings`).
- **Env:** `YANDEX_API_TOKEN` for maintenance scripts; database and SMTP via `.env` / Docker.

## License

MIT