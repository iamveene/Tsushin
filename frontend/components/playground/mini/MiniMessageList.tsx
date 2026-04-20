'use client'

/**
 * MiniMessageList — scrollable message list for Playground Mini. Renders
 * user/assistant bubbles and auto-scrolls to the latest content. When
 * `isSending` is true it appends the MiniStreamingMessage pending indicator.
 */

import React, { useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { PlaygroundMessage } from '@/lib/client'
import { BotIcon, UserIcon, MessageIcon } from '@/components/ui/icons'
import MiniStreamingMessage from './MiniStreamingMessage'

interface MiniMessageListProps {
  messages: PlaygroundMessage[]
  isSending: boolean
  isLoadingMessages: boolean
  sendError: string | null
  agentName?: string | null
  emptyHint?: string
}

export default function MiniMessageList({
  messages,
  isSending,
  isLoadingMessages,
  sendError,
  agentName,
  emptyHint,
}: MiniMessageListProps) {
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages.length, isSending])

  const hasContent = messages.length > 0 || isSending

  return (
    <div
      className="flex-1 min-h-0 overflow-y-auto px-3 py-3 space-y-3"
      aria-live="polite"
    >
      {!hasContent && !isLoadingMessages && (
        <div className="h-full min-h-[180px] flex flex-col items-center justify-center text-center px-4">
          <div className="w-10 h-10 rounded-full bg-tsushin-elevated border border-tsushin-border flex items-center justify-center text-tsushin-accent mb-3">
            <MessageIcon size={18} />
          </div>
          <p className="text-sm font-medium text-gray-200">Ask {agentName || 'your agent'} anything</p>
          <p className="text-xs text-tsushin-slate mt-1">{emptyHint || 'Type a message below to start the conversation.'}</p>
        </div>
      )}

      {isLoadingMessages && messages.length === 0 && (
        <div className="h-full min-h-[120px] flex items-center justify-center text-tsushin-slate text-xs">
          Loading conversation…
        </div>
      )}

      {messages.map((msg, idx) => {
        const isUser = msg.role === 'user'
        const key = msg.message_id || `${msg.role}-${idx}-${msg.timestamp}`
        return (
          <div key={key} className={`flex items-start gap-2 ${isUser ? 'flex-row-reverse' : ''}`}>
            <div
              className={`flex-shrink-0 w-6 h-6 rounded-md border flex items-center justify-center ${
                isUser
                  ? 'bg-tsushin-indigo/20 border-tsushin-indigo/40 text-tsushin-indigo-glow'
                  : 'bg-tsushin-elevated border-tsushin-border text-tsushin-accent'
              }`}
            >
              {isUser ? <UserIcon size={14} /> : <BotIcon size={14} />}
            </div>
            <div
              className={`max-w-[78%] rounded-lg px-3 py-2 text-sm break-words ${
                isUser
                  ? 'bg-tsushin-indigo/15 border border-tsushin-indigo/30 text-gray-100 whitespace-pre-wrap'
                  : 'bg-tsushin-elevated border border-tsushin-border text-gray-100 mini-markdown'
              }`}
            >
              {isUser ? (
                msg.content || ''
              ) : msg.content ? (
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    a: ({ href, children, ...rest }) => (
                      <a href={href} target="_blank" rel="noopener noreferrer" {...rest}>
                        {children}
                      </a>
                    ),
                  }}
                >
                  {msg.content}
                </ReactMarkdown>
              ) : (
                '…'
              )}
            </div>
          </div>
        )
      })}

      {isSending && <MiniStreamingMessage />}

      {sendError && (
        <div className="text-xs text-tsushin-vermilion bg-tsushin-vermilion/10 border border-tsushin-vermilion/30 rounded-md px-3 py-2">
          {sendError}
        </div>
      )}

      <div ref={endRef} />
    </div>
  )
}
