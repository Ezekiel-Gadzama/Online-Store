import apiClient from './client'

export interface MarketStore {
  id: number
  name: string
  yandex_campaign_id?: string | null
  yandex_business_id?: string | null
  store_types?: string[]
}

export interface CreateStorePayload {
  name: string
  copy_settings_from_store_id?: number | null
  store_types?: string[]
}

export interface StoreAttentionFlags {
  has_attention: boolean
  missing_api: boolean
  pending_orders: number
  chats_waiting: number
}

export const storesApi = {
  list: async (): Promise<MarketStore[]> => {
    const res = await apiClient.get<MarketStore[]>('/stores/')
    return res.data
  },
  create: async (payload: CreateStorePayload): Promise<MarketStore> => {
    const res = await apiClient.post<MarketStore>('/stores/', payload)
    return res.data
  },
  requestDeleteOtp: async (storeId: number): Promise<{ message: string; expires_in_minutes: number }> => {
    const res = await apiClient.post<{ message: string; expires_in_minutes: number }>(
      `/stores/${storeId}/delete-request`,
    )
    return res.data
  },
  deleteStore: async (storeId: number, otp: string): Promise<{ success: boolean }> => {
    const res = await apiClient.delete<{ success: boolean }>(`/stores/${storeId}`, { data: { otp } })
    return res.data
  },
  updateStoreTypes: async (storeId: number, store_types: string[]): Promise<MarketStore> => {
    const res = await apiClient.patch<MarketStore>(`/stores/${storeId}`, { store_types })
    return res.data
  },
  attention: async (seen_at: Record<string, string>): Promise<{ stores: Record<string, StoreAttentionFlags> }> => {
    const res = await apiClient.post<{ stores: Record<string, StoreAttentionFlags> }>('/stores/attention', {
      seen_at,
    })
    return res.data
  },
}