'use client'

/**
 * Phase 17: Tool Sandbox Component
 *
 * Tool browser and direct execution interface for cockpit mode.
 * Features:
 * - Tool browser with search
 * - Parameter form generation
 * - Direct tool execution
 * - Result display with copy
 */

import React, { useState, useEffect, useCallback } from 'react'
import { api } from '@/lib/client'
import { copyToClipboard } from '@/lib/clipboard'
import { LightningIcon, WrenchIcon } from '@/components/ui/icons'

interface ToolParameter {
  name: string
  type: string
  required: boolean
  description?: string
}

interface ToolCommand {
  id?: number
  name: string
  description?: string
  parameters: ToolParameter[]
}

interface AvailableTool {
  id: number
  name: string
  tool_type: string
  description?: string
  commands: ToolCommand[]
}

interface ToolSandboxProps {
  agentId: number | null
  isOpen: boolean
  onClose: () => void
}

export default function ToolSandbox({ agentId, isOpen, onClose }: ToolSandboxProps) {
  const [tools, setTools] = useState<AvailableTool[]>([])
  const [loading, setLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedTool, setSelectedTool] = useState<AvailableTool | null>(null)
  const [selectedCommand, setSelectedCommand] = useState<ToolCommand | null>(null)
  const [parameters, setParameters] = useState<Record<string, string>>({})
  const [executing, setExecuting] = useState(false)
  const [result, setResult] = useState<{ output?: string; error?: string } | null>(null)

  // Load available tools
  useEffect(() => {
    if (agentId && isOpen) {
      loadTools()
    }
  }, [agentId, isOpen])

  const loadTools = async () => {
    if (!agentId) return
    setLoading(true)
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8081'}/api/playground/tools/${agentId}`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('tsushin_auth_token')}`
        }
      })
      if (response.ok) {
        const data = await response.json()
        setTools(data)
      }
    } catch (error) {
      console.error('Failed to load tools:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleToolSelect = (tool: AvailableTool) => {
    setSelectedTool(tool)
    setSelectedCommand(null)
    setParameters({})
    setResult(null)
  }

  const handleCommandSelect = (command: ToolCommand) => {
    setSelectedCommand(command)
    // Initialize parameters with empty values
    const initialParams: Record<string, string> = {}
    command.parameters.forEach(p => {
      initialParams[p.name] = ''
    })
    setParameters(initialParams)
    setResult(null)
  }

  const handleExecute = async () => {
    if (!selectedTool || !selectedCommand || !agentId) return

    setExecuting(true)
    setResult(null)

    try {
      // For built-in tools, we need a different execution path
      if (selectedTool.id < 0) {
        // Built-in tool - execute via playground chat with tool invocation
        const toolQuery = `Use the ${selectedTool.name} tool with: ${JSON.stringify(parameters)}`
        const response = await api.sendPlaygroundMessage(agentId, toolQuery)
        setResult({ output: response.message || 'Tool executed successfully' })
      } else {
        // Custom tool - use the custom tools execute endpoint
        const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8081'}/custom-tools/execute/`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('tsushin_auth_token')}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            tool_id: selectedTool.id,
            command_id: selectedCommand.id,
            parameters: parameters
          })
        })

        if (response.ok) {
          const data = await response.json()
          setResult({ output: data.output || JSON.stringify(data, null, 2), error: data.error })
        } else {
          const errorData = await response.json()
          setResult({ error: errorData.detail || 'Execution failed' })
        }
      }
    } catch (error: any) {
      setResult({ error: error.message || 'Execution failed' })
    } finally {
      setExecuting(false)
    }
  }

  const copyResult = () => {
    if (result?.output) {
      copyToClipboard(result.output)
    }
  }

  const filteredTools = tools.filter(t =>
    t.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    t.description?.toLowerCase().includes(searchQuery.toLowerCase())
  )

  if (!isOpen) return null

  return (
    <div className="h-full flex flex-col bg-[#0a0a0f] border-t border-white/[0.06]">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.06]">
        <div className="flex items-center gap-3">
          <LightningIcon size={18} className="text-teal-400" />
          <h3 className="text-sm font-semibold text-white">Tool Sandbox</h3>
          <span className="text-xs text-white/40 bg-white/[0.04] px-2 py-0.5 rounded">
            {tools.length} tools
          </span>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded-lg text-white/40 hover:text-white hover:bg-white/[0.04] transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Tool List */}
        <div className="w-64 border-r border-white/[0.06] flex flex-col">
          {/* Search */}
          <div className="p-3 border-b border-white/[0.06]">
            <div className="relative">
              <input
                type="text"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder="Search tools..."
                className="w-full bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-white placeholder:text-white/30 outline-none focus:border-teal-500/50"
              />
              <svg className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
          </div>

          {/* Tools */}
          <div className="flex-1 overflow-y-auto p-2">
            {loading ? (
              <div className="flex items-center justify-center py-8">
                <div className="w-5 h-5 border-2 border-white/20 border-t-teal-500 rounded-full animate-spin" />
              </div>
            ) : filteredTools.length === 0 ? (
              <div className="text-center py-8 text-white/40 text-sm">
                No tools available
              </div>
            ) : (
              <div className="space-y-1">
                {filteredTools.map(tool => (
                  <button
                    key={tool.id}
                    onClick={() => handleToolSelect(tool)}
                    className={`
                      w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-colors
                      ${selectedTool?.id === tool.id
                        ? 'bg-teal-500/15 text-teal-400 border border-teal-500/30'
                        : 'text-white/70 hover:bg-white/[0.04] border border-transparent'
                      }
                    `}
                  >
                    <span className="flex items-center justify-center w-5 h-5">
                      {tool.tool_type === 'built_in' ? <LightningIcon size={16} /> : <WrenchIcon size={16} />}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate">{tool.name}</div>
                      <div className="text-xs text-white/40 truncate">{tool.tool_type}</div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Tool Details & Execution */}
        <div className="flex-1 flex flex-col">
          {!selectedTool ? (
            <div className="flex-1 flex items-center justify-center text-white/40">
              <div className="text-center">
                <span className="flex items-center justify-center mb-3"><WrenchIcon size={48} /></span>
                <p className="text-sm">Select a tool to get started</p>
              </div>
            </div>
          ) : (
            <>
              {/* Tool Info */}
              <div className="p-4 border-b border-white/[0.06]">
                <div className="flex items-center gap-3 mb-2">
                  <h4 className="text-base font-semibold text-white">{selectedTool.name}</h4>
                  <span className="text-xs bg-white/[0.06] px-2 py-0.5 rounded text-white/50">
                    {selectedTool.tool_type}
                  </span>
                </div>
                {selectedTool.description && (
                  <p className="text-sm text-white/50">{selectedTool.description}</p>
                )}
              </div>

              {/* Commands */}
              <div className="p-4 border-b border-white/[0.06]">
                <label className="text-xs text-white/50 uppercase tracking-wider mb-2 block">Command</label>
                <div className="flex flex-wrap gap-2">
                  {selectedTool.commands.map((cmd, idx) => (
                    <button
                      key={cmd.id || idx}
                      onClick={() => handleCommandSelect(cmd)}
                      className={`
                        px-3 py-1.5 rounded-lg text-sm transition-colors
                        ${selectedCommand?.name === cmd.name
                          ? 'bg-teal-500/20 text-teal-400 border border-teal-500/30'
                          : 'bg-white/[0.04] text-white/70 hover:bg-white/[0.06] border border-white/[0.08]'
                        }
                      `}
                    >
                      {cmd.name}
                    </button>
                  ))}
                </div>
              </div>

              {/* Parameters */}
              {selectedCommand && (
                <div className="p-4 border-b border-white/[0.06]">
                  <label className="text-xs text-white/50 uppercase tracking-wider mb-3 block">Parameters</label>
                  <div className="space-y-3">
                    {selectedCommand.parameters.length === 0 ? (
                      <p className="text-sm text-white/40">No parameters required</p>
                    ) : (
                      selectedCommand.parameters.map(param => (
                        <div key={param.name}>
                          <label className="text-sm text-white/70 mb-1 block">
                            {param.name}
                            {param.required && <span className="text-red-400 ml-1">*</span>}
                          </label>
                          <input
                            type="text"
                            value={parameters[param.name] || ''}
                            onChange={e => setParameters(prev => ({ ...prev, [param.name]: e.target.value }))}
                            placeholder={param.description || `Enter ${param.name}`}
                            className="w-full bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-white placeholder:text-white/30 outline-none focus:border-teal-500/50"
                          />
                          {param.description && (
                            <p className="text-xs text-white/40 mt-1">{param.description}</p>
                          )}
                        </div>
                      ))
                    )}
                  </div>

                  {/* Execute Button */}
                  <button
                    onClick={handleExecute}
                    disabled={executing || !selectedCommand}
                    className={`
                      mt-4 w-full py-2.5 rounded-lg text-sm font-medium transition-all
                      ${executing
                        ? 'bg-white/[0.04] text-white/40 cursor-not-allowed'
                        : 'bg-gradient-to-r from-teal-500 to-cyan-500 text-white hover:opacity-90'
                      }
                    `}
                  >
                    {executing ? (
                      <span className="flex items-center justify-center gap-2">
                        <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                        Executing...
                      </span>
                    ) : (
                      <span className="flex items-center justify-center gap-2">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        Execute
                      </span>
                    )}
                  </button>
                </div>
              )}

              {/* Result */}
              {result && (
                <div className="flex-1 p-4 overflow-auto">
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-xs text-white/50 uppercase tracking-wider">Result</label>
                    {result.output && (
                      <button
                        onClick={copyResult}
                        className="text-xs text-white/50 hover:text-white flex items-center gap-1"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                        </svg>
                        Copy
                      </button>
                    )}
                  </div>
                  <div className={`
                    rounded-lg p-3 font-mono text-sm overflow-auto max-h-[200px]
                    ${result.error
                      ? 'bg-red-500/10 border border-red-500/20 text-red-400'
                      : 'bg-white/[0.04] border border-white/[0.08] text-green-400'
                    }
                  `}>
                    <pre className="whitespace-pre-wrap break-words">
                      {result.error || result.output}
                    </pre>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
