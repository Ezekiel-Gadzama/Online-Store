import { useQuery } from '@tanstack/react-query'
import { chatApi } from '../../api/chat'

export default function OrderIdWithChat({
  orderId,
  hasChat,
  onOpenChat,
}: {
  orderId: string
  hasChat?: boolean
  onOpenChat: (orderId: string) => void
}) {
  const { data: unreadCount } = useQuery({
    queryKey: ['order-chat-unread', orderId],
    queryFn: () => chatApi.getUnreadCount(orderId),
    enabled: !!hasChat,
    refetchInterval: 15000,
  })

  const chatKnown = hasChat === true
  const showLink = chatKnown || hasChat === undefined

  return (
    <div className="flex items-center gap-2">
      {showLink ? (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            onOpenChat(orderId)
          }}
          className={`font-medium underline-offset-2 hover:underline ${
            chatKnown ? 'text-indigo-700' : 'text-gray-900'
          }`}
          title={chatKnown ? 'Open order chat' : 'Open chat (if available)'}
        >
          {orderId}
        </button>
      ) : (
        <span className="font-medium text-gray-900">{orderId}</span>
      )}
      {chatKnown && unreadCount != null && unreadCount > 0 && (
        <span className="inline-flex items-center justify-center min-w-[1.25rem] h-5 px-1 rounded-full bg-red-500 text-white text-xs font-bold">
          +{unreadCount > 9 ? '9' : unreadCount}
        </span>
      )}
    </div>
  )
}