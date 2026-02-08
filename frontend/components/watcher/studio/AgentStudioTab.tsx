'use client'

/**
 * Agent Studio Tab - Visual Agent Builder
 * "The Sims"-like agent configuration using React Flow canvas
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import dynamic from 'next/dynamic'
import StudioAgentSelector from './StudioAgentSelector'
import StudioLeftPanel from './StudioLeftPanel'
import { NodeConfigPanel } from './config'
import { useAgentBuilder } from './hooks/useAgentBuilder'
import { useStudioData } from './hooks/useStudioData'
import { api, type SkillDefinition } from '@/lib/client'
import type { StudioCanvasRef } from './StudioCanvas'
import type { DragTransferData, BuilderNodeData, BuilderNodeType, ConfigPanelTarget } from './types'
import './studio.css'

const StudioCanvasComponent = dynamic(() => import('./StudioCanvas'), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-96">
      <div className="text-center">
        <div className="relative w-12 h-12 mx-auto mb-4">
          <div className="absolute inset-0 rounded-full border-4 border-tsushin-surface"></div>
          <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-tsushin-indigo animate-spin"></div>
        </div>
        <p className="text-tsushin-slate font-medium">Loading Agent Studio...</p>
      </div>
    </div>
  ),
}) as typeof import('./StudioCanvas').default

const MaximizeIcon = ({ className }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5v-4m0 4h-4m4 0l-5-5" />
  </svg>
)

const MinimizeIcon = ({ className }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 9V4.5M9 9H4.5M9 9L3.75 3.75M9 15v4.5M9 15H4.5M9 15l-5.25 5.25M15 9h4.5M15 9V4.5M15 9l5.25-5.25M15 15h4.5M15 15v4.5m0-4.5l5.25 5.25" />
  </svg>
)

export default function AgentStudioTab() {
  const [selectedAgentId, setSelectedAgentId] = useState<number | null>(null)
  const [isMaximized, setIsMaximized] = useState(false)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null)
  const [configPanel, setConfigPanel] = useState<ConfigPanelTarget | null>(null)
  const [skillDefinitions, setSkillDefinitions] = useState<SkillDefinition[]>([])
  const canvasRef = useRef<StudioCanvasRef | null>(null)

  const studioData = useStudioData(selectedAgentId)
  const builder = useAgentBuilder(selectedAgentId, studioData)

  // Auto-select default agent on initial load or after refresh if selected agent is gone
  useEffect(() => {
    if (studioData.loading || studioData.agents.length === 0) return
    if (selectedAgentId === null) {
      const defaultAgent = studioData.agents.find(a => a.is_default)
      setSelectedAgentId(defaultAgent?.id ?? studioData.agents[0].id)
      return
    }
    if (!studioData.agents.some(a => a.id === selectedAgentId)) {
      const defaultAgent = studioData.agents.find(a => a.is_default)
      setSelectedAgentId(defaultAgent?.id ?? studioData.agents[0].id)
    }
  }, [selectedAgentId, studioData.agents, studioData.loading])

  // Load skill definitions once for schema-driven config forms
  useEffect(() => {
    api.getAvailableSkills().then(setSkillDefinitions).catch(() => {})
  }, [])

  const handleCanvasReady = useCallback((methods: StudioCanvasRef) => {
    canvasRef.current = methods
  }, [])

  useEffect(() => {
    const handleRefresh = () => studioData.refetch()
    window.addEventListener('tsushin:refresh', handleRefresh)
    return () => window.removeEventListener('tsushin:refresh', handleRefresh)
  }, [studioData.refetch])

  useEffect(() => {
    if (!isMaximized) return
    const handleEscape = (e: KeyboardEvent) => { if (e.key === 'Escape') setIsMaximized(false) }
    window.addEventListener('keydown', handleEscape)
    return () => window.removeEventListener('keydown', handleEscape)
  }, [isMaximized])

  useEffect(() => {
    if (isMaximized) { document.body.style.overflow = 'hidden' } else { document.body.style.overflow = '' }
    return () => { document.body.style.overflow = '' }
  }, [isMaximized])

  useEffect(() => {
    const t = setTimeout(() => canvasRef.current?.fitView(), 350)
    return () => clearTimeout(t)
  }, [isMaximized])

  useEffect(() => {
    if (!toast) return
    const timer = setTimeout(() => setToast(null), 3000)
    return () => clearTimeout(timer)
  }, [toast])

  // Close config panel when agent changes
  useEffect(() => {
    setConfigPanel(null)
  }, [selectedAgentId])

  const handleNodeDoubleClick = useCallback((nodeId: string, nodeType: string, nodeData: BuilderNodeData) => {
    setConfigPanel({ nodeId, nodeType: nodeType as BuilderNodeType, nodeData })
  }, [])

  const handleConfigPanelClose = useCallback(() => {
    setConfigPanel(null)
  }, [])

  const handleSave = async () => {
    try {
      await builder.save()
      setToast({ type: 'success', message: 'Agent configuration saved successfully' })
      studioData.refetch()
    } catch (err) {
      setToast({ type: 'error', message: err instanceof Error ? err.message : 'Failed to save' })
    }
  }

  const handleDrop = useCallback((data: DragTransferData) => {
    builder.attachProfile(data.categoryId, {
      id: data.itemId, name: data.itemName, categoryId: data.categoryId,
      nodeType: data.nodeType, isAttached: false, metadata: data.metadata,
    })
  }, [builder.attachProfile])

  const handleDeleteSelected = useCallback((nodeIds: string[]) => {
    for (const nodeId of nodeIds) {
      const node = builder.nodes.find(n => n.id === nodeId)
      if (!node || node.data.type === 'builder-agent' || node.data.type === 'builder-group') continue
      const data = node.data
      let categoryId: string | undefined
      let itemId: string | number | undefined
      if (data.type === 'builder-persona') { categoryId = 'persona'; itemId = data.personaId }
      else if (data.type === 'builder-channel') { categoryId = 'channels'; itemId = data.channelType }
      else if (data.type === 'builder-skill') { categoryId = 'skills'; itemId = data.skillType }
      else if (data.type === 'builder-tool') { categoryId = 'tools'; itemId = data.toolId }
      else if (data.type === 'builder-sentinel') { categoryId = 'security'; itemId = data.profileId }
      else if (data.type === 'builder-knowledge') { categoryId = 'knowledge'; itemId = data.docId }
      if (categoryId && itemId !== undefined) {
        builder.detachProfile(categoryId as any, itemId)
      }
    }
  }, [builder.nodes, builder.detachProfile])

  const handleAgentCreated = useCallback((agentId: number) => {
    setSelectedAgentId(agentId)
    studioData.refetch()
  }, [studioData.refetch])

  if (studioData.loading && !studioData.agents.length) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <div className="relative w-12 h-12 mx-auto mb-4">
            <div className="absolute inset-0 rounded-full border-4 border-tsushin-surface"></div>
            <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-tsushin-indigo animate-spin"></div>
          </div>
          <p className="text-tsushin-slate font-medium">Loading studio data...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4 animate-fade-in">
      <div className="flex items-center justify-between">
        <StudioAgentSelector agents={studioData.agents} selectedAgentId={selectedAgentId} onAgentSelect={setSelectedAgentId} onAgentCreated={handleAgentCreated} />
        <div className="flex items-center gap-3">
          {selectedAgentId && (
            <button onClick={handleSave} disabled={!builder.isDirty || builder.isSaving}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${builder.isDirty ? 'bg-tsushin-indigo text-white hover:bg-tsushin-indigo/90 save-button-dirty' : 'bg-tsushin-surface text-tsushin-muted cursor-not-allowed'} ${builder.isSaving ? 'opacity-60 cursor-wait' : ''}`}>
              {builder.isSaving ? 'Saving...' : builder.isDirty ? 'Save Changes' : 'Saved'}
            </button>
          )}
          <button onClick={() => setIsMaximized(!isMaximized)} className="p-2 rounded-lg bg-tsushin-surface border border-tsushin-border hover:border-tsushin-muted transition-colors" title={isMaximized ? 'Exit fullscreen' : 'Fullscreen'}>
            {isMaximized ? <MinimizeIcon className="w-4 h-4 text-tsushin-slate" /> : <MaximizeIcon className="w-4 h-4 text-tsushin-slate" />}
          </button>
        </div>
      </div>

      {isMaximized && <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40" onClick={() => setIsMaximized(false)} />}

      <div className={`${isMaximized ? 'fixed inset-4 z-50 h-auto' : 'h-[600px] relative'} glass-card rounded-xl p-1 transition-all duration-300`}>
        {selectedAgentId ? (
          <>
            <StudioLeftPanel studioData={studioData} builder={builder} onSave={handleSave} />
            <StudioCanvasComponent nodes={builder.nodes} edges={builder.edges} onNodesChange={builder.onNodesChange} onDrop={handleDrop} onDeleteSelected={handleDeleteSelected} onNodeDoubleClick={handleNodeDoubleClick} onReady={handleCanvasReady} onExpandAll={builder.expandAll} onCollapseAll={builder.collapseAll} onResetLayout={builder.resetLayout} hasAnyExpanded={builder.expandedCategories.size > 0} />
            {configPanel && (() => {
              const liveNode = builder.nodes.find(n => n.id === configPanel.nodeId)
              const liveData = liveNode?.data || configPanel.nodeData
              return (
                <NodeConfigPanel
                  isOpen={!!configPanel}
                  nodeId={configPanel.nodeId}
                  nodeType={configPanel.nodeType}
                  nodeData={liveData}
                  onClose={handleConfigPanelClose}
                  onUpdate={builder.updateNodeConfig}
                  skillDefinitions={skillDefinitions}
                />
              )
            })()}
          </>
        ) : (
          <div className="flex items-center justify-center h-full">
            <div className="text-center max-w-md">
              <svg className="w-16 h-16 text-tsushin-muted mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" />
              </svg>
              <h3 className="text-lg font-medium text-white mb-2">Select an Agent</h3>
              <p className="text-tsushin-slate text-sm">Choose an agent from the dropdown above to start building its configuration visually. You can also create a new agent with the + button.</p>
            </div>
          </div>
        )}
      </div>

      {toast && (
        <div className={`fixed bottom-6 right-6 z-[100] px-4 py-3 rounded-lg shadow-lg flex items-center gap-2 animate-fade-in ${toast.type === 'success' ? 'bg-green-500/20 border border-green-500/30 text-green-300' : 'bg-red-500/20 border border-red-500/30 text-red-300'}`}>
          <span className="text-sm">{toast.message}</span>
          <button onClick={() => setToast(null)} className="ml-2 text-current opacity-60 hover:opacity-100">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>
      )}
    </div>
  )
}
