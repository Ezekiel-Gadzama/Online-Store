import axios, { AxiosError } from 'axios'
import { getToken, clearToken } from '../utils/authStorage'
import {
  getActiveStoreId,
  getDataViewHeader,
  getMarketplaceHeader,
  getMarketplacesHeader,
} from '../utils/storeSelection'

// Store reference to showError function
let showConfigurationError: ((error: any) => void) | null = null

export function setConfigurationErrorHandler(handler: (error: any) => void) {
  showConfigurationError = handler
}

const apiClient = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
})

// Use the browser's single auth token (shared across tabs)
apiClient.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  const storeId = getActiveStoreId()
  if (storeId != null) {
    config.headers['X-Store-Id'] = String(storeId)
  }
  const markets = getMarketplacesHeader()
  if (markets) {
    config.headers['X-Marketplaces'] = markets
  }
  const dataView = getDataViewHeader()
  if (dataView) {
    config.headers['X-Data-View'] = dataView
  }
  const marketplace = getMarketplaceHeader()
  if (marketplace) {
    config.headers['X-Marketplace'] = marketplace
  }
  return config
})

// Intercept responses to handle configuration errors and 401 errors
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 502 || error.response?.status === 503) {
      return Promise.reject(error)
    }

    if (error.response?.status === 401) {
      const url = error.config?.url || ''
      if (url.includes('/auth/me')) {
        clearToken()
      }
    }

    if (error.response?.status === 400) {
      const errorData = error.response.data as any
      if (errorData?.error === 'CONFIGURATION_REQUIRED' && showConfigurationError) {
        showConfigurationError(errorData)
      }
    }
    return Promise.reject(error)
  }
)

export default apiClient
