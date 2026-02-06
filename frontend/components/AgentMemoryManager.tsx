'use client'

import { useEffect, useState } from 'react'
import { api, MemoryStats, ConversationSummary, ConversationDetails, Agent } from '@/lib/client'
import { formatDateTimeFull } from '@/lib/dateUtils'
import { LockIcon, DatabaseIcon, MessageIcon, TrashIcon, MessagesSquareIcon, AlertTriangleIcon, MessageSquareIcon, BrainIcon, BookOpenIcon } from '@/components/ui/icons'

interface Props {
  agentId: number
  agentName: string
}

export default function AgentMemoryManager({ agentId, agentName }: Props) {
  const [agent, setAgent] = useState<Agent | null>(null)
  const [stats, setStats] = useState<MemoryStats | null>(null)
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [selectedConversation, setSelectedConversation] = useState<ConversationDetails | null>(null)
  const [selectedSenderKey, setSelectedSenderKey] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [cleanDays, setCleanDays] = useState(30)
  const [cleanPreview, setCleanPreview] = useState<{ deleted_count: number; preview: string[] } | null>(null)
  const [showResetConfirm, setShowResetConfirm] = useState(false)

  // Memory Configuration state
  const [memorySize, setMemorySize] = useState<number | null>(null)
  const [memoryIsolationMode, setMemoryIsolationMode] = useState('isolated')
  const [contextMessageCount, setContextMessageCount] = useState<number | null>(null)
  const [contextCharLimit, setContextCharLimit] = useState<number | null>(null)
  const [enableSemanticSearch, setEnableSemanticSearch] = useState<boolean>(false)
  const [semanticSearchResults, setSemanticSearchResults] = useState<number>(5)
  const [semanticSimilarityThreshold, setSemanticSimilarityThreshold] = useState<number>(0.5)

  useEffect(() => {
    loadData()
  }, [agentId])

  const loadData = async () => {
    setLoading(true)
    try {
      const [agentData, statsData, conversationsData] = await Promise.all([
        api.getAgent(agentId),
        api.getAgentMemoryStats(agentId).catch(() => null),
        api.getAgentConversations(agentId).catch(() => []),
      ])

      setAgent(agentData)
      setStats(statsData)
      setConversations(conversationsData)

      // Load memory configuration from agent
      setMemorySize(agentData.memory_size ?? null)
      setMemoryIsolationMode(agentData.memory_isolation_mode || 'isolated')
      setContextMessageCount(agentData.context_message_count ?? null)
      setContextCharLimit(agentData.context_char_limit ?? null)
      setEnableSemanticSearch(agentData.enable_semantic_search || false)
      setSemanticSearchResults(agentData.semantic_search_results || 5)
      setSemanticSimilarityThreshold(agentData.semantic_similarity_threshold || 0.5)
    } catch (err) {
      console.error('Failed to load memory data:', err)
      // Don't alert - Phase 5.0 not implemented yet
    } finally {
      setLoading(false)
    }
  }

  const viewConversation = async (senderKey: string) => {
    try {
      const details = await api.getConversationDetails(agentId, senderKey)
      setSelectedConversation(details)
      setSelectedSenderKey(senderKey)
    } catch (err) {
      console.error('Failed to load conversation:', err)
      alert('Failed to load conversation details')
    }
  }

  const deleteConversation = async (senderKey: string) => {
    if (!confirm(`Delete all memory for ${senderKey}?\n\nThis will remove:\n- Working memory (ring buffer)\n- Episodic memory (vector store)\n- Semantic facts\n\nThis action cannot be undone.`)) {
      return
    }

    try {
      await api.deleteConversation(agentId, senderKey)
      alert('Conversation deleted successfully')
      setSelectedConversation(null)
      setSelectedSenderKey(null)
      loadData()
    } catch (err) {
      console.error('Failed to delete conversation:', err)
      alert('Failed to delete conversation')
    }
  }

  const previewCleanOldMessages = async () => {
    try {
      const result = await api.cleanOldMessages(agentId, cleanDays, true)
      setCleanPreview(result)
    } catch (err) {
      console.error('Failed to preview clean:', err)
      alert('Failed to preview clean operation')
    }
  }

  const executeCleanOldMessages = async () => {
    if (!cleanPreview) return

    if (!confirm(`Delete ${cleanPreview.deleted_count} messages older than ${cleanDays} days?\n\nThis action cannot be undone.`)) {
      return
    }

    try {
      await api.cleanOldMessages(agentId, cleanDays, false)
      alert(`Successfully deleted ${cleanPreview.deleted_count} old messages`)
      setCleanPreview(null)
      loadData()
    } catch (err) {
      console.error('Failed to clean old messages:', err)
      alert('Failed to clean old messages')
    }
  }

  const resetMemory = async () => {
    if (!showResetConfirm) {
      setShowResetConfirm(true)
      return
    }

    const confirmToken = prompt(`⚠️ NUCLEAR OPTION ⚠️\n\nYou are about to delete ALL memory for ${agentName}.\n\nThis will permanently erase:\n- All conversations\n- All working memory\n- All episodic memory\n- All semantic facts\n\nType the agent name to confirm:`)

    if (confirmToken !== agentName) {
      alert('Agent name did not match. Reset cancelled.')
      setShowResetConfirm(false)
      return
    }

    try {
      await api.resetAgentMemory(agentId, confirmToken)
      alert('Agent memory has been completely reset')
      setShowResetConfirm(false)
      setSelectedConversation(null)
      setSelectedSenderKey(null)
      loadData()
    } catch (err) {
      console.error('Failed to reset memory:', err)
      alert('Failed to reset memory')
      setShowResetConfirm(false)
    }
  }

  // Save memory configuration
  const saveMemoryConfig = async () => {
    setSaving(true)
    try {
      const payload: any = {
        memory_size: memorySize,
        memory_isolation_mode: memoryIsolationMode,
        context_message_count: contextMessageCount,
        context_char_limit: contextCharLimit,
        enable_semantic_search: enableSemanticSearch,
        semantic_search_results: semanticSearchResults,
        semantic_similarity_threshold: semanticSimilarityThreshold,
      }

      await api.updateAgent(agentId, payload)
      alert('Memory configuration saved successfully!')
      await loadData()
    } catch (err: any) {
      console.error('Failed to save:', err)
      alert(err.message || 'Failed to save memory configuration')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="p-8 text-center">Loading memory data...</div>
  }

  // Phase 5.0 not implemented yet
  if (!stats) {
    return (
      <div className="p-8">
        <div className="border dark:border-yellow-700 rounded-lg p-6 bg-yellow-50 dark:bg-yellow-900/20">
          <h3 className="text-lg font-semibold mb-2 text-yellow-800 dark:text-yellow-200 flex items-center gap-2">
            <AlertTriangleIcon size={20} /> Memory Management (Phase 5.0)
          </h3>
          <p className="text-sm text-yellow-700 dark:text-yellow-300 mb-4">
            Advanced memory management features are planned for Phase 5.0 and are not yet implemented.
          </p>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            <strong>Planned Features:</strong>
          </p>
          <ul className="list-disc list-inside text-sm text-gray-600 dark:text-gray-400 mt-2 space-y-1">
            <li>View conversation history per user</li>
            <li>Manage working memory (ring buffer)</li>
            <li>Browse episodic memory (vector embeddings)</li>
            <li>Clean old messages by date range</li>
            <li>Reset agent memory completely</li>
            <li>Memory usage statistics and analytics</li>
          </ul>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Memory Statistics */}
      {stats && (
        <div className="grid grid-cols-4 gap-4">
          <div className="border dark:border-gray-700 rounded-lg p-4 bg-blue-50 dark:bg-blue-900/20">
            <div className="text-sm text-gray-600 dark:text-gray-400 mb-1">Total Conversations</div>
            <div className="text-2xl font-bold text-blue-600">{stats.total_conversations}</div>
          </div>
          <div className="border dark:border-gray-700 rounded-lg p-4 bg-green-50 dark:bg-green-900/20">
            <div className="text-sm text-gray-600 dark:text-gray-400 mb-1">Total Messages</div>
            <div className="text-2xl font-bold text-green-600">{stats.total_messages}</div>
          </div>
          <div className="border dark:border-gray-700 rounded-lg p-4 bg-purple-50 dark:bg-purple-900/20">
            <div className="text-sm text-gray-600 dark:text-gray-400 mb-1">Vector Embeddings</div>
            <div className="text-2xl font-bold text-purple-600">{stats.total_embeddings}</div>
          </div>
          <div className="border dark:border-gray-700 rounded-lg p-4 bg-orange-50 dark:bg-orange-900/20">
            <div className="text-sm text-gray-600 dark:text-gray-400 mb-1">Storage Size</div>
            <div className="text-2xl font-bold text-orange-600">{stats.storage_size_mb.toFixed(2)} MB</div>
          </div>
        </div>
      )}

      {/* Memory Isolation Mode */}
      <div className="border dark:border-gray-700 rounded-lg p-4 bg-white dark:bg-gray-900">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2"><LockIcon size={20} /> Memory Isolation Mode</h3>
        <div className="space-y-2">
          <label className="flex items-center gap-2">
            <input
              type="radio"
              name="memory_isolation_mode"
              value="isolated"
              checked={memoryIsolationMode === 'isolated'}
              onChange={(e) => setMemoryIsolationMode(e.target.value)}
              className="text-blue-600"
            />
            <div>
              <div className="font-medium">Isolated</div>
              <div className="text-sm text-gray-600 dark:text-gray-400">
                Separate memory per agent (each agent has isolated ChromaDB directory)
              </div>
            </div>
          </label>
          <label className="flex items-center gap-2">
            <input
              type="radio"
              name="memory_isolation_mode"
              value="channel_isolated"
              checked={memoryIsolationMode === 'channel_isolated'}
              onChange={(e) => setMemoryIsolationMode(e.target.value)}
              className="text-blue-600"
            />
            <div>
              <div className="font-medium">Channel Isolated</div>
              <div className="text-sm text-gray-600 dark:text-gray-400">
                Separate memory per channel (groups/DMs isolated within agent)
              </div>
            </div>
          </label>
          <label className="flex items-center gap-2">
            <input
              type="radio"
              name="memory_isolation_mode"
              value="shared"
              checked={memoryIsolationMode === 'shared'}
              onChange={(e) => setMemoryIsolationMode(e.target.value)}
              className="text-blue-600"
            />
            <div>
              <div className="font-medium">Shared</div>
              <div className="text-sm text-gray-600 dark:text-gray-400">
                Shared memory across all channels (single ChromaDB for entire agent)
              </div>
            </div>
          </label>
        </div>
      </div>

      {/* Memory Configuration */}
      <div className="border dark:border-gray-700 rounded-lg p-4 bg-white dark:bg-gray-900">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2"><DatabaseIcon size={20} /> Memory Configuration</h3>

        <div className="space-y-4">
          {/* Memory Size */}
          <div>
            <label className="block text-sm font-medium mb-2">
              Memory Size (messages per sender)
              <span className="text-gray-500 dark:text-gray-400 ml-2 font-normal">
                {memorySize === null ? '(Using system default)' : ''}
              </span>
            </label>
            <input
              type="number"
              min="1"
              max="5000"
              value={memorySize ?? ''}
              onChange={(e) => setMemorySize(e.target.value ? parseInt(e.target.value) : null)}
              placeholder="Use system default (1000)"
              className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
            />
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              Number of recent messages to remember per sender (1-5000). Leave empty to use system default (1000).
            </p>
          </div>

          {/* Semantic Search Configuration */}
          <div className="space-y-4 pt-4 border-t dark:border-gray-700">
            <div>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={enableSemanticSearch}
                  onChange={(e) => setEnableSemanticSearch(e.target.checked)}
                  className="rounded"
                />
                <span className="text-sm font-medium">Enable Semantic Search</span>
              </label>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 ml-6">
                Use vector embeddings to find semantically similar past messages
              </p>
            </div>

            {enableSemanticSearch && (
              <>
                <div>
                  <label className="block text-sm font-medium mb-2">
                    Number of Semantic Results
                  </label>
                  <input
                    type="number"
                    min="1"
                    max="50"
                    value={semanticSearchResults}
                    onChange={(e) => setSemanticSearchResults(parseInt(e.target.value) || 5)}
                    className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    Number of semantically similar messages to include (1-50)
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">
                    Similarity Threshold
                  </label>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={semanticSimilarityThreshold}
                    onChange={(e) => setSemanticSimilarityThreshold(parseFloat(e.target.value))}
                    className="w-full"
                  />
                  <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400">
                    <span>0% (any similarity)</span>
                    <span className="font-medium">{(semanticSimilarityThreshold * 100).toFixed(0)}%</span>
                    <span>100% (exact match)</span>
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    Minimum similarity score to include a message (higher = more relevant)
                  </p>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Group Message Context */}
      <div className="border dark:border-gray-700 rounded-lg p-4 bg-white dark:bg-gray-900">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2"><MessageIcon size={20} /> Group Message Context</h3>

        <div className="space-y-4">
          {/* Context Message Count */}
          <div>
            <label className="block text-sm font-medium mb-2">
              Context Message Count
              <span className="text-gray-500 dark:text-gray-400 ml-2 font-normal">
                {contextMessageCount === null ? '(Using system default)' : ''}
              </span>
            </label>
            <input
              type="number"
              min="1"
              max="5000"
              value={contextMessageCount ?? ''}
              onChange={(e) => setContextMessageCount(e.target.value ? parseInt(e.target.value) : null)}
              placeholder="Use system default (10)"
              className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
            />
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              Number of recent group messages to include as context (1-5000). Leave empty to use system default (10).
            </p>
          </div>

          {/* Context Character Limit */}
          <div>
            <label className="block text-sm font-medium mb-2">
              Context Character Limit
              <span className="text-gray-500 dark:text-gray-400 ml-2 font-normal">
                {contextCharLimit === null ? '(Using system default)' : ''}
              </span>
            </label>
            <input
              type="number"
              min="100"
              max="100000"
              value={contextCharLimit ?? ''}
              onChange={(e) => setContextCharLimit(e.target.value ? parseInt(e.target.value) : null)}
              placeholder="Use system default (1000)"
              className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
            />
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              Maximum characters for group context (100-100000). Leave empty to use system default (1000).
            </p>
          </div>
        </div>
      </div>

      {/* Save Button */}
      <div className="flex justify-end">
        <button
          onClick={saveMemoryConfig}
          disabled={saving}
          className="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
        >
          {saving ? 'Saving...' : 'Save Memory Configuration'}
        </button>
      </div>

      {/* Bulk Actions */}
      <div className="border dark:border-gray-700 rounded-lg p-4 bg-gray-50 dark:bg-gray-900">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2"><TrashIcon size={20} /> Bulk Actions</h3>

        {/* Clean Old Messages */}
        <div className="mb-4">
          <label className="block text-sm font-medium mb-2">Clean Old Messages</label>
          <div className="flex gap-2">
            <input
              type="number"
              value={cleanDays}
              onChange={(e) => setCleanDays(parseInt(e.target.value) || 1)}
              className="px-3 py-2 border dark:border-gray-700 rounded-md w-24 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              min="1"
            />
            <span className="py-2 text-sm text-gray-600 dark:text-gray-400">days old</span>
            <button
              onClick={previewCleanOldMessages}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
            >
              Preview
            </button>
            {cleanPreview && (
              <button
                onClick={executeCleanOldMessages}
                className="px-4 py-2 bg-orange-600 text-white rounded-md hover:bg-orange-700"
              >
                Delete {cleanPreview.deleted_count} Messages
              </button>
            )}
          </div>
          {cleanPreview && (
            <div className="mt-2 p-2 bg-orange-50 dark:bg-orange-900/20 border dark:border-gray-700 border-orange-200 rounded text-xs">
              <p className="font-medium">Preview: {cleanPreview.deleted_count} messages will be deleted</p>
              <ul className="list-disc list-inside mt-1 text-gray-600 dark:text-gray-400">
                {cleanPreview.preview.slice(0, 5).map((msg, i) => (
                  <li key={i}>{msg}</li>
                ))}
                {cleanPreview.preview.length > 5 && <li>...and {cleanPreview.preview.length - 5} more</li>}
              </ul>
            </div>
          )}
        </div>

        {/* Reset All Memory */}
        <div>
          <label className="text-sm font-medium mb-2 text-red-600 flex items-center gap-2"><AlertTriangleIcon size={16} /> Reset All Memory (Destructive)</label>
          <button
            onClick={resetMemory}
            className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700"
          >
            {showResetConfirm ? 'Click Again to Confirm' : 'Reset All Memory'}
          </button>
          {showResetConfirm && (
            <span className="ml-3 text-sm text-red-600">
              This will permanently delete ALL memory for {agentName}
            </span>
          )}
        </div>
      </div>

      {/* Conversation List */}
      <div className="border dark:border-gray-700 rounded-lg overflow-hidden">
        <div className="bg-gray-100 dark:bg-gray-800 px-4 py-3 border-b">
          <h3 className="text-lg font-semibold flex items-center gap-2"><MessagesSquareIcon size={20} /> Conversations</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 dark:bg-gray-900 border-b">
              <tr>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-600 dark:text-gray-400">Sender</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-600 dark:text-gray-400">Messages</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-600 dark:text-gray-400">Last Activity</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-gray-600 dark:text-gray-400">Actions</th>
              </tr>
            </thead>
            <tbody>
              {conversations.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">
                    No conversations found
                  </td>
                </tr>
              ) : (
                conversations.map((conv) => (
                  <tr
                    key={conv.sender_key}
                    className={`border-b hover:bg-gray-50 dark:hover:bg-gray-700 dark:bg-gray-900 ${selectedSenderKey === conv.sender_key ? 'bg-blue-50 dark:bg-blue-900/20' : ''}`}
                  >
                    <td className="px-4 py-3">
                      <div className="font-medium">{conv.sender_name || conv.sender_key}</div>
                      {conv.sender_name && (
                        <div className="text-xs text-gray-500 dark:text-gray-400">{conv.sender_key}</div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-sm">{conv.message_count}</td>
                    <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">
                      {formatDateTimeFull(conv.last_activity)}
                    </td>
                    <td className="px-4 py-3 text-right space-x-2">
                      <button
                        onClick={() => viewConversation(conv.sender_key)}
                        className="px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700"
                      >
                        View
                      </button>
                      <button
                        onClick={() => deleteConversation(conv.sender_key)}
                        className="px-3 py-1 bg-red-600 text-white text-sm rounded hover:bg-red-700"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Conversation Details Modal */}
      {selectedConversation && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-gray-800 rounded-lg max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col">
            <div className="bg-gray-100 dark:bg-gray-800 px-6 py-4 border-b flex justify-between items-center">
              <h3 className="text-lg font-semibold">Conversation: {selectedSenderKey}</h3>
              <button
                onClick={() => setSelectedConversation(null)}
                className="text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 dark:text-gray-200"
              >
                ✕
              </button>
            </div>

            <div className="overflow-y-auto p-6 space-y-6 flex-1">
              {/* Working Memory */}
              <div>
                <h4 className="font-semibold mb-3 flex items-center gap-2"><MessageSquareIcon size={18} /> Working Memory (Ring Buffer)</h4>
                <div className="space-y-2">
                  {selectedConversation.working_memory.map((msg, i) => (
                    <div key={i} className="border dark:border-gray-700 rounded p-3 bg-gray-50 dark:bg-gray-900">
                      <div className="flex justify-between mb-1">
                        <span className={`text-sm font-medium ${msg.role === 'user' ? 'text-blue-600' : 'text-green-600'}`}>
                          {msg.role.toUpperCase()}
                        </span>
                        <span className="text-xs text-gray-500 dark:text-gray-400">{formatDateTimeFull(msg.timestamp)}</span>
                      </div>
                      <p className="text-sm">{msg.content}</p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Episodic Memory */}
              <div>
                <h4 className="font-semibold mb-3 flex items-center gap-2"><BrainIcon size={18} /> Episodic Memory (Semantic Search)</h4>
                <div className="space-y-2">
                  {selectedConversation.episodic_memory.length === 0 ? (
                    <p className="text-sm text-gray-500 dark:text-gray-400">No episodic memories found</p>
                  ) : (
                    selectedConversation.episodic_memory.map((mem, i) => (
                      <div key={i} className="border dark:border-gray-700 rounded p-3 bg-purple-50 dark:bg-purple-900/20">
                        <div className="flex justify-between mb-1">
                          <span className="text-xs text-purple-600 font-medium">
                            Similarity: {(mem.similarity * 100).toFixed(1)}%
                          </span>
                          <span className="text-xs text-gray-500 dark:text-gray-400">{formatDateTimeFull(mem.timestamp)}</span>
                        </div>
                        <p className="text-sm">{mem.content}</p>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* Semantic Facts */}
              <div>
                <h4 className="font-semibold mb-3 flex items-center gap-2"><BookOpenIcon size={18} /> Semantic Facts (Learned Knowledge)</h4>
                {Object.keys(selectedConversation.semantic_facts).length === 0 ? (
                  <p className="text-sm text-gray-500 dark:text-gray-400">No learned facts yet</p>
                ) : (
                  <div className="grid grid-cols-2 gap-4">
                    {Object.entries(selectedConversation.semantic_facts).map(([topic, facts]: [string, any]) => (
                      <div key={topic} className="border dark:border-gray-700 rounded p-3 bg-green-50 dark:bg-green-900/20">
                        <h5 className="font-medium text-sm mb-2 text-green-700 dark:text-green-300">{topic}</h5>
                        <ul className="space-y-1">
                          {Object.entries(facts).map(([key, value]: [string, any]) => (
                            <li key={key} className="text-sm">
                              <span className="font-medium">{key}:</span> {value.value}
                              {value.confidence && (
                                <span className="text-xs text-gray-500 dark:text-gray-400 ml-1">
                                  ({(value.confidence * 100).toFixed(0)}% confidence)
                                </span>
                              )}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="bg-gray-100 dark:bg-gray-800 px-6 py-4 border-t">
              <button
                onClick={() => setSelectedConversation(null)}
                className="px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
