import type { User, UserPermissions } from '../api/auth'

export const PERM_KEYS: (keyof UserPermissions)[] = [
  'view_staff',
  'view_settings',
  'client_right',
  'view_marketing_emails',
  'dashboard_right',
  'view_product_prices',
  'create_store',
  'delete_store',
]

export function permissionsForStore(member: User, storeId: number | null): UserPermissions {
  if (storeId == null) return member.permissions
  const byStore = member.store_permissions
  if (!byStore || typeof byStore !== 'object') return member.permissions
  const raw = byStore[String(storeId)]
  if (!raw || typeof raw !== 'object') return member.permissions
  const merged = { ...member.permissions }
  for (const k of PERM_KEYS) {
    if (k in raw) {
      merged[k] = !!(raw as Record<string, boolean>)[k]
    }
  }
  return merged
}