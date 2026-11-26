import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { storesApi, type MarketStore } from '../api/stores'
import { loadStoreViewPrefs, setActiveStoreId } from '../utils/storeSelection'
import { getStoreAttentionSeenMap, markStoreAttentionSeen } from '../utils/storeAttention'
import { useAuth } from './AuthContext'

interface StoreContextValue {
  stores: MarketStore[]
  currentStore: MarketStore | null
  setCurrentStoreId: (id: number) => void
  refreshStores: () => Promise<void>
  isLoading: boolean
}

const StoreContext = createContext<StoreContextValue | null>(null)

export function StoreProvider({ children }: { children: React.ReactNode }) {
  const { user, refreshUser } = useAuth()
  const queryClient = useQueryClient()
  const [currentStoreId, setCurrentStoreIdState] = useState<number | null>(() => {
    const raw = localStorage.getItem('active_store_id')
    return raw ? Number(raw) : null
  })

  const { data: stores = [], isLoading, refetch } = useQuery({
    queryKey: ['stores'],
    queryFn: () => storesApi.list(),
    enabled: !!user,
  })

  useEffect(() => {
    if (!user) {
      setCurrentStoreIdState(null)
      setActiveStoreId(null)
      return
    }
    if (!stores.length) return
    const valid =
      currentStoreId != null && stores.some((s) => s.id === currentStoreId)
        ? currentStoreId
        : stores[0].id
    if (valid !== currentStoreId) {
      setCurrentStoreIdState(valid)
    }
    setActiveStoreId(valid)
    if (!getStoreAttentionSeenMap()[String(valid)]) {
      markStoreAttentionSeen(valid)
    }
    loadStoreViewPrefs(valid, user?.store_ui_preferences ?? null)
  }, [user, stores, currentStoreId])

  const setCurrentStoreId = useCallback(
    (id: number) => {
      setCurrentStoreIdState(id)
      setActiveStoreId(id)
      markStoreAttentionSeen(id)
      loadStoreViewPrefs(id, user?.store_ui_preferences ?? null)
      queryClient.invalidateQueries()
      void refreshUser()
    },
    [queryClient, user?.store_ui_preferences, refreshUser],
  )

  const currentStore = useMemo(
    () => stores.find((s) => s.id === currentStoreId) ?? stores[0] ?? null,
    [stores, currentStoreId],
  )

  const refreshStores = useCallback(async () => {
    await refetch()
  }, [refetch])

  const value: StoreContextValue = {
    stores,
    currentStore,
    setCurrentStoreId,
    refreshStores,
    isLoading,
  }

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>
}

export function useStore() {
  const ctx = useContext(StoreContext)
  if (!ctx) {
    throw new Error('useStore must be used within StoreProvider')
  }
  return ctx
}