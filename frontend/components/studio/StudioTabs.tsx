'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

/**
 * Single source of truth for all Studio sub-navigation tabs.
 * To add a new tab, just append an entry to STUDIO_TABS below.
 */

interface StudioTab {
  href: string
  label: string
  /** Tailwind colour class for the icon (e.g. "text-teal-400") */
  iconColor: string
  /** Gradient classes for the active underline */
  gradient: string
  /** SVG path(s) — each string is a <path d="…"> */
  paths: string[]
  /** Use startsWith matching instead of exact match (for nested routes like /agents/projects/[id]) */
  prefixMatch?: boolean
}

const STUDIO_TABS: StudioTab[] = [
  {
    href: '/agents',
    label: 'Agents',
    iconColor: 'text-teal-400',
    gradient: 'from-teal-500 to-cyan-400',
    paths: [
      'M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z',
    ],
  },
  {
    href: '/agents/contacts',
    label: 'Contacts',
    iconColor: 'text-blue-400',
    gradient: 'from-blue-500 to-cyan-400',
    paths: [
      'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z',
    ],
  },
  {
    href: '/agents/personas',
    label: 'Personas',
    iconColor: 'text-purple-400',
    gradient: 'from-purple-500 to-pink-400',
    paths: [
      'M5.121 17.804A13.937 13.937 0 0112 16c2.5 0 4.847.655 6.879 1.804M15 10a3 3 0 11-6 0 3 3 0 016 0zm6 2a9 9 0 11-18 0 9 9 0 0118 0z',
    ],
  },
  {
    href: '/agents/projects',
    label: 'Projects',
    iconColor: 'text-amber-400',
    gradient: 'from-amber-500 to-yellow-400',
    paths: [
      'M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z',
    ],
    prefixMatch: true,
  },
  {
    href: '/agents/security',
    label: 'Security',
    iconColor: 'text-red-400',
    gradient: 'from-red-500 to-orange-400',
    paths: [
      'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z',
    ],
    prefixMatch: true,
  },
  {
    href: '/agents/builder',
    label: 'Builder',
    iconColor: 'text-indigo-400',
    gradient: 'from-indigo-500 to-purple-400',
    paths: [
      'M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5',
    ],
  },
  {
    href: '/agents/custom-skills',
    label: 'Custom Skills',
    iconColor: 'text-violet-400',
    gradient: 'from-violet-500 to-purple-400',
    paths: [
      'M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z',
    ],
  },
]

export default function StudioTabs() {
  const pathname = usePathname()

  const isActive = (tab: StudioTab) => {
    if (tab.prefixMatch) return pathname?.startsWith(tab.href) ?? false
    return pathname === tab.href
  }

  return (
    <div className="glass-card rounded-xl overflow-hidden">
      <div className="border-b border-tsushin-border/50">
        <nav className="flex">
          {STUDIO_TABS.map((tab) => (
            <Link
              key={tab.href}
              href={tab.href}
              className={`relative px-6 py-3.5 font-medium text-sm transition-all duration-200 ${
                isActive(tab)
                  ? 'text-white'
                  : 'text-tsushin-slate hover:text-white'
              }`}
            >
              <span className="relative z-10 flex items-center gap-1.5">
                <svg
                  className={`w-4 h-4 ${tab.iconColor}`}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  {tab.paths.map((d, i) => (
                    <path
                      key={i}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d={d}
                    />
                  ))}
                </svg>
                {tab.label}
              </span>
              {isActive(tab) && (
                <span
                  className={`absolute bottom-0 left-1/2 -translate-x-1/2 w-12 h-0.5 rounded-full bg-gradient-to-r ${tab.gradient}`}
                />
              )}
            </Link>
          ))}
        </nav>
      </div>
    </div>
  )
}
