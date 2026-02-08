/**
 * Agent Studio - Type Definitions
 * Visual agent builder using React Flow
 */

import { Node, Edge } from '@xyflow/react'

// Builder node type identifiers
export type BuilderNodeType =
  | 'builder-agent'
  | 'builder-group'
  | 'builder-persona'
  | 'builder-channel'
  | 'builder-skill'
  | 'builder-skill-provider'
  | 'builder-tool'
  | 'builder-sentinel'
  | 'builder-knowledge'
  | 'builder-memory'

// Profile category for the palette
export type ProfileCategoryId =
  | 'persona'
  | 'channels'
  | 'skills'
  | 'tools'
  | 'security'
  | 'knowledge'
  | 'memory'

// Cardinality rules per category
export const CATEGORY_CARDINALITY: Record<ProfileCategoryId, { min: number; max: number | null; label: string }> = {
  persona: { min: 0, max: 1, label: '0..1' },
  channels: { min: 0, max: null, label: '0..N' },
  skills: { min: 0, max: null, label: '0..N' },
  tools: { min: 0, max: null, label: '0..N' },
  security: { min: 0, max: 1, label: '0..1' },
  knowledge: { min: 0, max: null, label: '0..N' },
  memory: { min: 1, max: 1, label: '1' },
}

// Categories that render as expandable group nodes (0..N cardinality)
export const GROUPED_CATEGORIES: ProfileCategoryId[] = ['channels', 'skills', 'tools', 'knowledge']

// Categories that render as direct individual nodes
export const DIRECT_CATEGORIES: ProfileCategoryId[] = ['persona', 'security', 'memory']

// Display configuration per category
export const CATEGORY_DISPLAY: Record<ProfileCategoryId, { label: string; color: string; borderColor: string; bgColor: string }> = {
  persona: { label: 'Persona', color: 'text-purple-400', borderColor: 'border-purple-500/50', bgColor: 'bg-purple-500/10' },
  channels: { label: 'Channels', color: 'text-blue-400', borderColor: 'border-blue-500/50', bgColor: 'bg-blue-500/10' },
  skills: { label: 'Skills', color: 'text-teal-400', borderColor: 'border-teal-500/50', bgColor: 'bg-teal-500/10' },
  tools: { label: 'Tools', color: 'text-orange-400', borderColor: 'border-orange-500/50', bgColor: 'bg-orange-500/10' },
  security: { label: 'Security', color: 'text-red-400', borderColor: 'border-red-500/50', bgColor: 'bg-red-500/10' },
  knowledge: { label: 'Knowledge', color: 'text-violet-400', borderColor: 'border-violet-500/50', bgColor: 'bg-violet-500/10' },
  memory: { label: 'Memory', color: 'text-sky-400', borderColor: 'border-sky-500/50', bgColor: 'bg-sky-500/10' },
}

// Radial layout sector definitions (degrees)
export const SECTOR_ANGLES: Record<ProfileCategoryId, { start: number; end: number }> = {
  persona: { start: 330, end: 30 },
  skills: { start: 30, end: 90 },
  tools: { start: 90, end: 150 },
  knowledge: { start: 150, end: 195 },
  memory: { start: 195, end: 210 },
  security: { start: 210, end: 270 },
  channels: { start: 270, end: 330 },
}

// --- Node Data Interfaces ---

export interface BuilderAgentData {
  [key: string]: unknown
  type: 'builder-agent'
  agentId: number
  name: string
  modelProvider: string
  modelName: string
  isActive: boolean
  isDefault: boolean
  enabledChannels: string[]
  skillsCount: number
  personaName?: string
  avatar?: string | null
  onAvatarChange?: (slug: string | null) => void
}

export interface BuilderPersonaData {
  [key: string]: unknown
  type: 'builder-persona'
  personaId: number
  name: string
  role?: string
  personalityTraits?: string
  isActive: boolean
}

export interface BuilderChannelData {
  [key: string]: unknown
  type: 'builder-channel'
  channelType: 'whatsapp' | 'telegram' | 'playground' | 'phone' | 'discord' | 'email' | 'sms'
  label: string
  instanceId?: number
  phoneNumber?: string
  botUsername?: string
  status?: string
}

export interface BuilderSkillData {
  [key: string]: unknown
  type: 'builder-skill'
  skillId: number
  skillType: string
  skillName: string
  category?: string
  providerName?: string
  providerType?: string
  isEnabled: boolean
  config?: Record<string, unknown>
  hasProviders?: boolean
  isExpanded?: boolean
  onToggleExpand?: (skillType: string) => void
}

export interface BuilderSkillProviderData {
  [key: string]: unknown
  type: 'builder-skill-provider'
  parentSkillType: string
  providerType: string
  providerName: string
  isConfigured: boolean
  requiresIntegration: boolean
  integrationId?: number
}

export interface BuilderToolData {
  [key: string]: unknown
  type: 'builder-tool'
  toolId: number
  name: string
  toolType: string
  isEnabled: boolean
}

export interface BuilderSentinelData {
  [key: string]: unknown
  type: 'builder-sentinel'
  profileId: number
  name: string
  mode: string
  isSystem: boolean
}

export interface BuilderKnowledgeData {
  [key: string]: unknown
  type: 'builder-knowledge'
  docId: number
  filename: string
  contentType: string
  fileSize: number
  status: string
  chunkCount?: number
  uploadDate?: string
  isExpanded?: boolean
  onToggleExpand?: (docId: number) => void
}

export interface BuilderMemoryData {
  [key: string]: unknown
  type: 'builder-memory'
  isolationMode: string
  memorySize: number
  enableSemanticSearch: boolean
}

export interface BuilderGroupData {
  [key: string]: unknown
  type: 'builder-group'
  categoryId: ProfileCategoryId
  categoryLabel: string
  categoryColor: string
  childCount: number
  isExpanded: boolean
  onExpand: (categoryId: ProfileCategoryId) => void
  onCollapse: (categoryId: ProfileCategoryId) => void
}

// Union of all builder node data
export type BuilderNodeData =
  | BuilderAgentData
  | BuilderGroupData
  | BuilderPersonaData
  | BuilderChannelData
  | BuilderSkillData
  | BuilderSkillProviderData
  | BuilderToolData
  | BuilderSentinelData
  | BuilderKnowledgeData
  | BuilderMemoryData

// React Flow types
export type BuilderNode = Node<BuilderNodeData>
export type BuilderEdge = Edge

// --- Palette Item Type ---

export interface PaletteItemData {
  id: string | number
  name: string
  categoryId: ProfileCategoryId
  nodeType: BuilderNodeType
  isAttached: boolean
  metadata: Record<string, unknown>
}

// --- Agent Builder State ---

export interface AgentBuilderState {
  agentId: number | null
  agent: {
    name: string
    modelProvider: string
    modelName: string
    isActive: boolean
    isDefault: boolean
    personaId: number | null
    enabledChannels: string[]
    whatsappIntegrationId: number | null
    telegramIntegrationId: number | null
    memorySize: number
    memoryIsolationMode: string
    enableSemanticSearch: boolean
    avatar: string | null
  } | null
  attachedPersonaId: number | null
  attachedChannels: string[]
  attachedSkills: Array<{ skillType: string; skillId: number; config?: Record<string, unknown> }>
  attachedTools: number[]
  toolEnabledOverrides: Record<number, boolean>
  attachedSentinelProfileId: number | null
  attachedSentinelAssignmentId: number | null
  attachedKnowledgeDocs: number[]
  isDirty: boolean
  isSaving: boolean
}

// Drag-and-drop transfer data
export interface DragTransferData {
  categoryId: ProfileCategoryId
  nodeType: BuilderNodeType
  itemId: string | number
  itemName: string
  metadata: Record<string, unknown>
}

// Config panel target (for inline editing)
export interface ConfigPanelTarget {
  nodeId: string
  nodeType: BuilderNodeType
  nodeData: BuilderNodeData
}
