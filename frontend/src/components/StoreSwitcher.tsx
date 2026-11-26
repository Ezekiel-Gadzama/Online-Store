import { useState, useRef, useEffect, useMemo } from 'react'
import { createPortal } from 'react-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, Plus, Trash2 } from 'lucide-react'
import { useStore } from '../contexts/StoreContext'
import { storesApi } from '../api/stores'
import { getStoreAttentionSeenMap } from '../utils/storeAttention'
import { useAuth } from '../contexts/AuthContext'
import { formatApiError } from '../utils/apiError'
import { canCreateStore, canDeleteStore } from '../utils/staffStoreAccess'
import StoreDeleteModal from './StoreDeleteModal'

export default function StoreSwitcher() {
  const { user } = useAuth()
  const { stores, currentStore, setCurrentStoreId, refreshStores, isLoading } = useStore()
  const [open, setOpen] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const [name, setName] = useState('')
  const [copySettings, setCopySettings] = useState(false)
  const [saving, setSaving] = useState(false)
  const [showDelete, setShowDelete] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    if (open) {
      document.addEventListener('mousedown', onClick)
      return () => document.removeEventListener('mousedown', onClick)
    }
  }, [open])

  useEffect(() => {
    if (!showCreate) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [showCreate])

  const title = currentStore?.name || (isLoading ? '…' : 'Store')
  const canCreate = canCreateStore(user)
  const canDelete = canDeleteStore(user) && !!currentStore && stores.length > 1

  const { data: attentionData } = useQuery({
    queryKey: ['stores', 'attention', stores.map((s) => s.id).join(',')],
    queryFn: () => storesApi.attention(getStoreAttentionSeenMap()),
    enabled: stores.length > 0,
    refetchInterval: 30000,
  })

  const attentionByStore = attentionData?.stores ?? {}

  const otherStoresNeedAttention = useMemo(() => {
    if (!currentStore) return false
    return stores.some((s) => s.id !== currentStore.id && attentionByStore[String(s.id)]?.has_attention)
  }, [stores, currentStore, attentionByStore])

  const submitCreate = async () => {
    setError(null)
    if (!name.trim()) {
      setError('Store name is required.')
      return
    }
    setSaving(true)
    try {
      const created = await storesApi.create({
        name: name.trim(),
        copy_settings_from_store_id: copySettings ? currentStore?.id ?? null : null,
      })
      await refreshStores()
      setCurrentStoreId(created.id)
      setShowCreate(false)
      setName('')
      setOpen(false)
    } catch (e: unknown) {
      setError(formatApiError(e, 'Failed to create store'))
    } finally {
      setSaving(false)
    }
  }

  const createModal =
    showCreate &&
    createPortal(
      <div
        className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/50 p-4"
        onMouseDown={(e) => {
          if (e.target === e.currentTarget) setShowCreate(false)
        }}
      >
        <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6 relative z-[10001]">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">New store</h2>
          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-gray-700">Store name</label>
              <input
                className="mt-1 w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Second shop"
                autoFocus
              />
            </div>
            <div className="flex items-center gap-2 text-sm text-gray-600">
              <input
                type="checkbox"
                checked={copySettings}
                onChange={(e) => setCopySettings(e.target.checked)}
              />
              Copy General and SMTP settings from the current store
            </div>
            {error && <p className="text-sm text-red-600">{error}</p>}
          </div>
          <div className="mt-6 flex justify-end gap-2">
            <button
              type="button"
              className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-md"
              onClick={() => setShowCreate(false)}
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={saving}
              className="px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
              onClick={submitCreate}
            >
              {saving ? 'Creating…' : 'Create store'}
            </button>
          </div>
        </div>
      </div>,
      document.body,
    )

  return (
    <>
      <div className="relative flex items-center gap-1 min-w-0" ref={ref}>
        <button
          type="button"
          onClick={() => setOpen(!open)}
          className="relative flex items-center gap-1 text-xl font-bold text-gray-900 hover:text-blue-700 truncate max-w-[200px] lg:max-w-[280px]"
          disabled={isLoading}
        >
          <span className="truncate">{title}</span>
          <span className="relative shrink-0">
            <ChevronDown className="h-5 w-5 text-gray-500" />
            {otherStoresNeedAttention && (
              <span
                className="absolute -top-0.5 -right-0.5 h-2.5 w-2.5 rounded-full bg-orange-500 ring-2 ring-white"
                title="Another store has new activity"
              />
            )}
          </span>
        </button>
        {canCreate && (
          <button
            type="button"
            title="Add store"
            onClick={() => {
              setShowCreate(true)
              setOpen(false)
            }}
            className="p-1 rounded-md text-gray-600 hover:bg-gray-100 hover:text-blue-700"
          >
            <Plus className="h-5 w-5" />
          </button>
        )}
        {canDelete && currentStore && (
          <button
            type="button"
            title={`Delete Store ${currentStore.name}`}
            onClick={() => {
              setShowDelete(true)
              setOpen(false)
            }}
            className="p-1 rounded-md text-red-600 hover:bg-red-50 hover:text-red-800"
          >
            <Trash2 className="h-5 w-5" />
          </button>
        )}
        {open && stores.length > 0 && (
          <div className="absolute left-0 top-full mt-1 z-50 w-64 bg-white border border-gray-200 rounded-md shadow-lg py-1">
            {stores.map((s) => (
              <button
                key={s.id}
                type="button"
                onClick={() => {
                  setCurrentStoreId(s.id)
                  setOpen(false)
                }}
                className={`w-full text-left px-3 py-2 text-sm hover:bg-gray-50 ${
                  s.id === currentStore?.id ? 'bg-blue-50 text-blue-800 font-medium' : 'text-gray-800'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate">{s.name}</span>
                  {attentionByStore[String(s.id)]?.has_attention && (
                    <span
                      className="shrink-0 h-2 w-2 rounded-full bg-orange-500"
                      title={
                        attentionByStore[String(s.id)]?.missing_api
                          ? 'Configure API'
                          : 'New activity'
                      }
                    />
                  )}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
      {createModal}
      {currentStore && (
        <StoreDeleteModal
          storeId={currentStore.id}
          storeName={currentStore.name}
          open={showDelete}
          onClose={() => setShowDelete(false)}
          onDeleted={async () => {
            await refreshStores()
            const list = await storesApi.list()
            if (list[0]) setCurrentStoreId(list[0].id)
          }}
        />
      )}
    </>
  )
}