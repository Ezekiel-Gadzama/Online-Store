import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { useStore } from '../contexts/StoreContext'
import { storesApi } from '../api/stores'
import { formatApiError } from '../utils/apiError'
import { canCreateStore } from '../utils/staffStoreAccess'
import { LogOut } from 'lucide-react'

export default function CreateFirstStore() {
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const { refreshStores, setCurrentStoreId, stores, isLoading } = useStore()
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!isLoading && stores.length > 0) {
    navigate('/dashboard', { replace: true })
    return null
  }

  const canCreate = canCreateStore(user)

  const submit = async () => {
    setError(null)
    if (!name.trim()) {
      setError('Store name is required.')
      return
    }
    setSaving(true)
    try {
      const created = await storesApi.create({
        name: name.trim(),
        copy_settings_from_store_id: null,
      })
      await refreshStores()
      setCurrentStoreId(created.id)
      navigate('/dashboard', { replace: true })
    } catch (e: unknown) {
      setError(formatApiError(e, 'Failed to create store'))
    } finally {
      setSaving(false)
    }
  }

  const businessLabel = user?.business_name?.trim() || 'your business'

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <header className="flex items-center justify-between px-6 py-4 bg-white border-b border-gray-200">
        <div className="text-sm font-semibold text-gray-900">{businessLabel}</div>
        <button
          type="button"
          onClick={() => logout()}
          className="inline-flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900"
        >
          <LogOut className="h-4 w-4" />
          Logout
        </button>
      </header>
      <main className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-lg bg-white rounded-lg shadow-md border border-gray-200 p-8">
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Create your first store</h1>
          <p className="text-sm text-gray-600 mb-6">{businessLabel}</p>
          {canCreate ? (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Store name</label>
                <input
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Kateskate"
                  autoFocus
                />
              </div>
              {error && <p className="text-sm text-red-600">{error}</p>}
              <button
                type="button"
                disabled={saving}
                onClick={submit}
                className="w-full py-2.5 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50"
              >
                {saving ? 'Creating…' : 'Create store and continue'}
              </button>
            </div>
          ) : (
            <p className="text-sm text-gray-700">
              Your account cannot create stores. Ask your business admin to add a store and grant you access.
            </p>
          )}
        </div>
      </main>
    </div>
  )
}