import apiClient from './client'

export type MarketplaceId = 'yandex' | 'ozon' | 'wildberries' | 'aliexpress' | 'other'

export interface MarketplaceConnection {
  id: number
  store_id: number
  marketplace: MarketplaceId
  label: string | null
  credentials: Record<string, string>
  is_enabled: boolean
}

export interface MarketplaceConnectionInput {
  marketplace: MarketplaceId
  label?: string | null
  credentials: Record<string, string>
  is_enabled?: boolean
}

export const marketplaceConnectionsApi = {
  list: async (): Promise<MarketplaceConnection[]> => {
    const res = await apiClient.get<MarketplaceConnection[]>('/marketplace-connections/')
    return res.data
  },
  create: async (body: MarketplaceConnectionInput): Promise<MarketplaceConnection> => {
    const res = await apiClient.post<MarketplaceConnection>('/marketplace-connections/', body)
    return res.data
  },
  update: async (id: number, body: Partial<MarketplaceConnectionInput>): Promise<MarketplaceConnection> => {
    const res = await apiClient.put<MarketplaceConnection>(`/marketplace-connections/${id}`, body)
    return res.data
  },
  remove: async (id: number): Promise<void> => {
    await apiClient.delete(`/marketplace-connections/${id}`)
  },
}

export const MARKETPLACE_OPTIONS: { id: MarketplaceId; label: string }[] = [
  { id: 'yandex', label: 'Yandex Market' },
  { id: 'ozon', label: 'Ozon' },
  { id: 'wildberries', label: 'Wildberries' },
  { id: 'aliexpress', label: 'AliExpress' },
  { id: 'other', label: 'Other' },
]