/**
 * Agent Studio - Type Definitions
 * Visual agent builder using React Flow
 */

import { Node, Edge } from '@xyflow/react'

// Builder node type identifiers
export type BuilderNodeType =
  | 'builder-agent'
  | 'builder-persona'
  | 'builder-channel'
  | 'builder-skill'
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
}

export interface BuilderPersonaData {
  type: 'builder-persona'
  personaId: number
  name: string
  role?: string
  personalityTraits?: string
  isActive: boolean
}

export interface BuilderChannelData {
  type: 'builder-channel'
  channelType: 'whatsapp' | 'telegram' | 'playground' | 'phone' | 'discord' | 'email' | 'sms'
  label: string
  instanceId?: number
  phoneNumber?: string
  botUsername?: string
  status?: string
}

export interface BuilderSkillData {
  type: 'builder-skill'
  skillId: number
  skillType: string
  skillName: string
  category?: string
  providerName?: string
  isEnabled: boolean
}

export interface BuilderToolData {
  type: 'builder-tool'
  toolId: number
  name: string
  toolType: string
  isEnabled: boolean
}

export interface BuilderSentinelData {
  type: 'builder-sentinel'
  profileId: number
  name: string
  mode: string
  isSystem: boolean
}

export interface BuilderKnowledgeData {
  type: 'builder-knowledge'
  docId: number
  filename: string
  contentType: string
  fileSize: number
  status: string
  chunkCount?: number
}

export interface BuilderMemoryData {
  type: 'builder-memory'
  isolationMode: string
  memorySize: number
  enableSemanticSearch: boolean
}

// Union of all builder node data
export type BuilderNodeData =
  | BuilderAgentData
  | BuilderPersonaData
  | BuilderChannelData
  | BuilderSkillData
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
  } | null
  attachedPersonaId: number | null
  attachedChannels: string[]
  attachedSkills: Array<{ skillType: string; skillId: number; config?: Record<string, unknown> }>
  attachedTools: number[]
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
