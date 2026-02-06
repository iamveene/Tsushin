'use client'

/**
 * GraphCanvas - React Flow wrapper with Tsushin styling
 * Phase 2: Added drag, auto-layout, and ReactFlowProvider
 * Phase 3: Fixed sync with external data changes
 * Phase 5: Added expansion state management for agent child nodes
 * Phase 6: Added expand data caching, batch endpoint, KnowledgeSummaryNode
 * Phase 7: Added skill grouping by category (threshold: 4 skills)
 */

import { useCallback, useEffect, useImperativeHandle, forwardRef, useRef, useState, useMemo } from 'react'
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  useReactFlow,
  BackgroundVariant,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import { nodeTypes } from './nodes'
import { GraphNode, GraphEdge, AgentNodeData, ChannelNodeData, SkillNodeData, KnowledgeSummaryNodeData, SkillCategoryNodeData, SkillProviderNodeData } from './types'
import type { LayoutOptions } from './layout'
import { DEFAULT_LAYOUT_OPTIONS } from './layout'
// Import useAutoLayout directly to avoid SSR issues (this file is dynamically imported)
import { useAutoLayout } from './layout/useAutoLayout'
import { api, AgentExpandDataResponse } from '@/lib/client'

export interface GraphCanvasRef {
  runLayout: () => void
  expandAll: () => Promise<void>
  collapseAll: () => void
  hasExpandableNodes: () => boolean
  hasExpandedNodes: () => boolean
  fitView: () => void  // Phase 10: Expose fitView for fullscreen mode
}

// Phase 8: Activity state passed from parent for real-time graph updates
export interface ActivityState {
  processingAgents: Set<number>
  activeChannels: Set<string>
  recentSkillUse: Map<number, { skillType: string; skillName: string; timestamp: number }>
  recentKbUse: Map<number, { docCount: number; chunkCount: number; timestamp: number }>
  fadingAgents: Set<number>
  fadingChannels: Set<string>
}

interface GraphCanvasProps {
  initialNodes: GraphNode[]
  initialEdges: GraphEdge[]
  onNodeClick?: (node: GraphNode) => void
  autoFit?: boolean
  layoutOptions?: LayoutOptions
  // Callback to notify parent when expanded agents count changes
  onExpandedCountChange?: (count: number) => void
  // Callback to pass ref methods to parent (workaround for Next.js dynamic import ref issue)
  onReady?: (methods: GraphCanvasRef) => void
  // Phase 8: Real-time activity state for node animations
  activityState?: ActivityState
}

/**
 * Inner component that uses React Flow hooks
 * Must be wrapped in ReactFlowProvider
 */
const GraphCanvasInner = forwardRef<GraphCanvasRef, GraphCanvasProps>(
  function GraphCanvasInner(
    {
      initialNodes,
      initialEdges,
      onNodeClick,
      autoFit = true,
      layoutOptions = DEFAULT_LAYOUT_OPTIONS,
      onExpandedCountChange,
      onReady,
      activityState,
    },
    ref
  ) {
    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
    const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)
    const { fitView } = useReactFlow()
    const { runLayout } = useAutoLayout(layoutOptions)
    const prevNodesLengthRef = useRef(initialNodes.length)

    // Phase 5: Track expanded agents
    const [expandedAgents, setExpandedAgents] = useState<Set<number>>(new Set())

    // Notify parent when expanded count changes
    useEffect(() => {
      onExpandedCountChange?.(expandedAgents.size)
    }, [expandedAgents.size, onExpandedCountChange])

    // Phase 6: Cache for expand data to eliminate delay on subsequent clicks
    const expandDataCache = useRef<Map<number, AgentExpandDataResponse>>(new Map())

    // Phase 6: Track loading state for expand buttons
    const [loadingAgents, setLoadingAgents] = useState<Set<number>>(new Set())

    // Phase 7: Track expanded skill categories (key: "agentId-category")
    const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set())


    // Phase 7: Threshold for skill grouping - always use category grouping for consistency
    // Set to 0 to always show consolidation nodes (Agent → Category → Skill)
    const SKILL_GROUPING_THRESHOLD = 0

    // Phase 11: Standalone skill categories - these bypass category grouping
    // Skills with these categories are shown directly under Agent (not grouped)
    // Example: Agent > Email > Gmail (not Agent > Email > Email > Gmail)
    const STANDALONE_CATEGORIES = new Set(['email', 'scheduler', 'flight_search'])

    // Phase 11: Excluded skill types - these are not shown in Graph View
    const EXCLUDED_SKILL_TYPES = new Set(['automation'])  // Multi-Step Automation is internal

    // Phase 11: Helper to check if a skill has a configured provider
    // Now determined dynamically from expand data (provider_type field) instead of static set
    const skillHasConfiguredProvider = useCallback((skill: { provider_type?: string | null; provider_name?: string | null }): boolean => {
      return !!(skill.provider_type && skill.provider_name)
    }, [])

    // Phase 9: Track expanded skills (key: "agentId-skillId")
    const [expandedSkills, setExpandedSkills] = useState<Set<string>>(new Set())

    // Phase 6: Pre-fetch expand data for visible agents (background prefetch)
    useEffect(() => {
      const agentNodes = initialNodes.filter(n => n.data.type === 'agent')
      // Pre-fetch for first 5 agents with skills or KB
      const prefetchCount = 5
      let prefetched = 0

      agentNodes.forEach(node => {
        if (prefetched >= prefetchCount) return
        const agentData = node.data as AgentNodeData
        // Only prefetch for agents that have skills or KB
        if ((agentData.skillsCount && agentData.skillsCount > 0) || agentData.hasKnowledgeBase) {
          const agentId = agentData.id
          if (!expandDataCache.current.has(agentId)) {
            prefetched++
            // Silently prefetch in background
            api.getAgentExpandData(agentId)
              .then(data => {
                expandDataCache.current.set(agentId, data)
              })
              .catch(() => {
                // Ignore prefetch errors - will fetch on demand
              })
          }
        }
      })
    }, [initialNodes])

    // Phase 7: Category display names mapping
    const categoryDisplayNames: Record<string, string> = {
      search: 'Search',
      audio: 'Audio',
      integration: 'Integrations',
      automation: 'Automation',
      system: 'System',
      media: 'Media',
      travel: 'Travel',
      special: 'Special',
      other: 'Other',
      // Standalone skill categories (shown directly under agent, not grouped)
      email: 'Email',
      flight_search: 'Flight Search',
      scheduler: 'Scheduler',
    }

    // Phase 11: Handle skill expand - shows ONLY the configured provider (from backend data)
    const handleSkillExpand = useCallback(async (agentId: number, skillId: number, skillType: string) => {
      // Get skill data from cached expand data - this now contains provider_type and provider_name
      const expandData = expandDataCache.current.get(agentId)
      const skillData = expandData?.skills.find(s => s.id === skillId)

      // If no provider configured for this skill, don't expand
      if (!skillData?.provider_type || !skillData?.provider_name) {
        console.warn(`No provider configured for skill ${skillType} on agent ${agentId}`)
        return
      }

      // Create SINGLE provider node for the configured provider only
      const providerNode: GraphNode = {
        id: `skill-provider-${agentId}-${skillId}-${skillData.provider_type}`,
        type: 'skill-provider',
        position: { x: 0, y: 0 },
        data: {
          type: 'skill-provider',
          parentAgentId: agentId,
          parentSkillId: skillId,
          parentSkillType: skillType,
          providerType: skillData.provider_type,
          providerName: skillData.provider_name,
          providerDescription: '',
          requiresIntegration: !!skillData.integration_id,
          isConfigured: true,  // Always true - we only show the configured provider
        } as SkillProviderNodeData,
      }

      // Create edge from skill to provider
      const providerEdge: GraphEdge = {
        id: `e-skill-${agentId}-${skillId}-${providerNode.id}`,
        source: `skill-${agentId}-${skillId}`,
        target: providerNode.id,
      }

      // Update skill node to show expanded state and add provider node
      setNodes(prev => {
        const updatedNodes = prev.map(n => {
          if (n.id === `skill-${agentId}-${skillId}` && n.data.type === 'skill') {
            return {
              ...n,
              data: {
                ...n.data,
                isExpanded: true,
              } as SkillNodeData,
            }
          }
          return n
        })
        return [...updatedNodes, providerNode]
      })

      setEdges(prev => [...prev, providerEdge])
      setExpandedSkills(prev => new Set(prev).add(`${agentId}-${skillId}`))

      setTimeout(() => runLayout(), 50)
    }, [setNodes, setEdges, runLayout])

    // Phase 9: Handle skill collapse - removes provider nodes from skill
    const handleSkillCollapse = useCallback((agentId: number, skillId: number) => {
      // Remove provider nodes for this skill
      setNodes(prev => {
        const filtered = prev.filter(n =>
          !(n.data.type === 'skill-provider' && n.id.startsWith(`skill-provider-${agentId}-${skillId}-`))
        )
        // Update skill node to show collapsed state
        return filtered.map(n => {
          if (n.id === `skill-${agentId}-${skillId}` && n.data.type === 'skill') {
            return {
              ...n,
              data: {
                ...n.data,
                isExpanded: false,
              } as SkillNodeData,
            }
          }
          return n
        })
      })

      // Remove edges from skill to providers
      setEdges(prev => prev.filter(e => !e.id.startsWith(`e-skill-${agentId}-${skillId}-`)))

      setExpandedSkills(prev => {
        const next = new Set(prev)
        next.delete(`${agentId}-${skillId}`)
        return next
      })

      setTimeout(() => runLayout(), 50)
    }, [setNodes, setEdges, runLayout])

    // Phase 7 & 9: Handle skill category expand - creates skill nodes with provider expansion capability
    const handleCategoryExpand = useCallback((agentId: number, category: string) => {
      const expandData = expandDataCache.current.get(agentId)
      if (!expandData) return

      // Get skills for this category
      const categorySkills = expandData.skills.filter(s => (s.category || 'other') === category)

      const childNodes: GraphNode[] = []
      const childEdges: GraphEdge[] = []

      // Create skill nodes directly - each skill can be expanded to show its configured provider
      categorySkills.forEach((skill) => {
        // Phase 11: Determine if skill has a configured provider (from backend data)
        const hasProviders = skillHasConfiguredProvider(skill)

        childNodes.push({
          id: `skill-${agentId}-${skill.id}`,
          type: 'skill',
          position: { x: 0, y: 0 },
          data: {
            type: 'skill',
            id: skill.id,
            parentAgentId: agentId,
            skillType: skill.skill_type,
            skillName: skill.skill_name,
            skillDescription: skill.skill_description,
            category: skill.category,
            providerName: skill.provider_name,
            // Phase 11: Pass provider type and integration ID from backend
            providerType: skill.provider_type,
            integrationId: skill.integration_id,
            isEnabled: skill.is_enabled,
            config: skill.config,
            // Phase 11: Provider expansion now based on actual configured provider
            hasProviders,
            isExpanded: false,
            onExpand: hasProviders ? handleSkillExpand : undefined,
            onCollapse: hasProviders ? handleSkillCollapse : undefined,
          } as SkillNodeData,
        })

        // Edge from category to skill
        childEdges.push({
          id: `e-category-${agentId}-${category}-skill-${agentId}-${skill.id}`,
          source: `skill-category-${agentId}-${category}`,
          target: `skill-${agentId}-${skill.id}`,
        })
      })

      // Update category node to show expanded state and add child nodes
      setNodes(prev => {
        const updatedNodes = prev.map(n => {
          if (n.id === `skill-category-${agentId}-${category}` && n.data.type === 'skill-category') {
            return {
              ...n,
              data: {
                ...n.data,
                isExpanded: true,
              } as SkillCategoryNodeData,
            }
          }
          return n
        })
        return [...updatedNodes, ...childNodes]
      })

      setEdges(prev => [...prev, ...childEdges])
      setExpandedCategories(prev => new Set(prev).add(`${agentId}-${category}`))

      setTimeout(() => runLayout(), 50)
    }, [setNodes, setEdges, runLayout, handleSkillExpand, handleSkillCollapse, skillHasConfiguredProvider])

    // Phase 7 & 9: Handle skill category collapse - also removes skill-provider nodes
    const handleCategoryCollapse = useCallback((agentId: number, category: string) => {
      // Remove skill nodes AND skill-provider nodes for this category
      setNodes(prev => {
        const expandData = expandDataCache.current.get(agentId)
        const categorySkillIds = expandData?.skills
          .filter(s => (s.category || 'other') === category)
          .map(s => s.id) || []

        // Filter out skill nodes and skill-provider nodes for this category
        const filtered = prev.filter(n => {
          // Remove skill nodes for this category
          if (n.data.type === 'skill' && categorySkillIds.some(id => n.id === `skill-${agentId}-${id}`)) return false
          // Remove skill-provider nodes for skills in this category
          if (n.data.type === 'skill-provider' && categorySkillIds.some(id => n.id.startsWith(`skill-provider-${agentId}-${id}-`))) return false
          return true
        })

        // Update category node to show collapsed state
        return filtered.map(n => {
          if (n.id === `skill-category-${agentId}-${category}` && n.data.type === 'skill-category') {
            return {
              ...n,
              data: {
                ...n.data,
                isExpanded: false,
              } as SkillCategoryNodeData,
            }
          }
          return n
        })
      })

      // Remove edges from category to skills AND from skills to providers
      setEdges(prev => prev.filter(e =>
        !e.id.startsWith(`e-category-${agentId}-${category}-`) &&
        !e.id.startsWith(`e-skill-${agentId}-`)
      ))

      setExpandedCategories(prev => {
        const next = new Set(prev)
        next.delete(`${agentId}-${category}`)
        return next
      })

      // Also clear expanded skills for this category
      setExpandedSkills(prev => {
        const next = new Set(prev)
        prev.forEach(key => {
          if (key.startsWith(`${agentId}-`)) {
            // Check if this skill is in the collapsed category
            const expandData = expandDataCache.current.get(agentId)
            const skillId = parseInt(key.split('-')[1])
            const skill = expandData?.skills.find(s => s.id === skillId)
            if (skill && (skill.category || 'other') === category) {
              next.delete(key)
            }
          }
        })
        return next
      })

      setTimeout(() => runLayout(), 50)
    }, [setNodes, setEdges, runLayout])

    // Phase 6 & 7: Handle agent expand - uses batch endpoint with caching and skill grouping
    const handleAgentExpand = useCallback(async (agentId: number) => {
      try {
        // Set loading state
        setLoadingAgents(prev => new Set(prev).add(agentId))

        // Check cache first
        let expandData = expandDataCache.current.get(agentId)

        // If not cached, fetch from batch endpoint
        if (!expandData) {
          expandData = await api.getAgentExpandData(agentId)
          expandDataCache.current.set(agentId, expandData)
        }

        const childNodes: GraphNode[] = []

        // Phase 11: Filter out excluded skill types (e.g., Multi-Step Automation)
        const filteredSkills = expandData.skills.filter(
          skill => !EXCLUDED_SKILL_TYPES.has(skill.skill_type)
        )

        // Phase 7: Group skills by category if there are more than threshold
        if (filteredSkills.length > SKILL_GROUPING_THRESHOLD) {
          // Group skills by category
          const skillsByCategory = new Map<string, typeof filteredSkills>()
          filteredSkills.forEach(skill => {
            const category = skill.category || 'other'
            if (!skillsByCategory.has(category)) {
              skillsByCategory.set(category, [])
            }
            skillsByCategory.get(category)!.push(skill)
          })

          // Create category nodes or individual skill nodes depending on category type
          skillsByCategory.forEach((skills, category) => {
            // Phase 11: Standalone categories bypass grouping - create skill nodes directly
            if (STANDALONE_CATEGORIES.has(category)) {
              // Create individual skill nodes for standalone categories (Agent > Skill > Provider)
              skills.forEach((skill) => {
                const hasProviders = skillHasConfiguredProvider(skill)
                childNodes.push({
                  id: `skill-${agentId}-${skill.id}`,
                  type: 'skill',
                  position: { x: 0, y: 0 },
                  data: {
                    type: 'skill',
                    id: skill.id,
                    parentAgentId: agentId,
                    skillType: skill.skill_type,
                    skillName: skill.skill_name,
                    skillDescription: skill.skill_description,
                    category: skill.category,
                    providerName: skill.provider_name,
                    providerType: skill.provider_type,
                    integrationId: skill.integration_id,
                    isEnabled: skill.is_enabled,
                    config: skill.config,
                    hasProviders,
                    isExpanded: false,
                    onExpand: hasProviders ? handleSkillExpand : undefined,
                    onCollapse: hasProviders ? handleSkillCollapse : undefined,
                  } as SkillNodeData,
                })
              })
            } else {
              // Create category node for non-standalone categories (Agent > Category > Skill > Provider)
              childNodes.push({
                id: `skill-category-${agentId}-${category}`,
                type: 'skill-category',
                position: { x: 0, y: 0 },
                data: {
                  type: 'skill-category',
                  parentAgentId: agentId,
                  category,
                  categoryDisplayName: categoryDisplayNames[category] || category,
                  skillCount: skills.length,
                  skills: skills.map(s => ({
                    type: 'skill' as const,
                    id: s.id,
                    parentAgentId: agentId,
                    skillType: s.skill_type,
                    skillName: s.skill_name,
                    skillDescription: s.skill_description,
                    category: s.category,
                    providerName: s.provider_name,
                    isEnabled: s.is_enabled,
                    config: s.config,
                  })),
                  isExpanded: false,
                  onExpand: handleCategoryExpand,
                  onCollapse: handleCategoryCollapse,
                } as SkillCategoryNodeData,
              })
            }
          })
        } else {
          // Create individual skill nodes (original behavior for <= threshold skills)
          // Phase 11: Add provider expansion capability based on actual configured provider
          filteredSkills.forEach((skill) => {
            const hasProviders = skillHasConfiguredProvider(skill)
            childNodes.push({
              id: `skill-${agentId}-${skill.id}`,
              type: 'skill',
              position: { x: 0, y: 0 },
              data: {
                type: 'skill',
                id: skill.id,
                parentAgentId: agentId,
                skillType: skill.skill_type,
                skillName: skill.skill_name,
                skillDescription: skill.skill_description,
                category: skill.category,
                providerName: skill.provider_name,
                // Phase 11: Pass provider type and integration ID from backend
                providerType: skill.provider_type,
                integrationId: skill.integration_id,
                isEnabled: skill.is_enabled,
                config: skill.config,
                // Phase 11: Provider expansion now based on actual configured provider
                hasProviders,
                isExpanded: false,
                onExpand: hasProviders ? handleSkillExpand : undefined,
                onCollapse: hasProviders ? handleSkillCollapse : undefined,
              } as SkillNodeData,
            })
          })
        }

        // Phase 6: Create single KnowledgeSummaryNode instead of individual nodes
        if (expandData.knowledge_summary.total_documents > 0) {
          childNodes.push({
            id: `knowledge-summary-${agentId}`,
            type: 'knowledge-summary',
            position: { x: 0, y: 0 },
            data: {
              type: 'knowledge-summary',
              parentAgentId: agentId,
              totalDocuments: expandData.knowledge_summary.total_documents,
              totalChunks: expandData.knowledge_summary.total_chunks,
              totalSizeBytes: expandData.knowledge_summary.total_size_bytes,
              documentTypes: expandData.knowledge_summary.document_types,
              allCompleted: expandData.knowledge_summary.all_completed,
            } as KnowledgeSummaryNodeData,
          })
        }

        // Create edges from agent to children
        // Note: Both category nodes AND standalone skill nodes connect directly to agent
        const childEdges: GraphEdge[] = childNodes.map(n => ({
          id: `e-agent-${agentId}-${n.id}`,
          source: `agent-${agentId}`,
          target: n.id,
        }))

        // Update nodes with expansion state and add children
        setNodes(prev => {
          // Update agent node with isExpanded
          const updatedNodes = prev.map(n => {
            if (n.id === `agent-${agentId}` && n.data.type === 'agent') {
              return {
                ...n,
                data: {
                  ...n.data,
                  isExpanded: true,
                } as AgentNodeData,
              }
            }
            return n
          })
          return [...updatedNodes, ...childNodes]
        })

        setEdges(prev => [...prev, ...childEdges])
        setExpandedAgents(prev => new Set(prev).add(agentId))

        // Re-run layout after nodes added
        setTimeout(() => runLayout(), 50)
      } catch (err) {
        console.error('[GraphCanvas] Failed to expand agent:', err)
      } finally {
        // Clear loading state
        setLoadingAgents(prev => {
          const next = new Set(prev)
          next.delete(agentId)
          return next
        })
      }
    }, [setNodes, setEdges, runLayout, handleCategoryExpand, handleCategoryCollapse, handleSkillExpand, handleSkillCollapse, SKILL_GROUPING_THRESHOLD, skillHasConfiguredProvider])

    // Phase 5, 7 & 9: Handle agent collapse - also removes category nodes, skill-provider nodes, and their expanded skills
    const handleAgentCollapse = useCallback((agentId: number) => {
      // Remove child nodes for this agent (skills, skill-categories, skill-providers, and knowledge-summary)
      setNodes(prev => {
        const filtered = prev.filter(n => {
          // Remove skill nodes, skill-category nodes, skill-provider nodes, knowledge nodes, and knowledge-summary nodes
          if ((n.data.type === 'skill' || n.data.type === 'skill-category' || n.data.type === 'skill-provider' || n.data.type === 'knowledge' || n.data.type === 'knowledge-summary') &&
              'parentAgentId' in n.data &&
              n.data.parentAgentId === agentId) {
            return false
          }
          return true
        })

        // Update agent node isExpanded state
        return filtered.map(n => {
          if (n.id === `agent-${agentId}` && n.data.type === 'agent') {
            return {
              ...n,
              data: {
                ...n.data,
                isExpanded: false,
              } as AgentNodeData,
            }
          }
          return n
        })
      })

      // Remove edges to children (skill nodes, category nodes, skill-provider nodes, and knowledge nodes)
      setEdges(prev => prev.filter(e =>
        !e.id.startsWith(`e-agent-${agentId}-skill-`) &&
        !e.id.startsWith(`e-agent-${agentId}-knowledge-`) &&
        !e.id.startsWith(`e-category-${agentId}-`) &&
        !e.id.startsWith(`e-skill-${agentId}-`)
      ))

      setExpandedAgents(prev => {
        const next = new Set(prev)
        next.delete(agentId)
        return next
      })

      // Clear expanded categories for this agent
      setExpandedCategories(prev => {
        const next = new Set(prev)
        prev.forEach(key => {
          if (key.startsWith(`${agentId}-`)) {
            next.delete(key)
          }
        })
        return next
      })

      // Phase 9: Clear expanded skills for this agent
      setExpandedSkills(prev => {
        const next = new Set(prev)
        prev.forEach(key => {
          if (key.startsWith(`${agentId}-`)) {
            next.delete(key)
          }
        })
        return next
      })

      // Re-run layout
      setTimeout(() => runLayout(), 50)
    }, [setNodes, setEdges, runLayout])

    // Phase 6: Check if agent is loading
    const isAgentLoading = useCallback((agentId: number) => {
      return loadingAgents.has(agentId)
    }, [loadingAgents])

    // Phase 7: Expand All - expand all agent nodes that have expandable content
    // Uses initialNodes as the source of truth for data properties
    const expandAll = useCallback(async () => {
      // Find all agent nodes that have skills or KB and are not expanded
      const agentNodes = initialNodes.filter(n => {
        if (n.data.type !== 'agent') return false
        const agentData = n.data as AgentNodeData
        if (expandedAgents.has(agentData.id)) return false
        // Only expand agents that have skills or knowledge base
        return (agentData.skillsCount && agentData.skillsCount > 0) || agentData.hasKnowledgeBase
      })

      // Expand each agent sequentially to avoid race conditions
      for (const node of agentNodes) {
        const agentData = node.data as AgentNodeData
        await handleAgentExpand(agentData.id)
      }
    }, [initialNodes, expandedAgents, handleAgentExpand])

    // Phase 7: Collapse All - collapse all expanded agent nodes
    const collapseAll = useCallback(() => {
      // Collapse all expanded agents
      const expandedAgentIds = Array.from(expandedAgents)
      expandedAgentIds.forEach(agentId => {
        handleAgentCollapse(agentId)
      })
    }, [expandedAgents, handleAgentCollapse])

    // Phase 7: Check if there are expandable nodes (for button visibility)
    // Uses initialNodes as the source of truth since it has the complete data from API
    const hasExpandableNodes = useCallback(() => {
      return initialNodes.some(n => {
        if (n.data.type !== 'agent') return false
        const agentData = n.data as AgentNodeData
        if (expandedAgents.has(agentData.id)) return false
        return (agentData.skillsCount && agentData.skillsCount > 0) || agentData.hasKnowledgeBase
      })
    }, [initialNodes, expandedAgents])

    // Phase 7: Check if there are expanded nodes (for button visibility)
    const hasExpandedNodes = useCallback(() => {
      return expandedAgents.size > 0
    }, [expandedAgents])

    // Expose runLayout and expand/collapse methods to parent via ref
    // Phase 10: Wrap fitView for ref exposure
    const handleFitView = useCallback(() => {
      fitView({ padding: 0.2, duration: 300 })
    }, [fitView])

    const refMethods: GraphCanvasRef = useMemo(() => ({
      runLayout,
      expandAll,
      collapseAll,
      hasExpandableNodes,
      hasExpandedNodes,
      fitView: handleFitView,
    }), [runLayout, expandAll, collapseAll, hasExpandableNodes, hasExpandedNodes, handleFitView])

    useImperativeHandle(ref, () => refMethods, [refMethods])

    // Call onReady callback with ref methods (workaround for Next.js dynamic import ref issue)
    useEffect(() => {
      onReady?.(refMethods)
    }, [onReady, refMethods])

    // Sync nodes and edges when initialNodes/initialEdges change (e.g., filter toggle, view change)
    // Also runs on initial mount to inject handlers
    const initializedRef = useRef(false)
    const prevInitialNodesRef = useRef<string>('')
    useEffect(() => {
      // Create a stable key from initialNodes to detect actual external changes
      const initialNodesKey = initialNodes.map(n => n.id).sort().join(',')

      // Only sync when initialNodes actually changes from external source (not from internal setNodes)
      if (!initializedRef.current || initialNodesKey !== prevInitialNodesRef.current) {
        initializedRef.current = true
        prevInitialNodesRef.current = initialNodesKey

        // Inject expand/collapse handlers into agent nodes
        const nodesWithHandlers = initialNodes.map(n => {
          if (n.data.type === 'agent') {
            return {
              ...n,
              data: {
                ...n.data,
                isExpanded: false,
                onExpand: handleAgentExpand,
                onCollapse: handleAgentCollapse,
                isLoading: isAgentLoading,
              } as AgentNodeData,
            }
          }
          return n
        })

        setNodes(nodesWithHandlers)
        setEdges(initialEdges)
        prevNodesLengthRef.current = initialNodes.length
        // Reset expansion state when view changes
        setExpandedAgents(new Set())
        // Phase 7: Reset expanded categories when view changes
        setExpandedCategories(new Set())
        // Clear cache when view changes
        expandDataCache.current.clear()
        // Run layout after state update
        setTimeout(() => runLayout(), 50)
      }
    }, [initialNodes, initialEdges, setNodes, setEdges, runLayout, handleAgentExpand, handleAgentCollapse, isAgentLoading])

    // Phase 8: Merge real-time activity state into React Flow's internal nodes
    // Uses session-based model: all glows coordinated by agent processing lifecycle
    useEffect(() => {
      if (!activityState) return

      setNodes(prev => prev.map(node => {
        // Agent nodes - set isProcessing, hasActiveSkill, hasActiveKb, isFading
        if (node.data.type === 'agent') {
          const agentData = node.data as AgentNodeData
          const isProcessing = activityState.processingAgents.has(agentData.id)
          const isFading = activityState.fadingAgents.has(agentData.id)
          const hasActiveSkill = activityState.recentSkillUse.has(agentData.id)
          const hasActiveKb = activityState.recentKbUse.has(agentData.id)
          if (isProcessing !== (agentData.isProcessing ?? false) ||
              isFading !== (agentData.isFading ?? false) ||
              hasActiveSkill !== (agentData.hasActiveSkill ?? false) ||
              hasActiveKb !== (agentData.hasActiveKb ?? false)) {
            return { ...node, data: { ...agentData, isProcessing, isFading, hasActiveSkill, hasActiveKb } }
          }
        }

        // Skill nodes - set isActive and isFading when skill was recently used
        // Note: Backend emits "flows" for skill_type but graph may show "scheduler" (transformed by expand-data API)
        if (node.data.type === 'skill') {
          const skillData = node.data as SkillNodeData
          const skillUse = activityState.recentSkillUse.get(skillData.parentAgentId)
          const isActive = skillUse ? (
            skillUse.skillType === skillData.skillType ||
            (skillUse.skillType === 'flows' && skillData.skillType === 'scheduler')
          ) : false
          const isFading = isActive && activityState.fadingAgents.has(skillData.parentAgentId)
          if (isActive !== (skillData.isActive ?? false) ||
              isFading !== (skillData.isFading ?? false)) {
            return { ...node, data: { ...skillData, isActive, isFading } }
          }
        }

        // Skill category nodes - set isActive and isFading when any skill in category was recently used
        if (node.data.type === 'skill-category') {
          const catData = node.data as SkillCategoryNodeData
          const skillUse = activityState.recentSkillUse.get(catData.parentAgentId)
          const isActive = skillUse ? catData.skills.some(s =>
            s.skillType === skillUse.skillType ||
            (skillUse.skillType === 'flows' && s.skillType === 'scheduler')
          ) : false
          const isFading = isActive && activityState.fadingAgents.has(catData.parentAgentId)
          if (isActive !== (catData.isActive ?? false) ||
              isFading !== (catData.isFading ?? false)) {
            return { ...node, data: { ...catData, isActive, isFading } }
          }
        }

        // Skill provider nodes - glow when parent skill is active
        if (node.data.type === 'skill-provider') {
          const provData = node.data as SkillProviderNodeData
          const skillUse = activityState.recentSkillUse.get(provData.parentAgentId)
          const isActive = skillUse ? (
            skillUse.skillType === provData.parentSkillType ||
            (skillUse.skillType === 'flows' && provData.parentSkillType === 'scheduler')
          ) : false
          const isFading = isActive && activityState.fadingAgents.has(provData.parentAgentId)
          if (isActive !== (provData.isActive ?? false) ||
              isFading !== (provData.isFading ?? false)) {
            return { ...node, data: { ...provData, isActive, isFading } }
          }
        }

        // Knowledge summary nodes - set isActive and isFading when KB was recently accessed
        if (node.data.type === 'knowledge-summary') {
          const kbData = node.data as KnowledgeSummaryNodeData
          const isActive = activityState.recentKbUse.has(kbData.parentAgentId)
          const isFading = isActive && activityState.fadingAgents.has(kbData.parentAgentId)
          if (isActive !== (kbData.isActive ?? false) ||
              isFading !== (kbData.isFading ?? false)) {
            return { ...node, data: { ...kbData, isActive, isFading } }
          }
        }

        // Channel nodes - set isGlowing and isFading when channel has recent activity
        if (node.data.type === 'channel') {
          const channelData = node.data as ChannelNodeData
          const isGlowing = activityState.activeChannels.has(channelData.channelType)
          const isFading = activityState.fadingChannels.has(channelData.channelType)
          if (isGlowing !== (channelData.isGlowing ?? false) ||
              isFading !== (channelData.isFading ?? false)) {
            return { ...node, data: { ...channelData, isGlowing, isFading } }
          }
        }

        return node
      }))
    }, [activityState, setNodes])

    // Fit view when autoFit is toggled on
    useEffect(() => {
      if (autoFit) {
        fitView({ padding: 0.2, duration: 300 })
      }
    }, [autoFit, fitView])

    const handleNodeClick = useCallback(
      (_: React.MouseEvent, node: GraphNode) => {
        onNodeClick?.(node)
      },
      [onNodeClick]
    )

    return (
      <div
        className="w-full h-full rounded-xl overflow-hidden border border-tsushin-border"
        role="application"
        aria-label="Interactive network graph visualization showing relationships between agents, channels, and other entities"
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={handleNodeClick}
          nodeTypes={nodeTypes}
          fitView={autoFit}
          fitViewOptions={{ padding: 0.2 }}
          proOptions={{ hideAttribution: true }}
          // Phase 2: Enable individual node dragging
          nodesDraggable={true}
          selectNodesOnDrag={false}  // CRITICAL: Prevents multi-node drag
          nodesConnectable={false}
          elementsSelectable={true}
          // Styling
          className="bg-tsushin-deep"
        >
          <Background
            variant={BackgroundVariant.Dots}
            gap={20}
            size={1}
            color="rgba(139, 146, 158, 0.15)"
          />
          <Controls
            className="!bg-tsushin-surface !border-tsushin-border !rounded-lg !shadow-card"
            showInteractive={false}
          />
          <MiniMap
            className="!bg-tsushin-surface !border-tsushin-border !rounded-lg"
            nodeColor={(node) => {
              if (node.type === 'agent') return '#3C5AFE'           // Blue
              if (node.type === 'channel') return '#00D9FF'         // Cyan
              if (node.type === 'project') return '#8B5CF6'         // Purple
              if (node.type === 'user') return '#F59E0B'            // Amber
              if (node.type === 'skill') return '#14B8A6'           // Teal
              if (node.type === 'skill-category') return '#14B8A6'  // Teal (same as skill)
              if (node.type === 'knowledge') return '#A855F7'       // Violet
              if (node.type === 'knowledge-summary') return '#A855F7' // Violet
              return '#484F58'
            }}
            maskColor="rgba(11, 15, 20, 0.8)"
          />
        </ReactFlow>
      </div>
    )
  }
)

/**
 * GraphCanvas wrapper that provides ReactFlowProvider context
 * Required for React Flow hooks to work properly
 */
const GraphCanvas = forwardRef<GraphCanvasRef, GraphCanvasProps>(
  function GraphCanvas(props, ref) {
    return (
      <ReactFlowProvider>
        <GraphCanvasInner ref={ref} {...props} />
      </ReactFlowProvider>
    )
  }
)

export default GraphCanvas
