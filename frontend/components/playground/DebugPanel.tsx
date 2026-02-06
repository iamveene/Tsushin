'use client'

/**
 * Phase 17: Debug Panel Component
 *
 * Debug and diagnostic view for cockpit mode.
 * Features:
 * - Recent tool calls timeline
 * - Token usage tracking
 * - Model information
 * - Agent reasoning display
 */

import React, { useState, useEffect } from 'react'
import {
  BugIcon,
  BotIcon,
  ChartBarIcon,
  WrenchIcon,
  SearchIcon,
  AlertTriangleIcon,
  MessageIcon,
  ArrowUpIcon,
  ArrowDownIcon
} from '@/components/ui/icons'
import { parseUTCTimestamp } from '@/lib/dateUtils'

interface ToolCall {
  id: number
  tool_name: string
  command_name: string
  parameters: Record<string, any>
  result?: string
  status: string
  execution_time_ms?: number
  created_at: string
}

interface DebugData {
  recent_tool_calls: ToolCall[]
  token_usage: {
    total?: number
    input?: number
    output?: number
  }
  estimated_cost?: number  // Estimated cost in USD
  last_reasoning?: string
  model_info: {
    provider: string
    model: string
    memory_size: number
    semantic_search: boolean
  }
}

interface DebugPanelProps {
  agentId: number | null
}

export default function DebugPanel({ agentId }: DebugPanelProps) {
  const [debugData, setDebugData] = useState<DebugData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expandedCall, setExpandedCall] = useState<number | null>(null)

  useEffect(() => {
    if (agentId) {
      loadDebugInfo()
    }
  }, [agentId])

  const loadDebugInfo = async () => {
    if (!agentId) return
    setLoading(true)
    setError(null)

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8081'}/api/playground/debug/${agentId}`,
        {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('tsushin_auth_token')}`
          }
        }
      )

      if (response.ok) {
        const data = await response.json()
        setDebugData(data)
      } else {
        setError('Failed to load debug info')
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load debug info')
    } finally {
      setLoading(false)
    }
  }

  const formatTime = (ts: string) => {
    try {
      return parseUTCTimestamp(ts).toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      })
    } catch {
      return ts
    }
  }

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'completed':
      case 'success':
        return 'text-green-400 bg-green-500/10 border-green-500/20'
      case 'failed':
      case 'error':
        return 'text-red-400 bg-red-500/10 border-red-500/20'
      case 'running':
      case 'pending':
        return 'text-amber-400 bg-amber-500/10 border-amber-500/20'
      default:
        return 'text-white/60 bg-white/5 border-white/10'
    }
  }

  const formatCost = (cost: number | undefined) => {
    if (cost === undefined || cost === null) return '$0.0000'
    if (cost === 0) return '$0.0000'
    if (cost < 0.0001) return `$${cost.toFixed(6)}`
    if (cost < 0.01) return `$${cost.toFixed(4)}`
    return `$${cost.toFixed(4)}`
  }

  return (
    <div className="h-full flex flex-col bg-[#0d0d14]">
      {/* Header */}
      <div className="px-4 py-3 border-b border-white/[0.06]">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-white/70"><BugIcon size={18} /></span>
            <h3 className="text-sm font-semibold text-white">Debug Panel</h3>
          </div>
          <button
            onClick={loadDebugInfo}
            disabled={loading}
            className="p-1.5 rounded-lg text-white/40 hover:text-white hover:bg-white/[0.04] transition-colors disabled:opacity-50"
            title="Refresh"
          >
            <svg className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <div className="w-6 h-6 border-2 border-white/20 border-t-teal-500 rounded-full animate-spin" />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-full text-center p-4">
            <span className="text-red-400 mb-2"><AlertTriangleIcon size={48} /></span>
            <p className="text-sm text-red-400">{error}</p>
          </div>
        ) : !debugData ? (
          <div className="flex flex-col items-center justify-center h-full text-center p-4">
            <span className="text-white/30 mb-2"><SearchIcon size={48} /></span>
            <p className="text-sm text-white/40">Select an agent to view debug info</p>
          </div>
        ) : (
          <div className="p-4 space-y-4">
            {/* Model Info Card */}
            <div className="bg-white/[0.02] rounded-xl border border-white/[0.06] p-4">
              <h4 className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-3 flex items-center gap-2">
                <BotIcon size={14} /> Model Configuration
              </h4>
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <span className="text-white/40">Provider</span>
                  <p className="text-white font-medium mt-0.5">{debugData.model_info.provider}</p>
                </div>
                <div>
                  <span className="text-white/40">Model</span>
                  <p className="text-white font-medium mt-0.5">{debugData.model_info.model}</p>
                </div>
                <div>
                  <span className="text-white/40">Memory Size</span>
                  <p className="text-white font-medium mt-0.5">{debugData.model_info.memory_size} messages</p>
                </div>
                <div>
                  <span className="text-white/40">Semantic Search</span>
                  <p className={`font-medium mt-0.5 ${debugData.model_info.semantic_search ? 'text-green-400' : 'text-white/50'}`}>
                    {debugData.model_info.semantic_search ? 'Enabled' : 'Disabled'}
                  </p>
                </div>
              </div>
            </div>

            {/* Token Usage & Cost Card */}
            <div className="bg-white/[0.02] rounded-xl border border-white/[0.06] p-4">
              <h4 className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-3 flex items-center gap-2">
                <ChartBarIcon size={14} /> Token Usage & Cost (Session)
              </h4>
              <div className="grid grid-cols-2 gap-4 text-xs">
                {/* Token metrics row */}
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg bg-purple-500/10 flex items-center justify-center">
                    <span className="text-purple-400"><ArrowUpIcon size={18} /></span>
                  </div>
                  <div>
                    <span className="text-white/40 block">Input</span>
                    <span className="text-white font-semibold">{(debugData.token_usage.input || 0).toLocaleString()}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg bg-teal-500/10 flex items-center justify-center">
                    <span className="text-teal-400"><ArrowDownIcon size={18} /></span>
                  </div>
                  <div>
                    <span className="text-white/40 block">Output</span>
                    <span className="text-white font-semibold">{(debugData.token_usage.output || 0).toLocaleString()}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg bg-amber-500/10 flex items-center justify-center">
                    <span className="text-amber-400 text-lg font-bold">Σ</span>
                  </div>
                  <div>
                    <span className="text-white/40 block">Total Tokens</span>
                    <span className="text-white font-semibold">{(debugData.token_usage.total || 0).toLocaleString()}</span>
                  </div>
                </div>
                {/* Cost metric */}
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg bg-emerald-500/10 flex items-center justify-center">
                    <span className="text-emerald-400 text-lg">$</span>
                  </div>
                  <div>
                    <span className="text-white/40 block">Est. Cost</span>
                    <span className="text-emerald-400 font-semibold">{formatCost(debugData.estimated_cost)}</span>
                  </div>
                </div>
              </div>
              {debugData.estimated_cost !== undefined && debugData.estimated_cost > 0 && (
                <p className="text-[10px] text-white/30 mt-3">
                  Cost estimate based on {debugData.model_info.model} pricing
                </p>
              )}
            </div>

            {/* Last Reasoning */}
            {debugData.last_reasoning && (
              <div className="bg-white/[0.02] rounded-xl border border-white/[0.06] p-4">
                <h4 className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-3 flex items-center gap-2">
                  <MessageIcon size={14} /> Last Internal Reasoning
                </h4>
                <div className="bg-indigo-500/5 border border-indigo-500/20 rounded-lg p-3">
                  <pre className="text-xs text-indigo-300 whitespace-pre-wrap font-mono">
                    {debugData.last_reasoning}
                  </pre>
                </div>
              </div>
            )}

            {/* Tool Calls Timeline */}
            <div className="bg-white/[0.02] rounded-xl border border-white/[0.06] p-4">
              <h4 className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-3 flex items-center gap-2">
                <WrenchIcon size={14} /> Recent Tool Calls
              </h4>
              {debugData.recent_tool_calls.length === 0 ? (
                <p className="text-xs text-white/40 text-center py-4">No recent tool calls</p>
              ) : (
                <div className="space-y-2">
                  {debugData.recent_tool_calls.map(call => (
                    <div
                      key={call.id}
                      className="bg-white/[0.02] rounded-lg border border-white/[0.06] overflow-hidden"
                    >
                      <button
                        onClick={() => setExpandedCall(expandedCall === call.id ? null : call.id)}
                        className="w-full flex items-center gap-3 p-3 text-left hover:bg-white/[0.02] transition-colors"
                      >
                        <div className="w-8 h-8 rounded-lg bg-white/[0.04] flex items-center justify-center text-white/60">
                          <WrenchIcon size={18} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-white">{call.tool_name}</span>
                            <span className={`text-[10px] px-1.5 py-0.5 rounded border ${getStatusColor(call.status)}`}>
                              {call.status}
                            </span>
                          </div>
                          <div className="flex items-center gap-2 text-xs text-white/40 mt-0.5">
                            <span>{formatTime(call.created_at)}</span>
                            {call.execution_time_ms && (
                              <span>• {call.execution_time_ms}ms</span>
                            )}
                          </div>
                        </div>
                        <svg
                          className={`w-4 h-4 text-white/40 transition-transform ${expandedCall === call.id ? 'rotate-180' : ''}`}
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                        </svg>
                      </button>

                      {expandedCall === call.id && (
                        <div className="px-3 pb-3 border-t border-white/[0.06] pt-3">
                          {call.result && (
                            <div className="mb-2">
                              <label className="text-[10px] text-white/40 uppercase tracking-wider block mb-1">Result</label>
                              <pre className="text-xs text-green-400 bg-green-500/5 border border-green-500/10 rounded-lg p-2 overflow-auto max-h-32 font-mono whitespace-pre-wrap">
                                {call.result}
                              </pre>
                            </div>
                          )}
                          {Object.keys(call.parameters).length > 0 && (
                            <div>
                              <label className="text-[10px] text-white/40 uppercase tracking-wider block mb-1">Parameters</label>
                              <pre className="text-xs text-white/70 bg-white/[0.02] rounded-lg p-2 font-mono overflow-auto">
                                {JSON.stringify(call.parameters, null, 2)}
                              </pre>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
