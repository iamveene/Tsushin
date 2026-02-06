'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { api, Agent } from '@/lib/client'
import AgentMemoryManager from '@/components/AgentMemoryManager'
import AgentSkillsManager from '@/components/AgentSkillsManager'
import AgentKnowledgeManager from '@/components/AgentKnowledgeManager'
import AgentSandboxedToolsManager from '@/components/AgentSandboxedToolsManager'
import AgentConfigurationManager from '@/components/AgentConfigurationManager'
import AgentChannelsManager from '@/components/AgentChannelsManager'
import SharedKnowledgeViewer from '@/components/SharedKnowledgeViewer'
import {
  SettingsIcon, RadioIcon, BrainIcon, SparklesIcon, BookOpenIcon,
  LinkIcon, WrenchIcon, TheaterIcon, BotIcon, LightningIcon, KeyIcon, StarIcon, MicrophoneIcon
} from '@/components/ui/icons'

type Tab = 'configuration' | 'channels' | 'memory' | 'skills' | 'knowledge' | 'shared-knowledge' | 'custom-tools'

const VALID_TABS: Tab[] = ['configuration', 'channels', 'memory', 'skills', 'knowledge', 'shared-knowledge', 'custom-tools']

export default function AgentDetailPage() {
  const params = useParams()
  const router = useRouter()
  const searchParams = useSearchParams()
  const agentId = parseInt(params.id as string)

  const [agent, setAgent] = useState<Agent | null>(null)
  const [loading, setLoading] = useState(true)
  // BUG-011 Fix: Read initial tab from query params
  const initialTab = (searchParams.get('tab') as Tab) || 'configuration'
  const [activeTab, setActiveTab] = useState<Tab>(VALID_TABS.includes(initialTab) ? initialTab : 'configuration')
  const [skillsCount, setSkillsCount] = useState<number>(0)

  useEffect(() => {
    loadAgent()
  }, [agentId])

  // Listen for global refresh events
  useEffect(() => {
    const handleRefresh = () => {
      loadAgent()
    }
    window.addEventListener('tsushin:refresh', handleRefresh)
    return () => window.removeEventListener('tsushin:refresh', handleRefresh)
  }, [agentId])

  const loadAgent = async () => {
    setLoading(true)
    try {
      const agentData = await api.getAgent(agentId)
      setAgent(agentData)

      // Load skills count
      try {
        const skills = await api.getAgentSkills(agentId)
        setSkillsCount(skills.filter(s => s.is_enabled).length)
      } catch (err) {
        console.error('Failed to load skills:', err)
        setSkillsCount(0)
      }
    } catch (err) {
      console.error('Failed to load agent:', err)
      alert('Failed to load agent details')
      router.push('/agents')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-lg text-gray-600 dark:text-gray-400">Loading agent...</div>
      </div>
    )
  }

  if (!agent) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <p className="text-lg text-gray-600 dark:text-gray-400 mb-4">Agent not found</p>
          <button
            onClick={() => router.push('/agents')}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Back to Agents
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Header */}
      <div className="bg-white dark:bg-gray-800 shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center gap-4 mb-4">
            <button
              onClick={() => router.push('/agents')}
              className="text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 dark:text-gray-200"
            >
              ← Back
            </button>
            <div className="h-6 w-px bg-gray-300 dark:bg-gray-600"></div>
            <div className="flex-1">
              <div className="flex items-center gap-3">
                <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{agent.contact_name}</h1>
                {agent.is_default && (
                  <span className="px-2 py-1 text-xs font-medium bg-yellow-100 dark:bg-yellow-800/30 text-yellow-800 dark:text-yellow-200 rounded-full inline-flex items-center gap-1">
                    <StarIcon size={12} /> Default
                  </span>
                )}
                {agent.is_active ? (
                  <span className="px-2 py-1 text-xs font-medium bg-green-100 dark:bg-green-800/30 text-green-800 dark:text-green-200 rounded-full">
                    ✓ Active
                  </span>
                ) : (
                  <span className="px-2 py-1 text-xs font-medium bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-200 rounded-full">
                    ○ Inactive
                  </span>
                )}
              </div>
              <div className="mt-1 flex flex-wrap gap-4 text-sm text-gray-600 dark:text-gray-400">
                <span className="inline-flex items-center gap-1"><TheaterIcon size={14} /> Tone: {agent.tone_preset_name || 'Custom'}</span>
                <span className="inline-flex items-center gap-1"><BotIcon size={14} /> Model: {agent.model_name}</span>
                <span className="inline-flex items-center gap-1"><LightningIcon size={14} /> Skills: {skillsCount}</span>
                <span className="inline-flex items-center gap-1"><KeyIcon size={14} /> Keywords: {agent.keywords.length || 0}</span>
              </div>
            </div>
            <button
              onClick={() => setActiveTab('configuration')}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              <SettingsIcon size={16} /> Edit Configuration
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6">
        {/* Tabs */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow mb-6">
          <nav className="flex border-b">
            <button
              onClick={() => setActiveTab('configuration')}
              className={`px-6 py-4 font-medium text-sm border-b-2 transition-colors inline-flex items-center gap-1.5 ${activeTab === 'configuration'
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 dark:text-gray-100'
                }`}
            >
              <SettingsIcon size={16} /> Configuration
            </button>
            <button
              onClick={() => setActiveTab('channels')}
              className={`px-6 py-4 font-medium text-sm border-b-2 transition-colors inline-flex items-center gap-1.5 ${activeTab === 'channels'
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 dark:text-gray-100'
                }`}
            >
              <RadioIcon size={16} /> Channels
            </button>
            <button
              onClick={() => setActiveTab('memory')}
              className={`px-6 py-4 font-medium text-sm border-b-2 transition-colors inline-flex items-center gap-1.5 ${activeTab === 'memory'
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 dark:text-gray-100'
                }`}
            >
              <BrainIcon size={16} /> Memory Management
            </button>
            <button
              onClick={() => setActiveTab('skills')}
              className={`px-6 py-4 font-medium text-sm border-b-2 transition-colors inline-flex items-center gap-1.5 ${activeTab === 'skills'
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 dark:text-gray-100'
                }`}
            >
              <SparklesIcon size={16} /> Skills
            </button>
            <button
              onClick={() => setActiveTab('knowledge')}
              className={`px-6 py-4 font-medium text-sm border-b-2 transition-colors inline-flex items-center gap-1.5 ${activeTab === 'knowledge'
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 dark:text-gray-100'
                }`}
            >
              <BookOpenIcon size={16} /> Knowledge Base
            </button>
            <button
              onClick={() => setActiveTab('shared-knowledge')}
              className={`px-6 py-4 font-medium text-sm border-b-2 transition-colors inline-flex items-center gap-1.5 ${activeTab === 'shared-knowledge'
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 dark:text-gray-100'
                }`}
            >
              <LinkIcon size={16} /> Shared Knowledge
            </button>
            <button
              onClick={() => setActiveTab('custom-tools')}
              className={`px-6 py-4 font-medium text-sm border-b-2 transition-colors inline-flex items-center gap-1.5 ${activeTab === 'custom-tools'
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 dark:text-gray-100'
                }`}
            >
              <WrenchIcon size={16} /> Sandboxed Tools
            </button>
          </nav>
        </div>

        {/* Tab Content */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
          {activeTab === 'configuration' && (
            <AgentConfigurationManager agentId={agentId} />
          )}

          {activeTab === 'channels' && (
            <AgentChannelsManager agentId={agentId} />
          )}

          {activeTab === 'memory' && (
            <AgentMemoryManager agentId={agentId} agentName={agent.contact_name} />
          )}

          {activeTab === 'skills' && (
            <AgentSkillsManager agentId={agentId} />
          )}

          {activeTab === 'knowledge' && (
            <AgentKnowledgeManager agentId={agentId} />
          )}

          {activeTab === 'shared-knowledge' && (
            <SharedKnowledgeViewer agentId={agentId} />
          )}

          {activeTab === 'custom-tools' && (
            <AgentSandboxedToolsManager agentId={agentId} />
          )}
        </div>
      </div>
    </div>
  )
}
