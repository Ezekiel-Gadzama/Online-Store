import { Link, useLocation } from 'react-router-dom'
import { 
  LayoutDashboard, 
  Package, 
  ShoppingCart, 
  Mail, 
  Settings,
  Menu,
  X,
  Users,
  Send,
  FileText,
  Star,
  MessageCircle,
  UserCog,
  LogOut,
  Key
} from 'lucide-react'
import { useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '../contexts/AuthContext'
import NotificationIcon from './NotificationIcon'
import StoreSwitcher from './StoreSwitcher'
import StoreViewControls from './StoreViewControls'
import { useStore } from '../contexts/StoreContext'
import { marketplaceConnectionsApi } from '../api/marketplaceConnections'
import { loadStoreViewPrefs } from '../utils/storeSelection'
import { marketplaceHeaderLine } from '../utils/marketplaceHeaderLine'
import { userDisplayName } from '../utils/userDisplay'
import UserTimezoneModal from './UserTimezoneModal'
import { chatApi } from '../api/chat'

interface LayoutProps {
  children: React.ReactNode
}

interface NavItem {
  name: string
  href: string
  icon: any
  permission?: string
}

export default function Layout({ children }: LayoutProps) {
  const location = useLocation()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const { user, logout } = useAuth()
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const [timezoneOpen, setTimezoneOpen] = useState(false)
  const userMenuRef = useRef<HTMLDivElement>(null)
  
  // Close user menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target as Node)) {
        setUserMenuOpen(false)
      }
    }
    
    if (userMenuOpen) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [userMenuOpen])

  const allNavItems: NavItem[] = [
    { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
    { name: 'Products', href: '/products', icon: Package },
    { name: 'Orders', href: '/orders', icon: ShoppingCart },
    { name: 'Chats', href: '/chats', icon: MessageCircle },
    { name: 'Activation Templates', href: '/activation-templates', icon: Mail },
    { name: 'Reviews', href: '/reviews', icon: Star },
    { name: 'Clients', href: '/clients', icon: Users },
    { name: 'Marketing Emails', href: '/marketing-emails', icon: Send, permission: 'view_marketing_emails' },
    { name: 'Documentations', href: '/documentations', icon: FileText },
    { name: 'Staff', href: '/staff', icon: UserCog, permission: 'view_staff' },
    { name: 'Settings', href: '/settings', icon: Settings, permission: 'view_settings' },
  ]

  const hasPermission = (permission?: string) => {
    if (!permission) return true
    if (!user) return false
    if (user.is_admin) return true
    return user.permissions[permission as keyof typeof user.permissions] === true
  }

  const navigation = allNavItems.filter(item => hasPermission(item.permission))

  const { data: chatsNavData } = useQuery({
    queryKey: ['chats', 'nav-unread'],
    queryFn: () => chatApi.listChats(20),
    enabled: !!user,
    staleTime: 15_000,
    refetchInterval: 30_000,
  })

  const businessDisplayName = user?.business_name?.trim() || ''
  const accountDisplayName = userDisplayName(user)
  const { currentStore } = useStore()
  const storeId = currentStore?.id

  const { data: marketplaceConnections = [] } = useQuery({
    queryKey: ['marketplace-connections', storeId, 'header'],
    queryFn: () => marketplaceConnectionsApi.list(),
    enabled: storeId != null,
    staleTime: 30_000,
  })

  const [marketplaceSubtitle, setMarketplaceSubtitle] = useState('')

  useEffect(() => {
    if (storeId == null) {
      setMarketplaceSubtitle('')
      return
    }
    const sync = () => {
      const prefs = loadStoreViewPrefs(storeId, user?.store_ui_preferences ?? null)
      setMarketplaceSubtitle(marketplaceHeaderLine(marketplaceConnections, prefs.selected_marketplaces))
    }
    sync()
    const onPrefs = (ev: Event) => {
      const d = (ev as CustomEvent<{ storeId: number }>).detail
      if (d?.storeId === storeId) sync()
    }
    window.addEventListener('store-view-prefs-changed', onPrefs)
    return () => window.removeEventListener('store-view-prefs-changed', onPrefs)
  }, [storeId, user?.store_ui_preferences, marketplaceConnections])

  const hasUnreadChats = (() => {
    const chats = chatsNavData?.chats ?? []
    for (const c of chats) {
      const updatedAt = c.updatedAt || c.createdAt
      if (!updatedAt) continue
      // For ORDER chats, prefer the shared order key so Orders <-> Chats stay in sync.
      const lastSeen =
        c.orderId != null
          ? (localStorage.getItem(`order_chat_last_seen_${c.orderId}`) || localStorage.getItem(`chat_last_seen_${c.chatId}`))
          : localStorage.getItem(`chat_last_seen_${c.chatId}`)
      if (!lastSeen) return true
      const u = new Date(updatedAt).getTime()
      const s = new Date(lastSeen).getTime()
      if (!Number.isNaN(u) && !Number.isNaN(s) && u > s) return true
    }
    return false
  })()

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Mobile sidebar */}
      <div className={`fixed inset-0 z-40 lg:hidden ${sidebarOpen ? '' : 'hidden'}`}>
        <div className="fixed inset-0 bg-gray-600 bg-opacity-75" onClick={() => setSidebarOpen(false)} />
        <div className="fixed inset-y-0 left-0 flex w-64 flex-col bg-white">
          <div className="flex h-16 items-center justify-between px-4 border-b">
            <StoreSwitcher />
            <button onClick={() => setSidebarOpen(false)} className="text-gray-500">
              <X className="h-6 w-6" />
            </button>
          </div>
          <nav className="flex-1 space-y-1 px-2 py-4">
            {navigation.map((item) => {
              const isActive = location.pathname === item.href
              return (
                <Link
                  key={item.name}
                  to={item.href}
                  onClick={() => setSidebarOpen(false)}
                  className={`flex items-center px-3 py-2 text-sm font-medium rounded-md ${
                    isActive
                      ? 'bg-blue-50 text-blue-700'
                      : 'text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  <span className="relative mr-3">
                    <item.icon className="h-5 w-5" />
                    {item.href === '/chats' && hasUnreadChats && (
                      <span className="absolute -top-1 -right-1 h-2.5 w-2.5 rounded-full bg-red-500" />
                    )}
                  </span>
                  {item.name}
                </Link>
              )
            })}
          </nav>
          <div className="border-t px-4 py-4">
            <div className="text-sm text-gray-700 mb-2">{accountDisplayName}</div>
            {user?.is_admin && (
              <div className="text-xs text-blue-600 mb-2">Admin</div>
            )}
            {!user?.is_admin && (
              <Link
                to="/reset-password"
                onClick={() => setSidebarOpen(false)}
                className="flex items-center text-sm text-gray-700 hover:text-gray-900 mb-2"
              >
                <Key className="mr-2 h-4 w-4" />
                Reset password
              </Link>
            )}
            <button
              onClick={() => {
                logout()
                setSidebarOpen(false)
              }}
              className="flex items-center text-sm text-gray-700 hover:text-gray-900"
            >
              <LogOut className="mr-2 h-4 w-4" />
              Logout
            </button>
          </div>
        </div>
      </div>

      {/* Desktop sidebar */}
      <div className="hidden lg:fixed lg:inset-y-0 lg:flex lg:w-64 lg:flex-col">
        <div className="flex flex-col flex-grow bg-white border-r border-gray-200">
          <div className="flex h-16 items-center px-4 border-b">
            <StoreSwitcher />
          </div>
          <nav className="flex-1 space-y-1 px-2 py-4">
            {navigation.map((item) => {
              const isActive = location.pathname === item.href
              return (
                <Link
                  key={item.name}
                  to={item.href}
                  className={`flex items-center px-3 py-2 text-sm font-medium rounded-md ${
                    isActive
                      ? 'bg-blue-50 text-blue-700'
                      : 'text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  <span className="relative mr-3">
                    <item.icon className="h-5 w-5" />
                    {item.href === '/chats' && hasUnreadChats && (
                      <span className="absolute -top-1 -right-1 h-2.5 w-2.5 rounded-full bg-red-500" />
                    )}
                  </span>
                  {item.name}
                </Link>
              )
            })}
          </nav>
        </div>
      </div>

      {/* Main content */}
      <div className="lg:pl-64">
        {/* Mobile header */}
        <div className="sticky top-0 z-10 flex h-16 bg-white border-b border-gray-200 lg:hidden">
          <button
            onClick={() => setSidebarOpen(true)}
            className="px-4 text-gray-500"
          >
            <Menu className="h-6 w-6" />
          </button>
          <div className="flex items-center flex-1 gap-2 px-2 min-w-0 relative">
            <StoreSwitcher />
            <StoreViewControls />
            <div className="flex-1 text-center px-2 min-w-0 pointer-events-none">
              <div
                className="text-[10px] font-medium uppercase tracking-wider text-gray-400 leading-tight truncate"
                title={marketplaceSubtitle || undefined}
              >
                {marketplaceSubtitle || '…'}
              </div>
              <div
                className="text-base font-bold text-gray-900 truncate leading-tight"
                title={businessDisplayName || undefined}
              >
                {businessDisplayName || '…'}
              </div>
            </div>
            <div className="text-xs text-gray-700 truncate max-w-[120px] shrink-0" title={user?.email}>
              {accountDisplayName}
            </div>
          </div>
        </div>
        
        {/* Desktop header */}
        <div className="hidden lg:block sticky top-0 z-10 h-16 bg-white border-b border-gray-200">
          <div className="relative flex items-center gap-4 h-full px-6">
            <StoreViewControls />
            <div className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 text-center max-w-lg w-full px-32">
              <p
                className="text-xs font-medium uppercase tracking-wider text-gray-400 truncate"
                title={marketplaceSubtitle || undefined}
              >
                {marketplaceSubtitle || '…'}
              </p>
              <p
                className="text-2xl font-bold text-gray-900 truncate"
                title={businessDisplayName || undefined}
              >
                {businessDisplayName || '…'}
              </p>
            </div>
            <div className="ml-auto flex items-center gap-4 z-10">
              <NotificationIcon />
              <div className="relative" ref={userMenuRef}>
              <button
                onClick={() => setUserMenuOpen(!userMenuOpen)}
                className="flex items-center space-x-2 text-sm text-gray-700 hover:text-gray-900 px-3 py-2 rounded-md hover:bg-gray-50"
              >
                <span title={user?.email}>{accountDisplayName}</span>
                {user?.is_admin && (
                  <span className="text-xs text-blue-600">(Owner)</span>
                )}
                {!user?.is_admin && user?.is_business_admin && (
                  <span className="text-xs text-blue-600">(Admin)</span>
                )}
                <UserCog className="h-5 w-5" />
              </button>
              {userMenuOpen && (
                <div className="absolute right-0 mt-2 w-48 bg-white rounded-md shadow-lg py-1 z-50 border border-gray-200">
                  <button
                    type="button"
                    onClick={() => {
                      setTimezoneOpen(true)
                      setUserMenuOpen(false)
                    }}
                    className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                  >
                    Profile
                  </button>
                  {!user?.is_admin && (
                    <Link
                      to="/reset-password"
                      onClick={() => setUserMenuOpen(false)}
                      className="w-full block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 flex items-center"
                    >
                      <Key className="mr-2 h-4 w-4" />
                      Reset password
                    </Link>
                  )}
                  <button
                    onClick={() => {
                      logout()
                      setUserMenuOpen(false)
                    }}
                    className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 flex items-center"
                  >
                    <LogOut className="mr-2 h-4 w-4" />
                    Logout
                  </button>
                </div>
              )}
              </div>
            </div>
          </div>
        </div>
        
        <main className="py-6">
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
            {children}
          </div>
        </main>
      </div>
      <UserTimezoneModal open={timezoneOpen} onClose={() => setTimezoneOpen(false)} />
    </div>
  )
}
