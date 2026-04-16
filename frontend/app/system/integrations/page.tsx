'use client'

/**
 * System Overview Page (Global Admin Only)
 * Landing page for the system administration area.
 * Provides navigation cards for all admin sections.
 */

import React from 'react'
import Link from 'next/link'
import { useRequireGlobalAdmin } from '@/contexts/AuthContext'

interface AdminCard {
  title: string
  description: string
  href: string
  icon: React.ReactNode
}

const adminCards: AdminCard[] = [
  {
    title: 'Tenant Management',
    description: 'View, create, and manage all organizations on the platform. Update plan limits and status.',
    href: '/system/tenants',
    icon: (
      <svg className="w-8 h-8 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
      </svg>
    ),
  },
  {
    title: 'User Management',
    description: 'View and manage all users across all tenants. Search, filter, and administer accounts.',
    href: '/system/users',
    icon: (
      <svg className="w-8 h-8 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
      </svg>
    ),
  },
  {
    title: 'Plans & Limits',
    description: 'Configure platform subscription plans, feature entitlements, and resource limits.',
    href: '/system/plans',
    icon: (
      <svg className="w-8 h-8 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
      </svg>
    ),
  },
  {
    title: 'Platform Integrations',
    description: 'Manage global platform-wide integration settings and third-party service configurations.',
    href: '/system/integrations',
    icon: (
      <svg className="w-8 h-8 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
      </svg>
    ),
  },
  {
    title: 'Remote Access',
    description: 'Expose Tsushin via a Cloudflare Tunnel and control per-tenant access to the public URL.',
    href: '/system/remote-access',
    icon: (
      <svg className="w-8 h-8 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 21a9 9 0 100-18 9 9 0 000 18zm0 0c-2.5 0-4.5-4-4.5-9S9.5 3 12 3s4.5 4 4.5 9-2 9-4.5 9zM3.6 9h16.8M3.6 15h16.8" />
      </svg>
    ),
  },
]

export default function SystemOverviewPage() {
  const { user, loading } = useRequireGlobalAdmin()

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-tsushin-slate">Loading...</div>
      </div>
    )
  }

  if (!user) {
    return null
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center space-x-3 mb-2">
          <h1 className="text-3xl font-display font-bold text-white">
            System Administration
          </h1>
          <span className="px-3 py-1 bg-purple-500/20 text-purple-300 text-sm font-semibold rounded-full border border-purple-500/30">
            Global Admin
          </span>
        </div>
        <p className="text-tsushin-slate mb-8">
          Manage the entire platform — tenants, users, plans, and integrations.
        </p>

        {/* Admin navigation cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-10">
          {adminCards.map((card) => (
            <Link key={card.href} href={card.href}>
              <div className="glass-card rounded-xl p-6 hover:border-purple-500/50 transition-all hover:scale-[1.02] cursor-pointer group">
                <div className="w-14 h-14 rounded-xl bg-purple-500/10 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                  {card.icon}
                </div>
                <h3 className="text-lg font-semibold text-white mb-2">
                  {card.title}
                </h3>
                <p className="text-sm text-tsushin-slate">
                  {card.description}
                </p>
              </div>
            </Link>
          ))}
        </div>

        {/* Signed-in admin info */}
        <div className="glass-card rounded-lg p-4 text-sm text-tsushin-slate">
          Signed in as <span className="font-medium text-white">{user.email}</span>
          {' '}with Global Admin privileges.
        </div>
      </div>
    </div>
  )
}
