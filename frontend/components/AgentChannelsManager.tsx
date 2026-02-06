'use client'

import { useEffect, useState } from 'react'
import React from 'react'
import { api, Agent, WhatsAppMCPInstance, TelegramBotInstance } from '@/lib/client'
import { GamepadIcon, WhatsAppIcon, TelegramIcon, CheckCircleIcon, CircleIcon, IconProps } from '@/components/ui/icons'

interface Props {
  agentId: number
}

const AVAILABLE_CHANNELS: { id: string; name: string; Icon: React.FC<IconProps>; description: string; disabled?: boolean }[] = [
  { id: 'playground', name: 'Playground', Icon: GamepadIcon, description: 'Web UI chat interface' },
  { id: 'whatsapp', name: 'WhatsApp', Icon: WhatsAppIcon, description: 'WhatsApp messaging' },
  { id: 'telegram', name: 'Telegram', Icon: TelegramIcon, description: 'Telegram messaging' },  // Phase 10.1.1: Now available!
]

export default function AgentChannelsManager({ agentId }: Props) {
  const [agent, setAgent] = useState<Agent | null>(null)
  const [mcpInstances, setMcpInstances] = useState<WhatsAppMCPInstance[]>([])
  const [telegramInstances, setTelegramInstances] = useState<TelegramBotInstance[]>([])  // Phase 10.1.1
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  // Form state
  const [enabledChannels, setEnabledChannels] = useState<string[]>(['playground', 'whatsapp'])
  const [whatsappIntegrationId, setWhatsappIntegrationId] = useState<number | null>(null)
  const [telegramIntegrationId, setTelegramIntegrationId] = useState<number | null>(null)  // Phase 10.1.1

  useEffect(() => {
    loadData()
  }, [agentId])

  const loadData = async () => {
    setLoading(true)
    try {
      const [agentData, instancesData, telegramData] = await Promise.all([
        api.getAgent(agentId),
        api.getMCPInstances(),
        api.getTelegramInstances(),  // Phase 10.1.1
      ])

      setAgent(agentData)
      setMcpInstances(instancesData.filter(i => i.instance_type === 'agent'))
      setTelegramInstances(telegramData)  // Phase 10.1.1

      // Populate form
      setEnabledChannels(agentData.enabled_channels || ['playground', 'whatsapp'])
      setWhatsappIntegrationId(agentData.whatsapp_integration_id || null)
      setTelegramIntegrationId(agentData.telegram_integration_id || null)  // Phase 10.1.1
    } catch (err) {
      console.error('Failed to load data:', err)
      alert('Failed to load channel configuration')
    } finally {
      setLoading(false)
    }
  }

  const handleChannelToggle = (channelId: string) => {
    setEnabledChannels(prev => {
      if (prev.includes(channelId)) {
        return prev.filter(c => c !== channelId)
      } else {
        return [...prev, channelId]
      }
    })
  }

  const handleSave = async () => {
    if (!agent) return

    setSaving(true)
    try {
      await api.updateAgent(agentId, {
        enabled_channels: enabledChannels,
        whatsapp_integration_id: enabledChannels.includes('whatsapp') ? whatsappIntegrationId : null,
        telegram_integration_id: enabledChannels.includes('telegram') ? telegramIntegrationId : null,  // Phase 10.1.1
      })

      // Reload to confirm
      await loadData()
      alert('Channel configuration saved successfully!')
    } catch (err) {
      console.error('Failed to save:', err)
      alert('Failed to save channel configuration')
    } finally {
      setSaving(false)
    }
  }

  const handleSetGroupHandler = async (instanceId: number, isGroupHandler: boolean) => {
    try {
      await api.setMCPGroupHandler(instanceId, isGroupHandler)
      // Reload instances to reflect change
      const instancesData = await api.getMCPInstances()
      setMcpInstances(instancesData.filter(i => i.instance_type === 'agent'))
    } catch (err) {
      console.error('Failed to set group handler:', err)
      alert('Failed to update group handler')
    }
  }

  if (loading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <div className="animate-pulse">
          <div className="h-6 bg-gray-200 dark:bg-gray-700 rounded w-1/4 mb-4"></div>
          <div className="space-y-3">
            <div className="h-12 bg-gray-200 dark:bg-gray-700 rounded"></div>
            <div className="h-12 bg-gray-200 dark:bg-gray-700 rounded"></div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Channel Toggles */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
          Enabled Channels
        </h2>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
          Select which channels this agent can interact through.
        </p>

        <div className="space-y-3">
          {AVAILABLE_CHANNELS.map(channel => (
            <label
              key={channel.id}
              className={`flex items-center justify-between p-4 border rounded-lg cursor-pointer transition-colors ${
                channel.disabled
                  ? 'bg-gray-50 dark:bg-gray-900 border-gray-200 dark:border-gray-700 opacity-50 cursor-not-allowed'
                  : enabledChannels.includes(channel.id)
                    ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-300 dark:border-blue-700'
                    : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 hover:border-blue-200 dark:hover:border-blue-800'
              }`}
            >
              <div className="flex items-center gap-3">
                <channel.Icon size={24} />
                <div>
                  <div className="font-medium text-gray-900 dark:text-gray-100">
                    {channel.name}
                    {channel.disabled && (
                      <span className="ml-2 text-xs px-2 py-0.5 bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded-full">
                        Coming Soon
                      </span>
                    )}
                  </div>
                  <div className="text-sm text-gray-500 dark:text-gray-400">
                    {channel.description}
                  </div>
                </div>
              </div>
              <input
                type="checkbox"
                checked={enabledChannels.includes(channel.id)}
                onChange={() => handleChannelToggle(channel.id)}
                disabled={channel.disabled}
                className="h-5 w-5 text-blue-600 rounded focus:ring-blue-500"
              />
            </label>
          ))}
        </div>
      </div>

      {/* WhatsApp Integration Selection */}
      {enabledChannels.includes('whatsapp') && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
            WhatsApp Integration
          </h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
            Select which WhatsApp phone number this agent should use to send and receive messages.
          </p>

          {mcpInstances.length === 0 ? (
            <div className="text-center py-6 text-gray-500 dark:text-gray-400">
              <p>No WhatsApp integrations available.</p>
              <p className="text-sm mt-1">Go to System → Integrations to create one.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {mcpInstances.map(instance => (
                <label
                  key={instance.id}
                  className={`flex items-center justify-between p-4 border rounded-lg cursor-pointer transition-colors ${
                    whatsappIntegrationId === instance.id
                      ? 'bg-green-50 dark:bg-green-900/20 border-green-300 dark:border-green-700'
                      : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 hover:border-green-200 dark:hover:border-green-800'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <input
                      type="radio"
                      name="whatsapp_integration"
                      checked={whatsappIntegrationId === instance.id}
                      onChange={() => setWhatsappIntegrationId(instance.id)}
                      className="h-4 w-4 text-green-600 focus:ring-green-500"
                    />
                    <div>
                      <div className="font-medium text-gray-900 dark:text-gray-100">
                        {instance.phone_number}
                        {instance.is_group_handler && (
                          <span className="ml-2 text-xs px-2 py-0.5 bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-300 rounded-full">
                            Group Handler
                          </span>
                        )}
                      </div>
                      <div className="text-sm text-gray-500 dark:text-gray-400">
                        Port {instance.mcp_port} • {instance.status}
                        {instance.health_status && ` • ${instance.health_status}`}
                      </div>
                    </div>
                  </div>
                  <div className={`px-2 py-1 text-xs font-medium rounded-full ${
                    instance.status === 'running'
                      ? 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300'
                      : instance.status === 'stopped'
                        ? 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-300'
                        : 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300'
                  }`}>
                    {instance.status}
                  </div>
                </label>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Phase 10.1.1: Telegram Integration Selection */}
      {enabledChannels.includes('telegram') && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
            Telegram Integration
          </h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
            Select which Telegram bot this agent should use to send and receive messages.
          </p>

          {telegramInstances.length === 0 ? (
            <div className="text-center py-6 text-gray-500 dark:text-gray-400">
              <p>No Telegram bots available.</p>
              <p className="text-sm mt-1">Go to Hub → Communication to create one.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {telegramInstances.map(instance => (
                <label
                  key={instance.id}
                  className={`flex items-center justify-between p-4 border rounded-lg cursor-pointer transition-colors ${
                    telegramIntegrationId === instance.id
                      ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-300 dark:border-blue-700'
                      : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 hover:border-blue-200 dark:hover:border-blue-800'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <input
                      type="radio"
                      name="telegram_integration"
                      checked={telegramIntegrationId === instance.id}
                      onChange={() => setTelegramIntegrationId(instance.id)}
                      className="h-4 w-4 text-blue-600 focus:ring-blue-500"
                    />
                    <div>
                      <div className="font-medium text-gray-900 dark:text-gray-100">
                        @{instance.bot_username}
                      </div>
                      <div className="text-sm text-gray-500 dark:text-gray-400">
                        {instance.bot_name || 'Telegram Bot'} • {instance.status}
                      </div>
                    </div>
                  </div>
                  <div className={`px-2 py-1 text-xs font-medium rounded-full ${
                    instance.status === 'active'
                      ? 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300'
                      : instance.status === 'inactive'
                        ? 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-300'
                        : 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300'
                  }`}>
                    {instance.status}
                  </div>
                </label>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Group Handler Configuration */}
      {enabledChannels.includes('whatsapp') && mcpInstances.length > 1 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
            Group Message Handler
          </h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
            When multiple WhatsApp numbers are members of the same group, only one should respond to prevent duplicates.
            Select which integration should handle group messages.
          </p>

          <div className="space-y-2">
            {mcpInstances.map(instance => (
              <button
                key={instance.id}
                onClick={() => handleSetGroupHandler(instance.id, !instance.is_group_handler)}
                className={`w-full flex items-center justify-between p-3 border rounded-lg transition-colors ${
                  instance.is_group_handler
                    ? 'bg-purple-50 dark:bg-purple-900/20 border-purple-300 dark:border-purple-700'
                    : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 hover:border-purple-200 dark:hover:border-purple-800'
                }`}
              >
                <div className="flex items-center gap-3">
                  {instance.is_group_handler ? <CheckCircleIcon size={20} className="text-green-600" /> : <CircleIcon size={20} className="text-gray-400" />}
                  <span className="font-medium text-gray-900 dark:text-gray-100">
                    {instance.phone_number}
                  </span>
                </div>
                <span className={`text-sm ${
                  instance.is_group_handler
                    ? 'text-purple-700 dark:text-purple-300 font-medium'
                    : 'text-gray-500 dark:text-gray-400'
                }`}>
                  {instance.is_group_handler ? 'Handles Groups' : 'DMs Only'}
                </span>
              </button>
            ))}
          </div>

          <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">
            Only one integration can be the group handler at a time. Selecting a new one will automatically
            unset the previous one.
          </p>
        </div>
      )}

      {/* Save Button */}
      <div className="flex justify-end">
        <button
          onClick={handleSave}
          disabled={saving}
          className={`px-6 py-2.5 rounded-lg font-medium transition-colors ${
            saving
              ? 'bg-gray-400 text-gray-600 cursor-not-allowed'
              : 'bg-blue-600 text-white hover:bg-blue-700'
          }`}
        >
          {saving ? 'Saving...' : 'Save Changes'}
        </button>
      </div>
    </div>
  )
}
