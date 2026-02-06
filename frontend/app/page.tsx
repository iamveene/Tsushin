'use client'

/**
 * Watcher Module - Observability & Monitoring Hub
 *
 * Single pane of glass for system observability with three views:
 * - Dashboard: High-level statistics and KPIs
 * - Conversations: Message and agent execution monitoring
 * - Flows: Flow execution monitoring and performance
 * - Graph View: Network visualization (Admin only - Phase 2)
 */

import { useState } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import DashboardTab from '@/components/watcher/DashboardTab'
import GraphViewTab from '@/components/watcher/GraphViewTab'
import ConversationsTab from '@/components/watcher/ConversationsTab'
import FlowsTab from '@/components/watcher/FlowsTab'
import BillingTab from '@/components/watcher/BillingTab'
import SecurityTab from '@/components/watcher/SecurityTab'

// Inline SVG icon to match codebase patterns
const LockClosedIcon = ({ className }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z" />
  </svg>
)

type WatcherTab = 'dashboard' | 'graph' | 'conversations' | 'flows' | 'security' | 'billing'

export default function WatcherPage() {
  const [activeTab, setActiveTab] = useState<WatcherTab>('dashboard')
  const { hasPermission } = useAuth()

  // Phase 2: Graph View requires admin permissions (org.settings.write is admin/owner only)
  const canViewGraph = hasPermission('org.settings.write')

  const tabs = [
    { id: 'dashboard' as WatcherTab, label: 'Dashboard', description: 'System Overview' },
    { id: 'graph' as WatcherTab, label: 'Graph View', description: 'Network Visualization', adminOnly: true },
    { id: 'conversations' as WatcherTab, label: 'Conversations', description: 'Message & Agent Monitoring' },
    { id: 'flows' as WatcherTab, label: 'Flows', description: 'Flow Execution Monitoring' },
    { id: 'security' as WatcherTab, label: 'Security', description: 'Sentinel Security Events' },
    { id: 'billing' as WatcherTab, label: 'Billing', description: 'AI Cost & Consumption' },
  ]

  // Filter tabs based on permissions
  const visibleTabs = tabs.filter(tab => {
    if (tab.adminOnly && !canViewGraph) {
      return false
    }
    return true
  })

  return (
    <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-8 animate-fade-in">
      {/* Page Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-display font-bold text-white mb-2">Watcher</h1>
        <p className="text-tsushin-slate">Observability & Monitoring Hub</p>
      </div>

      {/* Tab Navigation */}
      <div className="mb-6">
        <div className="glass-card rounded-xl p-1.5 inline-flex">
          {visibleTabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`
                relative px-5 py-3 text-sm font-medium rounded-lg transition-all duration-200
                ${activeTab === tab.id
                  ? 'text-white'
                  : 'text-tsushin-slate hover:text-white'
                }
              `}
            >
              {/* Active background */}
              {activeTab === tab.id && (
                <span className="absolute inset-0 rounded-lg bg-tsushin-surface border border-tsushin-border/50 shadow-lg" />
              )}
              <span className="relative flex items-center gap-2">
                <span className="flex flex-col items-start">
                  <span>{tab.label}</span>
                  <span className="text-2xs text-tsushin-muted">{tab.description}</span>
                </span>
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      <div key={activeTab} className="animate-fade-in">
        {activeTab === 'dashboard' && <DashboardTab />}
        {activeTab === 'graph' && (
          canViewGraph ? (
            <GraphViewTab />
          ) : (
            <div className="glass-card rounded-xl p-12 text-center">
              <LockClosedIcon className="w-12 h-12 text-tsushin-slate mx-auto mb-4" />
              <h3 className="text-xl font-medium text-white mb-2">Admin Access Required</h3>
              <p className="text-tsushin-slate max-w-md mx-auto">
                The Graph View feature is only available to tenant administrators.
                Contact your admin to request access.
              </p>
            </div>
          )
        )}
        {activeTab === 'conversations' && <ConversationsTab />}
        {activeTab === 'flows' && <FlowsTab />}
        {activeTab === 'security' && <SecurityTab />}
        {activeTab === 'billing' && <BillingTab />}
      </div>
    </div>
  )
}
