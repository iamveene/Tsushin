'use client'

import { useState } from 'react'
import PaletteCategory from './palette/PaletteCategory'
import PaletteItem from './palette/PaletteItem'
import { CATEGORY_CARDINALITY } from './types'
import type { PaletteItemData } from './types'
import type { UseStudioDataReturn } from './hooks/useStudioData'
import type { UseAgentBuilderReturn } from './hooks/useAgentBuilder'

interface StudioLeftPanelProps { studioData: UseStudioDataReturn; builder: UseAgentBuilderReturn; onSave: () => void }

const Icon = ({ d, color }: { d: string; color: string }) => (
  <svg className={`w-4 h-4 ${color}`} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={d} /></svg>
)

export default function StudioLeftPanel({ studioData, builder, onSave }: StudioLeftPanelProps) {
  const [collapsed, setCollapsed] = useState(false)
  const handleItemToggle = (item: PaletteItemData) => { item.isAttached ? builder.detachProfile(item.categoryId, item.id) : builder.attachProfile(item.categoryId, item) }

  const personaItems: PaletteItemData[] = studioData.personas.map(p => ({ id: p.id, name: p.name, categoryId: 'persona' as const, nodeType: 'builder-persona' as const, isAttached: builder.state.attachedPersonaId === p.id, metadata: { role: p.role_description, personalityTraits: p.personality_traits, isActive: p.is_active } }))
  const channelItems: PaletteItemData[] = ['playground', 'whatsapp', 'telegram'].map(ch => ({ id: ch, name: ch.charAt(0).toUpperCase() + ch.slice(1), categoryId: 'channels' as const, nodeType: 'builder-channel' as const, isAttached: builder.state.attachedChannels.includes(ch), metadata: { channelType: ch } }))
  const skillItems: PaletteItemData[] = (studioData.skills || []).map(s => ({ id: s.skill_type, name: s.skill_name, categoryId: 'skills' as const, nodeType: 'builder-skill' as const, isAttached: builder.state.attachedSkills.some(as => as.skillType === s.skill_type), metadata: { skillId: s.id, skillType: s.skill_type, category: s.category, providerName: s.provider_name, isEnabled: s.is_enabled } }))
  const toolItems: PaletteItemData[] = studioData.tools.map(t => ({ id: t.id, name: t.name, categoryId: 'tools' as const, nodeType: 'builder-tool' as const, isAttached: builder.state.attachedTools.includes(t.id), metadata: { toolType: t.tool_type, isEnabled: t.is_enabled } }))
  const securityItems: PaletteItemData[] = studioData.sentinelProfiles.map(sp => ({ id: sp.id, name: sp.name, categoryId: 'security' as const, nodeType: 'builder-sentinel' as const, isAttached: builder.state.attachedSentinelProfileId === sp.id, metadata: { mode: sp.detection_mode, isSystem: sp.is_system } }))
  const knowledgeItems: PaletteItemData[] = (studioData.knowledge || []).map(k => ({ id: k.id, name: k.document_name, categoryId: 'knowledge' as const, nodeType: 'builder-knowledge' as const, isAttached: builder.state.attachedKnowledgeDocs.includes(k.id), metadata: { contentType: k.document_type, fileSize: k.file_size_bytes, status: k.status } }))
  const memoryItems: PaletteItemData[] = builder.state.agent ? [{ id: 'memory', name: 'Memory Configuration', categoryId: 'memory' as const, nodeType: 'builder-memory' as const, isAttached: true, metadata: { isolationMode: builder.state.agent.memoryIsolationMode, memorySize: builder.state.agent.memorySize, enableSemanticSearch: builder.state.agent.enableSemanticSearch } }] : []

  if (collapsed) return (
    <div className="absolute left-2 top-2 z-10">
      <button onClick={() => setCollapsed(false)} className="p-2 rounded-lg bg-tsushin-surface/90 backdrop-blur-sm border border-tsushin-border hover:border-tsushin-muted transition-colors" title="Show palette">
        <Icon d="M9 5l7 7-7 7" color="text-tsushin-slate" />
      </button>
    </div>
  )

  return (
    <div className="absolute left-2 top-2 bottom-2 z-10 w-64 flex flex-col bg-tsushin-deep/95 backdrop-blur-sm border border-tsushin-border rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-tsushin-border/50">
        <h3 className="text-sm font-medium text-white">Profiles</h3>
        <button onClick={() => setCollapsed(true)} className="p-1 rounded hover:bg-tsushin-surface transition-colors"><Icon d="M15 19l-7-7 7-7" color="text-tsushin-muted" /></button>
      </div>
      <div className="flex-1 overflow-y-auto studio-palette">
        <PaletteCategory title="Persona" icon={<Icon d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" color="text-purple-400" />} count={personaItems.length} attachedCount={personaItems.filter(i => i.isAttached).length} cardinality={CATEGORY_CARDINALITY.persona.label} defaultOpen>
          {personaItems.map(item => <PaletteItem key={item.id} item={item} disabled={!item.isAttached && builder.state.attachedPersonaId !== null} onDoubleClick={handleItemToggle} />)}
        </PaletteCategory>
        <PaletteCategory title="Channels" icon={<Icon d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z" color="text-cyan-400" />} count={channelItems.length} attachedCount={channelItems.filter(i => i.isAttached).length} cardinality={CATEGORY_CARDINALITY.channels.label} defaultOpen>
          {channelItems.map(item => <PaletteItem key={String(item.id)} item={item} onDoubleClick={handleItemToggle} />)}
        </PaletteCategory>
        <PaletteCategory title="Skills" icon={<Icon d="M11.42 15.17l-5.1-3.06a1 1 0 01-.42-.83V7.06a1 1 0 01.42-.83l5.1-3.06a1 1 0 011.16 0l5.1 3.06a1 1 0 01.42.83v4.22a1 1 0 01-.42.83l-5.1 3.06a1 1 0 01-1.16 0z" color="text-teal-400" />} count={skillItems.length} attachedCount={skillItems.filter(i => i.isAttached).length} cardinality={CATEGORY_CARDINALITY.skills.label}>
          {skillItems.map(item => <PaletteItem key={String(item.id)} item={item} onDoubleClick={handleItemToggle} />)}
        </PaletteCategory>
        <PaletteCategory title="Sandboxed Tools" icon={<Icon d="M21 7.5l-2.25-1.313M21 7.5v2.25m0-2.25l-2.25 1.313M3 7.5l2.25-1.313M3 7.5l2.25 1.313M3 7.5v2.25m9 3l2.25-1.313M12 12.75l-2.25-1.313M12 12.75V15m0 6.75l2.25-1.313M12 21.75V19.5m0 2.25l-2.25-1.313m0-16.875L12 2.25l2.25 1.313M21 14.25v2.25l-2.25 1.313m-13.5 0L3 16.5v-2.25" color="text-orange-400" />} count={toolItems.length} attachedCount={toolItems.filter(i => i.isAttached).length} cardinality={CATEGORY_CARDINALITY.tools.label}>
          {toolItems.map(item => <PaletteItem key={String(item.id)} item={item} onDoubleClick={handleItemToggle} />)}
        </PaletteCategory>
        <PaletteCategory title="Security" icon={<Icon d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" color="text-red-400" />} count={securityItems.length} attachedCount={securityItems.filter(i => i.isAttached).length} cardinality={CATEGORY_CARDINALITY.security.label}>
          {securityItems.map(item => <PaletteItem key={String(item.id)} item={item} disabled={!item.isAttached && builder.state.attachedSentinelProfileId !== null} onDoubleClick={handleItemToggle} />)}
        </PaletteCategory>
        <PaletteCategory title="Knowledge Base" icon={<Icon d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" color="text-violet-400" />} count={knowledgeItems.length} attachedCount={knowledgeItems.filter(i => i.isAttached).length} cardinality={CATEGORY_CARDINALITY.knowledge.label}>
          {knowledgeItems.map(item => <PaletteItem key={String(item.id)} item={item} onDoubleClick={handleItemToggle} />)}
        </PaletteCategory>
        <PaletteCategory title="Memory" icon={<Icon d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" color="text-blue-400" />} count={memoryItems.length} attachedCount={memoryItems.filter(i => i.isAttached).length} cardinality={CATEGORY_CARDINALITY.memory.label}>
          {memoryItems.map(item => <PaletteItem key={String(item.id)} item={item} disabled onDoubleClick={handleItemToggle} />)}
        </PaletteCategory>
      </div>
      <div className="p-3 border-t border-tsushin-border/50">
        <button onClick={onSave} disabled={!builder.isDirty || builder.isSaving}
          className={`w-full px-4 py-2 rounded-lg text-sm font-medium transition-all ${builder.isDirty ? 'bg-tsushin-indigo text-white hover:bg-tsushin-indigo/90 save-button-dirty' : 'bg-tsushin-surface text-tsushin-muted cursor-not-allowed'} ${builder.isSaving ? 'opacity-60 cursor-wait' : ''}`}>
          {builder.isSaving ? 'Saving...' : builder.isDirty ? 'Save Changes' : 'Saved'}
        </button>
      </div>
    </div>
  )
}
