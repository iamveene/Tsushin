'use client'

import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import { useNodesState, type OnNodesChange, type Node, type Edge, type NodeChange } from '@xyflow/react'
import { api } from '@/lib/client'
import type { BuilderSaveRequest } from '@/lib/client'
import { calculateGroupedRadialLayout, type GroupedCategoryInput } from '../layout/radialLayout'
import { calculateDagreBuilderLayout } from '../layout/dagreBuilderLayout'
import type {
  AgentBuilderState, BuilderNodeData, PaletteItemData, ProfileCategoryId,
  BuilderAgentData, BuilderPersonaData, BuilderChannelData, BuilderSkillData,
  BuilderSkillProviderData, BuilderToolData, BuilderSentinelData, BuilderKnowledgeData,
  BuilderMemoryData, BuilderGroupData,
} from '../types'
import { GROUPED_CATEGORIES, CATEGORY_DISPLAY } from '../types'
import type { UseStudioDataReturn } from './useStudioData'

export interface UseAgentBuilderReturn {
  state: AgentBuilderState; nodes: Node<BuilderNodeData>[]; edges: Edge[]
  onNodesChange: OnNodesChange<Node<BuilderNodeData>>
  attachProfile: (categoryId: ProfileCategoryId, item: PaletteItemData) => void
  detachProfile: (categoryId: ProfileCategoryId, itemId: string | number) => void
  updateNodeConfig: (nodeType: string, nodeId: string, config: Record<string, unknown>) => void
  updateAvatar: (slug: string | null) => void
  save: () => Promise<void>; isDirty: boolean; isSaving: boolean
  expandedCategories: Set<ProfileCategoryId>
  toggleCategoryExpand: (categoryId: ProfileCategoryId) => void
  expandAll: () => void
  collapseAll: () => void
  resetLayout: () => void
}

const INITIAL_STATE: AgentBuilderState = {
  agentId: null, agent: null, attachedPersonaId: null, attachedChannels: [], attachedSkills: [],
  attachedTools: [], toolEnabledOverrides: {}, attachedSentinelProfileId: null, attachedSentinelAssignmentId: null, attachedKnowledgeDocs: [],
  isDirty: false, isSaving: false,
}

export function useAgentBuilder(agentId: number | null, studioData: UseStudioDataReturn): UseAgentBuilderReturn {
  const [state, setState] = useState<AgentBuilderState>(INITIAL_STATE)
  const [nodes, setNodes, rawOnNodesChange] = useNodesState<Node<BuilderNodeData>>([])
  const [edges, setEdges] = useState<Edge[]>([])
  const savedSnapshot = useRef<string>('')
  const [expandedCategories, setExpandedCategories] = useState<Set<ProfileCategoryId>>(new Set())
  const [expandedSkills, setExpandedSkills] = useState<Set<string>>(new Set())
  const [expandedKnowledge, setExpandedKnowledge] = useState<Set<number>>(new Set())

  // Phase A: Track user-dragged positions so layout doesn't overwrite them
  const userPositions = useRef<Map<string, { x: number; y: number }>>(new Map())
  const structuralFingerprint = useRef<string>('')
  const layoutVersion = useRef(0)

  // Wrapped onNodesChange: intercept drag-end to store user positions
  const onNodesChange: OnNodesChange<Node<BuilderNodeData>> = useCallback((changes: NodeChange<Node<BuilderNodeData>>[]) => {
    for (const change of changes) {
      if (change.type === 'position' && change.position && !change.dragging) {
        // Drag ended — store final position
        userPositions.current.set(change.id, { ...change.position })
      }
    }
    rawOnNodesChange(changes)
  }, [rawOnNodesChange])

  const toggleCategoryExpand = useCallback((categoryId: ProfileCategoryId) => {
    // Clear user positions for children of this group when toggling
    setExpandedCategories(prev => {
      const next = new Set(prev)
      const wasExpanded = next.has(categoryId)
      if (wasExpanded) {
        next.delete(categoryId)
      } else {
        next.add(categoryId)
      }
      // Clear child positions for this category since they're appearing/disappearing
      const prefix = categoryId === 'channels' ? 'channel-'
        : categoryId === 'skills' ? 'skill-'
        : categoryId === 'tools' ? 'tool-'
        : categoryId === 'knowledge' ? 'knowledge-'
        : ''
      if (prefix) {
        for (const key of userPositions.current.keys()) {
          if (key.startsWith(prefix)) userPositions.current.delete(key)
        }
      }
      return next
    })
  }, [])

  const expandAll = useCallback(() => {
    userPositions.current.clear()
    setExpandedCategories(new Set(GROUPED_CATEGORIES as ProfileCategoryId[]))
  }, [])

  const collapseAll = useCallback(() => {
    userPositions.current.clear()
    setExpandedCategories(new Set())
    setExpandedSkills(new Set())
    setExpandedKnowledge(new Set())
  }, [])

  const toggleSkillExpand = useCallback((skillType: string) => {
    setExpandedSkills(prev => {
      const next = new Set(prev)
      if (next.has(skillType)) {
        next.delete(skillType)
      } else {
        next.add(skillType)
      }
      // Clear provider node positions
      for (const key of userPositions.current.keys()) {
        if (key.startsWith(`provider-${skillType}-`)) userPositions.current.delete(key)
      }
      return next
    })
  }, [])

  const toggleKnowledgeExpand = useCallback((docId: number) => {
    setExpandedKnowledge(prev => {
      const next = new Set(prev)
      if (next.has(docId)) next.delete(docId)
      else next.add(docId)
      return next
    })
  }, [])

  const resetLayout = useCallback(() => {
    userPositions.current.clear()
    layoutVersion.current += 1
    // Force re-layout by bumping structural fingerprint
    structuralFingerprint.current = ''
    // Trigger state update to force the effect to re-run
    setState(prev => ({ ...prev }))
  }, [])

  const updateAvatar = useCallback((slug: string | null) => {
    setState(prev => {
      if (!prev.agent) return prev
      return { ...prev, agent: { ...prev.agent, avatar: slug } }
    })
  }, [])

  // Load agent state from studio data
  useEffect(() => {
    if (!agentId || !studioData.agent) { setState(INITIAL_STATE); setNodes([]); setEdges([]); savedSnapshot.current = ''; userPositions.current.clear(); return }
    const agent = studioData.agent
    const agentAssignment = studioData.sentinelAssignments.find(a => a.agent_id === agentId && !a.skill_type)
    // Validate persona reference: clear if persona doesn't exist in available list
    const validPersonaId = agent.persona_id && studioData.personas.some(p => p.id === agent.persona_id) ? agent.persona_id : null
    const newState: AgentBuilderState = {
      agentId, agent: {
        name: agent.contact_name, modelProvider: agent.model_provider, modelName: agent.model_name,
        isActive: agent.is_active, isDefault: agent.is_default, personaId: validPersonaId,
        enabledChannels: agent.enabled_channels || [], whatsappIntegrationId: agent.whatsapp_integration_id || null,
        telegramIntegrationId: agent.telegram_integration_id || null, memorySize: agent.memory_size || 10,
        memoryIsolationMode: agent.memory_isolation_mode || 'isolated', enableSemanticSearch: agent.enable_semantic_search || false,
        avatar: agent.avatar || null,
      },
      attachedPersonaId: validPersonaId,
      attachedChannels: agent.enabled_channels || [],
      attachedSkills: studioData.skills.filter(s => s.is_enabled).map(s => ({ skillType: s.skill_type, skillId: s.id, config: s.config || undefined })),
      attachedTools: studioData.agentTools,
      toolEnabledOverrides: {},
      attachedSentinelProfileId: agentAssignment?.profile_id || null,
      attachedSentinelAssignmentId: agentAssignment?.id || null,
      attachedKnowledgeDocs: studioData.knowledge.map(k => k.id),
      isDirty: false, isSaving: false,
    }
    setState(newState)
    userPositions.current.clear()
    savedSnapshot.current = JSON.stringify({
      personaId: newState.attachedPersonaId, channels: newState.attachedChannels,
      skills: newState.attachedSkills.map(s => ({ t: s.skillType, c: s.config })).sort((a, b) => a.t.localeCompare(b.t)),
      tools: [...newState.attachedTools].sort(), sentinelProfileId: newState.attachedSentinelProfileId,
      memory: { size: newState.agent?.memorySize, mode: newState.agent?.memoryIsolationMode, semantic: newState.agent?.enableSemanticSearch },
      toolOverrides: {},
      avatar: newState.agent?.avatar || null,
    })
  }, [agentId, studioData.agent, studioData.skills, studioData.agentTools, studioData.knowledge, studioData.sentinelAssignments, setNodes])

  // Compute structural fingerprint — only changes when nodes are added/removed/expanded/collapsed
  const currentFingerprint = useMemo(() => JSON.stringify({
    agentId: state.agentId,
    channels: [...state.attachedChannels].sort(),
    skills: state.attachedSkills.map(s => s.skillType).sort(),
    tools: [...state.attachedTools].sort(),
    personaId: state.attachedPersonaId,
    sentinelId: state.attachedSentinelProfileId,
    knowledgeDocs: [...state.attachedKnowledgeDocs].sort(),
    expanded: [...expandedCategories].sort(),
    expandedSkills: [...expandedSkills].sort(),
    expandedKnowledge: [...expandedKnowledge].sort(),
    version: layoutVersion.current,
  }), [state.agentId, state.attachedChannels, state.attachedSkills, state.attachedTools,
       state.attachedPersonaId, state.attachedSentinelProfileId, state.attachedKnowledgeDocs,
       expandedCategories, expandedSkills, expandedKnowledge])

  // Generate nodes/edges from state — only re-layout when structural fingerprint changes
  useEffect(() => {
    if (!state.agentId || !state.agent) return

    // Skip re-layout if structure hasn't changed
    if (currentFingerprint === structuralFingerprint.current) return
    structuralFingerprint.current = currentFingerprint

    const agentNode: Node<BuilderNodeData> = {
      id: `agent-${state.agentId}`, type: 'builder-agent', position: { x: 0, y: 0 }, draggable: false,
      data: { type: 'builder-agent', agentId: state.agentId, name: state.agent.name, modelProvider: state.agent.modelProvider, modelName: state.agent.modelName, isActive: state.agent.isActive, isDefault: state.agent.isDefault, enabledChannels: state.attachedChannels, skillsCount: state.attachedSkills.length, personaName: state.attachedPersonaId ? studioData.personas.find(p => p.id === state.attachedPersonaId)?.name : undefined, avatar: state.agent.avatar, onAvatarChange: updateAvatar } as BuilderAgentData,
    }

    // Build child nodes by category
    const channelNodes: Node<BuilderNodeData>[] = []
    const skillNodes: Node<BuilderNodeData>[] = []
    const toolNodes: Node<BuilderNodeData>[] = []
    const knowledgeNodes: Node<BuilderNodeData>[] = []
    const directNodes: Node<BuilderNodeData>[] = []

    // Channels (grouped)
    for (const ch of state.attachedChannels) {
      channelNodes.push({ id: `channel-${ch}`, type: 'builder-channel', position: { x: 0, y: 0 }, data: { type: 'builder-channel', channelType: ch as BuilderChannelData['channelType'], label: ch.charAt(0).toUpperCase() + ch.slice(1) } as BuilderChannelData })
    }

    // Skills (grouped) — with provider expansion support
    const providerNodes: Node<BuilderNodeData>[] = []
    const providerEdges: Edge[] = []
    for (const skill of state.attachedSkills) {
      const si = studioData.skills.find(s => s.skill_type === skill.skillType)
      const hasProviders = !!(si?.provider_type)
      const isSkillExpanded = expandedSkills.has(skill.skillType)
      skillNodes.push({ id: `skill-${skill.skillType}`, type: 'builder-skill', position: { x: 0, y: 0 }, data: { type: 'builder-skill', skillId: skill.skillId, skillType: skill.skillType, skillName: si?.skill_name || skill.skillType, category: si?.category, providerName: si?.provider_name || undefined, providerType: si?.provider_type || undefined, isEnabled: true, config: skill.config, hasProviders, isExpanded: isSkillExpanded, onToggleExpand: toggleSkillExpand } as BuilderSkillData })

      // Generate provider sub-nodes when skill is expanded
      if (isSkillExpanded && si?.provider_type) {
        const providerId = `provider-${skill.skillType}-${si.provider_type}`
        providerNodes.push({
          id: providerId, type: 'builder-skill-provider', position: { x: 0, y: 0 },
          data: { type: 'builder-skill-provider', parentSkillType: skill.skillType, providerType: si.provider_type, providerName: si.provider_name || si.provider_type, isConfigured: !!si.integration_id, requiresIntegration: true, integrationId: si.integration_id || undefined } as BuilderSkillProviderData,
        })
        providerEdges.push({ id: `e-skill-${skill.skillType}-provider-${si.provider_type}`, source: `skill-${skill.skillType}`, target: providerId, type: 'smoothstep', animated: true, style: { stroke: '#2dd4bf', strokeWidth: 1, opacity: 0.5 } })
      }
    }

    // Tools (grouped)
    for (const toolId of state.attachedTools) {
      const tool = studioData.tools.find(t => t.id === toolId)
      if (tool) {
        const isEnabled = state.toolEnabledOverrides[toolId] !== undefined ? state.toolEnabledOverrides[toolId] : tool.is_enabled
        toolNodes.push({ id: `tool-${toolId}`, type: 'builder-tool', position: { x: 0, y: 0 }, data: { type: 'builder-tool', toolId: tool.id, name: tool.name, toolType: tool.tool_type, isEnabled } as BuilderToolData })
      }
    }

    // Knowledge (grouped) — with inline expand support
    for (const docId of state.attachedKnowledgeDocs) {
      const doc = studioData.knowledge.find(k => k.id === docId)
      if (doc) knowledgeNodes.push({ id: `knowledge-${docId}`, type: 'builder-knowledge', position: { x: 0, y: 0 }, data: { type: 'builder-knowledge', docId: doc.id, filename: doc.document_name, contentType: doc.document_type, fileSize: doc.file_size_bytes, status: doc.status, chunkCount: doc.num_chunks, uploadDate: doc.upload_date, isExpanded: expandedKnowledge.has(docId), onToggleExpand: toggleKnowledgeExpand } as BuilderKnowledgeData })
    }

    // Direct nodes: persona, security, memory
    if (state.attachedPersonaId) {
      const persona = studioData.personas.find(p => p.id === state.attachedPersonaId)
      if (persona) directNodes.push({ id: `persona-${persona.id}`, type: 'builder-persona', position: { x: 0, y: 0 }, data: { type: 'builder-persona', personaId: persona.id, name: persona.name, role: persona.role_description, personalityTraits: persona.personality_traits, isActive: persona.is_active } as BuilderPersonaData })
    }
    if (state.attachedSentinelProfileId) {
      const profile = studioData.sentinelProfiles.find(p => p.id === state.attachedSentinelProfileId)
      if (profile) directNodes.push({ id: `sentinel-${profile.id}`, type: 'builder-sentinel', position: { x: 0, y: 0 }, data: { type: 'builder-sentinel', profileId: profile.id, name: profile.name, mode: profile.detection_mode, isSystem: profile.is_system } as BuilderSentinelData })
    }
    if (state.agent) {
      directNodes.push({ id: 'memory-config', type: 'builder-memory', position: { x: 0, y: 0 }, data: { type: 'builder-memory', isolationMode: state.agent.memoryIsolationMode, memorySize: state.agent.memorySize, enableSemanticSearch: state.agent.enableSemanticSearch } as BuilderMemoryData })
    }

    // Build grouped categories input
    const categoryChildMap: Record<string, { category: ProfileCategoryId; childNodes: Node<BuilderNodeData>[] }> = {
      channels: { category: 'channels', childNodes: channelNodes },
      skills: { category: 'skills', childNodes: skillNodes },
      tools: { category: 'tools', childNodes: toolNodes },
      knowledge: { category: 'knowledge', childNodes: knowledgeNodes },
    }

    const groupedCategories: GroupedCategoryInput[] = []
    for (const catId of GROUPED_CATEGORIES) {
      const entry = categoryChildMap[catId]
      if (!entry || entry.childNodes.length === 0) continue

      const display = CATEGORY_DISPLAY[catId]
      const isExpanded = expandedCategories.has(catId)

      const groupNode: Node<BuilderNodeData> = {
        id: `group-${catId}`,
        type: 'builder-group',
        position: { x: 0, y: 0 },
        draggable: false,
        selectable: false,
        data: {
          type: 'builder-group',
          categoryId: catId,
          categoryLabel: display.label,
          categoryColor: display.color,
          childCount: entry.childNodes.length,
          isExpanded,
          onExpand: toggleCategoryExpand,
          onCollapse: toggleCategoryExpand,
        } as BuilderGroupData,
      }

      groupedCategories.push({
        category: catId,
        groupNode,
        childNodes: entry.childNodes,
        isExpanded,
      })
    }

    // Clean up user positions for nodes that no longer exist
    const allNodeIds = new Set<string>()
    allNodeIds.add(agentNode.id)
    for (const gc of groupedCategories) {
      allNodeIds.add(gc.groupNode.id)
      for (const cn of gc.childNodes) allNodeIds.add(cn.id)
    }
    for (const dn of directNodes) allNodeIds.add(dn.id)
    for (const pn of providerNodes) allNodeIds.add(pn.id)
    for (const key of userPositions.current.keys()) {
      if (!allNodeIds.has(key)) userPositions.current.delete(key)
    }

    // Always use tree layout (top-down) for consistent TB handle routing
    let cancelled = false

    calculateDagreBuilderLayout(agentNode, groupedCategories, directNodes, userPositions.current, providerNodes, providerEdges)
      .then(layout => {
        if (!cancelled) { setNodes(layout.nodes); setEdges(layout.edges) }
      })
      .catch(err => {
        console.error('[Agent Studio] Tree layout failed, falling back to radial:', err)
        if (!cancelled) {
          const fallback = calculateGroupedRadialLayout(agentNode, groupedCategories, directNodes)
          setNodes(fallback.nodes); setEdges(fallback.edges)
        }
      })

    return () => { cancelled = true }
  }, [currentFingerprint, state, studioData.personas, studioData.skills, studioData.tools, studioData.sentinelProfiles, studioData.knowledge, setNodes, expandedCategories, expandedSkills, expandedKnowledge, toggleCategoryExpand, toggleSkillExpand, toggleKnowledgeExpand, updateAvatar])

  const isDirty = useMemo(() => {
    if (!state.agentId || !savedSnapshot.current) return false
    return JSON.stringify({
      personaId: state.attachedPersonaId, channels: state.attachedChannels,
      skills: state.attachedSkills.map(s => ({ t: s.skillType, c: s.config })).sort((a, b) => a.t.localeCompare(b.t)),
      tools: [...state.attachedTools].sort(), sentinelProfileId: state.attachedSentinelProfileId,
      memory: { size: state.agent?.memorySize, mode: state.agent?.memoryIsolationMode, semantic: state.agent?.enableSemanticSearch },
      toolOverrides: state.toolEnabledOverrides,
      avatar: state.agent?.avatar || null,
    }) !== savedSnapshot.current
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

  const updateNodeConfig = useCallback((nodeType: string, nodeId: string, config: Record<string, unknown>) => {
    setState(prev => {
      if (!prev.agent) return prev
      const next = { ...prev }
      switch (nodeType) {
        case 'builder-memory':
          next.agent = {
            ...prev.agent,
            memorySize: config.memorySize !== undefined ? (config.memorySize as number) : prev.agent.memorySize,
            memoryIsolationMode: config.memoryIsolationMode !== undefined ? (config.memoryIsolationMode as string) : prev.agent.memoryIsolationMode,
            enableSemanticSearch: config.enableSemanticSearch !== undefined ? (config.enableSemanticSearch as boolean) : prev.agent.enableSemanticSearch,
          }
          break
        case 'builder-skill': {
          const skillType = config.skillType as string
          next.attachedSkills = prev.attachedSkills.map(s =>
            s.skillType === skillType ? { ...s, config: config.skillConfig as Record<string, unknown> } : s
          )
          break
        }
        case 'builder-tool': {
          const toolId = config.toolId as number
          const isEnabled = config.isEnabled as boolean
          next.toolEnabledOverrides = { ...prev.toolEnabledOverrides, [toolId]: isEnabled }
          break
        }
      }
      return next
    })
  }, [])

  // Phase I: Atomic save using batch builder-save endpoint (replaces 10+ sequential calls with 1)
  const save = useCallback(async () => {
    if (!state.agentId || !state.agent) throw new Error('No agent selected')
    setState(prev => ({ ...prev, isSaving: true }))
    try {
      const request: BuilderSaveRequest = {}

      // Agent core fields
      request.agent = {
        persona_id: state.attachedPersonaId ?? 0,
        enabled_channels: state.attachedChannels,
        memory_size: state.agent.memorySize,
        memory_isolation_mode: state.agent.memoryIsolationMode,
        enable_semantic_search: state.agent.enableSemanticSearch,
        avatar: state.agent.avatar,
      }

      // Skills: send full desired state
      request.skills = studioData.skills.map(skill => {
        const attached = state.attachedSkills.find(s => s.skillType === skill.skill_type)
        return {
          skill_type: skill.skill_type,
          is_enabled: !!attached,
          config: attached?.config || undefined,
        }
      })

      // Tool overrides: only changed ones
      const toolOverrides = Object.entries(state.toolEnabledOverrides)
        .map(([toolIdStr, isEnabled]) => {
          const toolId = Number(toolIdStr)
          const mapping = studioData.agentToolMappings.find(m => m.sandboxed_tool_id === toolId)
          return mapping ? { mapping_id: mapping.id, is_enabled: isEnabled as boolean } : null
        })
        .filter((o): o is { mapping_id: number; is_enabled: boolean } => o !== null)
      if (toolOverrides.length > 0) request.tool_overrides = toolOverrides

      // Sentinel
      if (state.attachedSentinelProfileId) {
        const cur = state.attachedSentinelAssignmentId
          ? studioData.sentinelAssignments.find(a => a.id === state.attachedSentinelAssignmentId)
          : null
        if (cur && cur.profile_id === state.attachedSentinelProfileId) {
          // No change
        } else {
          request.sentinel = {
            action: 'assign',
            profile_id: state.attachedSentinelProfileId,
            assignment_id: state.attachedSentinelAssignmentId || undefined,
          }
        }
      } else if (state.attachedSentinelAssignmentId) {
        request.sentinel = {
          action: 'remove',
          assignment_id: state.attachedSentinelAssignmentId,
        }
      }

      await api.saveAgentBuilderData(state.agentId, request)

      savedSnapshot.current = JSON.stringify({
        personaId: state.attachedPersonaId, channels: state.attachedChannels,
        skills: state.attachedSkills.map(s => ({ t: s.skillType, c: s.config })).sort((a, b) => a.t.localeCompare(b.t)),
        tools: [...state.attachedTools].sort(), sentinelProfileId: state.attachedSentinelProfileId,
        memory: { size: state.agent.memorySize, mode: state.agent.memoryIsolationMode, semantic: state.agent.enableSemanticSearch },
        toolOverrides: {},
        avatar: state.agent?.avatar || null,
      })
      setState(prev => ({ ...prev, isDirty: false, isSaving: false, toolEnabledOverrides: {} }))
    } catch (err) { setState(prev => ({ ...prev, isSaving: false })); throw err }
  }, [state, studioData.skills, studioData.sentinelAssignments, studioData.agentToolMappings])

  return { state, nodes, edges, onNodesChange, attachProfile, detachProfile, updateNodeConfig, updateAvatar, save, isDirty, isSaving: state.isSaving, expandedCategories, toggleCategoryExpand, expandAll, collapseAll, resetLayout }
}
