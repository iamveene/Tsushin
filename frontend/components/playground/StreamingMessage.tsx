/**
 * Streaming Message Component (Phase 14.9)
 *
 * Displays a message that's being streamed token-by-token from the server.
 * Features:
 * - Progressive text rendering
 * - Blinking cursor while streaming
 * - Markdown rendering for complete messages
 * - Token count and timing display
 */

'use client'

import React, { useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export interface StreamingMessageProps {
  content: string
  isStreaming: boolean
  isComplete: boolean
  metadata?: {
    tokenCount?: number
    duration?: number
    agent_name?: string
  }
  onComplete?: () => void
}

export default function StreamingMessage({
  content,
  isStreaming,
  isComplete,
  metadata,
  onComplete
}: StreamingMessageProps) {
  const contentRef = useRef<HTMLDivElement>(null)
  const hasCalledOnComplete = useRef(false)

  // Call onComplete callback when streaming finishes
  useEffect(() => {
    if (isComplete && !isStreaming && onComplete && !hasCalledOnComplete.current) {
      hasCalledOnComplete.current = true
      onComplete()
    }
  }, [isComplete, isStreaming, onComplete])

  // Auto-scroll to bottom as content arrives
  useEffect(() => {
    if (contentRef.current && isStreaming) {
      contentRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [content, isStreaming])

  return (
    <div className="streaming-message" ref={contentRef}>
      <div className="message-content">
        {isStreaming && content.length === 0 ? (
          // Thinking indicator (before first token arrives)
          <div className="thinking-indicator">
            <span className="thinking-dot"></span>
            <span className="thinking-dot"></span>
            <span className="thinking-dot"></span>
          </div>
        ) : isComplete ? (
          // Complete message with markdown rendering
          <div className="markdown-content">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {content}
            </ReactMarkdown>
          </div>
        ) : (
          // Streaming text with cursor
          <div className="streaming-text">
            <span className="text-content">{content}</span>
            {isStreaming && <span className="streaming-cursor">▋</span>}
          </div>
        )}
      </div>

      {/* Metadata footer */}
      {isComplete && metadata && (
        <div className="message-metadata">
          {metadata.tokenCount && (
            <span className="metadata-item" title="Token count">
              {metadata.tokenCount} tokens
            </span>
          )}
          {metadata.duration && (
            <span className="metadata-item" title="Response time">
              {(metadata.duration / 1000).toFixed(1)}s
            </span>
          )}
        </div>
      )}

      <style jsx>{`
        .streaming-message {
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
        }

        .message-content {
          line-height: 1.6;
          word-wrap: break-word;
        }

        .thinking-indicator {
          display: flex;
          gap: 0.5rem;
          padding: 0.5rem 0;
        }

        .thinking-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background-color: currentColor;
          opacity: 0.6;
          animation: thinking-pulse 1.4s ease-in-out infinite;
        }

        .thinking-dot:nth-child(1) {
          animation-delay: 0s;
        }

        .thinking-dot:nth-child(2) {
          animation-delay: 0.2s;
        }

        .thinking-dot:nth-child(3) {
          animation-delay: 0.4s;
        }

        @keyframes thinking-pulse {
          0%, 60%, 100% {
            opacity: 0.3;
            transform: scale(0.8);
          }
          30% {
            opacity: 1;
            transform: scale(1.2);
          }
        }

        .streaming-text {
          display: flex;
          align-items: baseline;
          white-space: pre-wrap;
        }

        .text-content {
          flex: 1;
        }

        .streaming-cursor {
          display: inline-block;
          margin-left: 2px;
          font-weight: 700;
          animation: cursor-blink 1s step-end infinite;
          color: currentColor;
        }

        @keyframes cursor-blink {
          0%, 50% {
            opacity: 1;
          }
          51%, 100% {
            opacity: 0;
          }
        }

        .markdown-content {
          font-size: inherit;
          color: inherit;
        }

        .markdown-content :global(p) {
          margin-bottom: 0.75rem;
        }

        .markdown-content :global(p:last-child) {
          margin-bottom: 0;
        }

        .markdown-content :global(code) {
          background-color: rgba(0, 0, 0, 0.05);
          padding: 0.2em 0.4em;
          border-radius: 3px;
          font-size: 0.9em;
        }

        .markdown-content :global(pre) {
          background-color: rgba(0, 0, 0, 0.05);
          padding: 1rem;
          border-radius: 6px;
          overflow-x: auto;
          margin: 0.75rem 0;
        }

        .markdown-content :global(pre code) {
          background-color: transparent;
          padding: 0;
        }

        .markdown-content :global(ul),
        .markdown-content :global(ol) {
          margin-left: 1.5rem;
          margin-bottom: 0.75rem;
        }

        .markdown-content :global(li) {
          margin-bottom: 0.25rem;
        }

        .markdown-content :global(blockquote) {
          border-left: 3px solid currentColor;
          padding-left: 1rem;
          opacity: 0.8;
          margin: 0.75rem 0;
        }

        .markdown-content :global(h1),
        .markdown-content :global(h2),
        .markdown-content :global(h3),
        .markdown-content :global(h4) {
          margin-top: 1rem;
          margin-bottom: 0.5rem;
          font-weight: 600;
        }

        .markdown-content :global(h1) {
          font-size: 1.5em;
        }

        .markdown-content :global(h2) {
          font-size: 1.3em;
        }

        .markdown-content :global(h3) {
          font-size: 1.1em;
        }

        .message-metadata {
          display: flex;
          gap: 1rem;
          font-size: 0.75rem;
          opacity: 0.6;
          margin-top: 0.25rem;
        }

        .metadata-item {
          display: flex;
          align-items: center;
          gap: 0.25rem;
        }
      `}</style>
    </div>
  )
}
