'use client'

/**
 * Conversations Tab - Message & Agent Execution Monitoring
 *
 * Detailed view of:
 * - Message history with filter status
 * - Agent execution logs with expandable details
 * - Tool usage tracking
 * - Memory context indicators
 */

import { useEffect, useState } from 'react'
import { api, type Message, type AgentRun } from '@/lib/client'
import { formatTime } from '@/lib/dateUtils'
import {
  InboxIcon, BotIcon, BrainIcon, WrenchIcon, GamepadIcon,
  SearchIcon, CloudSunIcon, PlaneIcon, MessageIcon, ClipboardIcon,
  RefreshIcon, MicrophoneIcon, LightningIcon, SendIcon, GlobeIcon,
  ChartBarIcon, AlertTriangleIcon, CheckIcon, XIcon,
  ChevronDownIcon, ChevronRightIcon
} from '@/components/ui/icons'

export default function ConversationsTab() {
  const [messages, setMessages] = useState<Message[]>([])
  const [agentRuns, setAgentRuns] = useState<AgentRun[]>([])
  const [memoryStats, setMemoryStats] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [expandedRun, setExpandedRun] = useState<number | null>(null)
  const [activeView, setActiveView] = useState<'messages' | 'agent-runs'>('agent-runs')
  const [messagesLimit, setMessagesLimit] = useState(10)
  const [agentRunsLimit, setAgentRunsLimit] = useState(10)
  const [channelFilter, setChannelFilter] = useState<string>('all')  // Phase 10.1.1: Channel filter

  useEffect(() => {
    loadData()
    const interval = setInterval(loadData, 5000) // Poll every 5s

    // Listen for global refresh events
    const handleRefresh = () => {
      console.log('[ConversationsTab] Refresh event received')
      loadData()
    }
    window.addEventListener('tsushin:refresh', handleRefresh)

    return () => {
      clearInterval(interval)
      window.removeEventListener('tsushin:refresh', handleRefresh)
    }
  }, [])

  const loadData = async () => {
    try {
      const [msgs, runs, stats] = await Promise.all([
        api.getMessages(50),
        api.getAgentRuns(50),
        api.getMemoryStats()
      ])
      setMessages(msgs)
      setAgentRuns(runs)
      setMemoryStats(stats)
    } catch (err) {
      console.error('Failed to load data:', err)
    } finally {
      setLoading(false)
    }
  }

  // Phase 10.1.1: Channel badge helper
  const getChannelBadge = (channel?: string) => {
    switch (channel) {
      case 'whatsapp':
        return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-green-500/20 text-green-400"><MessageIcon size={14} /> WhatsApp</span>
      case 'playground':
        return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-purple-500/20 text-purple-400"><GamepadIcon size={14} /> Playground</span>
      case 'telegram':
        return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-blue-500/20 text-blue-400"><PlaneIcon size={14} /> Telegram</span>
      default:
        return <span className="px-2 py-0.5 rounded-full text-xs bg-gray-500/20 text-gray-400">Unknown</span>
    }
  }

  // Phase 10.1.1: Filter messages by channel
  const filteredMessages = channelFilter === 'all'
    ? messages
    : messages.filter(m => m.channel === channelFilter)

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-lg text-gray-600 dark:text-gray-400">Loading conversations...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* View Switcher */}
      <div className="flex justify-between items-center">
        <div className="inline-flex rounded-lg bg-gray-800 p-1 border border-gray-700">
          <button
            onClick={() => setActiveView('messages')}
            className={`px-4 py-2 text-sm font-medium rounded-md transition-all ${
              activeView === 'messages'
                ? 'bg-teal-500 text-white shadow-sm'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            <span className="inline-flex items-center gap-1"><InboxIcon size={14} /> Messages</span>
          </button>
          <button
            onClick={() => setActiveView('agent-runs')}
            className={`px-4 py-2 text-sm font-medium rounded-md transition-all ${
              activeView === 'agent-runs'
                ? 'bg-teal-500 text-white shadow-sm'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            <span className="inline-flex items-center gap-1"><BotIcon size={14} /> Agent Runs</span>
          </button>
        </div>

        <div className="text-sm text-tsushin-slate">
          {activeView === 'messages' ? `${messages.length} messages` : `${agentRuns.length} runs`}
        </div>
      </div>

      {/* Recent Messages */}
      {activeView === 'messages' && (
        <section className="bg-gray-900/50 border border-gray-800 rounded-lg shadow">
          <div className="flex justify-between items-center px-6 py-4 border-b border-gray-800">
            <h2 className="text-lg font-semibold text-white"><span className="inline-flex items-center gap-1"><InboxIcon size={16} /> Recent Messages</span></h2>
            <div className="flex gap-3 items-center">
              {/* Phase 10.1.1: Channel filter */}
              <div className="flex gap-2 items-center">
                <label className="text-sm text-tsushin-slate">Channel:</label>
                <select
                  value={channelFilter}
                  onChange={(e) => setChannelFilter(e.target.value)}
                  className="px-3 py-1.5 border border-gray-700 rounded-md text-sm text-white bg-gray-800 focus:ring-2 focus:ring-tsushin-indigo focus:border-transparent"
                >
                  <option value="all">All Channels</option>
                  <option value="whatsapp">WhatsApp</option>
                  <option value="playground">Playground</option>
                  <option value="telegram">Telegram</option>
                </select>
              </div>
              <div className="flex gap-2 items-center">
                <label className="text-sm text-tsushin-slate">Show:</label>
                <select
                  value={messagesLimit}
                  onChange={(e) => setMessagesLimit(Number(e.target.value))}
                  className="px-3 py-1.5 border border-gray-700 rounded-md text-sm text-white bg-gray-800 focus:ring-2 focus:ring-tsushin-indigo focus:border-transparent"
                >
                  <option value={10}>10</option>
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                  <option value={filteredMessages.length}>All ({filteredMessages.length})</option>
                </select>
              </div>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-800">
              <thead className="bg-gray-800/50 sticky top-0">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-tsushin-slate uppercase tracking-wider">Chat</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-tsushin-slate uppercase tracking-wider">Sender</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-tsushin-slate uppercase tracking-wider">Message</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-tsushin-slate uppercase tracking-wider w-32">Channel</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-tsushin-slate uppercase tracking-wider w-32">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-tsushin-slate uppercase tracking-wider w-32">Time</th>
                </tr>
              </thead>
              <tbody className="bg-transparent divide-y divide-gray-800">
                {filteredMessages.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-tsushin-slate">
                      {channelFilter === 'all' ? 'No messages yet' : `No ${channelFilter} messages`}
                    </td>
                  </tr>
                ) : (
                  filteredMessages.slice(0, messagesLimit).map((msg) => (
                    <tr key={msg.id} className="hover:bg-gray-800/50 transition-colors">
                      <td className="px-4 py-3 text-sm font-medium text-white">{msg.chat_name || '-'}</td>
                      <td className="px-4 py-3 text-sm text-tsushin-slate">{msg.sender_name || '-'}</td>
                      <td className="px-4 py-3 text-sm text-white max-w-md truncate">{msg.body}</td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        {getChannelBadge(msg.channel)}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <div className="flex gap-1 flex-wrap">
                          {msg.matched_filter && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 dark:bg-green-800/30 text-green-800 dark:text-green-200" title="Matched filter - triggered agent">
                              <CheckIcon size={12} /> Matched
                            </span>
                          )}
                          {msg.matched_filter && memoryStats?.semantic_search_enabled && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-purple-100 dark:bg-purple-800/30 text-purple-800 dark:text-purple-200" title="Embedded in vector store for semantic search">
                              <BrainIcon size={14} /> Indexed
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-xs text-tsushin-slate">
                        {formatTime(msg.seen_at)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Agent Runs */}
      {activeView === 'agent-runs' && (
        <section className="bg-gray-900/50 border border-gray-800 rounded-lg shadow">
          <div className="flex justify-between items-center px-6 py-4 border-b border-gray-800">
            <h2 className="text-lg font-semibold text-white"><span className="inline-flex items-center gap-1"><BotIcon size={16} /> Agent Executions</span></h2>
            <div className="flex gap-2 items-center">
              <label className="text-sm text-tsushin-slate">Show:</label>
              <select
                value={agentRunsLimit}
                onChange={(e) => setAgentRunsLimit(Number(e.target.value))}
                className="px-3 py-1.5 border border-gray-700 rounded-md text-sm text-white bg-gray-800 focus:ring-2 focus:ring-tsushin-indigo focus:border-transparent"
              >
                <option value={10}>10</option>
                <option value={25}>25</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
                <option value={agentRuns.length}>All ({agentRuns.length})</option>
              </select>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-800">
              <thead className="bg-gray-800/50 sticky top-0">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-tsushin-slate uppercase tracking-wider w-8"></th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-tsushin-slate uppercase tracking-wider w-32">Agent</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-tsushin-slate uppercase tracking-wider">Input</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-tsushin-slate uppercase tracking-wider">Output</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-tsushin-slate uppercase tracking-wider w-32">Skill/Tool</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-tsushin-slate uppercase tracking-wider w-32">Model</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-tsushin-slate uppercase tracking-wider w-24">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-tsushin-slate uppercase tracking-wider w-32">Time</th>
                </tr>
              </thead>
              <tbody className="bg-transparent divide-y divide-gray-800">
                {agentRuns.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="px-4 py-8 text-center text-tsushin-slate">No agent runs yet</td>
                  </tr>
                ) : (
                  agentRuns.slice(0, agentRunsLimit).map((run) => (
                    <>
                      <tr
                        key={run.id}
                        className="hover:bg-gray-800/50 cursor-pointer transition-colors"
                        onClick={() => setExpandedRun(expandedRun === run.id ? null : run.id)}
                      >
                        <td className="px-4 py-3 text-center">
                          <span className="text-tsushin-slate text-sm">{expandedRun === run.id ? <ChevronDownIcon size={14} /> : <ChevronRightIcon size={14} />}</span>
                        </td>
                        <td className="px-4 py-3 text-sm font-medium text-white whitespace-nowrap">
                          {run.agent_name || 'Unknown'}
                        </td>
                        <td className="px-4 py-3 text-sm text-white max-w-xs truncate">{run.input_preview}</td>
                        <td className="px-4 py-3 text-sm text-tsushin-slate max-w-md truncate">{run.output_preview}</td>
                        <td className="px-4 py-3 whitespace-nowrap text-sm">
                          <div className="flex flex-col gap-1">
                            {run.skill_type && (
                              <span className={`inline-flex items-center gap-1 px-2 py-1 text-xs rounded-md font-medium ${
                                run.skill_type === 'asana' ? 'bg-pink-100 dark:bg-pink-800/30 text-pink-800 dark:text-pink-200' :
                                run.skill_type === 'flows' ? 'bg-teal-500/10 text-teal-400 border border-teal-500/20' :
                                run.skill_type === 'audio_transcript' ? 'bg-purple-100 dark:bg-purple-800/30 text-purple-800 dark:text-purple-200' :
                                'bg-gray-100 dark:bg-gray-800/30 text-gray-800 dark:text-gray-200'
                              }`}>
                                {run.skill_type === 'asana' && <><ClipboardIcon size={14} /> Asana</>}
                                {run.skill_type === 'flows' && <><RefreshIcon size={14} /> Flows</>}
                                {run.skill_type === 'audio_transcript' && <><MicrophoneIcon size={14} /> Audio</>}
                                {!['asana', 'flows', 'audio_transcript'].includes(run.skill_type) && <><LightningIcon size={14} /> {run.skill_type}</>}
                              </span>
                            )}
                            {run.tool_used && (
                              <span className="inline-flex items-center gap-1 px-2 py-1 text-xs bg-blue-100 dark:bg-blue-800/30 text-blue-800 dark:text-blue-200 rounded-md font-medium">
                                <WrenchIcon size={14} /> {run.tool_used}
                              </span>
                            )}
                            {memoryStats?.semantic_search_enabled && (
                              <span className="inline-flex items-center gap-1 px-2 py-1 text-xs bg-purple-100 dark:bg-purple-800/30 text-purple-800 dark:text-purple-200 rounded-md font-medium" title="Used semantic search for context">
                                <BrainIcon size={14} /> Memory
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-xs text-tsushin-slate font-mono">{run.model_used}</td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          {run.status === 'success' ? (
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-500/10 text-green-400 border border-green-500/20"><CheckIcon size={14} /></span>
                          ) : (
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-500/10 text-red-400 border border-red-500/20"><XIcon size={14} /></span>
                          )}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-xs text-tsushin-slate">
                          {formatTime(run.created_at)}
                        </td>
                      </tr>
                      {expandedRun === run.id && (
                        <tr key={`${run.id}-detail`} className="bg-gray-800/30">
                          <td colSpan={8} className="px-6 py-5">
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                              {/* Left Column */}
                              <div className="space-y-3">
                                <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4 shadow-sm">
                                  <h4 className="font-semibold text-xs mb-2 text-tsushin-slate uppercase tracking-wide"><span className="inline-flex items-center gap-1"><InboxIcon size={14} /> Input Message</span></h4>
                                  <p className="text-sm text-white leading-relaxed">{run.input_preview}</p>
                                </div>

                                <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4 shadow-sm">
                                  <h4 className="font-semibold text-xs mb-2 text-tsushin-slate uppercase tracking-wide"><span className="inline-flex items-center gap-1"><SendIcon size={14} /> AI Response</span></h4>
                                  <p className="text-sm text-white leading-relaxed whitespace-pre-wrap">{run.output_preview}</p>
                                </div>

                                {/* Metrics Grid */}
                                <div className="grid grid-cols-3 gap-2">
                                  <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-3 shadow-sm">
                                    <p className="text-xs text-tsushin-slate mb-1">Model</p>
                                    <p className="text-xs font-mono text-white truncate">{run.model_used}</p>
                                  </div>
                                  <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-3 shadow-sm">
                                    <p className="text-xs text-tsushin-slate mb-1">Time</p>
                                    <p className="text-sm font-semibold text-white">{run.execution_time_ms ? `${run.execution_time_ms}ms` : 'N/A'}</p>
                                  </div>
                                  <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-3 shadow-sm">
                                    <p className="text-xs text-tsushin-slate mb-1">Status</p>
                                    <p className={`text-sm font-semibold ${run.status === 'success' ? 'text-green-400' : 'text-red-400'}`}>
                                      {run.status}
                                    </p>
                                  </div>
                                </div>
                              </div>

                              {/* Right Column */}
                              <div className="space-y-3">
                                {memoryStats?.semantic_search_enabled && (
                                  <div className="bg-gray-800/50 border border-tsushin-indigo/30 rounded-lg p-4 shadow-sm">
                                    <h4 className="font-semibold text-xs mb-2 text-tsushin-indigo uppercase tracking-wide"><span className="inline-flex items-center gap-1"><BrainIcon size={14} /> Memory Context</span></h4>
                                    <div className="space-y-2">
                                      <div className="flex items-center gap-2">
                                        <span className="inline-flex items-center px-2 py-1 text-xs bg-teal-500/10 text-teal-400 border border-teal-500/20 rounded font-medium">
                                          Semantic Search Active
                                        </span>
                                      </div>
                                      <p className="text-xs text-tsushin-slate">
                                        This agent run used semantic search to find relevant past messages.
                                        The AI received context from both recent conversation (ring buffer) and
                                        semantically similar messages from history.
                                      </p>
                                      <div className="grid grid-cols-2 gap-2 mt-2 pt-2 border-t border-gray-700">
                                        <div className="text-xs">
                                          <span className="text-tsushin-slate">Ring Buffer:</span>
                                          <span className="font-semibold text-white ml-1">{memoryStats.ring_buffer_size} msgs</span>
                                        </div>
                                        <div className="text-xs">
                                          <span className="text-tsushin-slate">Max Semantic:</span>
                                          <span className="font-semibold text-white ml-1">5 msgs</span>
                                        </div>
                                      </div>
                                    </div>
                                  </div>
                                )}

                                {run.tool_used && (
                                  <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4 shadow-sm">
                                    <h4 className="font-semibold text-xs mb-2 text-tsushin-slate uppercase tracking-wide"><span className="inline-flex items-center gap-1"><WrenchIcon size={14} /> Tool Used</span></h4>
                                    <p className="text-sm font-mono text-tsushin-indigo font-medium mb-1">{run.tool_used}</p>
                                    <p className="text-xs text-tsushin-slate">
                                      {run.tool_used === 'google_search' && <span className="inline-flex items-center gap-1"><SearchIcon size={14} /> Web search performed via Brave Search API</span>}
                                      {run.tool_used === 'weather' && <span className="inline-flex items-center gap-1"><CloudSunIcon size={14} /> Weather data fetched from OpenWeatherMap</span>}
                                      {run.tool_used === 'web_scraping' && <span className="inline-flex items-center gap-1"><GlobeIcon size={14} /> Website content extracted</span>}
                                    </p>
                                  </div>
                                )}

                                {run.tool_result && (
                                  <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4 shadow-sm">
                                    <h4 className="font-semibold text-xs mb-2 text-tsushin-slate uppercase tracking-wide"><span className="inline-flex items-center gap-1"><ChartBarIcon size={14} /> Raw Tool Response</span></h4>
                                    <div className="bg-gray-900/50 p-3 rounded border border-gray-700 max-h-80 overflow-y-auto">
                                      <pre className="text-xs whitespace-pre-wrap font-mono text-tsushin-slate">{run.tool_result}</pre>
                                    </div>
                                  </div>
                                )}

                                {run.error_text && (
                                  <div className="bg-gray-800/50 border border-red-500/30 rounded-lg p-4 shadow-sm">
                                    <h4 className="font-semibold text-xs mb-2 text-red-400 uppercase tracking-wide"><span className="inline-flex items-center gap-1"><AlertTriangleIcon size={14} /> Error</span></h4>
                                    <p className="text-sm bg-red-500/10 p-3 rounded border border-red-500/20 text-red-400">
                                      {run.error_text}
                                    </p>
                                  </div>
                                )}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  )
}
