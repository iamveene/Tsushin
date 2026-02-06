'use client'

/**
 * Organization Settings Hub Page
 * Central navigation for organization-focused settings
 * Agent configuration moved to Studio (/agents)
 */

import React from 'react'
import Link from 'next/link'
import { useAuth } from '@/contexts/AuthContext'

interface SettingCard {
  title: string
  description: string
  icon: React.ReactNode
  href: string
  permission?: string
}

// SVG Icon components
const icons = {
  organization: (
    <svg className="w-8 h-8 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
    </svg>
  ),
  team: (
    <svg className="w-8 h-8 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
    </svg>
  ),
  roles: (
    <svg className="w-8 h-8 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
    </svg>
  ),
  integrations: (
    <svg className="w-8 h-8 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
    </svg>
  ),
  security: (
    <svg className="w-8 h-8 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
    </svg>
  ),
  billing: (
    <svg className="w-8 h-8 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
    </svg>
  ),
  audit: (
    <svg className="w-8 h-8 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
    </svg>
  ),
  pricing: (
    <svg className="w-8 h-8 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  ai: (
    <svg className="w-8 h-8 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
    </svg>
  ),
  globe: (
    <svg className="w-8 h-8 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
    </svg>
  ),
  sentinel: (
    <svg className="w-8 h-8 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
    </svg>
  ),
}

export default function SettingsHubPage() {
  const { hasPermission, isGlobalAdmin } = useAuth()

  const settingsSections: SettingCard[] = [
    {
      title: 'Organization',
      description: 'Manage organization profile, plan, and usage limits',
      icon: icons.organization,
      href: '/settings/organization',
      permission: 'users.read',
    },
    {
      title: 'Team Members',
      description: 'Invite and manage team members, assign roles',
      icon: icons.team,
      href: '/settings/team',
      permission: 'users.read',
    },
    {
      title: 'Roles & Permissions',
      description: 'View role definitions and permission matrix',
      icon: icons.roles,
      href: '/settings/roles',
      permission: 'users.read',
    },
    {
      title: 'Integrations',
      description: 'Configure Google OAuth for SSO, Gmail, and Calendar',
      icon: icons.integrations,
      href: '/settings/integrations',
      permission: 'org.settings.write',
    },
    {
      title: 'Security & SSO',
      description: 'Configure single sign-on and authentication policies',
      icon: icons.security,
      href: '/settings/security',
      permission: 'org.settings.write',
    },
    {
      title: 'Billing & Plans',
      description: 'Manage subscription, payment methods, and billing history',
      icon: icons.billing,
      href: '/settings/billing',
      permission: 'billing.manage',
    },
    {
      title: 'Audit Logs',
      description: 'Track all activities and changes in your organization',
      icon: icons.audit,
      href: '/settings/audit-logs',
      permission: 'users.read',
    },
    {
      title: 'Model Pricing',
      description: 'Configure LLM pricing rates for cost estimation',
      icon: icons.pricing,
      href: '/settings/model-pricing',
      permission: 'org.settings.write',
    },
    {
      title: 'System AI',
      description: 'Configure AI provider for system operations',
      icon: icons.ai,
      href: '/settings/ai-configuration',
      permission: 'org.settings.write',
    },
    {
      title: 'Prompts & Patterns',
      description: 'Manage system prompts, tone presets, and command patterns',
      icon: icons.ai,
      href: '/settings/prompts',
      permission: 'org.settings.read',
    },
    {
      title: 'Sentinel Security',
      description: 'AI-powered security monitoring and threat detection',
      icon: icons.sentinel,
      href: '/settings/sentinel',
      permission: 'org.settings.write',
    },
  ]

  const globalAdminSections: SettingCard[] = [
    {
      title: 'Tenant Management',
      description: 'View and manage all organizations on the platform',
      icon: icons.globe,
      href: '/system/tenants',
    },
  ]

  // Filter sections based on permissions
  const availableSections = settingsSections.filter(
    (section) => !section.permission || hasPermission(section.permission)
  )

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-display font-bold text-white">Organization Settings</h1>
          <p className="text-tsushin-slate mt-2">
            Manage your organization, team, and billing
          </p>
        </div>

        {/* Global Admin Sections */}
        {isGlobalAdmin && (
          <div className="mb-12">
            <div className="flex items-center space-x-3 mb-6">
              <h2 className="text-xl font-display font-semibold text-white">
                Platform Administration
              </h2>
              <span className="badge badge-indigo">
                Global Admin
              </span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {globalAdminSections.map((section) => (
                <Link key={section.href} href={section.href}>
                  <div className="glass-card rounded-xl p-6 hover:border-purple-500/50 transition-all hover:scale-[1.02] cursor-pointer group">
                    <div className="w-14 h-14 rounded-xl bg-purple-500/10 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                      {section.icon}
                    </div>
                    <h3 className="text-lg font-semibold text-white mb-2">
                      {section.title}
                    </h3>
                    <p className="text-sm text-tsushin-slate">
                      {section.description}
                    </p>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )}

        {/* Settings Sections */}
        <div>
          <h2 className="text-xl font-display font-semibold text-white mb-6">
            Settings
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {availableSections.map((section) => (
              <Link key={section.href} href={section.href}>
                <div className="glass-card rounded-xl p-6 hover:border-teal-500/50 transition-all hover:scale-[1.02] cursor-pointer group">
                  <div className="w-14 h-14 rounded-xl bg-teal-500/10 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                    {section.icon}
                  </div>
                  <h3 className="text-lg font-semibold text-white mb-2">
                    {section.title}
                  </h3>
                  <p className="text-sm text-tsushin-slate">{section.description}</p>
                </div>
              </Link>
            ))}
          </div>
        </div>

        {/* Quick Links to Related Sections */}
        <div className="mt-12 glass-card rounded-xl p-6">
          <h3 className="text-lg font-semibold text-white mb-4">
            Looking for other settings?
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            <Link href="/agents" className="flex items-center gap-2 text-teal-400 hover:text-teal-300 transition-colors">
              <span>Agent Configuration</span>
              <span className="text-tsushin-slate">→ Studio</span>
            </Link>
            <Link href="/agents/contacts" className="flex items-center gap-2 text-teal-400 hover:text-teal-300 transition-colors">
              <span>Contact Identity</span>
              <span className="text-tsushin-slate">→ Studio / Contacts</span>
            </Link>
            <Link href="/hub" className="flex items-center gap-2 text-teal-400 hover:text-teal-300 transition-colors">
              <span>API Keys & Integrations</span>
              <span className="text-tsushin-slate">→ Hub</span>
            </Link>
            <Link href="/agents/personas" className="flex items-center gap-2 text-teal-400 hover:text-teal-300 transition-colors">
              <span>Personas</span>
              <span className="text-tsushin-slate">→ Studio / Personas</span>
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}
