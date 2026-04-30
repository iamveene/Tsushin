'use client'

/**
 * Layout Content Component
 * Premium UI with animated navigation, glass effects, and polished interactions
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { usePathname } from 'next/navigation'
import Link from 'next/link'
import RefreshButton from '@/components/RefreshButton'
import UserGuidePanel from '@/components/UserGuidePanel'
import { authenticatedFetch } from '@/lib/client'
import { useAuth, useRequireAuth } from '@/contexts/AuthContext'
import { useOnboarding } from '@/contexts/OnboardingContext'
import { useToast } from '@/contexts/ToastContext'

// Use relative paths in the browser to avoid mixed-content (HTTPS page → HTTP API)
const API_URL = ''

// Navigation items configuration
interface NavItem {
  href: string
  label: string
  activePrefix?: string  // Optional prefix for active-state matching (defaults to href)
}

const baseNavItems: NavItem[] = [
  { href: '/', label: 'Watcher' },
  { href: '/agents', label: 'Studio' },
  { href: '/hub', label: 'Hub' },
  { href: '/flows', label: 'Flows' },
  { href: '/playground', label: 'Playground' },
  { href: '/settings', label: 'Core' },
]

export default function LayoutContent({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const { logout, isGlobalAdmin } = useAuth()
  const { startTour } = useOnboarding()

  // Global admin reaches System pages via Core → System section cards.
  const navItems = baseNavItems

  // Mobile menu state
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)

  // Help menu state
  const [isHelpMenuOpen, setIsHelpMenuOpen] = useState(false)
  const [isUserGuideOpen, setIsUserGuideOpen] = useState(false)
  const helpMenuRef = useRef<HTMLDivElement>(null)

  // Close help menu on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (helpMenuRef.current && !helpMenuRef.current.contains(e.target as Node)) {
        setIsHelpMenuOpen(false)
      }
    }
    if (isHelpMenuOpen) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isHelpMenuOpen])

  // Listen for custom event to open User Guide (e.g. from onboarding tour)
  useEffect(() => {
    const handleOpenGuide = () => setIsUserGuideOpen(true)
    window.addEventListener('tsushin:open-user-guide', handleOpenGuide)
    return () => window.removeEventListener('tsushin:open-user-guide', handleOpenGuide)
  }, [])

  const openUserGuideFromShell = useCallback(() => {
    setIsUserGuideOpen(true)
    setIsHelpMenuOpen(false)
    window.dispatchEvent(new CustomEvent('tsushin:open-user-guide'))
  }, [])

  // BUG-325: Dispatch close event when User Guide panel closes so OnboardingContext
  // can defer auto-start of the tour until after the guide is closed.
  const handleUserGuideClose = () => {
    setIsUserGuideOpen(false)
    window.dispatchEvent(new CustomEvent('tsushin:close-user-guide'))
  }

  // Emergency Stop state — two independent scopes:
  //   - tenant: affects only the logged-in user's tenant (org.settings.write)
  //   - global: affects ALL tenants (global admin only)
  const toast = useToast()
  const [tenantStop, setTenantStop] = useState(false)
  const [globalStop, setGlobalStop] = useState(false)
  const [tenantBusy, setTenantBusy] = useState(false)
  const [globalBusy, setGlobalBusy] = useState(false)
  const [stopConfirm, setStopConfirm] = useState<null | 'tenant' | 'global'>(null)

  // Close mobile menu on route change
  useEffect(() => {
    setIsMobileMenuOpen(false)
  }, [pathname])

  // Prevent body scroll when mobile menu is open
  useEffect(() => {
    if (isMobileMenuOpen) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [isMobileMenuOpen])

  // Hide header/footer on auth pages
  const isAuthPage = pathname?.startsWith('/auth') || pathname?.startsWith('/setup')
  const isPlaygroundPage = pathname?.startsWith('/playground')

  // Require authentication for all non-auth pages
  const { user, loading } = useRequireAuth()

  // Check if nav item is active
  const isActive = (href: string, activePrefix?: string) => {
    if (href === '/') {
      return pathname === '/' ||
        pathname?.startsWith('/wake-events') ||
        pathname?.startsWith('/continuous-agents')
    }
    const prefix = activePrefix || href
    return pathname?.startsWith(prefix)
  }

  // Emergency stop status polling — reads both tenant and global flags.
  const checkEmergencyStopStatus = useCallback(async () => {
    if (isAuthPage || !user) {
      return
    }
    try {
      const response = await authenticatedFetch(`${API_URL}/api/system/status`)
      if (response.ok) {
        const data = await response.json()
        setTenantStop(Boolean(data.tenant_emergency_stop))
        setGlobalStop(Boolean(data.global_emergency_stop))
      }
    } catch { /* silent */ }
  }, [isAuthPage, user])

  useEffect(() => {
    if (isAuthPage || !user) {
      return
    }
    checkEmergencyStopStatus()
    const interval = setInterval(checkEmergencyStopStatus, 10000)
    return () => clearInterval(interval)
  }, [checkEmergencyStopStatus, isAuthPage, user])

  function handleTenantToggle() {
    if (!tenantStop) {
      setStopConfirm('tenant')
      return
    }
    executeToggle('tenant')
  }

  function handleGlobalToggle() {
    if (!globalStop) {
      setStopConfirm('global')
      return
    }
    executeToggle('global')
  }

  async function executeToggle(scope: 'tenant' | 'global') {
    setStopConfirm(null)
    const isStopping = scope === 'tenant' ? !tenantStop : !globalStop
    const setBusy = scope === 'tenant' ? setTenantBusy : setGlobalBusy
    const setFlag = scope === 'tenant' ? setTenantStop : setGlobalStop
    const endpoint =
      scope === 'tenant'
        ? isStopping ? '/api/system/emergency-stop' : '/api/system/resume'
        : isStopping ? '/api/system/global-emergency-stop' : '/api/system/global-resume'

    setBusy(true)
    try {
      const response = await authenticatedFetch(`${API_URL}${endpoint}`, {
        method: 'POST',
      })
      if (response.ok) {
        const data = await response.json()
        const newFlag = Boolean(
          scope === 'tenant' ? data.tenant_emergency_stop : data.global_emergency_stop
        )
        setFlag(newFlag)
        if (newFlag) {
          toast.error(
            scope === 'global' ? 'GLOBAL Emergency Stop' : 'Tenant Emergency Stop',
            scope === 'global'
              ? 'All message processing halted for every tenant'
              : `Message processing halted for ${user?.tenant_name || 'this tenant'}`
          )
        } else {
          toast.success(
            scope === 'global' ? 'Global Resumed' : 'Tenant Resumed',
            scope === 'global'
              ? 'Global kill switch cleared. Per-tenant stops (if any) remain in effect.'
              : 'Message processing resumed for this tenant'
          )
        }
      } else {
        toast.error('Error', `Failed to toggle ${scope} emergency stop`)
      }
    } catch {
      toast.error('Error', `Failed to toggle ${scope} emergency stop`)
    } finally {
      setBusy(false)
    }
  }

  if (isAuthPage) {
    return <>{children}</>
  }

  // Loading state with premium spinner
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          {/* Premium loading spinner */}
          <div className="relative w-20 h-20 mx-auto mb-6">
            <div className="absolute inset-0 rounded-full border-4 border-tsushin-surface"></div>
            <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-tsushin-indigo animate-spin"></div>
            <div className="absolute inset-2 rounded-full border-4 border-transparent border-t-tsushin-accent animate-spin" style={{ animationDirection: 'reverse', animationDuration: '1.5s' }}></div>
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="text-2xl">通</span>
            </div>
          </div>
          <p className="text-tsushin-slate font-medium">Loading Tsushin...</p>
        </div>
      </div>
    )
  }

  // BUG-4: distinguish "still loading" from "checked and unauthenticated".
  // AuthContext (and middleware, as a server-side fallback) has already
  // triggered a hard redirect to /auth/login. Render null while the
  // navigation completes to avoid flashing protected UI or stalling on
  // the spinner indefinitely.
  if (!user) {
    return null
  }

  return (
    <div className={`flex flex-col h-screen ${isPlaygroundPage ? 'overflow-hidden' : ''}`}>
      {/* Header with glass effect */}
      <header className="flex-shrink-0 z-50 glass-card border-t-0 border-x-0 rounded-none">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center space-x-3">
              {/* Hamburger menu button - mobile only */}
              {!isPlaygroundPage && (
                <button
                  onClick={() => setIsMobileMenuOpen(true)}
                  className="md:hidden p-2 rounded-lg text-tsushin-slate hover:text-white hover:bg-tsushin-surface/50 transition-colors"
                  aria-label="Open navigation menu"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                  </svg>
                </button>
              )}

            {/* Logo with hover animation */}
            <Link
              href="/"
              className="group flex items-center space-x-3 transition-all duration-300"
            >
              <div className="relative flex items-center justify-center w-9 h-9 rounded-lg overflow-hidden transition-transform duration-300 group-hover:scale-105">
                {/* Gradient background */}
                <div className="absolute inset-0 bg-gradient-primary opacity-90 group-hover:opacity-100 transition-opacity"></div>
                {/* Glow effect on hover */}
                <div className="absolute inset-0 bg-glow-indigo opacity-0 group-hover:opacity-100 transition-opacity"></div>
                <span className="relative text-white font-bold text-lg">通</span>
              </div>
              <div className="flex flex-col">
                <div className="flex items-center gap-2">
                  <span className="text-lg font-display font-bold tracking-tight text-white group-hover:text-gradient transition-colors">
                    TSUSHIN
                  </span>
                  <span className="px-1.5 py-0.5 text-[9px] font-bold tracking-wider rounded bg-blue-500/20 text-blue-400 border border-blue-400/30">
                    BETA
                  </span>
                </div>
                <span className="text-[10px] text-tsushin-slate -mt-0.5 tracking-wide uppercase">
                  Think, Secure, Build
                </span>
              </div>
            </Link>
            </div>

            {/* Navigation with active indicators */}
            <nav className="hidden md:flex items-center space-x-1">
              {navItems.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`relative px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 group
                    ${isActive(item.href, item.activePrefix)
                      ? 'text-white'
                      : 'text-tsushin-slate hover:text-white'
                    }`}
                >
                  {/* Background highlight for active item */}
                  {isActive(item.href, item.activePrefix) && (
                    <span className="absolute inset-0 rounded-lg bg-tsushin-surface/80 border border-tsushin-border/50" />
                  )}
                  {/* Hover background */}
                  <span className={`absolute inset-0 rounded-lg bg-tsushin-surface/0 group-hover:bg-tsushin-surface/50 transition-colors ${isActive(item.href, item.activePrefix) ? 'hidden' : ''}`} />
                  {/* Content */}
                  <span className="relative">
                    {item.label}
                  </span>
                  {/* Active underline indicator */}
                  {isActive(item.href, item.activePrefix) && (
                    <span className="absolute -bottom-[17px] left-1/2 -translate-x-1/2 w-8 h-0.5 rounded-full bg-gradient-to-r from-teal-500 to-cyan-400" />
                  )}
                </Link>
              ))}
            </nav>

            {/* Right section: Actions & User */}
            <div className="flex items-center space-x-3">
              {/* Refresh button */}
              <RefreshButton />

              {/* Global kill switch — visible only to global admins. Sits LEFT of
                  the tenant toggle so admins see scope increasing from right to left
                  (this tenant → everyone). Purple/amber palette keeps it visually
                  distinct from the red/green tenant toggle. */}
              {isGlobalAdmin && (
                <button
                  onClick={handleGlobalToggle}
                  disabled={globalBusy}
                  title={globalStop
                    ? 'GLOBAL STOP is ACTIVE — every tenant is halted. Click to clear.'
                    : 'GLOBAL KILL SWITCH — halts message processing for every tenant on this instance. Click to activate.'
                  }
                  role="switch"
                  aria-checked={globalStop}
                  aria-label="Global emergency stop"
                  className="flex items-center gap-2 group"
                >
                  <span className={`text-xs font-semibold tracking-wide transition-colors duration-300 hidden xl:inline ${
                    globalBusy ? 'text-amber-400' :
                    globalStop ? 'text-amber-300' : 'text-purple-300'
                  }`}>
                    {globalBusy ? '...' : globalStop ? 'Global Stopped' : 'Global'}
                  </span>

                  {/* Shield icon — telegraphs "system-wide" vs the tenant pill's check.
                      Stays visible from md up so even when the label is suppressed at
                      1024px (xl breakpoint gates the text), admins still see the second
                      toggle is distinct from the tenant one. */}
                  <span className={`hidden md:inline-flex items-center justify-center w-4 h-4 rounded-sm transition-colors ${
                    globalStop ? 'text-amber-300' : 'text-purple-300'
                  }`}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-4 h-4">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 3l8 4v5c0 5-3.5 8.5-8 9-4.5-.5-8-4-8-9V7l8-4z" />
                    </svg>
                  </span>

                  <div className={`relative w-9 h-5 rounded-full transition-all duration-300 ${
                    globalBusy
                      ? 'bg-amber-500/30 border border-amber-500/40'
                      : globalStop
                        ? 'bg-amber-500/30 border border-amber-500/60 shadow-[0_0_8px_rgba(245,158,11,0.4)]'
                        : 'bg-purple-500/20 border border-purple-500/40 group-hover:bg-purple-500/30'
                  }`}>
                    <div className={`absolute top-0.5 w-4 h-4 rounded-full shadow-md transition-all duration-300 ${
                      globalBusy
                        ? 'left-0.5 bg-amber-400 animate-pulse'
                        : globalStop
                          ? 'left-[18px] bg-amber-300'
                          : 'left-0.5 bg-purple-300'
                    }`}>
                      {globalStop && !globalBusy && (
                        <span className="absolute inset-0 rounded-full bg-amber-300 animate-ping opacity-40"></span>
                      )}
                    </div>
                  </div>
                </button>
              )}

              {/* Tenant emergency stop — always visible. Affects the caller's
                  tenant only. Disabled visually when a global stop is in force,
                  so the operator understands their resume would be no-op. */}
              <button
                onClick={handleTenantToggle}
                disabled={tenantBusy || globalStop}
                title={globalStop
                  ? 'Blocked by GLOBAL stop — all tenants are halted. A global admin must clear the global kill switch first.'
                  : tenantStop
                    ? `STOPPED for ${user?.tenant_name || 'your tenant'} — Click to resume`
                    : `Online — Click to halt message processing for ${user?.tenant_name || 'your tenant'} only`
                }
                role="switch"
                aria-checked={!tenantStop}
                aria-label="Tenant emergency stop"
                className={`flex items-center gap-2 group ${globalStop ? 'opacity-60 cursor-not-allowed' : ''}`}
              >
                <span className={`text-xs font-semibold tracking-wide transition-colors duration-300 hidden sm:inline ${
                  tenantBusy ? 'text-amber-400' :
                  globalStop ? 'text-slate-400' :
                  tenantStop ? 'text-red-400' : 'text-tsushin-success'
                }`}>
                  {tenantBusy ? '...' : tenantStop ? 'Tenant Stopped' : globalStop ? 'Tenant (blocked)' : 'Online'}
                </span>

                <div className={`relative w-9 h-5 rounded-full transition-all duration-300 ${
                  tenantBusy
                    ? 'bg-amber-500/30 border border-amber-500/40'
                    : globalStop
                      ? 'bg-slate-500/30 border border-slate-500/40'
                      : tenantStop
                        ? 'bg-red-500/30 border border-red-500/50'
                        : 'bg-emerald-500/30 border border-emerald-500/50 group-hover:bg-emerald-500/40'
                }`}>
                  <div className={`absolute top-0.5 w-4 h-4 rounded-full shadow-md transition-all duration-300 ${
                    tenantBusy
                      ? 'left-0.5 bg-amber-400 animate-pulse'
                      : globalStop
                        ? 'left-0.5 bg-slate-400'
                        : tenantStop
                          ? 'left-0.5 bg-red-400'
                          : 'left-[18px] bg-emerald-400'
                  }`}>
                    {!tenantStop && !tenantBusy && !globalStop && (
                      <span className="absolute inset-0 rounded-full bg-emerald-400 animate-ping opacity-40"></span>
                    )}
                    {tenantStop && !tenantBusy && (
                      <span className="absolute inset-0 rounded-full bg-red-400 animate-ping opacity-40"></span>
                    )}
                  </div>
                </div>
              </button>

              {/* Divider */}
              <div className="h-8 w-px bg-tsushin-border/50"></div>

              {/* User Menu */}
              <div className="flex items-center space-x-3">
                {/* User avatar placeholder */}
                <div className="flex items-center justify-center w-8 h-8 rounded-full bg-gradient-to-br from-teal-500 to-cyan-400">
                  <span className="text-white text-xs font-bold">
                    {(user.full_name || user.email || 'U').charAt(0).toUpperCase()}
                  </span>
                </div>
                <div className="text-right hidden sm:block">
                  <div className="text-sm font-medium text-white truncate max-w-[120px]">
                    {user.full_name || user.email}
                  </div>
                  <div className="text-xs text-tsushin-slate">
                    {isGlobalAdmin ? (
                      <span className="text-purple-400 flex items-center justify-end gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-purple-400"></span>
                        Global Admin
                      </span>
                    ) : (
                      <span className="truncate max-w-[100px]">{user.tenant_name || user.tenant_id}</span>
                    )}
                  </div>
                </div>
                <div className="relative hidden sm:block" ref={helpMenuRef}>
                  <button
                    onClick={() => setIsHelpMenuOpen(!isHelpMenuOpen)}
                    className="btn-ghost text-sm p-2 hover:bg-tsushin-hover rounded-lg transition-colors"
                    title="Help"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </button>
                  {isHelpMenuOpen && (
                    <div className="absolute right-0 top-full mt-2 w-48 bg-tsushin-surface border border-tsushin-border rounded-lg shadow-xl overflow-hidden z-50">
                      <button
                        onClick={() => { startTour(); setIsHelpMenuOpen(false) }}
                        className="flex items-center gap-2.5 w-full text-left px-4 py-2.5 text-sm text-tsushin-slate hover:text-white hover:bg-tsushin-hover transition-colors"
                      >
                        <svg className="w-4 h-4 text-teal-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                        </svg>
                        Take Tour
                      </button>
                      <button
                        onClick={openUserGuideFromShell}
                        className="flex items-center gap-2.5 w-full text-left px-4 py-2.5 text-sm text-tsushin-slate hover:text-white hover:bg-tsushin-hover transition-colors"
                      >
                        <svg className="w-4 h-4 text-teal-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                        </svg>
                        User Guide
                      </button>
                    </div>
                  )}
                </div>
                <button
                  onClick={logout}
                  className="hidden sm:inline-flex btn-ghost text-sm py-1.5 px-3"
                >
                  Logout
                </button>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Mobile Navigation Drawer */}
      {!isPlaygroundPage && (
        <>
          {/* Backdrop overlay */}
          <div
            className={`fixed inset-0 z-40 bg-black/60 backdrop-blur-sm transition-opacity duration-300 md:hidden ${
              isMobileMenuOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'
            }`}
            onClick={() => setIsMobileMenuOpen(false)}
          />

          {/* Drawer panel */}
          <div
            className={`fixed top-0 left-0 z-40 h-full w-72 bg-tsushin-surface border-r border-tsushin-border transform transition-transform duration-300 ease-in-out md:hidden ${
              isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full'
            }`}
          >
            <div className="flex flex-col h-full">
              {/* Drawer header with logo and close button */}
              <div className="flex items-center justify-between p-4 border-b border-tsushin-border/50">
                <Link
                  href="/"
                  className="group flex items-center space-x-3"
                  onClick={() => setIsMobileMenuOpen(false)}
                >
                  <div className="relative flex items-center justify-center w-9 h-9 rounded-lg overflow-hidden">
                    <div className="absolute inset-0 bg-gradient-primary opacity-90"></div>
                    <span className="relative text-white font-bold text-lg">通</span>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-lg font-display font-bold tracking-tight text-white">
                      TSUSHIN
                    </span>
                    <span className="text-[10px] text-tsushin-slate -mt-0.5 tracking-wide uppercase">
                      Think, Secure, Build
                    </span>
                  </div>
                </Link>
                <button
                  onClick={() => setIsMobileMenuOpen(false)}
                  className="p-2 rounded-lg text-tsushin-slate hover:text-white hover:bg-tsushin-surface/50 transition-colors"
                  aria-label="Close navigation menu"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              {/* Navigation links */}
              <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
                {navItems.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setIsMobileMenuOpen(false)}
                    className={`relative flex items-center px-4 py-3 rounded-lg text-sm font-medium transition-all duration-200
                      ${isActive(item.href, item.activePrefix)
                        ? 'text-white bg-tsushin-surface/80 border border-tsushin-border/50'
                        : 'text-tsushin-slate hover:text-white hover:bg-tsushin-surface/50'
                      }`}
                  >
                    <span>{item.label}</span>
                    {/* Active teal accent */}
                    {isActive(item.href, item.activePrefix) && (
                      <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-6 rounded-full bg-gradient-to-b from-teal-500 to-cyan-400" />
                    )}
                  </Link>
                ))}
              </nav>

              {/* User info section at bottom */}
              <div className="border-t border-tsushin-border/50 p-4">
                <div className="flex items-center space-x-3 mb-3">
                  <div className="flex items-center justify-center w-10 h-10 rounded-full bg-gradient-to-br from-teal-500 to-cyan-400">
                    <span className="text-white text-sm font-bold">
                      {(user.full_name || user.email || 'U').charAt(0).toUpperCase()}
                    </span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-white truncate">
                      {user.full_name || user.email}
                    </div>
                    <div className="text-xs text-tsushin-slate">
                      {isGlobalAdmin ? (
                        <span className="text-purple-400 flex items-center gap-1">
                          <span className="w-1.5 h-1.5 rounded-full bg-purple-400"></span>
                          Global Admin
                        </span>
                      ) : (
                        <span className="truncate block">{user.tenant_name || user.tenant_id}</span>
                      )}
                    </div>
                  </div>
                </div>
                <button
                  onClick={() => {
                    setIsMobileMenuOpen(false)
                    logout()
                  }}
                  className="w-full btn-ghost text-sm py-2 px-3 rounded-lg text-tsushin-slate hover:text-white hover:bg-tsushin-surface/50 transition-colors text-center"
                >
                  Logout
                </button>
              </div>
            </div>
          </div>
        </>
      )}

      {/* Emergency Stop Confirmation Dialog — rendered for either scope. Copy
          differs so the user cannot mistake a global halt for a tenant halt. */}
      {stopConfirm && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-[100] p-4">
          <div className={`bg-slate-800 rounded-2xl max-w-md w-full shadow-2xl overflow-hidden border ${
            stopConfirm === 'global' ? 'border-amber-500/40' : 'border-red-500/30'
          }`}>
            <div className={`px-6 py-4 border-b ${
              stopConfirm === 'global' ? 'bg-amber-500/10 border-amber-500/20' : 'bg-red-500/10 border-red-500/20'
            }`}>
              <div className="flex items-center gap-3">
                <div className={`w-10 h-10 rounded-full flex items-center justify-center ${
                  stopConfirm === 'global' ? 'bg-amber-500/20' : 'bg-red-500/20'
                }`}>
                  {stopConfirm === 'global' ? (
                    <svg className="w-6 h-6 text-amber-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 3l8 4v5c0 5-3.5 8.5-8 9-4.5-.5-8-4-8-9V7l8-4z" />
                    </svg>
                  ) : (
                    <svg className="w-6 h-6 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
                    </svg>
                  )}
                </div>
                <div>
                  <h3 className={`text-lg font-bold ${stopConfirm === 'global' ? 'text-amber-300' : 'text-red-400'}`}>
                    {stopConfirm === 'global' ? 'Halt ALL Tenants?' : 'Tenant Emergency Stop'}
                  </h3>
                  <p className={`text-sm ${stopConfirm === 'global' ? 'text-amber-200/70' : 'text-red-300/70'}`}>
                    {stopConfirm === 'global'
                      ? 'Platform-wide kill switch — affects every tenant on this instance'
                      : `Affects ${user?.tenant_name || 'your tenant'} only — other tenants keep running`}
                  </p>
                </div>
              </div>
            </div>
            <div className="px-6 py-4">
              {stopConfirm === 'global' ? (
                <>
                  <p className="text-slate-300 text-sm">
                    This <strong className="text-white">GLOBAL kill switch</strong> halts all message processing
                    for <strong className="text-amber-300">every tenant</strong> on this instance, across WhatsApp,
                    Telegram, Slack, Discord, webhooks and API triggers.
                  </p>
                  <p className="text-slate-400 text-xs mt-3">
                    Use only for platform-level incidents (runaway loops, security response). Per-tenant stops
                    remain in effect even after the global switch is cleared.
                  </p>
                </>
              ) : (
                <>
                  <p className="text-slate-300 text-sm">
                    This will <strong className="text-white">immediately halt all message processing</strong> for{' '}
                    <strong className="text-white">{user?.tenant_name || 'your tenant'}</strong> across every
                    channel (WhatsApp, Telegram, Slack, Discord, webhooks, API). Other tenants are unaffected.
                  </p>
                  <p className="text-slate-400 text-xs mt-3">
                    Active flow runs will be cancelled. You can resume at any time by clicking the tenant toggle again.
                  </p>
                </>
              )}
            </div>
            <div className="px-6 py-4 border-t border-slate-700 flex justify-end gap-3">
              <button
                onClick={() => setStopConfirm(null)}
                className="px-4 py-2 text-sm text-slate-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => executeToggle(stopConfirm)}
                className={`px-5 py-2 text-white font-medium text-sm rounded-lg transition-colors ${
                  stopConfirm === 'global'
                    ? 'bg-amber-500 hover:bg-amber-400'
                    : 'bg-red-500 hover:bg-red-400'
                }`}
              >
                {stopConfirm === 'global' ? 'Halt Every Tenant' : 'Stop This Tenant'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Main Content */}
      <main className={`flex-1 flex flex-col min-h-0 ${isPlaygroundPage ? 'overflow-hidden' : 'overflow-y-auto scroll-smooth'}`}>
        {children}
      </main>

      {/* Footer - Hide on Playground */}
      {!isPlaygroundPage && (
        <footer className="flex-shrink-0 border-t border-tsushin-border/50 bg-tsushin-deep/80 backdrop-blur-sm">
          <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-4">
            <div className="flex items-center justify-between text-xs text-tsushin-slate">
              <span className="flex items-center gap-2">
                <span className="text-tsushin-indigo">©</span> 2026 Tsushin. Think, Secure, Build.
              </span>
              <span className="flex items-center gap-2">
                <span className="font-mono text-tsushin-muted">tsn-core</span>
                <span className="badge badge-indigo text-2xs py-0.5">v0.7.0</span>
              </span>
            </div>
          </div>
        </footer>
      )}
      {/* User Guide slide-over panel */}
      <UserGuidePanel isOpen={isUserGuideOpen} onClose={handleUserGuideClose} />
    </div>
  )
}
