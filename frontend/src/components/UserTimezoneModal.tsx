import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { useMutation } from '@tanstack/react-query'
import { authApi } from '../api/auth'
import { useAuth } from '../contexts/AuthContext'

export default function UserTimezoneModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { user, refreshUser } = useAuth()
  const resolved = Intl.DateTimeFormat().resolvedOptions().timeZone
  const [displayName, setDisplayName] = useState(user?.name?.trim() || '')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState(user?.timezone || resolved || 'Europe/Moscow')

  useEffect(() => {
    if (open && user) {
      setDisplayName(user.name?.trim() || '')
      setSelected(user.timezone || resolved || 'Europe/Moscow')
    }
  }, [open, user, resolved])

  const zones = useMemo(() => {
    const all =
      (Intl as unknown as { supportedValuesOf?: (k: string) => string[] }).supportedValuesOf?.('timeZone') || [
        'UTC',
        'Europe/Moscow',
        resolved,
      ]
    return all
      .filter((z) => z.toLowerCase().includes(search.trim().toLowerCase()))
      .sort((a, b) => a.localeCompare(b))
  }, [search, resolved])

  const saveMutation = useMutation({
    mutationFn: () =>
      authApi.updateProfile({
        name: displayName.trim() || null,
        timezone: selected,
      }),
    onSuccess: async () => {
      await refreshUser()
      onClose()
    },
  })

  if (!open) return null

  return createPortal(
    <div className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg p-6 max-h-[85vh] overflow-y-auto">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Profile</h2>
        <label className="block text-sm font-medium text-gray-700 mb-1">Your name</label>
        <input
          type="text"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder={user?.email || 'Display name'}
          className="w-full mb-4 px-3 py-2 border border-gray-300 rounded-md text-sm"
        />
        <label className="block text-sm font-medium text-gray-700 mb-1">Time zone</label>
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search"
          className="w-full mb-3 px-3 py-2 border border-gray-300 rounded-md text-sm"
        />
        <select
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          size={8}
          className="w-full border border-gray-300 rounded-md text-sm mb-4"
        >
          {zones.map((z) => (
            <option key={z} value={z}>
              {z}
            </option>
          ))}
        </select>
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-md">
            Cancel
          </button>
          <button
            type="button"
            disabled={saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
          >
            {saveMutation.isPending ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}