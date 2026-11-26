import { AxiosError } from 'axios'

export function formatApiError(error: unknown, fallback = 'Request failed'): string {
  if (!error || typeof error !== 'object' || !('response' in error)) {
    return fallback
  }
  const ax = error as AxiosError<{ detail?: unknown }>
  const detail = ax.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) {
    return detail
  }
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        if (typeof d === 'string') return d
        if (d && typeof d === 'object' && 'msg' in d) return String((d as { msg: string }).msg)
        return ''
      })
      .filter(Boolean)
      .join(', ') || fallback
  }
  if (detail && typeof detail === 'object' && 'message' in detail) {
    return String((detail as { message: string }).message)
  }
  return ax.message || fallback
}