/**
 * Watcher Graph View - Type Definitions
 * Phase 1: Foundation types for graph visualization
 * Phase 3: Enhanced with badges, status, and channel details
 */

import { Node, Edge } from '@xyflow/react'

// Memory isolation modes for agents
export type MemoryIsolationMode = 'isolated' | 'shared' | 'channel_isolated'

// Channel status types
export type ChannelStatus = 'running' | 'stopped' | 'error' | 'active' | 'inactive'

// User role types
export type UserRole = 'owner' | 'admin' | 'member'

// Knowledge document status
export type KnowledgeStatus = 'pending' | 'processing' | 'completed' | 'failed'

// Node data structures for each entity type
export interface AgentNodeData {
  type: 'agent'
  id: number
  name: string
  isActive: boolean
  modelProvider?: string
  modelName?: string
  avatar?: string | null
  // Phase 3: Badge and channel data
  memoryIsolationMode?: MemoryIsolationMode
  skillsCount?: number
  hasKnowledgeBase?: boolean
  hasSentinelProtection?: boolean
  enabledChannels?: string[]
  isDefault?: boolean
  // Phase 5: Expansion state
  isExpanded?: boolean
  onExpand?: (agentId: number) => void
  onCollapse?: (agentId: number) => void
  // Phase 6: Knowledge counts for expand preview
  knowledgeDocCount?: number
  knowledgeChunkCount?: number
  // Phase 6: Loading state checker
  isLoading?: (agentId: number) => boolean
  // Phase 8: Real-time activity state
  isProcessing?: boolean
  hasActiveSkill?: boolean   // Skill is being used (visible even when collapsed)
  hasActiveKb?: boolean      // KB is being accessed (visible even when collapsed)
  isFading?: boolean         // Post-processing coordinated fade-out
}

export interface ContactNodeData {
  type: 'contact'
  id: number
  name: string
  role: string
  isActive: boolean
  // Future: channels, dm_trigger badge
}

export interface ProjectNodeData {
  type: 'project'
  id: number
  name: string
  icon: string
  color: string
  isArchived: boolean
  // Phase 4: Badge and access data
  hasKnowledgeBase: boolean
  documentCount?: number
  agentAccessCount?: number
}

export interface ChannelNodeData {
  type: 'channel'
  channelType: 'whatsapp' | 'telegram' | 'playground' | 'phone' | 'discord' | 'email' | 'sms'
  label: string
  // Phase 3: Instance details
  instanceId?: number
  phoneNumber?: string
  botUsername?: string
  status?: ChannelStatus
  healthStatus?: string
  // Phase 8: Real-time activity (separate from isActive to avoid dimming node via BaseNode)
  isGlowing?: boolean
  isFading?: boolean  // Post-processing coordinated fade-out
}

// Phase 5: User node data
export interface UserNodeData {
  type: 'user'
  id: number
  name: string
  email: string
  role: UserRole
  roleDisplayName: string
  isActive: boolean
  avatarUrl: string | null
  lastLoginAt: string | null
  linkedContactId: number | null
  linkedContactName: string | null
}

// Phase 5: Skill node data (child of agent)
export interface SkillNodeData {
  type: 'skill'
  id: number
  parentAgentId: number
  skillType: string
  skillName: string
  isEnabled: boolean
  config?: Record<string, unknown>
  // Phase 6: Enhanced skill display
  skillDescription?: string
  category?: string  // "search", "audio", "integration", "automation", "media", "travel", "special", "other"
  providerName?: string
  // Phase 11: Provider type and integration ID for configured provider
  providerType?: string  // e.g., "gmail", "google_calendar", "brave"
  integrationId?: number  // The configured integration ID
  // Phase 8: Real-time activity glow
  isActive?: boolean
  isFading?: boolean  // Post-processing coordinated fade-out
  // Phase 9: Provider expansion for skills that have multiple providers
  hasProviders?: boolean  // Whether this skill type has expandable providers (now determined by providerType presence)
  isExpanded?: boolean
  onExpand?: (agentId: number, skillId: number, skillType: string) => void
  onCollapse?: (agentId: number, skillId: number) => void
}

// Phase 5: Knowledge node data (child of agent) - DEPRECATED: Use KnowledgeSummaryNodeData
export interface KnowledgeNodeData {
  type: 'knowledge'
  id: number
  parentAgentId: number
  documentName: string
  documentType: string
  status: KnowledgeStatus
  chunkCount: number
  fileSizeBytes?: number
  uploadDate?: string
}

// Phase 6: Knowledge summary node data (replaces individual KnowledgeNode)
export interface KnowledgeSummaryNodeData {
  type: 'knowledge-summary'
  parentAgentId: number
  totalDocuments: number
  totalChunks: number
  totalSizeBytes: number
  documentTypes: Record<string, number>  // e.g., {"pdf": 2, "txt": 1}
  allCompleted: boolean
  // Phase 8: Real-time activity glow
  isActive?: boolean
  isFading?: boolean  // Post-processing coordinated fade-out
}

// Phase 7: Skill category node data (groups multiple skills by category)
export interface SkillCategoryNodeData {
  type: 'skill-category'
  parentAgentId: number
  category: string
  categoryDisplayName: string
  skillCount: number
  skills: SkillNodeData[]  // Store skills for expansion
  isExpanded?: boolean
  onExpand?: (agentId: number, category: string) => void
  onCollapse?: (agentId: number, category: string) => void
  // Phase 8: Real-time activity glow
  isActive?: boolean
  isFading?: boolean  // Post-processing coordinated fade-out
}

// Phase 9: Skill Provider node data (shows available providers for a skill)
export interface SkillProviderNodeData {
  type: 'skill-provider'
  parentAgentId: number
  parentSkillId: number
  parentSkillType: string
  providerType: string          // e.g., "google_flights", "brave", "flows"
  providerName: string          // e.g., "Google Flights", "Brave", "Flows (Built-in)"
  providerDescription?: string  // Description of the provider
  requiresIntegration: boolean  // Whether the provider needs a Hub integration
  isConfigured: boolean         // Whether this provider is currently configured for this skill
  isActive?: boolean   // Phase 8: Provider glows when parent skill is active
  isFading?: boolean   // Post-processing coordinated fade-out
}

// Phase F (v1.6.0): Security hierarchy node types for Sentinel profile visualization

export type SecurityDetectionMode = 'block' | 'detect_only' | 'off'

export interface SecurityProfileBadge {
  id: number
  name: string
  slug: string
}

export interface SecurityEffectiveProfile extends SecurityProfileBadge {
  source: 'skill' | 'agent' | 'tenant' | 'system'
}

export interface TenantSecurityNodeData {
  type: 'tenant-security'
  tenantId: string
  tenantName: string
  profile: SecurityProfileBadge | null
  effectiveProfile: SecurityEffectiveProfile | null
  detectionMode: SecurityDetectionMode
  aggressivenessLevel: number
  isEnabled: boolean
}

export interface SecuritySkillData {
  skillType: string
  skillName: string
  isEnabled: boolean
  profile: SecurityProfileBadge | null
  effectiveProfile: SecurityEffectiveProfile | null
  detectionMode: SecurityDetectionMode
}

export interface AgentSecurityNodeData {
  type: 'agent-security'
  id: number
  name: string
  isActive: boolean
  profile: SecurityProfileBadge | null
  effectiveProfile: SecurityEffectiveProfile | null
  detectionMode: SecurityDetectionMode
  aggressivenessLevel: number
  isEnabled: boolean
  skillsCount: number
  skills: SecuritySkillData[]
  isExpanded?: boolean
  onExpand?: (agentId: number) => void
  onCollapse?: (agentId: number) => void
}

export interface SkillSecurityNodeData {
  type: 'skill-security'
  skillType: string
  skillName: string
  isEnabled: boolean
  parentAgentId: number
  profile: SecurityProfileBadge | null
  effectiveProfile: SecurityEffectiveProfile | null
  detectionMode: SecurityDetectionMode
}

// Union type for all node data
export type GraphNodeData =
  | AgentNodeData
  | ContactNodeData
  | ProjectNodeData
  | ChannelNodeData
  | UserNodeData
  | SkillNodeData
  | KnowledgeNodeData
  | KnowledgeSummaryNodeData
  | SkillCategoryNodeData
  | SkillProviderNodeData
  | TenantSecurityNodeData
  | AgentSecurityNodeData
  | SkillSecurityNodeData

// Custom node type for React Flow
export type GraphNode = Node<GraphNodeData>
export type GraphEdge = Edge

// Graph view types
export type GraphViewType = 'agents' | 'users' | 'projects' | 'security'

// Graph configuration
export interface GraphConfig {
  viewType: GraphViewType
  showInactive: boolean
}

// Graph filters for the left panel
export interface GraphFilters {
  showInactiveAgents: boolean
}
