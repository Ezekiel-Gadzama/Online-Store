# Deploy Online Store on VPS

Install path: **`/opt/online-store`**  
Compose: `docker-compose.vps.yml`  
Containers: `online-store-postgres`, `online-store-backend`, `online-store-frontend`

## Deploy from your PC

```powershell
cd "C:\Users\ezeki\PycharmProjects\Online Store"
$env:VPS_PASSWORD = "..."   # or VPS_HOST
python scripts/deploy_vps.py --skip-env   # keep existing remote .env after first deploy
```

Uploads the repo, builds images, runs `init_db` / bootstrap when not using `--skip-env`.

## On the server

```bash
cd /opt/online-store
docker compose -f docker-compose.vps.yml ps
docker compose -f docker-compose.vps.yml logs -f backend
```

Public URLs (default develop-vps): frontend `:3010`, API `:8010`.

## Yandex API

If sync returns `API_DISABLED`, enable the shop in the [Yandex partner cabinet](https://partner.market.yandex.ru/).