'use client'

import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface UserGuidePanelProps {
  isOpen: boolean
  onClose: () => void
}

interface TocEntry {
  id: string
  title: string
  level: number
}

export default function UserGuidePanel({ isOpen, onClose }: UserGuidePanelProps) {
  const [content, setContent] = useState<string>('')
  const [error, setError] = useState<string | null>(null)
  const [activeSection, setActiveSection] = useState<string>('')
  const contentRef = useRef<HTMLDivElement>(null)
  const closeButtonRef = useRef<HTMLButtonElement>(null)
  const previousFocusRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!isOpen || content) return

    let isCancelled = false

    const loadGuide = async () => {
      await Promise.resolve()
      if (isCancelled) return

      setError(null)

      try {
        const res = await fetch('/api/user-guide', { credentials: 'include' })
        if (!res.ok) throw new Error('Failed to load user guide')

        const md = await res.text()
        if (!isCancelled) {
          setContent(md)
        }
      } catch (err) {
        if (!isCancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load user guide')
        }
      }
    }

    void loadGuide()
    return () => {
      isCancelled = true
    }
  }, [isOpen, content])

  const loading = isOpen && !content && !error

  const toc = useMemo<TocEntry[]>(() => {
    if (!content) return []
    const entries: TocEntry[] = []
    const lines = content.split('\n')
    for (const line of lines) {
      const match = line.match(/^(#{2,3})\s+(.+)$/)
      if (match) {
        const level = match[1].length
        const title = match[2].replace(/\*\*/g, '')
        const id = title
          .toLowerCase()
          .replace(/[^\w\s-]/g, '')
          .replace(/\s+/g, '-')
          .replace(/-+/g, '-')
          .trim()
        entries.push({ id, title, level })
      }
    }
    return entries
  }, [content])

  const scrollToSection = useCallback((id: string) => {
    setActiveSection(id)
    const el = contentRef.current?.querySelector(`[id="${id}"]`)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [])

  useEffect(() => {
    if (!isOpen) return
    previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null

    const focusTimer = window.setTimeout(() => {
      closeButtonRef.current?.focus()
    }, 50)

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        e.stopPropagation()
        onClose()
      }
    }
    window.addEventListener('keydown', handleEscape, true)
    return () => {
      window.clearTimeout(focusTimer)
      window.removeEventListener('keydown', handleEscape, true)
      previousFocusRef.current?.focus()
    }
  }, [isOpen, onClose])

  // Track active section on scroll
  useEffect(() => {
    if (!isOpen || !contentRef.current) return
    const container = contentRef.current
    const handleScroll = () => {
      const headings = container.querySelectorAll('h2, h3')
      let current = ''
      for (const heading of headings) {
        const rect = heading.getBoundingClientRect()
        if (rect.top <= 160) {
          current = heading.id
        }
      }
      if (current) setActiveSection(current)
    }
    container.addEventListener('scroll', handleScroll, { passive: true })
    return () => container.removeEventListener('scroll', handleScroll)
  }, [isOpen, content])

  return (
    <>
      {/* Backdrop */}
      <div
        className={`fixed inset-0 z-[100] bg-black/50 backdrop-blur-sm transition-opacity duration-300 ${
          isOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
        }`}
        onClick={onClose}
      />

      {/* Slide-over panel */}
      <div
        className={`fixed top-0 right-0 z-[101] h-full w-full sm:max-w-2xl xl:max-w-3xl transform transition-transform duration-300 ease-in-out ${
          isOpen ? 'translate-x-0 pointer-events-auto' : 'translate-x-full pointer-events-none'
        }`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="user-guide-title"
      >
        <div className="h-full flex flex-col bg-tsushin-surface border-l border-tsushin-border shadow-2xl">
          {/* Header */}
          <div className="flex items-center justify-between gap-3 px-6 py-4 border-b border-tsushin-border bg-tsushin-surface/95 backdrop-blur-sm">
            <div className="flex items-center gap-3">
              <svg className="w-5 h-5 text-teal-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
              </svg>
              <div>
                <h2 id="user-guide-title" className="text-lg font-semibold text-white">User Guide</h2>
                <p className="text-xs text-tsushin-slate">Press Escape or use the close button to return to the dashboard.</p>
              </div>
            </div>
            <button
              ref={closeButtonRef}
              type="button"
              onClick={onClose}
              className="inline-flex items-center gap-2 rounded-lg border border-tsushin-border bg-tsushin-hover px-3 py-2 text-sm font-medium text-white hover:bg-tsushin-border/70 transition-colors"
              title="Close (Esc)"
              aria-label="Close User Guide"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
              <span>Close Guide</span>
            </button>
          </div>

          {/* Body */}
          <div className="flex flex-1 overflow-hidden">
            {/* TOC sidebar */}
            {toc.length > 0 && (
              <nav className="w-56 flex-shrink-0 border-r border-tsushin-border overflow-y-auto py-4 px-3 hidden lg:block">
                <div className="text-xs font-semibold text-tsushin-slate uppercase tracking-wider mb-3 px-2">
                  Contents
                </div>
                {toc.map(entry => (
                  <button
                    key={entry.id}
                    onClick={() => scrollToSection(entry.id)}
                    className={`block w-full text-left text-sm py-1.5 px-2 rounded-md transition-colors truncate ${
                      entry.level === 3 ? 'pl-5' : ''
                    } ${
                      activeSection === entry.id
                        ? 'text-teal-400 bg-teal-500/10'
                        : 'text-tsushin-slate hover:text-white hover:bg-tsushin-hover'
                    }`}
                    title={entry.title}
                  >
                    {entry.title}
                  </button>
                ))}
              </nav>
            )}

            {/* Content area */}
            <div ref={contentRef} className="flex-1 overflow-y-auto px-8 py-6">
              {loading && (
                <div className="flex items-center justify-center h-64">
                  <div className="flex items-center gap-3 text-tsushin-slate">
                    <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Loading user guide...
                  </div>
                </div>
              )}

              {error && (
                <div className="flex items-center justify-center h-64">
                  <div className="text-center text-tsushin-slate">
                    <p className="text-red-400 mb-2">Failed to load user guide</p>
                    <p className="text-sm">{error}</p>
                  </div>
                </div>
              )}

              {!loading && !error && content && (
                <div className="user-guide-content prose prose-invert prose-sm max-w-none">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      h1: ({ children, ...props }) => {
                        const text = String(children)
                        const id = text.toLowerCase().replace(/[^\w\s-]/g, '').replace(/\s+/g, '-').replace(/-+/g, '-').trim()
                        return <h1 id={id} className="text-2xl font-bold text-white mb-4 mt-0 pb-3 border-b border-tsushin-border" {...props}>{children}</h1>
                      },
                      h2: ({ children, ...props }) => {
                        const text = String(children)
                        const id = text.toLowerCase().replace(/[^\w\s-]/g, '').replace(/\s+/g, '-').replace(/-+/g, '-').trim()
                        return <h2 id={id} className="text-xl font-semibold text-white mt-10 mb-4 pb-2 border-b border-tsushin-border/50 scroll-mt-4" {...props}>{children}</h2>
                      },
                      h3: ({ children, ...props }) => {
                        const text = String(children)
                        const id = text.toLowerCase().replace(/[^\w\s-]/g, '').replace(/\s+/g, '-').replace(/-+/g, '-').trim()
                        return <h3 id={id} className="text-lg font-medium text-white mt-8 mb-3 scroll-mt-4" {...props}>{children}</h3>
                      },
                      h4: ({ children, ...props }) => (
                        <h4 className="text-base font-medium text-teal-300 mt-6 mb-2" {...props}>{children}</h4>
                      ),
                      p: ({ children, ...props }) => (
                        <p className="text-tsushin-slate leading-relaxed mb-3" {...props}>{children}</p>
                      ),
                      a: ({ children, href, ...props }) => (
                        <a href={href} className="text-teal-400 hover:text-teal-300 underline" target={href?.startsWith('http') ? '_blank' : undefined} {...props}>{children}</a>
                      ),
                      ul: ({ children, ...props }) => (
                        <ul className="list-disc list-inside space-y-1 mb-4 text-tsushin-slate" {...props}>{children}</ul>
                      ),
                      ol: ({ children, ...props }) => (
                        <ol className="list-decimal list-inside space-y-1 mb-4 text-tsushin-slate" {...props}>{children}</ol>
                      ),
                      li: ({ children, ...props }) => (
                        <li className="text-tsushin-slate leading-relaxed" {...props}>{children}</li>
                      ),
                      strong: ({ children, ...props }) => (
                        <strong className="text-white font-semibold" {...props}>{children}</strong>
                      ),
                      code: ({ children, className, ...props }) => {
                        const isBlock = className?.includes('language-')
                        if (isBlock) {
                          return <code className={`${className} block`} {...props}>{children}</code>
                        }
                        return <code className="px-1.5 py-0.5 rounded bg-tsushin-hover text-teal-300 text-xs font-mono" {...props}>{children}</code>
                      },
                      pre: ({ children, ...props }) => (
                        <pre className="bg-[#0d1117] border border-tsushin-border rounded-lg p-4 overflow-x-auto mb-4 text-sm" {...props}>{children}</pre>
                      ),
                      table: ({ children, ...props }) => (
                        <div className="overflow-x-auto mb-4">
                          <table className="min-w-full text-sm border border-tsushin-border rounded-lg overflow-hidden" {...props}>{children}</table>
                        </div>
                      ),
                      thead: ({ children, ...props }) => (
                        <thead className="bg-tsushin-hover" {...props}>{children}</thead>
                      ),
                      th: ({ children, ...props }) => (
                        <th className="px-3 py-2 text-left text-xs font-semibold text-white border-b border-tsushin-border" {...props}>{children}</th>
                      ),
                      td: ({ children, ...props }) => (
                        <td className="px-3 py-2 text-tsushin-slate border-b border-tsushin-border/50" {...props}>{children}</td>
                      ),
                      blockquote: ({ children, ...props }) => (
                        <blockquote className="border-l-4 border-teal-500/50 pl-4 my-4 text-tsushin-slate italic" {...props}>{children}</blockquote>
                      ),
                      hr: () => <hr className="border-tsushin-border my-8" />,
                    }}
                  >
                    {content}
                  </ReactMarkdown>
                </div>
              )}
            </div>
          </div>

          <div className="border-t border-tsushin-border bg-tsushin-surface/95 px-6 py-4">
            <button
              type="button"
              onClick={onClose}
              className="w-full rounded-lg border border-tsushin-border bg-tsushin-hover px-4 py-3 text-sm font-medium text-white hover:bg-tsushin-border/70 transition-colors"
            >
              Return to Dashboard
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
