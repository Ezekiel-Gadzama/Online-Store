import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ordersApi } from '../../api/orders'
import { getActiveStoreId } from '../../utils/storeSelection'
import { assigneeDisplayName } from '../../utils/userDisplay'

export default function OrderAcceptCell({
  yandexOrderId,
  marketplace,
  assignedToUserId,
  assignedToName,
}: {
  yandexOrderId: string
  marketplace?: string | null
  assignedToUserId?: number | null
  assignedToName?: string | null
}) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const panelRef = useRef<HTMLDivElement>(null)
  const market = marketplace || 'yandex'
  const storeId = getActiveStoreId()

  const { data: assignees = [], isError } = useQuery({
    queryKey: ['order-assignees', storeId, market],
    queryFn: () => ordersApi.getAssignees(market),
    enabled: storeId != null,
    staleTime: 60_000,
  })

  const assignMutation = useMutation({
    mutationFn: (assignToUserId?: number) => ordersApi.assignOrder(yandexOrderId, assignToUserId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orders'] })
      setOpen(false)
      setQuery('')
    },
  })

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  const q = query.trim().toLowerCase()
  const filtered = assignees.filter((u) => {
    if (!q) return true
    const hay = `${u.name ?? ''} ${u.email}`.toLowerCase()
    return hay.includes(q)
  })

  const picker = open && (
    <div
      ref={panelRef}
      className="absolute z-30 left-0 mt-1 w-64 bg-white border border-gray-200 rounded-md shadow-lg text-xs"
      onClick={(e) => e.stopPropagation()}
    >
      <div className="p-2 border-b border-gray-100">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Name or email"
          className="w-full px-2 py-1.5 border border-gray-300 rounded text-sm text-gray-900"
          autoFocus
        />
      </div>
      <div className="max-h-48 overflow-y-auto p-2 space-y-1.5">
        {isError && <p className="px-2 py-2 text-red-600">Could not load staff</p>}
        {!isError && filtered.length === 0 && (
          <p className="px-2 py-2 text-gray-500">{assignees.length ? 'No match' : 'No staff'}</p>
        )}
        {filtered.map((u) => (
          <button
            key={u.id}
            type="button"
            disabled={assignMutation.isPending}
            className="w-full text-left rounded-md border border-gray-200 bg-gray-50 px-3 py-2 hover:border-blue-300 hover:bg-blue-50 disabled:opacity-50"
            onClick={() => assignMutation.mutate(u.id)}
          >
            <span className="block text-sm font-medium text-gray-900">{assigneeDisplayName(u)}</span>
            {u.name?.trim() && (
              <span className="block text-xs text-gray-500 truncate mt-0.5">{u.email}</span>
            )}
          </button>
        ))}
      </div>
    </div>
  )

  if (assignedToUserId) {
    return (
      <div className="relative" onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          className="text-xs font-medium text-green-800 bg-green-50 border border-green-200 rounded px-2 py-1 hover:bg-green-100 max-w-[140px] truncate"
          onClick={() => setOpen((v) => !v)}
          title={assignedToName || 'Change assignee'}
        >
          {assignedToName || 'Assigned'}
        </button>
        {picker}
      </div>
    )
  }

  return (
    <div className="relative flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
      <button
        type="button"
        disabled={assignMutation.isPending}
        className="text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 rounded px-2 py-1 disabled:opacity-50"
        onClick={() => assignMutation.mutate(undefined)}
      >
        Me
      </button>
      <button
        type="button"
        className="text-xs font-medium text-blue-700 border border-blue-200 bg-white hover:bg-blue-50 rounded px-2 py-1"
        onClick={() => setOpen((v) => !v)}
      >
        Assign
      </button>
      {picker}
    </div>
  )
}