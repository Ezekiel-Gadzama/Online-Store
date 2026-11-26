import { createContext, useContext, useState, useEffect, ReactNode, useCallback } from 'react'
import { useAuth } from './AuthContext'
import { useStore } from './StoreContext'
import { marketplaceConnectionsApi } from '../api/marketplaceConnections'
import { settingsApi } from '../api/settings'
import { getToken } from '../utils/authStorage'

export interface Notification {
  id: string
  type: 'configuration' | 'info' | 'warning' | 'error'
  title: string
  message: string
  actionUrl?: string
  actionText?: string
  read: boolean
  createdAt: Date
}

interface NotificationContextType {
  notifications: Notification[]
  unreadCount: number
  markAsRead: (id: string) => void
  markAllAsRead: () => void
  clearNotification: (id: string) => void
  clearAllNotifications: () => void
}

const NotificationContext = createContext<NotificationContextType | undefined>(undefined)

function storeHasAnyApiKey(
  conns: Awaited<ReturnType<typeof marketplaceConnectionsApi.list>>,
  settings: Awaited<ReturnType<typeof settingsApi.get>>,
): boolean {
  for (const c of conns) {
    const token = (c.credentials?.api_token || '').trim()
    if (token) return true
  }
  return !!(settings.yandex_api_token || '').trim()
}

export function NotificationProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const { currentStore } = useStore()
  const [notifications, setNotifications] = useState<Notification[]>([])

  const checkConfiguration = useCallback(async () => {
    if (!user || !getToken() || !currentStore) return

    const storeId = currentStore.id
    const storeName = currentStore.name
    const storePrefix = `${storeName}: `

    try {
      const [conns, settings] = await Promise.all([marketplaceConnectionsApi.list(), settingsApi.get()])

      const needsApiKey = !storeHasAnyApiKey(conns, settings)

      const missingSmtpFields: string[] = []
      const smtpUser = settings.smtp_user || settings.from_email
      if (!settings.smtp_host?.trim()) missingSmtpFields.push('SMTP Host')
      if (!smtpUser?.trim()) missingSmtpFields.push('SMTP User')
      if (!settings.smtp_password?.trim()) missingSmtpFields.push('SMTP Password')
      if (!settings.from_email?.trim()) missingSmtpFields.push('From Email')

      setNotifications((prev) => {
        const apiId = `config-marketplace-api-store-${storeId}`
        const smtpId = `config-smtp-store-${storeId}`
        const kept = prev.filter(
          (n) =>
            !n.id.startsWith('config-marketplace-api-store-') &&
            !n.id.startsWith('config-yandex-store-') &&
            !n.id.startsWith('config-smtp-store-'),
        )
        const next = [...kept]

        if (needsApiKey) {
          const existing = prev.find((n) => n.id === apiId)
          next.push(
            existing ?? {
              id: apiId,
              type: 'configuration',
              title: `${storePrefix}Marketplace API`,
              message: 'Add API keys for this store under Settings → Configure API.',
              actionUrl: '/settings?tab=marketplace',
              actionText: 'Add API key',
              read: false,
              createdAt: new Date(),
            },
          )
        }

        if (missingSmtpFields.length > 0) {
          const existing = prev.find((n) => n.id === smtpId)
          next.push(
            existing ?? {
              id: smtpId,
              type: 'configuration',
              title: `${storePrefix}SMTP email setup`,
              message: `Configure SMTP for this store. Missing: ${missingSmtpFields.join(', ')}`,
              actionUrl: '/settings?tab=smtp',
              actionText: 'Go to SMTP',
              read: false,
              createdAt: new Date(),
            },
          )
        }

        return next
      })
    } catch (error: unknown) {
      const err = error as { response?: { status?: number } }
      if (err?.response?.status !== 401) {
        console.error('Failed to check configuration:', error)
      }
    }
  }, [user, currentStore])

  useEffect(() => {
    if (!user || !currentStore) {
      setNotifications((prev) => prev.filter((n) => !n.id.startsWith('config-')))
      return
    }

    checkConfiguration()
    const interval = setInterval(checkConfiguration, 8000)
    return () => clearInterval(interval)
  }, [user, currentStore, checkConfiguration])

  const markAsRead = useCallback((id: string) => {
    setNotifications((prev) => prev.map((notif) => (notif.id === id ? { ...notif, read: true } : notif)))
  }, [])

  const markAllAsRead = useCallback(() => {
    setNotifications((prev) => prev.map((notif) => ({ ...notif, read: true })))
  }, [])

  const clearNotification = useCallback((id: string) => {
    setNotifications((prev) => prev.filter((notif) => notif.id !== id))
  }, [])

  const clearAllNotifications = useCallback(() => {
    setNotifications([])
  }, [])

  const unreadCount = notifications.filter((n) => !n.read).length

  return (
    <NotificationContext.Provider
      value={{
        notifications,
        unreadCount,
        markAsRead,
        markAllAsRead,
        clearNotification,
        clearAllNotifications,
      }}
    >
      {children}
    </NotificationContext.Provider>
  )
}

export function useNotifications() {
  const context = useContext(NotificationContext)
  if (context === undefined) {
    throw new Error('useNotifications must be used within a NotificationProvider')
  }
  return context
}