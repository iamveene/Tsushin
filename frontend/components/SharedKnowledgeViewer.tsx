'use client'

import { useEffect, useState } from 'react'
import { api, SharedKnowledge, SharedMemoryStats } from '@/lib/client'
import { formatDateTimeFull } from '@/lib/dateUtils'
import { BookOpenIcon, FolderIcon } from '@/components/ui/icons'

interface Props {
  agentId: number
}

export default function SharedKnowledgeViewer({ agentId }: Props) {
  const [knowledge, setKnowledge] = useState<SharedKnowledge[]>([])
  const [stats, setStats] = useState<SharedMemoryStats | null>(null)
  const [topics, setTopics] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedTopic, setSelectedTopic] = useState<string>('')
  const [searchQuery, setSearchQuery] = useState('')
  const [expandedId, setExpandedId] = useState<number | null>(null)

  useEffect(() => {
    loadData()
  }, [agentId, selectedTopic])

  const loadData = async () => {
    setLoading(true)
    try {
      const [knowledgeData, statsData, topicsData] = await Promise.all([
        api.getSharedKnowledge(agentId, {
          topic: selectedTopic || undefined,
          limit: 50
        }),
        api.getSharedMemoryStats(agentId),
        api.getSharedMemoryTopics(agentId)
      ])
      setKnowledge(knowledgeData)
      setStats(statsData)
      setTopics(topicsData)
    } catch (err) {
      console.error('Failed to load shared knowledge:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleSearch = async () => {
    if (!searchQuery.trim()) {
      loadData()
      return
    }

    setLoading(true)
    try {
      const results = await api.searchSharedKnowledge(agentId, searchQuery, {
        topic: selectedTopic || undefined,
        limit: 50
      })
      setKnowledge(results)
    } catch (err) {
      console.error('Failed to search shared knowledge:', err)
      alert('Failed to search knowledge')
    } finally {
      setLoading(false)
    }
  }

  if (loading && knowledge.length === 0) {
    return <div className="p-8 text-center text-gray-600 dark:text-gray-400">Loading shared knowledge...</div>
  }

  return (
    <div className="space-y-6">
      {/* Header Info */}
      <div className="bg-blue-50 dark:bg-blue-900/20 border dark:border-gray-700 border-blue-200 dark:border-blue-700 rounded-lg p-4">
        <h3 className="text-sm font-medium text-blue-800 dark:text-blue-200 mb-2 inline-flex items-center gap-1"><BookOpenIcon size={14} /> Shared Knowledge Pool</h3>
        <p className="text-sm text-blue-700 dark:text-blue-300">
          This is the cross-agent knowledge sharing system. Facts and information extracted from conversations
          are stored here and accessible to all agents (based on permission settings).
        </p>
      </div>

      {/* Stats Summary */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-white dark:bg-gray-800 border dark:border-gray-700 rounded-lg p-4">
            <div className="text-sm text-gray-600 dark:text-gray-400">Total Shared</div>
            <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">{stats.total_shared}</div>
          </div>
          <div className="bg-white dark:bg-gray-800 border dark:border-gray-700 rounded-lg p-4">
            <div className="text-sm text-gray-600 dark:text-gray-400">Topics</div>
            <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">{Object.keys(stats.by_topic).length}</div>
          </div>
          <div className="bg-white dark:bg-gray-800 border dark:border-gray-700 rounded-lg p-4">
            <div className="text-sm text-gray-600 dark:text-gray-400">Sharing Agents</div>
            <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">{stats.sharing_agents}</div>
          </div>
          <div className="bg-white dark:bg-gray-800 border dark:border-gray-700 rounded-lg p-4">
            <div className="text-sm text-gray-600 dark:text-gray-400">Access Levels</div>
            <div className="text-sm font-medium text-gray-900 dark:text-gray-100 mt-2">
              {Object.entries(stats.by_access_level).map(([level, count]) => (
                <div key={level} className="flex justify-between">
                  <span className="capitalize">{level}:</span>
                  <span>{count}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Filters and Search */}
      <div className="bg-white dark:bg-gray-800 border dark:border-gray-700 rounded-lg p-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Topic Filter */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Filter by Topic
            </label>
            <select
              value={selectedTopic}
              onChange={(e) => setSelectedTopic(e.target.value)}
              className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
            >
              <option value="">All Topics</option>
              {topics.map(topic => (
                <option key={topic} value={topic}>{topic}</option>
              ))}
            </select>
          </div>

          {/* Search */}
          <div className="md:col-span-2">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Search Knowledge
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
                placeholder="Search for facts, information, or topics..."
                className="flex-1 px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
              />
              <button
                onClick={handleSearch}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
              >
                Search
              </button>
              <button
                onClick={() => {
                  setSearchQuery('')
                  loadData()
                }}
                className="px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700"
              >
                Clear
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Knowledge List */}
      <div className="bg-white dark:bg-gray-800 border dark:border-gray-700 rounded-lg">
        <div className="px-6 py-4 border-b dark:border-gray-700">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            Shared Knowledge ({knowledge.length})
          </h3>
        </div>

        {knowledge.length === 0 ? (
          <div className="p-12 text-center">
            <p className="text-gray-500 dark:text-gray-400 mb-2">No shared knowledge found</p>
            <p className="text-sm text-gray-400 dark:text-gray-500">
              Enable the Knowledge Sharing skill on agents to start building the shared knowledge pool
            </p>
          </div>
        ) : (
          <div className="divide-y divide-gray-200 dark:divide-gray-700">
            {knowledge.map((item) => (
              <div key={item.id} className="px-6 py-4 hover:bg-gray-50 dark:hover:bg-gray-700/50">
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    {/* Content Preview */}
                    <div className="text-sm text-gray-900 dark:text-gray-100 mb-2">
                      {expandedId === item.id ? (
                        <div className="whitespace-pre-wrap">{item.content}</div>
                      ) : (
                        <div className="line-clamp-2">{item.content}</div>
                      )}
                    </div>

                    {/* Metadata */}
                    <div className="flex flex-wrap gap-2 text-xs text-gray-600 dark:text-gray-400">
                      {item.topic && (
                        <span className="px-2 py-1 bg-purple-100 dark:bg-purple-800/30 text-purple-700 dark:text-purple-300 rounded inline-flex items-center gap-1">
                          <FolderIcon size={12} /> {item.topic}
                        </span>
                      )}
                      <span className="px-2 py-1 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded">
                        Agent #{item.shared_by_agent}
                      </span>
                      {item.meta_data?.confidence && (
                        <span className="px-2 py-1 bg-green-100 dark:bg-green-800/30 text-green-700 dark:text-green-300 rounded">
                          {Math.round(item.meta_data.confidence * 100)}% confidence
                        </span>
                      )}
                      {item.meta_data?.source && (
                        <span className="px-2 py-1 bg-blue-100 dark:bg-blue-800/30 text-blue-700 dark:text-blue-300 rounded">
                          from: {item.meta_data.source}
                        </span>
                      )}
                      <span className="text-gray-500 dark:text-gray-500">
                        {formatDateTimeFull(item.created_at)}
                      </span>
                    </div>

                    {/* Expanded Meta Data */}
                    {expandedId === item.id && item.meta_data && Object.keys(item.meta_data).length > 0 && (
                      <div className="mt-3 p-3 bg-gray-100 dark:bg-gray-900 rounded border dark:border-gray-700">
                        <div className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">Metadata:</div>
                        <pre className="text-xs text-gray-600 dark:text-gray-400 overflow-auto">
                          {JSON.stringify(item.meta_data, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>

                  {/* Toggle Button */}
                  <button
                    onClick={() => setExpandedId(expandedId === item.id ? null : item.id)}
                    className="ml-4 px-3 py-1 text-sm text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded"
                  >
                    {expandedId === item.id ? 'Collapse' : 'Expand'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Topic Distribution */}
      {stats && Object.keys(stats.by_topic).length > 0 && (
        <div className="bg-white dark:bg-gray-800 border dark:border-gray-700 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Knowledge by Topic</h3>
          <div className="space-y-3">
            {Object.entries(stats.by_topic)
              .sort(([, a], [, b]) => b - a)
              .map(([topic, count]) => (
                <div key={topic}>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="font-medium text-gray-700 dark:text-gray-300">{topic}</span>
                    <span className="text-gray-600 dark:text-gray-400">{count} items</span>
                  </div>
                  <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                    <div
                      className="bg-blue-600 h-2 rounded-full"
                      style={{ width: `${(count / stats.total_shared) * 100}%` }}
                    ></div>
                  </div>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  )
}
