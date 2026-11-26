import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, Plus, Trash2 } from 'lucide-react'
import {
  marketplaceConnectionsApi,
  MARKETPLACE_OPTIONS,
  type MarketplaceConnection,
  type MarketplaceId,
} from '../api/marketplaceConnections'

function defaultCredentials(marketplace: MarketplaceId): Record<string, string> {
  switch (marketplace) {
    case 'yandex':
      return { api_token: '', business_id: '', campaign_id: '', api_url: '' }
    case 'ozon':
      return { client_id: '', api_key: '' }
    case 'wildberries':
      return { api_key: '' }
    case 'aliexpress':
      return { app_key: '', app_secret: '' }
    default:
      return { api_key: '', notes: '' }
  }
}

function CredentialFields({
  marketplace,
  credentials,
  onChange,
  disabled,
}: {
  marketplace: MarketplaceId
  credentials: Record<string, string>
  onChange: (next: Record<string, string>) => void
  disabled: boolean
}) {
  const set = (key: string, value: string) => onChange({ ...credentials, [key]: value })

  if (marketplace === 'yandex') {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
        <MotionField label="API token" name="api_token" value={credentials.api_token} onChange={set} disabled={disabled} />
        <MotionField label="Business ID" name="business_id" value={credentials.business_id} onChange={set} disabled={disabled} />
        <MotionField label="Campaign ID" name="campaign_id" value={credentials.campaign_id} onChange={set} disabled={disabled} />
        <MotionField label="API URL (optional)" name="api_url" value={credentials.api_url} onChange={set} disabled={disabled} placeholder="https://api.partner.market.yandex.ru" />
      </div>
    )
  }

  const entries = Object.keys(Object.keys(credentials).length ? credentials : defaultCredentials(marketplace))
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
      {entries.map((key) => (
        <MotionField
          key={key}
          label={key.replace(/_/g, ' ')}
          name={key}
          value={credentials[key] || ''}
          onChange={set}
          disabled={disabled}
        />
      ))}
    </div>
  )
}

function MotionField(props: {
  label: string
  name: string
  value: string
  onChange: (key: string, value: string) => void
  disabled: boolean
  placeholder?: string
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-600 mb-1 capitalize">{props.label}</label>
      <input
        type={props.name.includes('token') || props.name.includes('password') || props.name.includes('secret') || props.name.includes('key') ? 'password' : 'text'}
        disabled={props.disabled}
        value={props.value}
        placeholder={props.placeholder}
        onChange={(e) => props.onChange(props.name, e.target.value)}
        className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm disabled:bg-gray-50"
        autoComplete="off"
      />
    </div>
  )
}

export default function MarketplaceConnectionsPanel() {
  const queryClient = useQueryClient()
  const [expandedId, setExpandedId] = useState<number | 'new' | null>(null)
  const [draft, setDraft] = useState<{
    marketplace: MarketplaceId
    label: string
    credentials: Record<string, string>
    is_enabled: boolean
  } | null>(null)

  const { data: connections = [], isLoading } = useQuery({
    queryKey: ['marketplace-connections'],
    queryFn: () => marketplaceConnectionsApi.list(),
  })

  const saveMutation = useMutation({
    mutationFn: async (payload: { id?: number; body: Parameters<typeof marketplaceConnectionsApi.create>[0] }) => {
      if (payload.id) {
        return marketplaceConnectionsApi.update(payload.id, payload.body)
      }
      return marketplaceConnectionsApi.create(payload.body)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['marketplace-connections'] })
      queryClient.invalidateQueries({ queryKey: ['app-settings'] })
      setExpandedId(null)
      setDraft(null)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => marketplaceConnectionsApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['marketplace-connections'] })
      queryClient.invalidateQueries({ queryKey: ['app-settings'] })
    },
  })

  const openNew = () => {
    const marketplace: MarketplaceId = 'yandex'
    setDraft({
      marketplace,
      label: '',
      credentials: defaultCredentials(marketplace),
      is_enabled: true,
    })
    setExpandedId('new')
  }

  const openEdit = (row: MarketplaceConnection) => {
    setDraft({
      marketplace: row.marketplace,
      label: row.label || '',
      credentials: { ...defaultCredentials(row.marketplace), ...row.credentials },
      is_enabled: row.is_enabled,
    })
    setExpandedId(row.id)
  }

  const marketplaceLabel = (id: string) => MARKETPLACE_OPTIONS.find((o) => o.id === id)?.label || id

  if (isLoading) {
    return <p className="text-sm text-gray-500">Loading marketplace connections…</p>
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-600">
        Add one or more marketplace API keys for this store. Yandex is fully supported today; other marketplaces are saved for future order integration.
      </p>
      <div className="space-y-2">
        {connections.map((row) => (
          <div key={row.id} className="border border-gray-200 rounded-lg overflow-hidden">
            <button
              type="button"
              className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-gray-100 text-left"
              onClick={() => (expandedId === row.id ? setExpandedId(null) : openEdit(row))}
            >
              <span className="flex items-center gap-2 text-sm font-medium text-gray-900">
                {expandedId === row.id ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                {row.label || marketplaceLabel(row.marketplace)}
                <span className="text-xs font-normal text-gray-500">({marketplaceLabel(row.marketplace)})</span>
                {!row.is_enabled && <span className="text-xs text-amber-600">Disabled</span>}
              </span>
            </button>
            {expandedId === row.id && draft && (
              <ConnectionEditor
                draft={draft}
                setDraft={setDraft}
                onSave={() =>
                  saveMutation.mutate({
                    id: row.id,
                    body: {
                      label: draft.label || null,
                      credentials: draft.credentials,
                      is_enabled: draft.is_enabled,
                      marketplace: draft.marketplace,
                    },
                  })
                }
                onDelete={() => deleteMutation.mutate(row.id)}
                saving={saveMutation.isPending}
              />
            )}
          </div>
        ))}
      </div>

      {expandedId === 'new' && draft && (
        <div className="border border-blue-200 rounded-lg p-4 bg-blue-50/40">
          <ConnectionEditor
            draft={draft}
            setDraft={setDraft}
            isNew
            onSave={() =>
              saveMutation.mutate({
                body: {
                  marketplace: draft.marketplace,
                  label: draft.label || null,
                  credentials: draft.credentials,
                  is_enabled: draft.is_enabled,
                },
              })
            }
            onCancel={() => {
              setExpandedId(null)
              setDraft(null)
            }}
            saving={saveMutation.isPending}
          />
        </div>
      )}

      <button
        type="button"
        onClick={openNew}
        className="inline-flex items-center px-4 py-2 text-sm font-medium text-blue-700 bg-blue-50 rounded-md hover:bg-blue-100"
      >
        <Plus className="h-4 w-4 mr-2" />
        Add marketplace API
      </button>
    </div>
  )
}

function ConnectionEditor({
  draft,
  setDraft,
  onSave,
  onDelete,
  onCancel,
  isNew,
  saving,
}: {
  draft: {
    marketplace: MarketplaceId
    label: string
    credentials: Record<string, string>
    is_enabled: boolean
  }
  setDraft: React.Dispatch<
    React.SetStateAction<{
      marketplace: MarketplaceId
      label: string
      credentials: Record<string, string>
      is_enabled: boolean
    } | null>
  >
  onSave: () => void
  onDelete?: () => void
  onCancel?: () => void
  isNew?: boolean
  saving: boolean
}) {
  return (
    <div className="px-4 py-4 border-t border-gray-200 bg-white">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {isNew && (
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Marketplace</label>
            <select
              value={draft.marketplace}
              onChange={(e) => {
                const mp = e.target.value as MarketplaceId
                setDraft((d) =>
                  d
                    ? {
                        ...d,
                        marketplace: mp,
                        credentials: defaultCredentials(mp),
                      }
                    : d,
                )
              }}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
            >
              {MARKETPLACE_OPTIONS.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
        )}
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Label (optional)</label>
          <input
            value={draft.label}
            onChange={(e) => setDraft((d) => (d ? { ...d, label: e.target.value } : d))}
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
            placeholder="e.g. Main Yandex account"
          />
        </div>
        <div className="flex items-center gap-2 text-sm text-gray-700 mt-6">
          <input
            type="checkbox"
            checked={draft.is_enabled}
            onChange={(e) => setDraft((d) => (d ? { ...d, is_enabled: e.target.checked } : d))}
          />
          Enabled
        </div>
      </div>
      <CredentialFields
        marketplace={draft.marketplace}
        credentials={draft.credentials}
        onChange={(credentials) => setDraft((d) => (d ? { ...d, credentials } : d))}
        disabled={false}
      />
      <div className="flex flex-wrap gap-2 mt-4 justify-end">
        {onCancel && (
          <button type="button" onClick={onCancel} className="px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-md">
            Cancel
          </button>
        )}
        {onDelete && (
          <button
            type="button"
            onClick={onDelete}
            className="inline-flex items-center px-3 py-2 text-sm text-red-700 hover:bg-red-50 rounded-md"
          >
            <Trash2 className="h-4 w-4 mr-1" />
            Remove
          </button>
        )}
        <button
          type="button"
          disabled={saving}
          onClick={onSave}
          className="px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
        >
          {saving ? 'Saving…' : 'Save connection'}
        </button>
      </div>
    </div>
  )
}