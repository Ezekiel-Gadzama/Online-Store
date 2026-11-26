# Deploy on develop-vps (144.172.100.41)

Runs **alongside** `church-app` (ports 3000, 3101, 8090, 8101, host Postgres). This stack uses:

| Service  | Host port |
|----------|-----------|
| Frontend | **3010**  |
| Backend  | **8010**  |
| Postgres | **5440** (container only; not host system DB) |

## One-shot deploy from Windows (project root)

```powershell
$env:VPS_PASSWORD = "<root-password>"
$env:VPS_YANDEX_TOKEN = "<ACMA:...>"
$env:VPS_SMTP_PASSWORD = "<app-password>"
python scripts/deploy_vps.py
```

The script installs Docker if missing, uploads the project, writes `/opt/yandex-market/.env` (legacy path name on the server), builds `docker-compose.vps.yml`, and runs `init_db`. Application title: **Online Store**.

## After first login (create admin)

1. Open http://144.172.100.41:3010 and **sign up** with your ezekiel email (first user = admin).
2. On the server:

```bash
cd /opt/yandex-market
docker compose -f docker-compose.vps.yml exec backend python scripts/vps_bootstrap.py
docker compose -f docker-compose.vps.yml exec backend python scripts/test_yandex_setup.py
```

`vps_bootstrap.py` sets Yandex business id **217104046**, API token, SMTP from `.env`, and deletes stored data for businesses whose admin email does **not** contain `ezekiel`.

## Yandex business id

Configure in **Settings** or `.env` as `YANDEX_MARKET_BUSINESS_ID=217104046`.

If Yandex returns `API_DISABLED` ("only disabled partners"), enable the shop/API in the [Yandex Market partner cabinet](https://partner.market.yandex.ru/) — the VPS stack can still run; sync works after Yandex enables the cabinet.

## API changes implemented (Telegram channel)

- Stocks / partner warehouses: **v3** (`/offers/stocks`, `/offers/stocks/update`, `/warehouses`).
- Business order list fallback: **POST** `v1/businesses/{businessId}/orders`.
- `GET v2/campaigns` uses `pageToken` pagination; `X-Business-Id` header sent when business id is set.

## Nginx (optional)

To expose on port 19082 without touching church nginx on 80/19080:

```nginx
server {
    listen 19082;
    server_name _;
    location / {
        proxy_pass http://127.0.0.1:3010;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## IPv6

Same ports on `2602:fa59:10:2f5::1` if the firewall allows them.