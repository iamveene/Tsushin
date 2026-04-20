'use client'

/**
 * PlaygroundMini — top-level floating chat bubble mounted once in the
 * global layout. Renders a FAB when closed and a PlaygroundMiniPanel when
 * open. Route-gated (hidden on /playground, /auth, /setup) and auth-gated
 * (null while unauthenticated). Integrates with the onboarding wizard: when
 * the tour reaches the Mini's step, the FAB glows briefly.
 */

import React, { useEffect, useRef, useState, useCallback } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'
import { usePlaygroundMini } from './usePlaygroundMini'
import PlaygroundMiniPanel from './PlaygroundMiniPanel'
import { MessageIcon, XIcon } from '@/components/ui/icons'

const MINI_OPEN_EVENT = 'tsushin:playground-mini:open'
const MINI_TEST_ID = 'playground-mini'
const GLOW_CLASS = 'playground-mini-tour-glow'
const GLOW_MS = 4500 // 1.4s × 3 iterations (~4.2s) + small buffer

function isExcludedPath(pathname: string | null): boolean {
  if (!pathname) return false
  return (
    pathname.startsWith('/playground') ||
    pathname.startsWith('/auth') ||
    pathname.startsWith('/setup')
  )
}

export default function PlaygroundMini() {
  const { user } = useAuth()
  const pathname = usePathname()
  const router = useRouter()

  const fabRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const glowTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const [isGlowing, setIsGlowing] = useState(false)

  const mini = usePlaygroundMini({ userId: user?.id ?? null })

  const excluded = isExcludedPath(pathname)

  // --- Glow trigger helper ---
  const triggerGlow = useCallback(() => {
    setIsGlowing(false)
    // Next tick so the class reapplies and the CSS animation restarts
    requestAnimationFrame(() => {
      setIsGlowing(true)
      if (glowTimerRef.current) clearTimeout(glowTimerRef.current)
      glowTimerRef.current = setTimeout(() => {
        setIsGlowing(false)
        glowTimerRef.current = null
      }, GLOW_MS)
    })
  }, [])

  // --- Listen for the "open me" event dispatched by the wizard step ---
  useEffect(() => {
    const handleOpen = () => {
      // If on an excluded page, bounce to home first so the Mini will render.
      if (isExcludedPath(window.location.pathname)) {
        router.push('/')
      }
      mini.setOpen(true)
      triggerGlow()
    }
    window.addEventListener(MINI_OPEN_EVENT, handleOpen as EventListener)
    return () => window.removeEventListener(MINI_OPEN_EVENT, handleOpen as EventListener)
  }, [mini, router, triggerGlow])

  // Observe the FAB for `.tour-highlight` toggling, and glow when it lands on us.
  // The wizard applies `.tour-highlight` to any element matching the active step's
  // `targetSelector`; we react to that class flip rather than tightly coupling to
  // the wizard's step data structure.
  useEffect(() => {
    const el = fabRef.current
    if (!el) return
    const observer = new MutationObserver(mutations => {
      for (const m of mutations) {
        if (m.type === 'attributes' && m.attributeName === 'class') {
          if (el.classList.contains('tour-highlight')) {
            triggerGlow()
          }
        }
      }
    })
    observer.observe(el, { attributes: true, attributeFilter: ['class'] })
    return () => observer.disconnect()
  }, [triggerGlow])

  // --- Global hotkeys ---
  useEffect(() => {
    if (!user || excluded) return

    const handleKeyDown = (e: KeyboardEvent) => {
      // Toggle: Ctrl/Cmd + Shift + L
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'L' || e.key === 'l')) {
        // Ignore if a modal dialog is currently open
        const hasDialog = document.querySelector('[role="dialog"][aria-modal="true"]')
        if (hasDialog) return
        e.preventDefault()
        mini.toggleOpen()
        return
      }
      // ESC closes the panel if focus is inside it
      if (e.key === 'Escape' && mini.isOpen) {
        const active = document.activeElement
        if (panelRef.current && active && panelRef.current.contains(active as Node)) {
          e.preventDefault()
          mini.setOpen(false)
          requestAnimationFrame(() => fabRef.current?.focus())
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [user, excluded, mini])

  // --- Auto-close Mini if the route becomes excluded (e.g. user navigates to /playground) ---
  useEffect(() => {
    if (excluded && mini.isOpen) {
      mini.setOpen(false)
    }
  }, [excluded, mini])

  // --- Cleanup glow timer on unmount ---
  useEffect(() => {
    return () => {
      if (glowTimerRef.current) clearTimeout(glowTimerRef.current)
    }
  }, [])

  if (!user || excluded) return null

  const fabBaseClasses =
    'fixed bottom-6 right-6 z-[70] w-14 h-14 rounded-full flex items-center justify-center text-white shadow-xl transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tsushin-accent'
  const fabColorClasses = mini.isOpen
    ? 'bg-tsushin-elevated border border-tsushin-border hover:bg-tsushin-surface'
    : 'bg-gradient-to-br from-tsushin-indigo to-tsushin-indigo-glow hover:scale-105'

  return (
    <>
      <button
        ref={fabRef}
        type="button"
        data-testid={MINI_TEST_ID}
        aria-label={mini.isOpen ? 'Close Playground Mini' : 'Open Playground Mini'}
        aria-expanded={mini.isOpen}
        onClick={() => mini.toggleOpen()}
        className={`${fabBaseClasses} ${fabColorClasses} ${isGlowing ? GLOW_CLASS : ''}`}
      >
        {mini.isOpen ? <XIcon size={20} /> : <MessageIcon size={22} />}
      </button>

      {mini.isOpen && (
        <PlaygroundMiniPanel
          data={mini}
          onClose={() => mini.setOpen(false)}
          panelRef={panelRef}
        />
      )}
    </>
  )
}
