import type { StoreMarketAccess } from './staffStoreAccess'
import type { UserPermissions } from '../api/auth'

/** New staff form defaults (Kate-style business admin, one store, Yandex). */
export const DEFAULT_NEW_STAFF_PERMISSIONS: UserPermissions = {
  view_staff: true,
  view_settings: true,
  client_right: true,
  view_marketing_emails: true,
  dashboard_right: true,
  view_product_prices: true,
  create_store: false,
  delete_store: false,
}

export function defaultNewStaffStoreAccess(storeId: number | undefined): StoreMarketAccess {
  if (storeId == null) {
    return { all_stores: false, stores: {} }
  }
  return { all_stores: false, stores: { [String(storeId)]: ['yandex'] } }
}