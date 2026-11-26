import apiClient from './client'

export interface ChatMessage {
  id: string
  text: string
  author: 'SELLER' | 'CUSTOMER' | 'SYSTEM'
  /** Staff member who sent this message from the admin app (Yandex only shows PARTNER). */
  sender_name?: string | null
  created_at?: string
  order_id?: string
  attachments?: {
    url: string
    type: 'image' | 'video' | 'file'
    name: string
  }[]
}

export function chatMessageSenderLabel(message: ChatMessage): string {
  if (message.author === 'CUSTOMER') return 'Customer'
  if (message.author === 'SYSTEM') return 'System'
  const name = message.sender_name?.trim()
  return name || 'Staff'
}

export interface ChatListItem {
  chatId: number
  type: 'CHAT' | 'ARBITRAGE'
  status: string
  createdAt?: string
  updatedAt?: string
  orderId?: number
  returnId?: number
  context?: any
}

export const chatApi = {
  getOrderMessages: async (orderId: string) => {
    const response = await apiClient.get<ChatMessage[]>(`chat/orders/${orderId}/messages`)
    return response.data
  },
  
  sendOrderMessage: async (orderId: string, text: string, attachments?: { url: string; type: string; name: string }[]) => {
    const payload: any = { text }
    if (attachments && attachments.length > 0) {
      payload.attachments = attachments
    }
    const response = await apiClient.post(`chat/orders/${orderId}/messages`, payload)
    return response.data
  },
  
  getUnreadCount: async (orderId: string) => {
    const response = await apiClient.get<{ unread_count: number }>(`chat/orders/${orderId}/unread-count`)
    return response.data.unread_count
  },
  
  markAsRead: async (orderId: string) => {
    const response = await apiClient.post(`chat/orders/${orderId}/mark-read`)
    return response.data
  },

  listChats: async (limit: number = 20, pageToken?: string) => {
    const params: any = { limit }
    if (pageToken) params.page_token = pageToken
    const response = await apiClient.get<{ chats: ChatListItem[]; nextPageToken?: string }>(`chat/chats`, { params })
    return response.data
  },

  getChatMessages: async (chatId: number, limit: number = 100, pageToken?: string) => {
    const params: any = { limit }
    if (pageToken) params.page_token = pageToken
    const response = await apiClient.get<{ context: any; messages: ChatMessage[]; nextPageToken?: string }>(
      `chat/chats/${chatId}/messages`,
      { params }
    )
    return response.data
  },

  sendChatMessage: async (chatId: number, text: string) => {
    const response = await apiClient.post(`chat/chats/${chatId}/messages`, { text })
    return response.data
  },

  orderMeta: async (orderIds: string[]) => {
    const response = await apiClient.post<{
      orders: Record<string, { has_chat: boolean; unread_count: number }>
    }>('chat/orders/meta', { order_ids: orderIds })
    return response.data
  },

  marketplaceOrderUrl: async (orderId: string, marketplace?: string) => {
    const response = await apiClient.get<{ url: string }>(`chat/orders/${orderId}/marketplace-url`, {
      params: marketplace ? { marketplace } : undefined,
    })
    return response.data.url
  },
}
