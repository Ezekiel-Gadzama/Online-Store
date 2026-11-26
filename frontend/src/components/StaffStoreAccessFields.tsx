import { useQuery } from '@tanstack/react-query'
import { storesApi } from '../api/stores'
import { MARKETPLACE_OPTIONS } from '../api/marketplaceConnections'
import type { StoreMarketAccess } from '../utils/staffStoreAccess'
import {
  actorMayGrantAllStores,
  actorStoreAccessGrantCeiling,
  canGrantMarketForStore,
  canGrantStoreForActor,
} from '../utils/staffRoles'
import type { User } from '../api/auth'

export default function StaffStoreAccessFields({
  value,
  onChange,
  actor,
}: {
  value: StoreMarketAccess
  onChange: (v: StoreMarketAccess) => void
  /** Logged-in user — limits to store/market pairs they already have. */
  actor?: User | null
}) {
  const { data: stores = [] } = useQuery({
    queryKey: ['stores'],
    queryFn: () => storesApi.list(),
  })

  const allStores = !!value.all_stores
  const storesMap = value.stores ?? {}

  const ceiling = actorStoreAccessGrantCeiling(actor ?? null)
  const canAll = actorMayGrantAllStores(actor ?? null)

  const setAllStores = (checked: boolean) => {
    if (checked && !canAll) return
    onChange({ all_stores: checked, stores: storesMap })
  }

  const canPickMarket = (storeId: number, slug: string) =>
    canGrantMarketForStore(ceiling, storeId, slug)

  const toggleMarket = (storeId: number, slug: string) => {
    const key = String(storeId)
    const cur = storesMap[key] ?? []
    const next = cur.includes(slug) ? cur.filter((s) => s !== slug) : [...cur, slug]
    onChange({ all_stores: false, stores: { ...storesMap, [key]: next } })
  }

  return (
    <div className="mb-4 border-t pt-4">
      <h4 className="text-sm font-medium text-gray-900 mb-2">Store &amp; marketplace access</h4>
      <div className="flex items-center mb-3">
        <input
          type="checkbox"
          checked={allStores}
          disabled={!canAll}
          onChange={(e) => setAllStores(e.target.checked)}
          className="mr-2"
        />
        <span className="text-sm text-gray-700">All stores and all marketplaces</span>
      </div>
      {!allStores && (
        <div className="space-y-3 max-h-48 overflow-y-auto">
          {stores.filter((store) => canGrantStoreForActor(ceiling, store.id)).map((store) => (
            <div key={store.id} className="rounded border border-gray-200 p-2">
              <p className="text-sm font-medium text-gray-800 mb-1">{store.name}</p>
              <div className="flex flex-wrap gap-2">
                {MARKETPLACE_OPTIONS.map((m) => (
                  <div key={m.id} className="flex items-center text-xs text-gray-700">
                    <input
                      type="checkbox"
                      className="mr-1"
                      disabled={!canPickMarket(store.id, m.id)}
                      checked={(storesMap[String(store.id)] ?? []).includes(m.id)}
                      onChange={() => toggleMarket(store.id, m.id)}
                    />
                    {m.label}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}