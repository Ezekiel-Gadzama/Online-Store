const STORE_KEY = 'active_store_id'
const VIEW_PREFS_KEY = 'store_ui_view_prefs'

export interface StoreViewPrefs {
  selected_marketplaces: string[]
}

let activeStoreId: number | null = null
let selectedMarketplaces: string[] = []

function readViewPrefsMap(): Record<string, StoreViewPrefs> {
  try {
    const raw = localStorage.getItem(VIEW_PREFS_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as Record<string, StoreViewPrefs>
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function writeViewPrefsMap(map: Record<string, StoreViewPrefs>) {
  localStorage.setItem(VIEW_PREFS_KEY, JSON.stringify(map))
}

export function setActiveStoreId(id: number | null) {
  activeStoreId = id
  if (id == null) {
    localStorage.removeItem(STORE_KEY)
  } else {
    localStorage.setItem(STORE_KEY, String(id))
  }
}

export function getActiveStoreId(): number | null {
  if (activeStoreId != null) {
    return activeStoreId
  }
  const raw = localStorage.getItem(STORE_KEY)
  if (!raw) return null
  const n = Number(raw)
  return Number.isFinite(n) ? n : null
}

export function setSelectedMarketplaces(slugs: string[]) {
  selectedMarketplaces = [...new Set(slugs.map((s) => s.trim().toLowerCase()).filter(Boolean))]
}

export function getSelectedMarketplaces(): string[] {
  return selectedMarketplaces
}

export function getMarketplacesHeader(): string | null {
  if (!selectedMarketplaces.length) return null
  return selectedMarketplaces.join(',')
}

/** @deprecated kept for API client compatibility */
export function getDataViewHeader(): 'merge' | 'separate' {
  return selectedMarketplaces.length === 1 ? 'separate' : 'merge'
}

export function getMarketplaceHeader(): string | null {
  return selectedMarketplaces.length === 1 ? selectedMarketplaces[0] : null
}

function prefsFromUserBlock(
  remote?: { selected_marketplaces?: string[]; data_view?: string; active_marketplace?: string | null },
  local?: StoreViewPrefs,
): StoreViewPrefs {
  if (remote?.selected_marketplaces?.length) {
    return { selected_marketplaces: remote.selected_marketplaces.map((m) => String(m).toLowerCase()) }
  }
  if (local?.selected_marketplaces?.length) {
    return local
  }
  if (remote?.data_view === 'separate' && remote?.active_marketplace) {
    return { selected_marketplaces: [String(remote.active_marketplace).toLowerCase()] }
  }
  return { selected_marketplaces: [] }
}

export function loadStoreViewPrefs(
  storeId: number,
  fromUser?: Record<string, { selected_marketplaces?: string[]; data_view?: string; active_marketplace?: string | null }> | null,
): StoreViewPrefs {
  const local = readViewPrefsMap()[String(storeId)]
  const prefs = prefsFromUserBlock(fromUser?.[String(storeId)], local)
  setSelectedMarketplaces(prefs.selected_marketplaces)
  const map = readViewPrefsMap()
  map[String(storeId)] = prefs
  writeViewPrefsMap(map)
  return prefs
}

export function persistStoreViewPrefs(storeId: number, prefs: StoreViewPrefs) {
  const map = readViewPrefsMap()
  map[String(storeId)] = prefs
  writeViewPrefsMap(map)
  setSelectedMarketplaces(prefs.selected_marketplaces)
  window.dispatchEvent(
    new CustomEvent('store-view-prefs-changed', {
      detail: { storeId, selected_marketplaces: prefs.selected_marketplaces },
    }),
  )
}