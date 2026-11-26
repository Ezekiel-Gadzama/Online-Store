import type { User, UserPermissions, OwnerRestrictions } from '../api/auth'
import { PERM_KEYS, permissionsForStore } from './staffPermissions'
import type { StoreMarketAccess } from './staffStoreAccess'

export function isOwner(user: User | null | undefined): boolean {
  return !!user?.is_admin
}

export function isBusinessAdmin(user: User | null | undefined): boolean {
  return !!user?.is_business_admin
}

export function canViewStaff(user: User | null | undefined): boolean {
  if (!user) return false
  if (isOwner(user)) return true
  return isBusinessAdmin(user) || user.permissions.view_staff
}

export function canManageStaffRights(user: User | null | undefined): boolean {
  if (!user) return false
  if (isOwner(user)) return true
  return isBusinessAdmin(user) && !ownerLockOn(user, 'view_staff')
}

export function ownerLockOn(user: User | null | undefined, key: keyof UserPermissions): boolean {
  return !!user?.owner_restrictions?.permissions?.[key]
}

export function ownerSectionLocked(
  staff: User | null | undefined,
  section: 'store_market_access' | 'password_change',
): boolean {
  return !!staff?.owner_restrictions?.[section]
}

export function showStoreAccessEditor(actor: User, target: User): boolean {
  if (ownerSectionLocked(target, 'store_market_access')) {
    return isOwner(actor)
  }
  if (actor.id === target.id) {
    return isOwner(actor)
  }
  return isOwner(actor) || canManageStaffRights(actor)
}

/** Owner: null = no limit. Else same store/market pairs the actor has. */
export function actorStoreAccessGrantCeiling(actor: User | null | undefined): StoreMarketAccess | null {
  if (!actor || isOwner(actor)) return null
  const raw = actor.store_market_access
  if (raw?.all_stores) return null
  return {
    all_stores: false,
    stores: { ...(raw?.stores ?? {}) },
  }
}

export function actorMayGrantAllStores(actor: User | null | undefined): boolean {
  if (!actor || isOwner(actor)) return true
  return !!actor.store_market_access?.all_stores
}

export function canGrantStoreForActor(ceiling: StoreMarketAccess | null, storeId: number): boolean {
  if (!ceiling) return true
  if (ceiling.all_stores) return true
  return Object.prototype.hasOwnProperty.call(ceiling.stores ?? {}, String(storeId))
}

export function canGrantMarketForStore(
  ceiling: StoreMarketAccess | null,
  storeId: number,
  marketplaceId: string,
): boolean {
  if (!ceiling) return true
  if (ceiling.all_stores) return true
  const list = ceiling.stores?.[String(storeId)]
  if (!Array.isArray(list)) return false
  const slug = marketplaceId.toLowerCase()
  return list.some((m) => String(m).toLowerCase() === slug)
}

export function actorCanGrantPermission(
  actor: User | null | undefined,
  key: (typeof PERM_KEYS)[number],
  storeId: number | null,
): boolean {
  if (!actor) return false
  if (isOwner(actor)) return true
  if (ownerLockOn(actor, key)) return false
  if (actor.is_business_admin) {
    const perms = permissionsForEditForm(actor)
    return !!perms[key]
  }
  const perms = storeId != null ? permissionsForStore(actor, storeId) : actor.permissions
  return !!perms[key]
}

export function showPasswordEditor(actor: User, target: User): boolean {
  if (ownerSectionLocked(target, 'password_change')) {
    return isOwner(actor)
  }
  if (actor.id === target.id) {
    return false
  }
  return isOwner(actor) || canManageStaffRights(actor)
}

export function allPermissionsChecked(): UserPermissions {
  return {
    view_staff: true,
    view_settings: true,
    client_right: true,
    view_marketing_emails: true,
    dashboard_right: true,
    view_product_prices: true,
    create_store: true,
    delete_store: true,
  }
}

export function permissionsForEditForm(staff: User): UserPermissions {
  if (staff.is_business_admin) {
    const all = allPermissionsChecked()
    for (const k of PERM_KEYS) {
      if (staff.owner_restrictions?.permissions?.[k]) {
        all[k] = false
      }
    }
    return all
  }
  return staff.permissions
}

export function emptyOwnerRestrictions(): OwnerRestrictions {
  return { permissions: {}, store_market_access: false, password_change: false }
}