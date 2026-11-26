import { useEffect, useRef, useState } from 'react'
import { ChevronDown, Layers, Plus } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useStore } from '../contexts/StoreContext'
import { useAuth } from '../contexts/AuthContext'
import { marketplaceConnectionsApi, MARKETPLACE_OPTIONS } from '../api/marketplaceConnections'
import { authApi } from '../api/auth'
import { loadStoreViewPrefs, persistStoreViewPrefs, type StoreViewPrefs } from '../utils/storeSelection'
import { allowedMarketplacesForStore } from '../utils/staffStoreAccess'

function marketplaceLabel(id: string, custom?: string | null) {
  if (custom?.trim()) return custom.trim()
  return MARKETPLACE_OPTIONS.find((o) => o.id === id)?.label ?? id
}

export default function StoreViewControls() {
  const { currentStore } = useStore()
  const { user, refreshUser } = useAuth()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState<string[]>([])
  const ref = useRef<HTMLDivElement>(null)
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const storeId = currentStore?.id
  const canConfigureApi = !!user?.is_admin || user?.permissions?.view_settings === true

  const { data: connections = [] } = useQuery({
    queryKey: ['marketplace-connections', storeId],
    queryFn: () => marketplaceConnectionsApi.list(),
    enabled: storeId != null,
  })

  const allowedSlugs = allowedMarketplacesForStore(user, storeId ?? -1)
  const enabled = connections.filter((c) => {
    if (!c.is_enabled) return false
    if (allowedSlugs === null) return true
    return allowedSlugs.includes(c.marketplace.toLowerCase())
  })

  useEffect(() => {
    if (storeId == null) return
    const enabledSlugs = enabled.map((c) => c.marketplace.toLowerCase())
    if (!enabledSlugs.length) {
      setSelected([])
      return
    }
    const loaded = loadStoreViewPrefs(storeId, user?.store_ui_preferences ?? null)
    const fromPrefs = (loaded.selected_marketplaces.length ? loaded.selected_marketplaces : enabledSlugs).map((s) =>
      s.toLowerCase(),
    )
    const valid = fromPrefs.filter((s) => enabledSlugs.includes(s))
    const next = valid.length ? valid : enabledSlugs
    setSelected(next)
    if (!valid.length || valid.length !== fromPrefs.length) {
      persistStoreViewPrefs(storeId, { selected_marketplaces: next })
    }
  }, [storeId, user?.store_ui_preferences, enabled.map((c) => c.marketplace).join(',')])

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    if (open) {
      document.addEventListener('mousedown', onClick)
      return () => document.removeEventListener('mousedown', onClick)
    }
  }, [open])

  const applySelection = (next: string[]) => {
    if (storeId == null) return
    const slugs = [...new Set(next.map((s) => s.toLowerCase()))]
    if (!slugs.length) return
    setSelected(slugs)
    const prefs: StoreViewPrefs = { selected_marketplaces: slugs }
    persistStoreViewPrefs(storeId, prefs)
    queryClient.invalidateQueries()
    if (saveTimer.current) clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(async () => {
      const base =
        user?.store_ui_preferences && typeof user.store_ui_preferences === 'object'
          ? { ...user.store_ui_preferences }
          : {}
      base[String(storeId)] = { selected_marketplaces: slugs }
      try {
        await authApi.updateProfile({ store_ui_preferences: base })
        await refreshUser()
      } catch {
        /* local prefs apply */
      }
    }, 400)
  }

  const toggle = (slug: string) => {
    if (allowedSlugs !== null && !allowedSlugs.includes(slug)) return
    const on = selected.includes(slug)
    if (on && selected.length === 1) return
    const next = on ? selected.filter((s) => s !== slug) : [...selected, slug]
    applySelection(next)
  }

  const selectedOnStore = selected.filter((s) =>
    enabled.some((c) => c.marketplace.toLowerCase() === s.toLowerCase()),
  )
  const summary =
    !enabled.length || !selectedOnStore.length || selectedOnStore.length === enabled.length
      ? 'All marketplaces'
      : selectedOnStore.length === 1
        ? marketplaceLabel(
            selectedOnStore[0],
            enabled.find((c) => c.marketplace.toLowerCase() === selectedOnStore[0].toLowerCase())?.label,
          )
        : `${selectedOnStore.length} marketplaces`

  if (!storeId) return null

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-2 max-w-[240px] px-3 py-1.5 text-sm text-gray-700 border border-gray-300 rounded-md bg-white hover:bg-gray-50"
      >
        <Layers className="h-4 w-4 shrink-0 text-gray-500" />
        <span className="truncate">{summary}</span>
        <ChevronDown className="h-4 w-4 shrink-0 text-gray-500" />
      </button>

      {open && (
        <div className="absolute left-0 mt-1 w-72 rounded-md border border-gray-200 bg-white shadow-lg z-50 p-3 text-sm">
          {currentStore?.name ? (
            <p className="text-xs font-medium text-gray-700 mb-2">{currentStore.name}</p>
          ) : null}
          {enabled.length === 0 ? (
            <div className="space-y-2">
              {canConfigureApi ? (
                <Link
                  to="/settings?tab=marketplace"
                  className="inline-flex items-center gap-1 text-xs font-medium text-blue-700 hover:text-blue-800"
                  onClick={() => setOpen(false)}
                >
                  <Plus className="h-3.5 w-3.5" />
                  Add marketplace API
                </Link>
              ) : null}
            </div>
          ) : (
            <ul className="space-y-2">
              {enabled.map((c) => (
                <li key={c.id}>
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={selected.includes(c.marketplace)}
                      disabled={
                        allowedSlugs !== null && !allowedSlugs.includes(c.marketplace.toLowerCase())
                      }
                      onChange={() => toggle(c.marketplace)}
                    />
                    <span>{marketplaceLabel(c.marketplace, c.label)}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}