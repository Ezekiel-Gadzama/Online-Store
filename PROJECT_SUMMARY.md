# Project summary: Online Store

## Overview

Full-stack admin for **multiple stores** and **multiple marketplaces**. Each owner can run several stores; each store has its own marketplace connections, product sync, orders, and staff scope. Yandex Market Partner API is the first integrated marketplace; the codebase is structured so additional marketplaces can plug in alongside `marketplace_connections` and store context helpers.

## Architecture

### Backend (FastAPI + PostgreSQL)
- Store-scoped models (`store_id` on orders, products, settings, etc.)
- `MarketStore`, `StoreMarketplaceConnection`, `AppSettings` per store
- `YandexMarketAPI` — Yandex-specific client (not the product name)
- Store templates: `backend/data/store_templates/<type>/catalog.json`

### Frontend (React + TypeScript)
- Store switcher, staff store access, marketplace connection UI
- TanStack Query, Tailwind, Vite

## Major features

| Area | Status |
|------|--------|
| Multi-store ownership & staff ACL | Implemented |
| Yandex product/order sync | Implemented |
| Digital activation & email templates | Implemented |
| Partner chat | Implemented |
| Default catalog templates (`digital`) | Implemented |
| Additional marketplaces | Planned / extend `marketplace_connections` |

## API surface (high level)

Store-aware routes under `/api/stores`, `/api/sync`, `/api/orders`, `/api/products`, etc. OpenAPI at `/docs`.

## Operations docs

- [STORE_SETUP.md](STORE_SETUP.md) — template catalogs  
- [DOCKER.md](DOCKER.md) — `online-store` compose project  
- [DEPLOY_VPS.md](DEPLOY_VPS.md) — `/opt/online-store` on VPS  