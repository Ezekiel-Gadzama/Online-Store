import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import { StoreProvider } from './contexts/StoreContext'
import { ConfigurationErrorProvider } from './contexts/ConfigurationErrorContext'
import { NotificationProvider } from './contexts/NotificationContext'
import { TimeZoneProvider } from './contexts/TimeZoneContext'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Products from './pages/Products'
import Orders from './pages/Orders'
import ActivationTemplates from './pages/ActivationTemplates'
import Clients from './pages/Clients'
import MarketingEmails from './pages/MarketingEmails'
import Documentations from './pages/Documentations'
import Settings from './pages/Settings'
import Reviews from './pages/Reviews'
import Chats from './pages/Chats'
import Login from './pages/Login'
import Signup from './pages/Signup'
import ForgotPassword from './pages/ForgotPassword'
import ResetPassword from './pages/ResetPassword'
import Staff from './pages/Staff'
import CreateFirstStore from './pages/CreateFirstStore'
import { useStore } from './contexts/StoreContext'

function ProtectedRoute({ children }: { children: React.ReactElement }) {
  const { user, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-gray-500">Loading...</div>
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  return children
}

function RequireStore({ children }: { children: React.ReactElement }) {
  const { stores, isLoading } = useStore()

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-gray-500">Loading...</div>
      </div>
    )
  }

  if (!stores.length) {
    return <Navigate to="/setup-store" replace />
  }

  return children
}

function AppRoutes() {
  const { user, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-gray-500">Loading...</div>
      </div>
    )
  }

  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/dashboard" replace /> : <Login />} />
      <Route path="/signup" element={user ? <Navigate to="/dashboard" replace /> : <Signup />} />
      <Route path="/forgot-password" element={user ? <Navigate to="/dashboard" replace /> : <ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route
        path="/setup-store"
        element={
          <ProtectedRoute>
            <CreateFirstStore />
          </ProtectedRoute>
        }
      />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <RequireStore>
              <Layout>
                <Navigate to="/dashboard" replace />
              </Layout>
            </RequireStore>
          </ProtectedRoute>
        }
      />
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <RequireStore>
              <Layout>
                <Dashboard />
              </Layout>
            </RequireStore>
          </ProtectedRoute>
        }
      />
      <Route
        path="/products"
        element={
          <ProtectedRoute>
            <RequireStore>
              <Layout>
                <Products />
              </Layout>
            </RequireStore>
          </ProtectedRoute>
        }
      />
      <Route
        path="/orders"
        element={
          <ProtectedRoute>
            <RequireStore>
              <Layout>
                <Orders />
              </Layout>
            </RequireStore>
          </ProtectedRoute>
        }
      />
      <Route
        path="/activation-templates"
        element={
          <ProtectedRoute>
            <RequireStore>
              <Layout>
                <ActivationTemplates />
              </Layout>
            </RequireStore>
          </ProtectedRoute>
        }
      />
      <Route
        path="/clients"
        element={
          <ProtectedRoute>
            <RequireStore>
              <Layout>
                <Clients />
              </Layout>
            </RequireStore>
          </ProtectedRoute>
        }
      />
      <Route
        path="/marketing-emails"
        element={
          <ProtectedRoute>
            <RequireStore>
              <Layout>
                <MarketingEmails />
              </Layout>
            </RequireStore>
          </ProtectedRoute>
        }
      />
      <Route
        path="/documentations"
        element={
          <ProtectedRoute>
            <RequireStore>
              <Layout>
                <Documentations />
              </Layout>
            </RequireStore>
          </ProtectedRoute>
        }
      />
      <Route
        path="/reviews"
        element={
          <ProtectedRoute>
            <RequireStore>
              <Layout>
                <Reviews />
              </Layout>
            </RequireStore>
          </ProtectedRoute>
        }
      />
      <Route
        path="/chats"
        element={
          <ProtectedRoute>
            <RequireStore>
              <Layout>
                <Chats />
              </Layout>
            </RequireStore>
          </ProtectedRoute>
        }
      />
      <Route
        path="/settings"
        element={
          <ProtectedRoute>
            <RequireStore>
              <Layout>
                <Settings />
              </Layout>
            </RequireStore>
          </ProtectedRoute>
        }
      />
      <Route
        path="/staff"
        element={
          <ProtectedRoute>
            <RequireStore>
              <Layout>
                <Staff />
              </Layout>
            </RequireStore>
          </ProtectedRoute>
        }
      />
    </Routes>
  )
}

function App() {
  return (
    <Router>
      <AuthProvider>
        <StoreProvider>
          <NotificationProvider>
            <ConfigurationErrorProvider>
              <TimeZoneProvider>
                <AppRoutes />
              </TimeZoneProvider>
            </ConfigurationErrorProvider>
          </NotificationProvider>
        </StoreProvider>
      </AuthProvider>
    </Router>
  )
}

export default App
