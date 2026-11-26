import type { User } from '../api/auth'

export type StoreMarketAccess = {
  all_stores?: boolean
  stores?: Record<string, string[]>
}

export function userStoreMarketAccess(user: User | null): StoreMarketAccess | null {
  const raw = user?.store_market_access
  if (!raw || typeof raw !== 'object') return null
  return raw as StoreMarketAccess
}

/** null = all marketplaces allowed for this store */
export function allowedMarketplacesForStore(user: User | null, storeId: number): string[] | null {
  if (!user || user.is_admin) return null
  const access = userStoreMarketAccess(user)
  if (!access) return []
  if (access.all_stores) return null
  const list = access.stores?.[String(storeId)]
  if (!Array.isArray(list)) return []
  return list.map((m) => String(m).toLowerCase()).filter(Boolean)
}

export function canCreateStore(user: User | null | undefined): boolean {
  if (!user) return false
  return user.is_admin || !!user.permissions?.create_store
}

export function canDeleteStore(user: User | null | undefined): boolean {
  if (!user) return false
  return user.is_admin || !!user.permissions?.delete_store
}