import apiClient from './client'

export interface OwnerRestrictions {
  permissions: Partial<Record<keyof UserPermissions, boolean>>
  store_market_access?: boolean
  password_change?: boolean
}

export interface User {
  id: number
  email: string
  name?: string | null
  is_admin: boolean
  is_business_admin?: boolean
  business_admin_all_stores?: boolean
  owner_restrictions?: OwnerRestrictions | null
  created_by_id: number | null
  permissions: UserPermissions
  is_active: boolean
  business_name?: string | null
  business_username?: string | null
  timezone?: string | null
  store_ui_preferences?: Record<
    string,
    { selected_marketplaces?: string[]; data_view?: string; active_marketplace?: string | null }
  > | null
  store_market_access?: { all_stores?: boolean; stores?: Record<string, string[]> } | null
  store_permissions?: Record<string, Partial<UserPermissions>> | null
  created_at: string
  updated_at: string | null
}

export interface UserProfileUpdate {
  name?: string | null
  timezone?: string | null
  store_ui_preferences?: Record<
    string,
    { selected_marketplaces?: string[]; data_view?: string; active_marketplace?: string | null }
  >
}

export interface UserPermissions {
  view_staff: boolean
  view_settings: boolean
  client_right: boolean
  view_marketing_emails: boolean
  dashboard_right: boolean
  view_product_prices: boolean
  create_store: boolean
  delete_store: boolean
}

export interface Token {
  access_token: string
  token_type: string
  user: User
}

export interface UserSignup {
  email: string
  password: string
  business_name?: string
  business_username?: string  // e.g. @Goal_sale
}

export interface UserLogin {
  business_identifier: string  // Admin email OR business username (e.g. @Goal_sale)
  email: string
  password: string
  remember_me?: boolean
}

export interface ChangePassword {
  previous_password: string
  new_password: string
}

export interface PasswordResetRequest {
  identifier: string  // Admin email OR business username (e.g. @Goal_sale)
}

export interface PasswordReset {
  token: string
  new_password: string
}

export interface PasswordResetWithPrevious {
  business_identifier: string  // Admin email OR business username (e.g. @Goal_sale)
  staff_email: string
  previous_password: string
  new_password: string
}

export const authApi = {
  signup: async (data: UserSignup): Promise<Token> => {
    const response = await apiClient.post<Token>('/auth/signup', data)
    return response.data
  },

  login: async (data: UserLogin): Promise<Token> => {
    const response = await apiClient.post<Token>('/auth/login', data)
    return response.data
  },

  getMe: async (): Promise<User> => {
    const response = await apiClient.get<User>('/auth/me')
    return response.data
  },

  updateProfile: async (data: UserProfileUpdate): Promise<User> => {
    const response = await apiClient.patch<User>('/auth/me/profile', data)
    return response.data
  },

  requestPasswordReset: async (data: PasswordResetRequest): Promise<{ message: string }> => {
    const response = await apiClient.post<{ message: string }>('/auth/request-password-reset', data)
    return response.data
  },

  resetPassword: async (data: PasswordReset): Promise<{ message: string }> => {
    const response = await apiClient.post<{ message: string }>('/auth/reset-password', data)
    return response.data
  },

  resetPasswordWithPrevious: async (data: PasswordResetWithPrevious): Promise<{ message: string }> => {
    const response = await apiClient.post<{ message: string }>('/auth/reset-password-with-previous', data)
    return response.data
  },

  changePassword: async (data: ChangePassword): Promise<{ message: string }> => {
    const response = await apiClient.post<{ message: string }>('/auth/change-password', data)
    return response.data
  },
}
