'use client'

/**
 * useGraphData - Custom hook for fetching and transforming graph data
 * Phase 3: Agents View Implementation
 * Phase 4: Projects View Implementation
 * Phase 6: Performance optimization with batch endpoints
 */

import { useState, useEffect, useCallback } from 'react'
import {
  api,
  Agent,
  Project,
  ProjectAgentAccess,
  UserContactMappingResponse,
  GraphPreviewResponse,
  AgentGraphPreviewItem,
  WhatsAppChannelInfo,
  TelegramChannelInfo,
  SentinelHierarchy,
} from '@/lib/client'
import { GraphNode, GraphEdge, ChannelStatus, GraphViewType, UserRole, SecurityDetectionMode } from '../types'


export interface UseGraphDataOptions {
  viewType?: GraphViewType
  showInactiveAgents?: boolean
  showArchivedProjects?: boolean
  showInactiveUsers?: boolean
}

export interface UseGraphDataReturn {
  nodes: GraphNode[]
  edges: GraphEdge[]
  loading: boolean
  error: string | null
  refetch: () => Promise<void>
}

/**
 * Transform batch API data into graph nodes and edges for Agents view
 * Phase 6: Uses optimized batch endpoint instead of N+1 queries
 */
function transformBatchToAgentsGraphData(
  data: GraphPreviewResponse,
  showInactiveAgents: boolean
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const nodes: GraphNode[] = []
  const edges: GraphEdge[] = []
  const channelNodeIds = new Set<string>()

  // Filter agents based on showInactiveAgents toggle
  const filteredAgents = showInactiveAgents
    ? data.agents
    : data.agents.filter(a => a.is_active)

  // Create agent nodes with all badge data from batch response
  filteredAgents.forEach(agent => {
    nodes.push({
      id: `agent-${agent.id}`,
      type: 'agent',
      position: { x: 0, y: 0 }, // Will be set by layout
      data: {
        type: 'agent',
        id: agent.id,
        name: agent.contact_name,
        isActive: agent.is_active,
        modelProvider: agent.model_provider,
        modelName: agent.model_name,
        memoryIsolationMode: agent.memory_isolation_mode as 'isolated' | 'shared' | 'channel_isolated',
        skillsCount: agent.skills_count,
        hasKnowledgeBase: agent.knowledge_doc_count > 0,
        hasSentinelProtection: agent.sentinel_enabled,
        enabledChannels: agent.enabled_channels,
        isDefault: agent.is_default,
        // Phase 6: Store knowledge counts for expand preview
        knowledgeDocCount: agent.knowledge_doc_count,
        knowledgeChunkCount: agent.knowledge_chunk_count,
      },
    })
  })

  // Track which instances are used by agents
  const usedWhatsAppInstances = new Set<number>()
  const usedTelegramInstances = new Set<number>()

  // Always show Playground channel node (always available for all agents)
  // Phase 6: Changed to always show Playground
  nodes.push({
    id: 'channel-playground',
    type: 'channel',
    position: { x: 0, y: 0 },
    data: {
      type: 'channel',
      channelType: 'playground',
      label: 'Playground',
      status: 'running' as ChannelStatus, // Always available
    },
  })
  channelNodeIds.add('channel-playground')

  // Create edges for channel connections
  // Phase 7: Edges now flow from Channel (source) → Agent (target) for hierarchical layout
  // This ensures: Channels (left) → Agents (center) → Skills/KB (right when expanded)
  filteredAgents.forEach(agent => {
    const agentId = `agent-${agent.id}`
    const enabledChannels = agent.enabled_channels || []

    // Playground channel - connect all active agents (dotted line for potential, solid for enabled)
    if (agent.is_active) {
      const isPlaygroundEnabled = enabledChannels.includes('playground')
      edges.push({
        id: `e-playground-${agentId}`,
        source: 'channel-playground',  // Channel is source (left)
        target: agentId,               // Agent is target (right)
        style: isPlaygroundEnabled ? undefined : { strokeDasharray: '5,5', opacity: 0.4 },
        animated: isPlaygroundEnabled,
      })
    }

    // WhatsApp channel
    if (enabledChannels.includes('whatsapp') && agent.whatsapp_integration_id) {
      usedWhatsAppInstances.add(agent.whatsapp_integration_id)
      edges.push({
        id: `e-whatsapp-${agent.whatsapp_integration_id}-${agentId}`,
        source: `channel-whatsapp-${agent.whatsapp_integration_id}`,  // Channel is source
        target: agentId,                                              // Agent is target
        animated: true,
      })
    }

    // Telegram channel
    if (enabledChannels.includes('telegram') && agent.telegram_integration_id) {
      usedTelegramInstances.add(agent.telegram_integration_id)
      edges.push({
        id: `e-telegram-${agent.telegram_integration_id}-${agentId}`,
        source: `channel-telegram-${agent.telegram_integration_id}`,  // Channel is source
        target: agentId,                                               // Agent is target
        animated: true,
      })
    }
  })

  // Create WhatsApp channel nodes (for all instances in tenant, not just used ones)
  // Phase 6: Show all available channels
  data.channels.whatsapp
    .forEach((instance: WhatsAppChannelInfo) => {
      const nodeId = `channel-whatsapp-${instance.id}`
      if (!channelNodeIds.has(nodeId)) {
        // Map status to ChannelStatus
        let status: ChannelStatus = 'stopped'
        if (instance.status === 'running') status = 'running'
        else if (instance.status === 'error') status = 'error'
        else if (instance.status === 'stopped') status = 'stopped'

        nodes.push({
          id: nodeId,
          type: 'channel',
          position: { x: 0, y: 0 },
          data: {
            type: 'channel',
            channelType: 'whatsapp',
            label: 'WhatsApp',
            instanceId: instance.id,
            phoneNumber: instance.phone_number,
            status,
            healthStatus: instance.health_status,
          },
        })
        channelNodeIds.add(nodeId)
      }
    })

  // Create Telegram channel nodes (for all instances in tenant)
  data.channels.telegram.forEach((instance: TelegramChannelInfo) => {
    const nodeId = `channel-telegram-${instance.id}`
    if (!channelNodeIds.has(nodeId)) {
      // Map status to ChannelStatus
      let status: ChannelStatus = 'inactive'
      if (instance.status === 'active') status = 'active'
      else if (instance.status === 'error') status = 'error'

      nodes.push({
        id: nodeId,
        type: 'channel',
        position: { x: 0, y: 0 },
        data: {
          type: 'channel',
          channelType: 'telegram',
          label: 'Telegram',
          instanceId: instance.id,
          botUsername: instance.bot_username,
          status,
          healthStatus: instance.health_status,
        },
      })
      channelNodeIds.add(nodeId)
    }
  })

  return { nodes, edges }
}

/**
 * Transform API data into graph nodes and edges for Projects view
 */
function transformToProjectsGraphData(
  projects: Project[],
  projectAgentAccess: Map<number, ProjectAgentAccess[]>,
  projectDocCounts: Map<number, number>,
  agents: Agent[],
  showArchivedProjects: boolean
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const nodes: GraphNode[] = []
  const edges: GraphEdge[] = []
  const agentNodeIds = new Set<string>()

  // Filter projects based on showArchivedProjects toggle
  const filteredProjects = showArchivedProjects
    ? projects
    : projects.filter(p => !p.is_archived)

  // Create project nodes
  filteredProjects.forEach(project => {
    const docCount = projectDocCounts.get(project.id) || 0
    const agentAccess = projectAgentAccess.get(project.id) || []

    nodes.push({
      id: `project-${project.id}`,
      type: 'project',
      position: { x: 0, y: 0 }, // Will be set by layout
      data: {
        type: 'project',
        id: project.id,
        name: project.name,
        icon: project.icon,
        color: project.color,
        isArchived: project.is_archived,
        hasKnowledgeBase: docCount > 0,
        documentCount: docCount,
        agentAccessCount: agentAccess.length,
      },
    })

    // Create edges from project to each agent with access
    agentAccess.forEach(access => {
      const agentNodeId = `agent-${access.agent_id}`

      // Track agent nodes we need to create
      agentNodeIds.add(agentNodeId)

      edges.push({
        id: `e-project-${project.id}-agent-${access.agent_id}`,
        source: `project-${project.id}`,
        target: agentNodeId,
      })
    })
  })

  // Create agent nodes for all agents that have access to any project
  agents.forEach(agent => {
    const agentNodeId = `agent-${agent.id}`
    if (agentNodeIds.has(agentNodeId)) {
      nodes.push({
        id: agentNodeId,
        type: 'agent',
        position: { x: 0, y: 0 },
        data: {
          type: 'agent',
          id: agent.id,
          name: agent.contact_name,
          isActive: agent.is_active,
          modelProvider: agent.model_provider,
          modelName: agent.model_name,
          // Simplified data for projects view - no need for all badges
          skillsCount: agent.skills_count || 0,
          isDefault: agent.is_default,
        },
      })
    }
  })

  return { nodes, edges }
}

/**
 * Transform API data into graph nodes and edges for Users view
 */
interface TeamMember {
  id: number
  email: string
  full_name: string | null
  role: string
  role_display_name: string
  is_active: boolean
  avatar_url: string | null
  last_login_at: string | null
}

function transformToUsersGraphData(
  teamMembers: TeamMember[],
  contactMappings: UserContactMappingResponse[],
  defaultAgent: Agent | null,
  showInactiveUsers: boolean
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const nodes: GraphNode[] = []
  const edges: GraphEdge[] = []

  // Build contact mapping lookup by user_id
  const contactMappingByUserId = new Map<number, UserContactMappingResponse>()
  contactMappings.forEach(mapping => {
    contactMappingByUserId.set(mapping.user_id, mapping)
  })

  // Filter users based on showInactiveUsers toggle
  const filteredUsers = showInactiveUsers
    ? teamMembers
    : teamMembers.filter(u => u.is_active)

  // Create user nodes
  filteredUsers.forEach(user => {
    const mapping = contactMappingByUserId.get(user.id)

    nodes.push({
      id: `user-${user.id}`,
      type: 'user',
      position: { x: 0, y: 0 }, // Will be set by layout
      data: {
        type: 'user',
        id: user.id,
        name: user.full_name || user.email.split('@')[0],
        email: user.email,
        role: user.role as UserRole,
        roleDisplayName: user.role_display_name,
        isActive: user.is_active,
        avatarUrl: user.avatar_url,
        lastLoginAt: user.last_login_at,
        linkedContactId: mapping?.contact_id || null,
        linkedContactName: mapping?.contact_name || null,
      },
    })

    // Create edge to default agent (if exists and user is active)
    if (defaultAgent && user.is_active) {
      edges.push({
        id: `e-user-${user.id}-default-agent-${defaultAgent.id}`,
        source: `user-${user.id}`,
        target: `agent-${defaultAgent.id}`,
      })
    }
  })

  // Create default agent node (if exists and any edges point to it)
  if (defaultAgent && edges.some(e => e.target === `agent-${defaultAgent.id}`)) {
    nodes.push({
      id: `agent-${defaultAgent.id}`,
      type: 'agent',
      position: { x: 0, y: 0 },
      data: {
        type: 'agent',
        id: defaultAgent.id,
        name: defaultAgent.contact_name,
        isActive: defaultAgent.is_active,
        modelProvider: defaultAgent.model_provider,
        modelName: defaultAgent.model_name,
        skillsCount: defaultAgent.skills_count || 0,
        isDefault: true,
      },
    })
  }

  return { nodes, edges }
}

/**
 * Fetch users view data
 */
async function fetchUsersViewData(showInactiveUsers: boolean): Promise<{ nodes: GraphNode[]; edges: GraphEdge[] }> {
  // Fetch team members and agents in parallel
  // Note: Backend limits page_size to 100. For large teams, pagination would be needed.
  const [teamResponse, agents, contactMappings] = await Promise.all([
    api.getTeamMembers({ page_size: 100 }), // Get team members (max 100 per request)
    api.getAgents(false), // Get all agents to find default
    api.getAllUserContactMappings().catch(() => [] as UserContactMappingResponse[]), // Graceful fallback
  ])

  // Find default agent
  const defaultAgent = agents.find(a => a.is_default) || null

  // Transform data into graph format
  return transformToUsersGraphData(
    teamResponse.members,
    contactMappings,
    defaultAgent,
    showInactiveUsers
  )
}

/**
 * Fetch agents view data - Phase 6: Optimized with batch endpoint
 * Single API call instead of 3 + 2N calls
 */
async function fetchAgentsViewData(showInactiveAgents: boolean): Promise<{ nodes: GraphNode[]; edges: GraphEdge[] }> {
  // Phase 6: Single batch API call for all data
  const data = await api.getAgentsGraphPreview()

  // Transform batch data into graph format
  return transformBatchToAgentsGraphData(data, showInactiveAgents)
}

/**
 * Fetch projects view data
 */
async function fetchProjectsViewData(showArchivedProjects: boolean): Promise<{ nodes: GraphNode[]; edges: GraphEdge[] }> {
  // Fetch projects and agents in parallel
  const [projects, agents] = await Promise.all([
    api.getProjects(showArchivedProjects), // Include archived if toggle is on
    api.getAgents(false), // Get all agents for reference
  ])

  // Fetch agent access and document counts for each project in parallel
  const [agentAccessResults, docCountResults] = await Promise.all([
    // Agent access for each project
    Promise.all(
      projects.map(project =>
        api.getProjectAgents(project.id).catch(() => [] as ProjectAgentAccess[])
      )
    ),
    // Document counts for each project
    Promise.all(
      projects.map(project =>
        api.getProjectDocuments(project.id)
          .then(docs => docs.length)
          .catch(() => 0)
      )
    ),
  ])

  // Build maps for quick lookup
  const projectAgentAccess = new Map<number, ProjectAgentAccess[]>()
  const projectDocCounts = new Map<number, number>()

  projects.forEach((project, index) => {
    projectAgentAccess.set(project.id, agentAccessResults[index])
    projectDocCounts.set(project.id, docCountResults[index])
  })

  // Transform data into graph format
  return transformToProjectsGraphData(
    projects,
    projectAgentAccess,
    projectDocCounts,
    agents,
    showArchivedProjects
  )
}

/**
 * Transform hierarchy API data into graph nodes and edges for Security view
 * Phase F (v1.6.0): Security hierarchy visualization
 */
function transformToSecurityGraphData(
  hierarchy: SentinelHierarchy
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const nodes: GraphNode[] = []
  const edges: GraphEdge[] = []

  if (!hierarchy.tenant) return { nodes, edges }

  const tenant = hierarchy.tenant

  // Determine tenant-level effective config from the first agent's data or defaults
  const tenantEffective = tenant.agents.length > 0
    ? tenant.agents[0].effective_profile
    : null
  const tenantDetectionMode = (tenantEffective?.detection_mode || 'block') as SecurityDetectionMode
  const tenantAggressiveness = tenantEffective?.aggressiveness_level ?? 1
  const tenantIsEnabled = tenantEffective?.is_enabled ?? true

  // 1. Tenant security node (root)
  const tenantNodeId = `tenant-security-${tenant.id}`
  nodes.push({
    id: tenantNodeId,
    type: 'tenant-security',
    position: { x: 0, y: 0 },
    data: {
      type: 'tenant-security',
      tenantId: tenant.id,
      tenantName: tenant.name,
      profile: tenant.profile ? { id: tenant.profile.id, name: tenant.profile.name, slug: tenant.profile.slug } : null,
      effectiveProfile: tenantEffective ? {
        id: tenantEffective.id,
        name: tenantEffective.name,
        slug: tenantEffective.slug,
        source: (tenantEffective.source || 'system') as 'skill' | 'agent' | 'tenant' | 'system',
      } : null,
      detectionMode: tenantDetectionMode,
      aggressivenessLevel: tenantAggressiveness,
      isEnabled: tenantIsEnabled,
    },
  })

  // 2. Agent security nodes
  tenant.agents.forEach(agent => {
    const agentNodeId = `agent-security-${agent.id}`
    const agentDetectionMode = (agent.effective_profile?.detection_mode || 'block') as SecurityDetectionMode
    const agentAggressiveness = agent.effective_profile?.aggressiveness_level ?? 1
    const agentIsEnabled = agent.effective_profile?.is_enabled ?? true

    nodes.push({
      id: agentNodeId,
      type: 'agent-security',
      position: { x: 0, y: 0 },
      data: {
        type: 'agent-security',
        id: agent.id,
        name: agent.name,
        isActive: agent.is_active,
        profile: agent.profile ? { id: agent.profile.id, name: agent.profile.name, slug: agent.profile.slug } : null,
        effectiveProfile: agent.effective_profile ? {
          id: agent.effective_profile.id,
          name: agent.effective_profile.name,
          slug: agent.effective_profile.slug,
          source: (agent.effective_profile.source || 'system') as 'skill' | 'agent' | 'tenant' | 'system',
        } : null,
        detectionMode: agentDetectionMode,
        aggressivenessLevel: agentAggressiveness,
        isEnabled: agentIsEnabled,
      },
    })

    // Edge: tenant -> agent
    const hasExplicitAgentProfile = agent.profile !== null
    edges.push({
      id: `e-${tenantNodeId}-${agentNodeId}`,
      source: tenantNodeId,
      target: agentNodeId,
      style: hasExplicitAgentProfile
        ? { stroke: '#3C5AFE' }  // Blue solid for explicit assignment
        : { strokeDasharray: '5,5', opacity: 0.5 },  // Dashed for inherited
    })

    // 3. Skill security nodes (only for skills with explicit assignments)
    agent.skills.forEach(skill => {
      const skillNodeId = `skill-security-${agent.id}-${skill.skill_type}`
      const skillDetectionMode = (skill.effective_profile?.detection_mode || agentDetectionMode) as SecurityDetectionMode

      nodes.push({
        id: skillNodeId,
        type: 'skill-security',
        position: { x: 0, y: 0 },
        data: {
          type: 'skill-security',
          skillType: skill.skill_type,
          skillName: skill.name,
          isEnabled: skill.is_enabled,
          parentAgentId: agent.id,
          profile: skill.profile ? { id: skill.profile.id, name: skill.profile.name, slug: skill.profile.slug } : null,
          effectiveProfile: skill.effective_profile ? {
            id: skill.effective_profile.id,
            name: skill.effective_profile.name,
            slug: skill.effective_profile.slug,
            source: (skill.effective_profile.source || 'agent') as 'skill' | 'agent' | 'tenant' | 'system',
          } : null,
          detectionMode: skillDetectionMode,
        },
      })

      // Edge: agent -> skill
      const hasExplicitSkillProfile = skill.profile !== null
      edges.push({
        id: `e-${agentNodeId}-${skillNodeId}`,
        source: agentNodeId,
        target: skillNodeId,
        style: hasExplicitSkillProfile
          ? { stroke: '#A855F7' }  // Purple solid for explicit skill assignment
          : { strokeDasharray: '5,5', opacity: 0.5 },
      })
    })
  })

  return { nodes, edges }
}

/**
 * Fetch security view data — calls hierarchy endpoint
 * Phase F (v1.6.0): Security hierarchy visualization
 */
async function fetchSecurityViewData(): Promise<{ nodes: GraphNode[]; edges: GraphEdge[] }> {
  const hierarchy = await api.getSentinelHierarchy()
  return transformToSecurityGraphData(hierarchy)
}

/**
 * Custom hook for fetching and transforming graph data
 */
export function useGraphData(options: UseGraphDataOptions = {}): UseGraphDataReturn {
  const {
    viewType = 'agents',
    showInactiveAgents = false,
    showArchivedProjects = false,
    showInactiveUsers = false,
  } = options

  const [nodes, setNodes] = useState<GraphNode[]>([])
  const [edges, setEdges] = useState<GraphEdge[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)

    try {
      let result: { nodes: GraphNode[]; edges: GraphEdge[] }

      switch (viewType) {
        case 'projects':
          result = await fetchProjectsViewData(showArchivedProjects)
          break
        case 'users':
          result = await fetchUsersViewData(showInactiveUsers)
          break
        case 'security':
          result = await fetchSecurityViewData()
          break
        case 'agents':
        default:
          result = await fetchAgentsViewData(showInactiveAgents)
          break
      }

      setNodes(result.nodes)
      setEdges(result.edges)
    } catch (err) {
      console.error('[useGraphData] Error fetching data:', err)
      setError(err instanceof Error ? err.message : 'Failed to load graph data')
    } finally {
      setLoading(false)
    }
  }, [viewType, showInactiveAgents, showArchivedProjects, showInactiveUsers])

  // Fetch data on mount and when options change
  useEffect(() => {
    fetchData()
  }, [fetchData])

  return {
    nodes,
    edges,
    loading,
    error,
    refetch: fetchData,
  }
}

export default useGraphData
