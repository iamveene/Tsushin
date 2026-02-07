'use client'

/**
 * Studio - Agent Builder Page
 * Visual node-based agent configuration builder
 */

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import AgentStudioTab from '@/components/watcher/studio/AgentStudioTab'

export default function BuilderPage() {
  const pathname = usePathname()

  return (
    <div className="min-h-screen animate-fade-in">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8 flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-display font-bold text-white mb-2">Agent Studio</h1>
            <p className="text-tsushin-slate">Visual agent configuration builder</p>
          </div>
        </div>
      </div>

      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-0 space-y-6">
        {/* Sub Navigation */}
        <div className="glass-card rounded-xl overflow-hidden">
          <div className="border-b border-tsushin-border/50">
            <nav className="flex">
              <Link
                href="/agents"
                className={`relative px-6 py-3.5 font-medium text-sm transition-all duration-200 ${
                  pathname === '/agents'
                    ? 'text-white'
                    : 'text-tsushin-slate hover:text-white'
                }`}
              >
                <span className="relative z-10">Agents</span>
                {pathname === '/agents' && (
                  <span className="absolute bottom-0 left-1/2 -translate-x-1/2 w-12 h-0.5 rounded-full bg-gradient-to-r from-teal-500 to-cyan-400" />
                )}
              </Link>
              <Link
                href="/agents/contacts"
                className={`relative px-6 py-3.5 font-medium text-sm transition-all duration-200 ${
                  pathname === '/agents/contacts'
                    ? 'text-white'
                    : 'text-tsushin-slate hover:text-white'
                }`}
              >
                <span className="relative z-10">Contacts</span>
                {pathname === '/agents/contacts' && (
                  <span className="absolute bottom-0 left-1/2 -translate-x-1/2 w-12 h-0.5 rounded-full bg-gradient-to-r from-teal-500 to-cyan-400" />
                )}
              </Link>
              <Link
                href="/agents/personas"
                className={`relative px-6 py-3.5 font-medium text-sm transition-all duration-200 ${
                  pathname === '/agents/personas'
                    ? 'text-white'
                    : 'text-tsushin-slate hover:text-white'
                }`}
              >
                <span className="relative z-10">Personas</span>
                {pathname === '/agents/personas' && (
                  <span className="absolute bottom-0 left-1/2 -translate-x-1/2 w-12 h-0.5 rounded-full bg-gradient-to-r from-teal-500 to-cyan-400" />
                )}
              </Link>
              <Link
                href="/agents/projects"
                className={`relative px-6 py-3.5 font-medium text-sm transition-all duration-200 ${
                  pathname?.startsWith('/agents/projects')
                    ? 'text-white'
                    : 'text-tsushin-slate hover:text-white'
                }`}
              >
                <span className="relative z-10">Projects</span>
                {pathname?.startsWith('/agents/projects') && (
                  <span className="absolute bottom-0 left-1/2 -translate-x-1/2 w-12 h-0.5 rounded-full bg-gradient-to-r from-teal-500 to-cyan-400" />
                )}
              </Link>
              <Link
                href="/agents/security"
                className={`relative px-6 py-3.5 font-medium text-sm transition-all duration-200 ${
                  pathname?.startsWith('/agents/security')
                    ? 'text-white'
                    : 'text-tsushin-slate hover:text-white'
                }`}
              >
                <span className="relative z-10 flex items-center gap-1.5">
                  <svg className="w-4 h-4 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                  </svg>
                  Security
                </span>
                {pathname?.startsWith('/agents/security') && (
                  <span className="absolute bottom-0 left-1/2 -translate-x-1/2 w-12 h-0.5 rounded-full bg-gradient-to-r from-red-500 to-orange-400" />
                )}
              </Link>
              <Link
                href="/agents/builder"
                className={`relative px-6 py-3.5 font-medium text-sm transition-all duration-200 ${
                  pathname === '/agents/builder'
                    ? 'text-white'
                    : 'text-tsushin-slate hover:text-white'
                }`}
              >
                <span className="relative z-10 flex items-center gap-1.5">
                  <svg className="w-4 h-4 text-tsushin-indigo" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" />
                  </svg>
                  Builder
                </span>
                {pathname === '/agents/builder' && (
                  <span className="absolute bottom-0 left-1/2 -translate-x-1/2 w-12 h-0.5 rounded-full bg-gradient-to-r from-tsushin-indigo to-purple-400" />
                )}
              </Link>
            </nav>
          </div>
        </div>

        {/* Agent Studio Content */}
        <AgentStudioTab />
      </div>
    </div>
  )
}
