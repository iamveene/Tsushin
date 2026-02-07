'use client'

import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import { useNodesState, type OnNodesChange, type Node, type Edge } from '@xyflow/react'
import { api } from '@/lib/client'
import { calculateRadialLayout } from '../layout/radialLayout'
import type {
  AgentBuilderState, BuilderNodeData, PaletteItemData, ProfileCategoryId,
  BuilderAgentData, BuilderPersonaData, BuilderChannelData, BuilderSkillData,
  BuilderToolData, BuilderSentinelData, BuilderKnowledgeData, BuilderMemoryData,
} from '../types'
import type { UseStudioDataReturn } from './useStudioData'

export interface UseAgentBuilderReturn {
  state: AgentBuilderState; nodes: Node<BuilderNodeData>[]; edges: Edge[]
  onNodesChange: OnNodesChange<Node<BuilderNodeData>>
  attachProfile: (categoryId: ProfileCategoryId, item: PaletteItemData) => void
  detachProfile: (categoryId: ProfileCategoryId, itemId: string | number) => void
  save: () => Promise<void>; isDirty: boolean; isSaving: boolean
}

const INITIAL_STATE: AgentBuilderState = {
  agentId: null, agent: null, attachedPersonaId: null, attachedChannels: [], attachedSkills: [],
  attachedTools: [], attachedSentinelProfileId: null, attachedSentinelAssignmentId: null, attachedKnowledgeDocs: [],
  isDirty: false, isSaving: false,
}

export function useAgentBuilder(agentId: number | null, studioData: UseStudioDataReturn): UseAgentBuilderReturn {
  const [state, setState] = useState<AgentBuilderState>(INITIAL_STATE)
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<BuilderNodeData>>([])
  const [edges, setEdges] = useState<Edge[]>([])
  const savedSnapshot = useRef<string>('')

  // Load agent state from studio data
  useEffect(() => {
    if (!agentId || !studioData.agent) { setState(INITIAL_STATE); setNodes([]); setEdges([]); savedSnapshot.current = ''; return }
    const agent = studioData.agent
    const agentAssignment = studioData.sentinelAssignments.find(a => a.agent_id === agentId && !a.skill_type)
    const newState: AgentBuilderState = {
      agentId, agent: {
        name: agent.contact_name, modelProvider: agent.model_provider, modelName: agent.model_name,
        isActive: agent.is_active, isDefault: agent.is_default, personaId: agent.persona_id || null,
        enabledChannels: agent.enabled_channels || [], whatsappIntegrationId: agent.whatsapp_integration_id || null,
        telegramIntegrationId: agent.telegram_integration_id || null, memorySize: agent.memory_size || 10,
        memoryIsolationMode: agent.memory_isolation_mode || 'isolated', enableSemanticSearch: agent.enable_semantic_search || false,
      },
      attachedPersonaId: agent.persona_id || null,
      attachedChannels: agent.enabled_channels || [],
      attachedSkills: studioData.skills.filter(s => s.is_enabled).map(s => ({ skillType: s.skill_type, skillId: s.id, config: s.config || undefined })),
      attachedTools: studioData.agentTools,
      attachedSentinelProfileId: agentAssignment?.profile_id || null,
      attachedSentinelAssignmentId: agentAssignment?.id || null,
      attachedKnowledgeDocs: studioData.knowledge.map(k => k.id),
      isDirty: false, isSaving: false,
    }
    setState(newState)
    savedSnapshot.current = JSON.stringify({ personaId: newState.attachedPersonaId, channels: newState.attachedChannels, skills: newState.attachedSkills.map(s => s.skillType).sort(), tools: [...newState.attachedTools].sort(), sentinelProfileId: newState.attachedSentinelProfileId })
  }, [agentId, studioData.agent, studioData.skills, studioData.agentTools, studioData.knowledge, studioData.sentinelAssignments, setNodes])

  // Generate nodes/edges from state
  useEffect(() => {
    if (!state.agentId || !state.agent) return
    const agentNode: Node<BuilderNodeData> = {
      id: `agent-${state.agentId}`, type: 'builder-agent', position: { x: 0, y: 0 }, draggable: false,
      data: { type: 'builder-agent', agentId: state.agentId, name: state.agent.name, modelProvider: state.agent.modelProvider, modelName: state.agent.modelName, isActive: state.agent.isActive, isDefault: state.agent.isDefault, enabledChannels: state.attachedChannels, skillsCount: state.attachedSkills.length, personaName: state.attachedPersonaId ? studioData.personas.find(p => p.id === state.attachedPersonaId)?.name : undefined } as BuilderAgentData,
    }
    const attached: Node<BuilderNodeData>[] = []

    if (state.attachedPersonaId) {
      const persona = studioData.personas.find(p => p.id === state.attachedPersonaId)
      if (persona) attached.push({ id: `persona-${persona.id}`, type: 'builder-persona', position: { x: 0, y: 0 }, data: { type: 'builder-persona', personaId: persona.id, name: persona.name, role: persona.role_description, personalityTraits: persona.personality_traits, isActive: persona.is_active } as BuilderPersonaData })
    }
    for (const ch of state.attachedChannels) {
      attached.push({ id: `channel-${ch}`, type: 'builder-channel', position: { x: 0, y: 0 }, data: { type: 'builder-channel', channelType: ch as BuilderChannelData['channelType'], label: ch.charAt(0).toUpperCase() + ch.slice(1) } as BuilderChannelData })
    }
    for (const skill of state.attachedSkills) {
      const si = studioData.skills.find(s => s.skill_type === skill.skillType)
      attached.push({ id: `skill-${skill.skillType}`, type: 'builder-skill', position: { x: 0, y: 0 }, data: { type: 'builder-skill', skillId: skill.skillId, skillType: skill.skillType, skillName: si?.skill_name || skill.skillType, category: si?.category, providerName: si?.provider_name || undefined, isEnabled: true } as BuilderSkillData })
    }
    for (const toolId of state.attachedTools) {
      const tool = studioData.tools.find(t => t.id === toolId)
      if (tool) attached.push({ id: `tool-${toolId}`, type: 'builder-tool', position: { x: 0, y: 0 }, data: { type: 'builder-tool', toolId: tool.id, name: tool.name, toolType: tool.tool_type, isEnabled: tool.is_enabled } as BuilderToolData })
    }
    if (state.attachedSentinelProfileId) {
      const profile = studioData.sentinelProfiles.find(p => p.id === state.attachedSentinelProfileId)
      if (profile) attached.push({ id: `sentinel-${profile.id}`, type: 'builder-sentinel', position: { x: 0, y: 0 }, data: { type: 'builder-sentinel', profileId: profile.id, name: profile.name, mode: profile.detection_mode, isSystem: profile.is_system } as BuilderSentinelData })
    }
    for (const docId of state.attachedKnowledgeDocs) {
      const doc = studioData.knowledge.find(k => k.id === docId)
      if (doc) attached.push({ id: `knowledge-${docId}`, type: 'builder-knowledge', position: { x: 0, y: 0 }, data: { type: 'builder-knowledge', docId: doc.id, filename: doc.document_name, contentType: doc.document_type, fileSize: doc.file_size_bytes, status: doc.status, chunkCount: doc.num_chunks } as BuilderKnowledgeData })
    }
    if (state.agent) {
      attached.push({ id: 'memory-config', type: 'builder-memory', position: { x: 0, y: 0 }, data: { type: 'builder-memory', isolationMode: state.agent.memoryIsolationMode, memorySize: state.agent.memorySize, enableSemanticSearch: state.agent.enableSemanticSearch } as BuilderMemoryData })
    }

    const layout = calculateRadialLayout(agentNode, attached)
    setNodes(layout.nodes); setEdges(layout.edges)
  }, [state.agentId, state.agent, state.attachedPersonaId, state.attachedChannels, state.attachedSkills, state.attachedTools, state.attachedSentinelProfileId, state.attachedKnowledgeDocs, studioData.personas, studioData.skills, studioData.tools, studioData.sentinelProfiles, studioData.knowledge, setNodes])

  const isDirty = useMemo(() => {
    if (!state.agentId || !savedSnapshot.current) return false
    return JSON.stringify({ personaId: state.attachedPersonaId, channels: state.attachedChannels, skills: state.attachedSkills.map(s => s.skillType).sort(), tools: [...state.attachedTools].sort(), sentinelProfileId: state.attachedSentinelProfileId }) !== savedSnapshot.current
  }, [state])

  const attachProfile = useCallback((categoryId: ProfileCategoryId, item: PaletteItemData) => {
    setState(prev => {
      const next = { ...prev, isDirty: true }
      switch (categoryId) {
        case 'persona': next.attachedPersonaId = item.id as number; break
        case 'channels': if (!next.attachedChannels.includes(item.id as string)) next.attachedChannels = [...next.attachedChannels, item.id as string]; break
        case 'skills': { const st = item.id as string; if (!next.attachedSkills.some(s => s.skillType === st)) next.attachedSkills = [...next.attachedSkills, { skillType: st, skillId: (item.metadata.skillId as number) || 0 }]; break }
        case 'tools': { const tid = item.id as number; if (!next.attachedTools.includes(tid)) next.attachedTools = [...next.attachedTools, tid]; break }
        case 'security': next.attachedSentinelProfileId = item.id as number; break
        case 'knowledge': { const did = item.id as number; if (!next.attachedKnowledgeDocs.includes(did)) next.attachedKnowledgeDocs = [...next.attachedKnowledgeDocs, did]; break }
      }
      return next
    })
  }, [])

  const detachProfile = useCallback((categoryId: ProfileCategoryId, itemId: string | number) => {
    setState(prev => {
      const next = { ...prev, isDirty: true }
      switch (categoryId) {
        case 'persona': next.attachedPersonaId = null; break
        case 'channels': next.attachedChannels = next.attachedChannels.filter(ch => ch !== itemId); break
        case 'skills': next.attachedSkills = next.attachedSkills.filter(s => s.skillType !== itemId); break
        case 'tools': next.attachedTools = next.attachedTools.filter(id => id !== itemId); break
        case 'security': next.attachedSentinelProfileId = null; next.attachedSentinelAssignmentId = null; break
        case 'knowledge': next.attachedKnowledgeDocs = next.attachedKnowledgeDocs.filter(id => id !== itemId); break
      }
      return next
    })
  }, [])

  const save = useCallback(async () => {
    if (!state.agentId || !state.agent) throw new Error('No agent selected')
    setState(prev => ({ ...prev, isSaving: true }))
    try {
      await api.updateAgent(state.agentId, { model_provider: state.agent.modelProvider, model_name: state.agent.modelName, is_active: state.agent.isActive })
      for (const skill of studioData.skills) {
        const isAttached = state.attachedSkills.some(s => s.skillType === skill.skill_type)
        if (isAttached !== skill.is_enabled) await api.updateAgentSkill(state.agentId, skill.skill_type, { is_enabled: isAttached })
      }
      if (state.attachedSentinelProfileId) {
        if (state.attachedSentinelAssignmentId) {
          const cur = studioData.sentinelAssignments.find(a => a.id === state.attachedSentinelAssignmentId)
          if (cur && cur.profile_id !== state.attachedSentinelProfileId) { await api.removeSentinelProfileAssignment(state.attachedSentinelAssignmentId); await api.assignSentinelProfile({ profile_id: state.attachedSentinelProfileId, agent_id: state.agentId }) }
        } else { await api.assignSentinelProfile({ profile_id: state.attachedSentinelProfileId, agent_id: state.agentId }) }
      } else if (state.attachedSentinelAssignmentId) { await api.removeSentinelProfileAssignment(state.attachedSentinelAssignmentId) }
      savedSnapshot.current = JSON.stringify({ personaId: state.attachedPersonaId, channels: state.attachedChannels, skills: state.attachedSkills.map(s => s.skillType).sort(), tools: [...state.attachedTools].sort(), sentinelProfileId: state.attachedSentinelProfileId })
      setState(prev => ({ ...prev, isDirty: false, isSaving: false }))
    } catch (err) { setState(prev => ({ ...prev, isSaving: false })); throw err }
  }, [state, studioData.skills, studioData.sentinelAssignments])

  return { state, nodes, edges, onNodesChange, attachProfile, detachProfile, save, isDirty, isSaving: state.isSaving }
}
