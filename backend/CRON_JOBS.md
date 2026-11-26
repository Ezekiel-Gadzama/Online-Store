# Cron Jobs for Online Store

**When running via Docker**, sync runs **automatically** in the backend container:
- Orders: every 60 seconds
- Products: every 15 minutes

No extra setup needed. For non-Docker deployments, use the manual cron setup below.

## Available Jobs

| Job | Description | Recommended interval |
|-----|-------------|----------------------|
| `orders` | Sync orders from Yandex, update statuses, auto-send activations | Every 1–5 minutes |
| `products` | Sync products/catalog from Yandex | Every 15–60 minutes |
| `all` | Run products then orders | Use if you prefer a single cron entry |

## Running Manually

From the project root (where `backend/` is):

```bash
cd backend
python -m app.jobs.runner orders
python -m app.jobs.runner products
python -m app.jobs.runner all
```

## Linux / macOS (crontab)

Edit crontab: `crontab -e`

```cron
# Sync orders every minute
* * * * * cd /path/to/Yandex\ Market/backend && python -m app.jobs.runner orders

# Sync products every 15 minutes
*/15 * * * * cd /path/to/Yandex\ Market/backend && python -m app.jobs.runner products
```

Replace with your project path (e.g. `C:\Users\ezeki\PycharmProjects\Online Store`).

## Windows (Task Scheduler)

1. Open Task Scheduler
2. Create Basic Task
3. Trigger: Daily, repeat every 1 minute (for orders) or 15 minutes (for products)
4. Action: Start a program
   - Program: `python`
   - Arguments: `-m app.jobs.runner orders`
   - Start in: `C:\path\to\Online Store\backend`

## Requirements

- Each business must have Yandex API configured in Settings (API token, Business ID).
- Jobs run only for businesses that have `yandex_api_token` or `yandex_business_id` set in `app_settings`.
