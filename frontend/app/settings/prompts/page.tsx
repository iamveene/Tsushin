'use client'

/**
 * Prompts & Patterns Admin Settings Page
 * Manage system-level prompt configuration:
 * - Global config (system prompt, response template)
 * - Tone presets
 * - Slash commands
 * - Project command patterns
 */

import React, { useState } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import {
  Toast,
  GlobalConfigTab,
  TonePresetsTab,
  SlashCommandsTab,
  ProjectPatternsTab
} from './components'
import { SettingsIcon, TheaterIcon, LightningIcon, WrenchIcon } from '@/components/ui/icons'

// =============================================================================
// Main Page Component
// =============================================================================

export default function PromptsSettingsPage() {
  const { hasPermission } = useAuth()
  const [activeTab, setActiveTab] = useState<'config' | 'tones' | 'commands' | 'patterns'>('config')
  const [toast, setToast] = useState<{ type: 'success' | 'error', message: string } | null>(null)

  // Permissions
  const canRead = hasPermission('org.settings.read')
  const canWrite = hasPermission('org.settings.write')

  const showToast = (type: 'success' | 'error', message: string) => {
    setToast({ type, message })
  }

  // Check permissions
  if (!canRead) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="glass-card rounded-xl p-8 text-center">
          <h2 className="text-xl font-semibold text-white mb-2">Access Denied</h2>
          <p className="text-tsushin-slate">
            You don't have permission to view prompt settings.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-display font-bold text-white">Prompts & Patterns</h1>
          <p className="text-tsushin-slate mt-2">
            Manage system prompts, tone presets, slash commands, and project patterns
          </p>
        </div>

        {/* Tab Navigation */}
        <div className="flex space-x-1 glass-card rounded-xl p-1 mb-6">
          <TabButton
            active={activeTab === 'config'}
            onClick={() => setActiveTab('config')}
            label="Global Config"
            icon={<SettingsIcon size={16} />}
          />
          <TabButton
            active={activeTab === 'tones'}
            onClick={() => setActiveTab('tones')}
            label="Tone Presets"
            icon={<TheaterIcon size={16} />}
          />
          <TabButton
            active={activeTab === 'commands'}
            onClick={() => setActiveTab('commands')}
            label="Slash Commands"
            icon={<LightningIcon size={16} />}
          />
          <TabButton
            active={activeTab === 'patterns'}
            onClick={() => setActiveTab('patterns')}
            label="Project Patterns"
            icon={<WrenchIcon size={16} />}
          />
        </div>

        {/* Tab Content */}
        {activeTab === 'config' && <GlobalConfigTab canWrite={canWrite} showToast={showToast} />}
        {activeTab === 'tones' && <TonePresetsTab canWrite={canWrite} showToast={showToast} />}
        {activeTab === 'commands' && <SlashCommandsTab canWrite={canWrite} showToast={showToast} />}
        {activeTab === 'patterns' && <ProjectPatternsTab canWrite={canWrite} showToast={showToast} />}
      </div>

      {/* Toast Notification */}
      {toast && (
        <Toast type={toast.type} message={toast.message} onClose={() => setToast(null)} />
      )}
    </div>
  )
}

// =============================================================================
// Tab Button Component
// =============================================================================

function TabButton({
  active,
  onClick,
  label,
  icon
}: {
  active: boolean
  onClick: () => void
  label: string
  icon: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      className={`flex-1 py-3 px-4 rounded-lg font-medium transition-all inline-flex items-center justify-center gap-1.5 ${
        active
          ? 'bg-teal-500/20 text-teal-400 border border-teal-500/50'
          : 'text-tsushin-slate hover:text-white hover:bg-tsushin-dark/30'
      }`}
    >
      {icon}
      {label}
    </button>
  )
}
