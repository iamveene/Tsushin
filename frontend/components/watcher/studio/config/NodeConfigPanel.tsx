'use client'

import { useEffect, useCallback } from 'react'
import type { BuilderNodeData, BuilderNodeType } from '../types'
import type { SkillDefinition } from '@/lib/client'
import MemoryConfigForm from './MemoryConfigForm'
import SkillConfigForm from './SkillConfigForm'
import ToolConfigForm from './ToolConfigForm'
import PersonaInfoPanel from './PersonaInfoPanel'
import ChannelInfoPanel from './ChannelInfoPanel'
import SentinelInfoPanel from './SentinelInfoPanel'
import KnowledgeInfoPanel from './KnowledgeInfoPanel'

interface NodeConfigPanelProps {
  isOpen: boolean
  nodeId: string
  nodeType: BuilderNodeType
  nodeData: BuilderNodeData
  onClose: () => void
  onUpdate: (nodeType: string, nodeId: string, config: Record<string, unknown>) => void
  skillDefinitions: SkillDefinition[]
}

const NODE_TYPE_TITLES: Record<string, string> = {
  'builder-memory': 'Memory Configuration',
  'builder-skill': 'Skill Configuration',
  'builder-tool': 'Tool Configuration',
  'builder-persona': 'Persona Details',
  'builder-channel': 'Channel Details',
  'builder-sentinel': 'Security Profile',
  'builder-knowledge': 'Knowledge Document',
}

const NODE_TYPE_COLORS: Record<string, string> = {
  'builder-memory': 'text-sky-400',
  'builder-skill': 'text-teal-400',
  'builder-tool': 'text-orange-400',
  'builder-persona': 'text-purple-400',
  'builder-channel': 'text-blue-400',
  'builder-sentinel': 'text-red-400',
  'builder-knowledge': 'text-violet-400',
}

export default function NodeConfigPanel({ isOpen, nodeId, nodeType, nodeData, onClose, onUpdate, skillDefinitions }: NodeConfigPanelProps) {
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.stopPropagation()
      onClose()
    }
  }, [onClose])

  useEffect(() => {
    if (!isOpen) return
    window.addEventListener('keydown', handleKeyDown, true)
    return () => window.removeEventListener('keydown', handleKeyDown, true)
  }, [isOpen, handleKeyDown])

  const renderContent = () => {
    switch (nodeType) {
      case 'builder-memory':
        return <MemoryConfigForm nodeId={nodeId} data={nodeData as any} onUpdate={onUpdate} />
      case 'builder-skill':
        return <SkillConfigForm nodeId={nodeId} data={nodeData as any} onUpdate={onUpdate} skillDefinitions={skillDefinitions} />
      case 'builder-tool':
        return <ToolConfigForm nodeId={nodeId} data={nodeData as any} onUpdate={onUpdate} />
      case 'builder-persona':
        return <PersonaInfoPanel data={nodeData as any} />
      case 'builder-channel':
        return <ChannelInfoPanel data={nodeData as any} />
      case 'builder-sentinel':
        return <SentinelInfoPanel data={nodeData as any} />
      case 'builder-knowledge':
        return <KnowledgeInfoPanel data={nodeData as any} />
      default:
        return <p className="text-xs text-tsushin-muted">No configuration available.</p>
    }
  }

  const isEditable = nodeType === 'builder-memory' || nodeType === 'builder-skill' || nodeType === 'builder-tool'

  return (
    <div className={`node-config-panel ${isOpen ? 'open' : ''}`}>
      <div className="node-config-panel-header">
        <div className="flex items-center gap-2 min-w-0">
          <span className={`text-xs font-medium ${NODE_TYPE_COLORS[nodeType] || 'text-tsushin-slate'}`}>
            {isEditable ? 'Edit' : 'Info'}
          </span>
          <h3 className="text-sm font-medium text-white truncate">
            {NODE_TYPE_TITLES[nodeType] || 'Node Details'}
          </h3>
        </div>
        <button
          onClick={onClose}
          className="flex-shrink-0 p-1 rounded hover:bg-tsushin-surface transition-colors"
          aria-label="Close panel"
        >
          <svg className="w-4 h-4 text-tsushin-slate" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
      <div className="node-config-panel-body">
        {renderContent()}
      </div>
    </div>
  )
}
