'use client'

/**
 * SkillNode - Compact child node for displaying agent skills in the graph
 * Phase 5: Expandable Agent Features
 * Phase 6: Enhanced with categories and provider info from batch endpoint
 * Phase 8: Real-time activity glow
 * Phase 9: Expandable to show available providers for skills like Scheduler, Flight Search
 */

import { memo, useState, useEffect, useRef, useCallback } from 'react'
import { NodeProps, Handle, Position } from '@xyflow/react'
import { SkillNodeData } from '../types'

// Category configuration with colors and icons
const categoryConfig: Record<string, { color: string; bgColor: string; borderColor: string }> = {
  search: { color: 'text-blue-400', bgColor: 'bg-blue-500/10', borderColor: 'border-blue-500/30' },
  audio: { color: 'text-orange-400', bgColor: 'bg-orange-500/10', borderColor: 'border-orange-500/30' },
  integration: { color: 'text-red-400', bgColor: 'bg-red-500/10', borderColor: 'border-red-500/30' },
  automation: { color: 'text-purple-400', bgColor: 'bg-purple-500/10', borderColor: 'border-purple-500/30' },
  system: { color: 'text-green-400', bgColor: 'bg-green-500/10', borderColor: 'border-green-500/30' },
  media: { color: 'text-pink-400', bgColor: 'bg-pink-500/10', borderColor: 'border-pink-500/30' },
  travel: { color: 'text-cyan-400', bgColor: 'bg-cyan-500/10', borderColor: 'border-cyan-500/30' },
  special: { color: 'text-amber-400', bgColor: 'bg-amber-500/10', borderColor: 'border-amber-500/30' },
  other: { color: 'text-teal-400', bgColor: 'bg-teal-500/10', borderColor: 'border-teal-500/30' },
}

// Skill type icon mapping
const skillIconConfig: Record<string, { icon: JSX.Element; color: string }> = {
  web_search: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
      </svg>
    ),
    color: 'text-blue-400',
  },
  web_scraping: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 013 12c0-1.605.42-3.113 1.157-4.418" />
      </svg>
    ),
    color: 'text-cyan-400',
  },
  weather: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15a4.5 4.5 0 004.5 4.5H18a3.75 3.75 0 001.332-7.257 3 3 0 00-3.758-3.848 5.25 5.25 0 00-10.233 2.33A4.502 4.502 0 002.25 15z" />
      </svg>
    ),
    color: 'text-sky-400',
  },
  flows: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5" />
      </svg>
    ),
    color: 'text-purple-400',
  },
  image: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5zm10.5-11.25h.008v.008h-.008V8.25zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z" />
      </svg>
    ),
    color: 'text-pink-400',
  },
  audio_transcript: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" />
      </svg>
    ),
    color: 'text-orange-400',
  },
  audio_tts: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M19.114 5.636a9 9 0 010 12.728M16.463 8.288a5.25 5.25 0 010 7.424M6.75 8.25l4.72-4.72a.75.75 0 011.28.53v15.88a.75.75 0 01-1.28.53l-4.72-4.72H4.51c-.88 0-1.704-.507-1.938-1.354A9.01 9.01 0 012.25 12c0-.83.112-1.633.322-2.396C2.806 8.756 3.63 8.25 4.51 8.25H6.75z" />
      </svg>
    ),
    color: 'text-amber-400',
  },
  shell: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 7.5l3 2.25-3 2.25m4.5 0h3m-9 8.25h13.5A2.25 2.25 0 0021 18V6a2.25 2.25 0 00-2.25-2.25H5.25A2.25 2.25 0 003 6v12a2.25 2.25 0 002.25 2.25z" />
      </svg>
    ),
    color: 'text-green-400',
  },
  gmail: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
      </svg>
    ),
    color: 'text-red-400',
  },
  browser_automation: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 17.25v1.007a3 3 0 01-.879 2.122L7.5 21h9l-.621-.621A3 3 0 0115 18.257V17.25m6-12V15a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 15V5.25m18 0A2.25 2.25 0 0018.75 3H5.25A2.25 2.25 0 003 5.25m18 0V12a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 12V5.25" />
      </svg>
    ),
    color: 'text-violet-400',
  },
  sandboxed_tools: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M11.42 15.17l-5.84-3.394a.75.75 0 01-.38-.65V5.416a.75.75 0 01.38-.65l5.84-3.394a.75.75 0 01.76 0l5.84 3.394a.75.75 0 01.38.65v5.71a.75.75 0 01-.38.65l-5.84 3.394a.75.75 0 01-.76 0z" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 12v6.75m0-6.75L6.18 8.7M12 12l5.82-3.3" />
      </svg>
    ),
    color: 'text-emerald-400',
  },
  flight_search: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
      </svg>
    ),
    color: 'text-cyan-400',
  },
  automation: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12a7.5 7.5 0 0015 0m-15 0a7.5 7.5 0 1115 0m-15 0H3m16.5 0H21m-1.5 0H12m-8.457 3.077l1.41-.513m14.095-5.13l1.41-.513M5.106 17.785l1.15-.964m11.49-9.642l1.149-.964M7.501 19.795l.75-1.3m7.5-12.99l.75-1.3m-6.063 16.658l.26-1.477m2.605-14.772l.26-1.477m0 17.726l-.26-1.477M10.698 4.614l-.26-1.477M16.5 19.794l-.75-1.299M7.5 4.205L12 12m6.894 5.785l-1.149-.964M6.256 7.178l-1.15-.964m15.352 8.864l-1.41-.513M4.954 9.435l-1.41-.514M12.002 12l-3.75 6.495" />
      </svg>
    ),
    color: 'text-purple-400',
  },
  adaptive_personality: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M15.182 15.182a4.5 4.5 0 01-6.364 0M21 12a9 9 0 11-18 0 9 9 0 0118 0zM9.75 9.75c0 .414-.168.75-.375.75S9 10.164 9 9.75 9.168 9 9.375 9s.375.336.375.75zm-.375 0h.008v.015h-.008V9.75zm5.625 0c0 .414-.168.75-.375.75s-.375-.336-.375-.75.168-.75.375-.75.375.336.375.75zm-.375 0h.008v.015h-.008V9.75z" />
      </svg>
    ),
    color: 'text-amber-400',
  },
  knowledge_sharing: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M7.217 10.907a2.25 2.25 0 100 2.186m0-2.186c.18.324.283.696.283 1.093s-.103.77-.283 1.093m0-2.186l9.566-5.314m-9.566 7.5l9.566 5.314m0 0a2.25 2.25 0 103.935 2.186 2.25 2.25 0 00-3.935-2.186zm0-12.814a2.25 2.25 0 103.933-2.185 2.25 2.25 0 00-3.933 2.185z" />
      </svg>
    ),
    color: 'text-amber-400',
  },
  agent_switcher: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5" />
      </svg>
    ),
    color: 'text-amber-400',
  },
  scheduler: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5m-9-6h.008v.008H12v-.008zM12 15h.008v.008H12V15zm0 2.25h.008v.008H12v-.008zM9.75 15h.008v.008H9.75V15zm0 2.25h.008v.008H9.75v-.008zM7.5 15h.008v.008H7.5V15zm0 2.25h.008v.008H7.5v-.008zm6.75-4.5h.008v.008h-.008v-.008zm0 2.25h.008v.008h-.008V15zm0 2.25h.008v.008h-.008v-.008zm2.25-4.5h.008v.008H16.5v-.008zm0 2.25h.008v.008H16.5V15z" />
      </svg>
    ),
    color: 'text-blue-400',
  },
  calendar: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" />
      </svg>
    ),
    color: 'text-blue-400',
  },
  asana: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    color: 'text-orange-400',
  },
  // Default for unknown skill types
  default: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
      </svg>
    ),
    color: 'text-teal-400',
  },
}

// Format skill type to display name (fallback)
function formatSkillName(skillType: string): string {
  return skillType
    .replace(/_skill$/, '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase())
}

function SkillNode(props: NodeProps<SkillNodeData>) {
  const { data, selected } = props
  const [showDetail, setShowDetail] = useState(false)
  const closeButtonRef = useRef<HTMLButtonElement>(null)
  const previousFocusRef = useRef<HTMLElement | null>(null)

  // Phase 8: Real-time activity glow
  const isActive = data.isActive ?? false
  const isFading = data.isFading ?? false

  // Phase 9: Check if this skill has expandable providers
  const hasProviders = data.hasProviders ?? false
  const isExpanded = data.isExpanded ?? false

  // Phase 9: Handle expand/collapse click
  const handleExpandClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    if (isExpanded) {
      data.onCollapse?.(data.parentAgentId, data.id)
    } else {
      data.onExpand?.(data.parentAgentId, data.id, data.skillType)
    }
  }, [data, isExpanded])

  // Escape key to close modal
  useEffect(() => {
    if (!showDetail) return

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setShowDetail(false)
      }
    }

    window.addEventListener('keydown', handleEscape)
    return () => window.removeEventListener('keydown', handleEscape)
  }, [showDetail])

  // Focus management - focus close button on open, restore focus on close
  useEffect(() => {
    if (showDetail) {
      previousFocusRef.current = document.activeElement as HTMLElement
      // Small delay to ensure modal is rendered
      setTimeout(() => closeButtonRef.current?.focus(), 50)
    } else if (previousFocusRef.current) {
      previousFocusRef.current.focus()
      previousFocusRef.current = null
    }
  }, [showDetail])

  const skillConfig = skillIconConfig[data.skillType] || skillIconConfig.default
  const category = data.category || 'other'
  const catConfig = categoryConfig[category] || categoryConfig.other
  const displayName = data.skillName || formatSkillName(data.skillType)

  return (
    <>
      <div
        className={`
          relative px-3 py-2 rounded-lg border min-w-[140px]
          transition-all duration-200 cursor-pointer
          ${selected
            ? `border-teal-500 bg-teal-500/10 shadow-lg shadow-teal-500/20`
            : 'border-tsushin-border bg-tsushin-surface hover:border-teal-500/50'
          }
          ${!data.isEnabled ? 'opacity-50' : ''}
          ${isActive && !isFading ? 'skill-node-active' : isFading ? 'skill-node-fading' : ''}
        `}
        onClick={() => setShowDetail(true)}
      >
        {/* Connection handle - target (connects from agent/category on the left in LR layout) */}
        <Handle
          type="target"
          position={Position.Left}
          className="!bg-teal-500 !w-2 !h-2 !border-2 !border-tsushin-deep"
        />

        {/* Phase 9: Source handle for expanded providers - always rendered but hidden when collapsed */}
        <Handle
          type="source"
          position={Position.Right}
          className={`!w-2 !h-2 !border-2 !border-tsushin-deep ${!isExpanded ? '!opacity-0' : ''}`}
          style={{
            backgroundColor: '#14B8A6',
            visibility: isExpanded ? 'visible' : 'hidden'
          }}
        />

        <div className="flex items-center gap-2">
          {/* Skill Icon */}
          <div className={`flex-shrink-0 ${skillConfig.color}`}>
            {skillConfig.icon}
          </div>

          {/* Skill Info */}
          <div className="flex flex-col min-w-0 flex-1">
            <div className="text-xs font-medium text-white truncate max-w-[100px]">
              {displayName}
            </div>
            <div className="flex items-center gap-1 text-[10px]">
              {/* Category badge */}
              <span className={`px-1.5 py-0.5 rounded ${catConfig.bgColor} ${catConfig.color} capitalize`}>
                {category}
              </span>
              {/* Provider name if available */}
              {data.providerName && (
                <span className="text-tsushin-slate truncate max-w-[60px]" title={data.providerName}>
                  via {data.providerName}
                </span>
              )}
            </div>
          </div>

          {/* Phase 9: Expand/Collapse button for skills with providers */}
          {hasProviders && data.onExpand && data.onCollapse && (
            <button
              onClick={handleExpandClick}
              aria-label={isExpanded ? `Collapse ${displayName} providers` : `Show ${displayName} providers`}
              aria-expanded={isExpanded}
              className={`
                p-1 rounded transition-colors flex-shrink-0
                ${isExpanded
                  ? 'bg-teal-500/20 text-teal-400'
                  : 'bg-tsushin-surface/50 text-tsushin-slate hover:text-white'
                }
              `}
            >
              <svg
                className={`w-3 h-3 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Detail Popup */}
      {showDetail && (
        <div
          className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/50"
          onClick={() => setShowDetail(false)}
          role="presentation"
        >
          <div
            className="bg-tsushin-deep border border-tsushin-border rounded-xl p-4 shadow-2xl min-w-[320px] max-w-[420px] animate-fade-in"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="skill-modal-title"
          >
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <div className={`${skillConfig.color}`}>{skillConfig.icon}</div>
                <h3 id="skill-modal-title" className="text-lg font-medium text-white">{displayName}</h3>
              </div>
              <button
                ref={closeButtonRef}
                onClick={() => setShowDetail(false)}
                className="p-1 hover:bg-tsushin-surface rounded transition-colors"
                aria-label="Close skill details"
              >
                <svg className="w-5 h-5 text-tsushin-slate" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Description */}
            {data.skillDescription && (
              <p className="text-sm text-tsushin-slate mb-4">
                {data.skillDescription}
              </p>
            )}

            {/* Content */}
            <div className="space-y-3">
              <div className="flex justify-between text-sm">
                <span className="text-tsushin-slate">Category:</span>
                <span className={`px-2 py-0.5 rounded ${catConfig.bgColor} ${catConfig.color} capitalize font-medium`}>
                  {category}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-tsushin-slate">Status:</span>
                <span className={`font-medium ${data.isEnabled ? 'text-green-400' : 'text-red-400'}`}>
                  {data.isEnabled ? 'Enabled' : 'Disabled'}
                </span>
              </div>
              {data.providerName && (
                <div className="flex justify-between text-sm">
                  <span className="text-tsushin-slate">Provider:</span>
                  <span className="text-white">{data.providerName}</span>
                </div>
              )}
              <div className="flex justify-between text-sm">
                <span className="text-tsushin-slate">Type:</span>
                <span className="text-white font-mono text-xs">{data.skillType}</span>
              </div>
              {data.config && Object.keys(data.config).length > 0 && (
                <div>
                  <span className="text-tsushin-slate text-sm block mb-2">Configuration:</span>
                  <pre className="bg-tsushin-surface rounded-lg p-2 text-xs text-tsushin-slate overflow-auto max-h-[150px]">
                    {JSON.stringify(data.config, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  )
}

export default memo(SkillNode)
