'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from '@/lib/client'
import type { Agent, Persona, SandboxedTool, SentinelProfile, SkillExpandInfo, AgentKnowledge, SentinelProfileAssignment, AgentSandboxedTool } from '@/lib/client'

export interface UseStudioDataReturn {
  agents: Agent[]; personas: Persona[]; tools: SandboxedTool[]; sentinelProfiles: SentinelProfile[]
  agent: Agent | null; skills: SkillExpandInfo[]; knowledge: AgentKnowledge[]; sentinelAssignments: SentinelProfileAssignment[]; agentTools: number[]
  agentToolMappings: AgentSandboxedTool[]
  loading: boolean; agentLoading: boolean; error: string | null; refetch: () => void
}

export function useStudioData(agentId: number | null): UseStudioDataReturn {
  const [agents, setAgents] = useState<Agent[]>([])
  const [personas, setPersonas] = useState<Persona[]>([])
  const [tools, setTools] = useState<SandboxedTool[]>([])
  const [sentinelProfiles, setSentinelProfiles] = useState<SentinelProfile[]>([])
  const [agent, setAgent] = useState<Agent | null>(null)
  const [skills, setSkills] = useState<SkillExpandInfo[]>([])
  const [knowledge, setKnowledge] = useState<AgentKnowledge[]>([])
  const [sentinelAssignments, setSentinelAssignments] = useState<SentinelProfileAssignment[]>([])
  const [agentTools, setAgentTools] = useState<number[]>([])
  const [agentToolMappings, setAgentToolMappings] = useState<AgentSandboxedTool[]>([])
  const [loading, setLoading] = useState(true)
  const [agentLoading, setAgentLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fetchVersion = useRef(0)

  const loadGlobalData = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const [a, p, t, sp] = await Promise.all([api.getAgents(), api.getPersonas(), api.getSandboxedTools(), api.getSentinelProfiles(true)])
      setAgents(a); setPersonas(p); setTools(t); setSentinelProfiles(sp)
    } catch (err) { setError(err instanceof Error ? err.message : 'Failed to load studio data') }
    finally { setLoading(false) }
  }, [])

  // Phase I: Use batch builder-data endpoint (replaces 4 parallel calls with 1)
  const loadAgentData = useCallback(async (id: number) => {
    const version = ++fetchVersion.current
    setAgentLoading(true); setError(null)
    try {
      const selectedAgent = agents.find(a => a.id === id) || null
      setAgent(selectedAgent)
      const builderData = await api.getAgentBuilderData(id)
      if (version !== fetchVersion.current) return
      setSkills(builderData.skills)
      setKnowledge(builderData.knowledge)
      setSentinelAssignments(builderData.sentinel_assignments)
      setAgentToolMappings(builderData.tool_mappings)
      setAgentTools(builderData.tool_mappings.filter(t => t.is_enabled).map(t => t.sandboxed_tool_id))
    } catch (err) { if (version !== fetchVersion.current) return; setError(err instanceof Error ? err.message : 'Failed to load agent data') }
    finally { if (version === fetchVersion.current) setAgentLoading(false) }
  }, [agents])

  useEffect(() => { loadGlobalData() }, [loadGlobalData])

  useEffect(() => {
    if (agentId && agents.length > 0) { loadAgentData(agentId) }
    else { setAgent(null); setSkills([]); setKnowledge([]); setSentinelAssignments([]); setAgentTools([]); setAgentToolMappings([]) }
  }, [agentId, agents, loadAgentData])

  const refetch = useCallback(() => {
    loadGlobalData()
    if (agentId) setTimeout(() => { if (agentId) loadAgentData(agentId) }, 200)
  }, [loadGlobalData, loadAgentData, agentId])

  return { agents, personas, tools, sentinelProfiles, agent, skills, knowledge, sentinelAssignments, agentTools, agentToolMappings, loading: loading || agentLoading, agentLoading, error, refetch }
}
