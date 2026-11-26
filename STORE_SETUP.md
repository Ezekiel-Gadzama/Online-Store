# Store-type default product catalogs

Each **store type** (e.g. `digital`) has a committed catalog file used to bootstrap products on a new server. Nothing is copied “from store A to store B” at deploy time — you use the file in git.

| Template id | Store types | Catalog file |
|-------------|-------------|----------------|
| `digital` | `digital` | `backend/data/store_templates/digital/catalog.json` |

Registry: `backend/app/store_templates.py`  
CLI: `backend/scripts/store_setup.py`  
Dedupe: `backend/app/catalog_bundle.py` (unique `offerId`)

## New server

1. Deploy app + Postgres.
2. Create owner, `market_stores` row, and Yandex token in settings.
3. `python scripts/store_setup.py push digital --store-id <id>` — uploads template to Yandex.
4. `python scripts/store_setup.py db-import digital --admin-user-id <id> --store-id <id>` — loads template into Postgres (no Yandex call).

## Add products to the template from any store

Export from whichever Yandex store has the catalog you want, then **merge** into the right store-type file (no duplicate `offerId`s):

```bash
python scripts/store_setup.py append-catalog digital --store-id <source_store_id>
# or
python scripts/store_setup.py append-catalog digital --business <id> --campaign <id>
```

- Default: new offerIds are added; existing offerIds in the file are **updated** from the export.
- `--new-only`: add only offerIds that are not already in the template.

Replace the whole template from one export (rare):

```bash
python scripts/store_setup.py refresh-catalog digital --store-id <id>
```

After changing `catalog.json`, commit it.

Default catalog lives only under `backend/data/store_templates/digital/`. Do not keep legacy bundles under `media/store_migration/` (old cross-store copies).

## For AI agents

When the user asks to save products as the default for a store type:

1. Identify store type (`digital`, etc.) → template id in `store_templates.py`.
2. Run **`append-catalog <template>`** with `--store-id` or `--business` / `--campaign` for the source store.
3. Commit updated `catalog.json`. Do not hand-edit duplicates — merge is by `offerId`.

Token: `YANDEX_API_TOKEN` or the source store’s token in `app_settings`.