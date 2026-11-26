import apiClient from './client'
import { User, UserPermissions, OwnerRestrictions } from './auth'
import type { StoreMarketAccess } from '../utils/staffStoreAccess'

export interface StaffCreate {
  email: string
  name?: string  // Optional display name for staff
  password?: string  // Optional. If set, staff uses this to login or reset at /reset-password
  store_market_access?: StoreMarketAccess
  is_business_admin?: boolean
  business_admin_all_stores?: boolean
}

export interface StaffCreateResponse {
  user: User
  invitation_email_sent: boolean
}

export interface UserUpdate {
  permissions?: UserPermissions
  is_active?: boolean
  name?: string  // Display name for staff (optional)
  new_password?: string  // Admin can set staff password directly
  store_market_access?: StoreMarketAccess
  apply_permissions_to_all_stores?: boolean
  permissions_store_id?: number | null
  is_business_admin?: boolean
  business_admin_all_stores?: boolean
  owner_restrictions?: OwnerRestrictions
}

export interface BusinessAccountUpdate {
  new_email?: string
  new_password?: string
  name?: string
  business_name?: string
  new_business_username?: string  // e.g. @Goal_sale
}

export const staffApi = {
  getAll: async (): Promise<User[]> => {
    const response = await apiClient.get<User[]>('/staff/')
    return response.data
  },

  create: async (data: StaffCreate): Promise<StaffCreateResponse> => {
    const response = await apiClient.post<StaffCreateResponse>('/staff/', data)
    return response.data
  },

  update: async (id: number, data: UserUpdate): Promise<User> => {
    const response = await apiClient.put<User>(`/staff/${id}`, data)
    return response.data
  },

  delete: async (id: number): Promise<void> => {
    await apiClient.delete(`/staff/${id}`)
  },

  resendPasswordReset: async (id: number): Promise<{ message: string }> => {
    const response = await apiClient.post<{ message: string }>(`/staff/${id}/resend-password-reset`)
    return response.data
  },

  getBusinessAccount: async (): Promise<User> => {
    const response = await apiClient.get<User>('/staff/business-account')
    return response.data
  },

  updateBusinessAccount: async (data: BusinessAccountUpdate): Promise<User> => {
    const response = await apiClient.put<User>('/staff/business-account', data)
    return response.data
  },
}
