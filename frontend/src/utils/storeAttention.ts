const SEEN_KEY = 'store_attention_seen_at'

export function getStoreAttentionSeenMap(): Record<string, string> {
  try {
    const raw = localStorage.getItem(SEEN_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as Record<string, string>
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

export function markStoreAttentionSeen(storeId: number) {
  const map = getStoreAttentionSeenMap()
  map[String(storeId)] = new Date().toISOString()
  localStorage.setItem(SEEN_KEY, JSON.stringify(map))
}