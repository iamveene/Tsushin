'use client'

/**
 * Layout Content Component
 * Premium UI with animated navigation, glass effects, and polished interactions
 */

import { usePathname } from 'next/navigation'
import Link from 'next/link'
import RefreshButton from '@/components/RefreshButton'
import { useAuth, useRequireAuth } from '@/contexts/AuthContext'
import { useOnboarding } from '@/contexts/OnboardingContext'

// Navigation items configuration
const navItems = [
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

  // Hide header/footer on auth pages
  const isAuthPage = pathname?.startsWith('/auth')
  const isPlaygroundPage = pathname?.startsWith('/playground')

  // Require authentication for all non-auth pages
  const { user, loading } = useRequireAuth()

  // Check if nav item is active
  const isActive = (href: string) => {
    if (href === '/') return pathname === '/'
    return pathname?.startsWith(href)
  }

  if (isAuthPage) {
    return <>{children}</>
  }

  // Loading state with premium spinner
  if (loading || !user) {
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

  return (
    <div className={`flex flex-col h-screen ${isPlaygroundPage ? 'overflow-hidden' : ''}`}>
      {/* Header with glass effect */}
      <header className="flex-shrink-0 z-50 glass-card border-t-0 border-x-0 rounded-none">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
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

            {/* Navigation with active indicators */}
            <nav className="hidden md:flex items-center space-x-1">
              {navItems.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`relative px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 group
                    ${isActive(item.href)
                      ? 'text-white'
                      : 'text-tsushin-slate hover:text-white'
                    }`}
                >
                  {/* Background highlight for active item */}
                  {isActive(item.href) && (
                    <span className="absolute inset-0 rounded-lg bg-tsushin-surface/80 border border-tsushin-border/50" />
                  )}
                  {/* Hover background */}
                  <span className={`absolute inset-0 rounded-lg bg-tsushin-surface/0 group-hover:bg-tsushin-surface/50 transition-colors ${isActive(item.href) ? 'hidden' : ''}`} />
                  {/* Content */}
                  <span className="relative">
                    {item.label}
                  </span>
                  {/* Active underline indicator */}
                  {isActive(item.href) && (
                    <span className="absolute -bottom-[17px] left-1/2 -translate-x-1/2 w-8 h-0.5 rounded-full bg-gradient-to-r from-teal-500 to-cyan-400" />
                  )}
                </Link>
              ))}
            </nav>

            {/* Right section: Actions & User */}
            <div className="flex items-center space-x-3">
              {/* Refresh button */}
              <RefreshButton />

              {/* Status indicator with pulse animation */}
              <div className="flex items-center space-x-2 px-3 py-1.5 rounded-full glass-card">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-tsushin-success opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-tsushin-success"></span>
                </span>
                <span className="text-xs font-medium text-tsushin-success">Online</span>
              </div>

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
                      <span className="truncate max-w-[100px]">{user.tenant_id}</span>
                    )}
                  </div>
                </div>
                <button
                  onClick={startTour}
                  className="btn-ghost text-sm p-2 hover:bg-tsushin-hover rounded-lg transition-colors"
                  title="Take Tour"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </button>
                <button
                  onClick={logout}
                  className="btn-ghost text-sm py-1.5 px-3"
                >
                  Logout
                </button>
              </div>
            </div>
          </div>
        </div>
      </header>

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
                <span className="badge badge-indigo text-2xs py-0.5">v0.5.0</span>
              </span>
            </div>
          </div>
        </footer>
      )}
    </div>
  )
}
