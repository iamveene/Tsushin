'use client'

import React, { useEffect, useState, useCallback } from 'react'
import { api, SentinelEffectiveConfig as EffectiveConfigType } from '@/lib/client'

interface EffectiveSecurityConfigProps {
  agentId?: number
  skillType?: string
  compact?: boolean
  className?: string
}

const SOURCE_BADGE_STYLES: Record<string, string> = {
  skill: 'bg-purple-500/20 text-purple-400',
  agent: 'bg-blue-500/20 text-blue-400',
  tenant: 'bg-teal-500/20 text-teal-400',
  system: 'bg-orange-500/20 text-orange-400',
  legacy: 'bg-gray-500/20 text-gray-400 border border-dashed border-gray-500',
}

const MODE_STYLES: Record<string, { label: string; color: string }> = {
  block: { label: 'Block', color: 'text-red-400' },
  detect_only: { label: 'Detect Only', color: 'text-yellow-400' },
  off: { label: 'Off', color: 'text-gray-400' },
}

const AGGRESSIVENESS_LABELS = ['Off', 'Moderate', 'Aggressive', 'Extra Aggressive']
const AGGRESSIVENESS_COLORS = ['text-gray-400', 'text-green-400', 'text-orange-400', 'text-red-400']

export default function EffectiveSecurityConfig({ agentId, skillType, compact = false, className = '' }: EffectiveSecurityConfigProps) {
  const [config, setConfig] = useState<EffectiveConfigType | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showDetections, setShowDetections] = useState(false)
  const [retryCount, setRetryCount] = useState(0)

  useEffect(() => {
    let cancelled = false
    const fetchConfig = async () => {
      setLoading(true)
      setError(null)
      try {
        const result = await api.getSentinelEffectiveConfig(agentId, skillType)
        if (!cancelled) setConfig(result)
      } catch (err: any) {
        if (!cancelled) setError(err.message || 'Failed to load effective config')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    fetchConfig()
    return () => { cancelled = true }
  }, [agentId, skillType, retryCount])

  if (loading) {
    return (
      <div className={`flex items-center gap-2 ${className}`}>
        <div className="w-4 h-4 border-2 border-gray-600 border-t-teal-400 rounded-full animate-spin" />
        <span className="text-sm text-tsushin-slate">Loading config...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className={`flex items-center gap-2 ${className}`}>
        <span className="text-sm text-red-400">{error}</span>
        <button onClick={() => setRetryCount(c => c + 1)} className="text-xs text-teal-400 hover:text-teal-300 underline">Retry</button>
      </div>
    )
  }

  if (!config) return null

  const modeInfo = MODE_STYLES[config.detection_mode] || MODE_STYLES.off
  const aggrLevel = Math.min(config.aggressiveness_level, 3)

  // Compact mode: single line
  if (compact) {
    return (
      <div className={`flex items-center gap-2 flex-wrap ${className}`}>
        <span className="text-sm font-medium text-white">{config.profile_name}</span>
        <span className={`px-1.5 py-0.5 text-xs rounded ${modeInfo.color} bg-gray-700/50`}>
          {modeInfo.label}
        </span>
        <span className={`px-1.5 py-0.5 text-xs rounded-full ${SOURCE_BADGE_STYLES[config.profile_source] || SOURCE_BADGE_STYLES.legacy}`}>
          {config.profile_source}
        </span>
      </div>
    )
  }

  // Full mode
  const enabledDetections = config.detections?.filter(d => d.enabled).length || 0
  const totalDetections = config.detections?.length || 0

  return (
    <div className={`bg-gray-800/50 rounded-lg border border-gray-700/50 ${className}`}>
      {/* Header */}
      <div className="p-4 border-b border-gray-700/50">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <svg className={`w-4 h-4 ${modeInfo.color}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
            <span className="font-medium text-white">{config.profile_name}</span>
            {!config.is_enabled && (
              <span className="px-1.5 py-0.5 text-xs rounded bg-red-500/20 text-red-400">Disabled</span>
            )}
          </div>
          <span className={`px-2 py-0.5 text-xs rounded-full ${SOURCE_BADGE_STYLES[config.profile_source] || SOURCE_BADGE_STYLES.legacy}`}>
            {config.profile_source}
          </span>
        </div>
      </div>

      {/* Settings Grid */}
      <div className="p-4 space-y-3">
        {/* Detection Mode & Aggressiveness */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-xs text-tsushin-slate mb-1">Detection Mode</p>
            <p className={`text-sm font-medium ${modeInfo.color}`}>{modeInfo.label}</p>
          </div>
          <div>
            <p className="text-xs text-tsushin-slate mb-1">Aggressiveness</p>
            <div className="flex items-center gap-2">
              <div className="flex gap-0.5">
                {[0, 1, 2, 3].map(level => (
                  <div
                    key={level}
                    className={`w-2 h-4 rounded-sm ${
                      level <= aggrLevel && aggrLevel > 0
                        ? level === 3 ? 'bg-red-500' : level === 2 ? 'bg-orange-500' : 'bg-green-500'
                        : 'bg-gray-700'
                    }`}
                  />
                ))}
              </div>
              <span className={`text-sm ${AGGRESSIVENESS_COLORS[aggrLevel]}`}>{AGGRESSIVENESS_LABELS[aggrLevel]}</span>
            </div>
          </div>
        </div>

        {/* Analysis Components */}
        <div>
          <p className="text-xs text-tsushin-slate mb-2">Analysis Components</p>
          <div className="flex gap-2">
            {[
              { key: 'enable_prompt_analysis', label: 'P', title: 'Prompt Analysis' },
              { key: 'enable_tool_analysis', label: 'T', title: 'Tool Analysis' },
              { key: 'enable_shell_analysis', label: 'S', title: 'Shell Analysis' },
              { key: 'enable_slash_command_analysis', label: '/', title: 'Slash Command Analysis' },
            ].map(comp => {
              const enabled = config[comp.key as keyof EffectiveConfigType] as boolean
              return (
                <span
                  key={comp.key}
                  title={`${comp.title}: ${enabled ? 'Enabled' : 'Disabled'}`}
                  className={`w-7 h-7 flex items-center justify-center text-xs font-bold rounded ${
                    enabled
                      ? 'bg-teal-500/20 text-teal-400 border border-teal-500/50'
                      : 'bg-gray-700/50 text-gray-500 border border-gray-600/50'
                  }`}
                >
                  {comp.label}
                </span>
              )
            })}
          </div>
        </div>

        {/* Detections (collapsible) */}
        {config.detections && config.detections.length > 0 && (
          <div>
            <button
              onClick={() => setShowDetections(!showDetections)}
              className="flex items-center gap-2 text-xs text-tsushin-slate hover:text-white transition-colors"
            >
              <svg
                className={`w-3 h-3 transition-transform ${showDetections ? 'rotate-90' : ''}`}
                fill="none" viewBox="0 0 24 24" stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
              Detections ({enabledDetections}/{totalDetections} enabled)
            </button>

            {showDetections && (
              <div className="mt-2 space-y-1.5">
                {config.detections.map(det => (
                  <div key={det.detection_type} className="flex items-center justify-between px-2 py-1 rounded bg-gray-800/50">
                    <div className="flex items-center gap-2">
                      <div className={`w-2 h-2 rounded-full ${det.enabled ? 'bg-green-500' : 'bg-gray-600'}`} />
                      <span className="text-xs text-gray-300">{det.name}</span>
                    </div>
                    <span className={`text-xs ${det.source === 'explicit' ? 'text-blue-400' : 'text-gray-500'}`}>
                      {det.source === 'explicit' ? 'explicit' : 'default'}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
