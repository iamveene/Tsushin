'use client'

/**
 * AgentSandboxedToolsManager (formerly AgentSandboxedToolsManager)
 * Skills-as-Tools Phase 6: Renamed for clarity
 *
 * Manages sandboxed tool assignments for an agent.
 * Sandboxed tools run in isolated Docker containers.
 */

import { useEffect, useState } from 'react'
import { api, AgentSandboxedTool, SandboxedTool } from '@/lib/client'
import { InfoIcon, AlertTriangleIcon, LinkIcon, PlaneIcon, ChartBarIcon, CheckIcon } from '@/components/ui/icons'

interface Props {
  agentId: number
}

export default function AgentSandboxedToolsManager({ agentId }: Props) {
  const [allTools, setAllTools] = useState<SandboxedTool[]>([])
  const [agentTools, setAgentTools] = useState<AgentSandboxedTool[]>([])
  const [loading, setLoading] = useState(true)
  const [updating, setUpdating] = useState<number | null>(null)

  useEffect(() => {
    loadData()
  }, [agentId])

  const loadData = async () => {
    setLoading(true)
    try {
      const [tools, assignments] = await Promise.all([
        api.getSandboxedTools(),
        api.getAgentSandboxedTools(agentId),
      ])
      setAllTools(tools.filter(t => t.is_enabled)) // Only show globally enabled tools
      setAgentTools(assignments)
    } catch (err) {
      console.error('Failed to load sandboxed tools:', err)
      alert('Failed to load sandboxed tools')
    } finally {
      setLoading(false)
    }
  }

  const isToolEnabled = (toolId: number): boolean => {
    return agentTools.some(at => at.sandboxed_tool_id === toolId && at.is_enabled)
  }

  const getToolMapping = (toolId: number): AgentSandboxedTool | undefined => {
    return agentTools.find(at => at.sandboxed_tool_id === toolId)
  }

  const toggleTool = async (tool: SandboxedTool, enabled: boolean) => {
    setUpdating(tool.id)
    try {
      const mapping = getToolMapping(tool.id)

      if (enabled) {
        if (mapping) {
          // Update existing mapping to enabled
          await api.updateAgentSandboxedTool(agentId, mapping.id, { is_enabled: true })
        } else {
          // Create new mapping
          await api.addAgentSandboxedTool(agentId, {
            sandboxed_tool_id: tool.id,
            is_enabled: true,
          })
        }
      } else {
        if (mapping) {
          // Disable existing mapping
          await api.updateAgentSandboxedTool(agentId, mapping.id, { is_enabled: false })
        }
      }

      await loadData()
    } catch (err) {
      console.error('Failed to toggle sandboxed tool:', err)
      alert('Failed to toggle sandboxed tool')
    } finally {
      setUpdating(null)
    }
  }

  if (loading) {
    return <div className="p-8 text-center">Loading sandboxed tools...</div>
  }

  if (allTools.length === 0) {
    return (
      <div className="p-8 text-center">
        <p className="text-gray-600 dark:text-gray-400 mb-4">No sandboxed tools available</p>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Sandboxed tools must be created and enabled globally before they can be assigned to agents.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="bg-blue-50 dark:bg-blue-900/20 border dark:border-gray-700 border-blue-200 dark:border-blue-700 rounded-lg p-4">
        <h3 className="text-sm font-medium text-blue-800 dark:text-blue-200 mb-2 flex items-center gap-2"><InfoIcon size={16} /> About Sandboxed Tools</h3>
        <p className="text-sm text-blue-700 dark:text-blue-300">
          Sandboxed tools run in isolated containers and can extend agent capabilities with custom functionality.
          Enable tools for this agent to allow it to use them when appropriate.
        </p>
      </div>

      <div className="grid gap-6">
        {allTools.map((tool) => {
          const enabled = isToolEnabled(tool.id)
          const isUpdating = updating === tool.id

          return (
            <div
              key={tool.id}
              className={`border dark:border-gray-700 rounded-lg p-6 transition-colors ${enabled
                  ? 'bg-green-50 dark:bg-green-900/20 border-green-300 dark:border-green-600'
                  : 'bg-gray-50 dark:bg-gray-900'
                }`}
            >
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <h3 className="text-lg font-semibold">{tool.name}</h3>
                    <span className="px-2 py-1 text-xs font-medium bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded">
                      {tool.tool_type}
                    </span>
                  </div>
                  <p className="text-sm text-gray-600 dark:text-gray-400 whitespace-pre-wrap">
                    {tool.system_prompt.split('\n').slice(0, 3).join('\n')}
                  </p>
                </div>
                <div className="flex items-center gap-3 ml-4">
                  <label className="flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={enabled}
                      disabled={isUpdating}
                      onChange={(e) => toggleTool(tool, e.target.checked)}
                      className="mr-2 w-5 h-5"
                    />
                    <span className="text-sm font-medium">
                      {isUpdating ? 'Updating...' : enabled ? 'Enabled' : 'Disabled'}
                    </span>
                  </label>
                </div>
              </div>

              {enabled && (
                <div className="mt-4 pt-4 border-t border-green-300 dark:border-green-600">
                  <div className="flex items-center gap-2 text-sm">
                    <span className="text-green-700 dark:text-green-300 font-medium inline-flex items-center gap-1"><CheckIcon size={14} /> Tool enabled for this agent</span>
                    <span className="text-gray-500 dark:text-gray-400">
                      • The agent can use this tool when processing messages
                    </span>
                  </div>
                </div>
              )}

              {/* Tool-specific warnings */}
              {tool.name === 'nmap' && (
                <div className="mt-4 p-3 bg-yellow-50 dark:bg-yellow-900/20 border dark:border-gray-700 border-yellow-200 dark:border-yellow-700 rounded text-sm">
                  <p className="font-medium text-yellow-800 dark:text-yellow-200 flex items-center gap-2"><AlertTriangleIcon size={16} /> Security Tool</p>
                  <p className="text-yellow-700 dark:text-yellow-300 mt-1">
                    Network scanning should only be performed on networks you own or have explicit permission to scan.
                    Unauthorized scanning may be illegal.
                  </p>
                </div>
              )}

              {tool.name === 'nuclei' && (
                <div className="mt-4 p-3 bg-yellow-50 dark:bg-yellow-900/20 border dark:border-gray-700 border-yellow-200 dark:border-yellow-700 rounded text-sm">
                  <p className="font-medium text-yellow-800 dark:text-yellow-200 flex items-center gap-2"><AlertTriangleIcon size={16} /> Vulnerability Scanner</p>
                  <p className="text-yellow-700 dark:text-yellow-300 mt-1">
                    Only scan targets you own or have explicit permission to test. Requires Nuclei installed on the system.
                  </p>
                </div>
              )}

              {tool.name === 'webhook' && (
                <div className="mt-4 p-3 bg-blue-50 dark:bg-blue-900/20 border dark:border-gray-700 border-blue-200 dark:border-blue-700 rounded text-sm">
                  <p className="font-medium text-blue-800 dark:text-blue-200 flex items-center gap-2"><LinkIcon size={16} /> HTTP Integration</p>
                  <p className="text-blue-700 dark:text-blue-300 mt-1">
                    Allows the agent to make HTTP requests to external services and APIs.
                  </p>
                </div>
              )}

              {tool.name === 'flights' && (
                <div className="mt-4 p-3 bg-blue-50 dark:bg-blue-900/20 border dark:border-gray-700 border-blue-200 dark:border-blue-700 rounded text-sm">
                  <p className="font-medium text-blue-800 dark:text-blue-200 flex items-center gap-2"><PlaneIcon size={16} /> Flight Search</p>
                  <p className="text-blue-700 dark:text-blue-300 mt-1">
                    Allows the agent to search for flights using the Amadeus API. The agent can find flight options with pricing and schedules when users ask about travel. Requires Amadeus API credentials.
                  </p>
                </div>
              )}
            </div>
          )
        })}
      </div>

      <div className="bg-gray-50 dark:bg-gray-900 border dark:border-gray-700 rounded-lg p-4">
        <h4 className="text-sm font-medium mb-2 flex items-center gap-2"><ChartBarIcon size={16} /> Tool Assignment Summary</h4>
        <div className="text-sm text-gray-600 dark:text-gray-400">
          <p>Total available tools: {allTools.length}</p>
          <p>Tools enabled for this agent: {agentTools.filter(at => at.is_enabled).length}</p>
        </div>
      </div>
    </div>
  )
}
