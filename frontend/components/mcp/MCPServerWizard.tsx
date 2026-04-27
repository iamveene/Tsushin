'use client'

import { useState, useEffect } from 'react'
import Modal from '@/components/ui/Modal'
import { api, Agent, CustomSkill, CustomSkillCreate } from '@/lib/client'

interface MCPServerWizardProps {
  isOpen: boolean
  onClose: () => void
  mcpServer: { id: number; server_name: string } | null
  onComplete?: () => void
}

interface MCPTool {
  id: number
  server_id: number
  tool_name: string
  namespaced_name: string
  description?: string | null
  input_schema: Record<string, any>
  is_enabled: boolean
}

export default function MCPServerWizard({ isOpen, onClose, mcpServer, onComplete }: MCPServerWizardProps) {
  const [currentStep, setCurrentStep] = useState(1)
  const [tools, setTools] = useState<MCPTool[]>([])
  const [toolsLoading, setToolsLoading] = useState(true)
  const [selectedTool, setSelectedTool] = useState<string | null>(null)
  const [skillName, setSkillName] = useState('')
  const [skillDescription, setSkillDescription] = useState('')
  const [createdSkill, setCreatedSkill] = useState<CustomSkill | null>(null)
  const [agents, setAgents] = useState<Agent[]>([])
  const [agentsLoading, setAgentsLoading] = useState(false)
  const [selectedAgentIds, setSelectedAgentIds] = useState<Set<number>>(new Set())
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!isOpen || !mcpServer) return
    setCurrentStep(1)
    setTools([])
    setSelectedTool(null)
    setSkillName('')
    setSkillDescription('')
    setCreatedSkill(null)
    setAgents([])
    setSelectedAgentIds(new Set())
    setError(null)

    setToolsLoading(true)
    api.getMCPServerTools(mcpServer.id)
      .then((data: any) => {
        const toolList = Array.isArray(data) ? data : data?.tools || []
        setTools(toolList)
        if (toolList.length > 0) {
          setSelectedTool(toolList[0].tool_name)
          setSkillName(`${mcpServer.server_name} — ${toolList[0].tool_name}`)
          setSkillDescription(toolList[0].description || '')
        }
      })
      .catch(() => setTools([]))
      .finally(() => setToolsLoading(false))
  }, [isOpen, mcpServer])

  useEffect(() => {
    if (currentStep !== 3 || agents.length > 0) return
    setAgentsLoading(true)
    api.getAgents(true)
      .then(setAgents)
      .catch(() => {})
      .finally(() => setAgentsLoading(false))
  }, [currentStep])

  const handleSelectTool = (toolName: string) => {
    setSelectedTool(toolName)
    const tool = tools.find(t => t.tool_name === toolName)
    setSkillName(`${mcpServer?.server_name} — ${toolName}`)
    setSkillDescription(tool?.description || '')
  }

  const handleCreateSkill = async () => {
    if (!selectedTool || !mcpServer) return
    setSaving(true)
    setError(null)
    try {
      const data: CustomSkillCreate = {
        name: skillName || `${mcpServer.server_name} — ${selectedTool}`,
        description: skillDescription || undefined,
        icon: '🔧',
        skill_type_variant: 'mcp_server',
        execution_mode: 'tool',
        trigger_mode: 'llm_decided',
        mcp_server_id: mcpServer.id,
        mcp_tool_name: selectedTool,
        timeout_seconds: 30,
        priority: 50,
      }
      const skill = await api.createCustomSkill(data)
      setCreatedSkill(skill)
      setCurrentStep(3)
    } catch (err: any) {
      setError(err.message || 'Failed to create custom skill')
    } finally {
      setSaving(false)
    }
  }

  const handleAssignAgents = async () => {
    if (!createdSkill || selectedAgentIds.size === 0) return
    setSaving(true)
    setError(null)
    try {
      for (const agentId of Array.from(selectedAgentIds)) {
        await api.assignCustomSkillToAgent(agentId, createdSkill.id, {})
      }
      onComplete?.()
      onClose()
    } catch (err: any) {
      setError(err.message || 'Failed to assign skill to agents')
    } finally {
      setSaving(false)
    }
  }

  const handleClose = () => {
    setCurrentStep(1)
    setTools([])
    setSelectedTool(null)
    setSkillName('')
    setSkillDescription('')
    setCreatedSkill(null)
    setAgents([])
    setSelectedAgentIds(new Set())
    setError(null)
    setSaving(false)
    onComplete?.()
    onClose()
  }

  if (!mcpServer) return null

  const stepIndicator = (
    <div className="flex items-center justify-center gap-2 mb-5">
      {[1, 2, 3].map(step => (
        <div key={step} className="flex items-center gap-2">
          <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-medium ${
            step === currentStep ? 'bg-emerald-500 text-white' :
            step < currentStep ? 'bg-emerald-500/20 text-emerald-400' :
            'bg-white/5 text-gray-500'
          }`}>
            {step < currentStep ? '✓' : step}
          </div>
          {step < 3 && <div className={`w-8 h-0.5 ${step < currentStep ? 'bg-emerald-500/40' : 'bg-white/5'}`} />}
        </div>
      ))}
    </div>
  )

  // Step 1: Success + Tools
  if (currentStep === 1) {
    const footer = (
      <div className="flex items-center justify-between w-full">
        <button onClick={handleClose} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">
          Skip &amp; Close
        </button>
        <button
          onClick={() => { setError(null); setCurrentStep(2) }}
          disabled={tools.length === 0}
          className="px-4 py-2 text-sm bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg disabled:opacity-50 transition-colors"
        >
          Next: Create Skill →
        </button>
      </div>
    )

    return (
      <Modal isOpen={isOpen} onClose={handleClose} title="MCP Server Created" footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}

          <div className="text-center">
            <div className="w-12 h-12 rounded-full bg-emerald-500/10 flex items-center justify-center mx-auto mb-3">
              <svg className="w-6 h-6 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h3 className="text-lg font-semibold text-white mb-1">{mcpServer.server_name}</h3>
            <p className="text-sm text-gray-400">Server registered successfully</p>
          </div>

          {toolsLoading ? (
            <div className="text-center py-6 text-sm text-gray-500">Discovering tools...</div>
          ) : tools.length > 0 ? (
            <div>
              <h4 className="text-sm font-medium text-gray-300 mb-2">Discovered Tools ({tools.length})</h4>
              <div className="max-h-48 overflow-y-auto space-y-1 border border-white/10 rounded-lg p-3">
                {tools.map(tool => (
                  <div key={tool.tool_name} className="flex items-start gap-3 p-2 rounded-lg bg-white/[0.02]">
                    <span className="text-emerald-400 mt-0.5 shrink-0">🔧</span>
                    <div className="min-w-0">
                      <div className="text-sm text-white font-mono">{tool.tool_name}</div>
                      {tool.description && (
                        <div className="text-xs text-gray-500 mt-0.5 line-clamp-2">{tool.description}</div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="text-center py-6 text-sm text-gray-500 border border-white/5 rounded-lg">
              No tools discovered. Connect the server first or check its configuration.
            </div>
          )}

          <div className="text-xs text-gray-500 text-center">
            Create a custom skill to make these tools available to your agents.
          </div>
        </div>
      </Modal>
    )
  }

  // Step 2: Create Custom Skill
  if (currentStep === 2) {
    const footer = (
      <div className="flex items-center justify-between w-full">
        <div className="flex items-center gap-2">
          <button onClick={() => setCurrentStep(1)} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">
            ← Back
          </button>
          <button onClick={handleClose} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">
            Skip
          </button>
        </div>
        <button
          onClick={handleCreateSkill}
          disabled={!selectedTool || saving}
          className="px-4 py-2 text-sm bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg disabled:opacity-50 transition-colors"
        >
          {saving ? 'Creating...' : 'Create & Continue →'}
        </button>
      </div>
    )

    return (
      <Modal isOpen={isOpen} onClose={handleClose} title="Create Custom Skill" footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}

          {error && (
            <div className="px-3 py-2 bg-red-400/10 border border-red-400/20 rounded-lg text-red-400 text-sm">
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm text-gray-300 mb-2">Select Tool</label>
            <div className="max-h-40 overflow-y-auto space-y-1 border border-white/10 rounded-lg p-2">
              {tools.map(tool => (
                <label
                  key={tool.tool_name}
                  className={`flex items-center gap-3 p-2.5 rounded-lg cursor-pointer transition-colors ${
                    selectedTool === tool.tool_name ? 'bg-emerald-500/10 border border-emerald-500/30' : 'hover:bg-white/5 border border-transparent'
                  }`}
                >
                  <input
                    type="radio"
                    name="tool"
                    checked={selectedTool === tool.tool_name}
                    onChange={() => handleSelectTool(tool.tool_name)}
                    className="w-4 h-4 text-emerald-500 focus:ring-emerald-500 bg-[#0a0a0f]"
                  />
                  <div className="min-w-0">
                    <div className="text-sm text-white font-mono">{tool.tool_name}</div>
                    {tool.description && (
                      <div className="text-xs text-gray-500 truncate">{tool.description}</div>
                    )}
                  </div>
                </label>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm text-gray-300 mb-1">Skill Name</label>
            <input
              type="text"
              value={skillName}
              onChange={(e) => setSkillName(e.target.value)}
              placeholder="My Custom Skill"
              className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] placeholder:text-gray-600 text-sm"
            />
          </div>

          <div>
            <label className="block text-sm text-gray-300 mb-1">Description</label>
            <input
              type="text"
              value={skillDescription}
              onChange={(e) => setSkillDescription(e.target.value)}
              placeholder="Optional description"
              className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] placeholder:text-gray-600 text-sm"
            />
          </div>

          <div className="text-xs text-gray-500">
            This creates a custom skill linked to <span className="text-emerald-400">{mcpServer.server_name}</span> → <span className="font-mono text-gray-400">{selectedTool}</span>
          </div>
        </div>
      </Modal>
    )
  }

  // Step 3: Assign to Agents
  const footer = (
    <div className="flex items-center justify-between w-full">
      <div className="flex items-center gap-2">
        <button onClick={() => { setError(null); setCurrentStep(2) }} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">
          ← Back
        </button>
        <button onClick={handleClose} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">
          Skip & Close
        </button>
      </div>
      <button
        onClick={handleAssignAgents}
        disabled={selectedAgentIds.size === 0 || saving}
        className="px-4 py-2 text-sm bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg disabled:opacity-50 transition-colors"
      >
        {saving ? 'Assigning...' : `Assign to ${selectedAgentIds.size} Agent${selectedAgentIds.size !== 1 ? 's' : ''}`}
      </button>
    </div>
  )

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Assign to Agents" footer={footer} size="lg">
      <div className="space-y-5">
        {stepIndicator}

        {error && (
          <div className="px-3 py-2 bg-red-400/10 border border-red-400/20 rounded-lg text-red-400 text-sm">
            {error}
          </div>
        )}

        {createdSkill && (
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-emerald-500/5 border border-emerald-500/20 text-sm">
            <span className="text-emerald-400">✓</span>
            <span className="text-gray-300">Skill created:</span>
            <span className="text-white font-medium">{createdSkill.name}</span>
          </div>
        )}

        {agentsLoading ? (
          <div className="text-center py-6 text-sm text-gray-500">Loading agents...</div>
        ) : agents.length > 0 ? (
          <div className="max-h-64 overflow-y-auto space-y-1 border border-white/10 rounded-lg p-3">
            {agents.map(agent => (
              <label
                key={agent.id}
                className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-white/5 cursor-pointer transition-colors"
              >
                <input
                  type="checkbox"
                  checked={selectedAgentIds.has(agent.id)}
                  onChange={(e) => {
                    const newSet = new Set(selectedAgentIds)
                    if (e.target.checked) newSet.add(agent.id)
                    else newSet.delete(agent.id)
                    setSelectedAgentIds(newSet)
                  }}
                  className="w-4 h-4 rounded border-white/20 text-emerald-500 focus:ring-emerald-500 bg-[#0a0a0f]"
                />
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-white truncate">{agent.contact_name}</div>
                  <div className="text-xs text-gray-500">{agent.model_provider}/{agent.model_name}</div>
                </div>
                {agent.is_default && (
                  <span className="text-xs text-teal-400 shrink-0">Default</span>
                )}
              </label>
            ))}
          </div>
        ) : (
          <div className="text-center py-6 text-sm text-gray-500">No active agents found.</div>
        )}

        <div className="text-xs text-gray-500 text-center">
          You can also assign skills later in Studio &gt; Agent &gt; Custom Skills.
        </div>
      </div>
    </Modal>
  )
}
