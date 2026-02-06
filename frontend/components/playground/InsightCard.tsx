'use client'

/**
 * Phase 14.6: Insight Card Component
 * Displays individual insights with type-specific icons and confidence scores
 */

import React, { useState } from 'react'
import { api } from '@/lib/client'
import { copyToClipboard } from '@/lib/clipboard'
import {
  LightbulbIcon,
  ChartBarIcon,
  CheckCircleIcon,
  PinIcon,
  HelpCircleIcon,
  IconProps
} from '@/components/ui/icons'

interface Insight {
  id: number
  insight_text: string
  insight_type: string
  confidence: number
}

interface InsightCardProps {
  insight: Insight
  onInsightUpdated?: () => void
  onInsightDeleted?: () => void
}

export default function InsightCard({ insight, onInsightUpdated, onInsightDeleted }: InsightCardProps) {
  const [copied, setCopied] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [editText, setEditText] = useState(insight.insight_text)
  const [editType, setEditType] = useState(insight.insight_type)
  const [editConfidence, setEditConfidence] = useState(insight.confidence)
  const [isSaving, setIsSaving] = useState(false)

  const INSIGHT_ICON_COMPONENTS: Record<string, React.FC<IconProps>> = {
    fact: LightbulbIcon,
    conclusion: ChartBarIcon,
    decision: CheckCircleIcon,
    action_item: PinIcon,
    question: HelpCircleIcon,
  }

  const getIcon = (type: string) => {
    const IconComponent = INSIGHT_ICON_COMPONENTS[type]
    if (IconComponent) {
      return <IconComponent size={16} />
    }
    return <span>•</span>
  }

  const getTypeColor = (type: string) => {
    switch (type) {
      case 'fact':
        return 'text-blue-400'
      case 'conclusion':
        return 'text-purple-400'
      case 'decision':
        return 'text-green-400'
      case 'action_item':
        return 'text-orange-400'
      case 'question':
        return 'text-yellow-400'
      default:
        return 'text-tsushin-slate'
    }
  }

  const handleCopy = () => {
    copyToClipboard(insight.insight_text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const startEdit = () => {
    setEditText(insight.insight_text)
    setEditType(insight.insight_type)
    setEditConfidence(insight.confidence)
    setIsEditing(true)
  }

  const cancelEdit = () => {
    setIsEditing(false)
    setEditText(insight.insight_text)
    setEditType(insight.insight_type)
    setEditConfidence(insight.confidence)
  }

  const saveEdit = async () => {
    setIsSaving(true)
    try {
      await api.updateInsight(insight.id, {
        insight_text: editText,
        insight_type: editType,
        confidence: editConfidence
      })
      setIsEditing(false)
      if (onInsightUpdated) onInsightUpdated()
    } catch (err: any) {
      console.error('Failed to update insight:', err)
      alert('Failed to update insight: ' + err.message)
    } finally {
      setIsSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!confirm('Delete this insight?')) return

    try {
      await api.deleteInsight(insight.id)
      if (onInsightDeleted) onInsightDeleted()
    } catch (err: any) {
      console.error('Failed to delete insight:', err)
      alert('Failed to delete insight: ' + err.message)
    }
  }

  const renderConfidence = (conf: number) => {
    const stars = Math.round(conf * 5)
    return (
      <div className="flex items-center gap-1">
        {[...Array(5)].map((_, i) => (
          <span key={i} className={i < stars ? 'text-yellow-400' : 'text-tsushin-slate/30'}>
            ★
          </span>
        ))}
      </div>
    )
  }

  const insightTypes = ['fact', 'conclusion', 'decision', 'action_item', 'question']

  if (isEditing) {
    return (
      <div className="bg-tsushin-deepBlue/50 border border-tsushin-accent rounded-lg p-3">
        {/* Edit Mode Header */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className="flex items-center justify-center w-5 h-5">{getIcon(editType)}</span>
            <select
              value={editType}
              onChange={(e) => setEditType(e.target.value)}
              className="text-xs font-medium bg-tsushin-surface border border-tsushin-border rounded px-2 py-1 text-white"
            >
              {insightTypes.map(type => (
                <option key={type} value={type}>
                  {type.replace('_', ' ').toUpperCase()}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Edit Textarea */}
        <textarea
          value={editText}
          onChange={(e) => setEditText(e.target.value)}
          className="w-full bg-tsushin-surface border border-tsushin-border rounded px-3 py-2 text-sm text-white mb-3 min-h-[80px] resize-none focus:outline-none focus:border-tsushin-accent"
          placeholder="Insight text..."
        />

        {/* Confidence Slider */}
        <div className="mb-3">
          <label className="text-xs text-tsushin-slate mb-1 block">
            Confidence: {editConfidence.toFixed(2)}
          </label>
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={editConfidence}
            onChange={(e) => setEditConfidence(parseFloat(e.target.value))}
            className="w-full"
          />
          <div className="text-xs mt-1">
            {renderConfidence(editConfidence)}
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex gap-2">
          <button
            onClick={saveEdit}
            disabled={isSaving || !editText.trim()}
            className="flex-1 px-3 py-1.5 bg-tsushin-accent hover:bg-tsushin-accent/80 disabled:bg-tsushin-slate/30 disabled:cursor-not-allowed text-white text-sm rounded transition-colors"
          >
            {isSaving ? 'Saving...' : 'Save'}
          </button>
          <button
            onClick={cancelEdit}
            disabled={isSaving}
            className="flex-1 px-3 py-1.5 bg-tsushin-surface hover:bg-tsushin-surface/80 disabled:opacity-50 text-white text-sm rounded transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    )
  }

  return (
    <div
      className="bg-tsushin-deepBlue/30 border border-tsushin-border rounded-lg p-3 group hover:border-tsushin-accent/30 transition-all cursor-pointer"
      onClick={startEdit}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="flex items-center justify-center w-5 h-5">{getIcon(insight.insight_type)}</span>
          <span className={`text-xs font-medium ${getTypeColor(insight.insight_type)}`}>
            {insight.insight_type.replace('_', ' ').toUpperCase()}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* Confidence */}
          <div className="text-xs">
            {renderConfidence(insight.confidence)}
          </div>

          {/* Delete Button */}
          <button
            onClick={(e) => {
              e.stopPropagation()
              handleDelete()
            }}
            className="opacity-0 group-hover:opacity-100 transition-opacity text-tsushin-slate hover:text-red-400"
            title="Delete insight"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>

          {/* Copy Button */}
          <button
            onClick={(e) => {
              e.stopPropagation()
              handleCopy()
            }}
            className="opacity-0 group-hover:opacity-100 transition-opacity text-tsushin-slate hover:text-white"
            title="Copy to clipboard"
          >
            {copied ? (
              <svg className="w-4 h-4 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            ) : (
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* Insight Text */}
      <p className="text-sm text-white leading-relaxed">
        {insight.insight_text}
      </p>

      {/* Edit hint */}
      <div className="text-xs text-tsushin-slate mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
        Click to edit
      </div>
    </div>
  )
}
