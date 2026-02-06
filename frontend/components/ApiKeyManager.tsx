'use client'

import { useEffect, useState } from 'react'

interface ApiKey {
  id: number
  service: string
  api_key_preview: string
  is_active: boolean
  created_at: string
  updated_at: string
}

interface SupportedServices {
  services: Record<string, string>
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'

export default function ApiKeyManager() {
  const [keys, setKeys] = useState<ApiKey[]>([])
  const [services, setServices] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [editingService, setEditingService] = useState<string | null>(null)
  const [newApiKey, setNewApiKey] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      // Load existing API keys
      const keysRes = await fetch(`${API_BASE}/api-keys`)
      if (!keysRes.ok) throw new Error('Failed to fetch API keys')
      const keysData = await keysRes.json()
      setKeys(Array.isArray(keysData) ? keysData : [])

      // Load supported services
      const servicesRes = await fetch(`${API_BASE}/api-keys/services`)
      if (!servicesRes.ok) throw new Error('Failed to fetch services')
      const servicesData: SupportedServices = await servicesRes.json()
      setServices(servicesData.services || {})
    } catch (err) {
      console.error('Failed to load API keys:', err)
      setKeys([])
      setServices({})
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async (service: string) => {
    if (!newApiKey.trim()) {
      alert('Please enter an API key')
      return
    }

    setSaving(true)
    try {
      const response = await fetch(`${API_BASE}/api-keys`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          service,
          api_key: newApiKey,
          is_active: true
        })
      })

      if (!response.ok) {
        throw new Error('Failed to save API key')
      }

      await loadData()
      setEditingService(null)
      setNewApiKey('')
      alert('API key saved successfully!')
    } catch (err) {
      console.error('Failed to save API key:', err)
      alert('Failed to save API key')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (service: string) => {
    if (!confirm(`Delete API key for ${services[service]}?`)) return

    try {
      const response = await fetch(`${API_BASE}/api-keys/${service}`, {
        method: 'DELETE'
      })

      if (!response.ok) {
        throw new Error('Failed to delete API key')
      }

      await loadData()
      alert('API key deleted successfully!')
    } catch (err) {
      console.error('Failed to delete API key:', err)
      alert('Failed to delete API key')
    }
  }

  const handleToggleActive = async (service: string, currentStatus: boolean) => {
    try {
      const response = await fetch(`${API_BASE}/api-keys/${service}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          is_active: !currentStatus
        })
      })

      if (!response.ok) {
        throw new Error('Failed to update API key')
      }

      await loadData()
    } catch (err) {
      console.error('Failed to toggle API key:', err)
      alert('Failed to update API key status')
    }
  }

  if (loading) return <div className="text-center py-4">Loading API keys...</div>

  const keysByService = Array.isArray(keys) ? keys.reduce((acc, key) => {
    acc[key.service] = key
    return acc
  }, {} as Record<string, ApiKey>) : {}

  return (
    <div className="border dark:border-gray-700 p-4 rounded-md bg-blue-50 dark:bg-blue-900/20">
      <h2 className="text-lg font-semibold mb-4">🔑 API Key Management</h2>
      <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
        Configure API keys for LLM providers and tool services. Keys stored here take priority over environment variables.
      </p>

      <div className="space-y-3">
        {Object.entries(services).map(([serviceKey, serviceName]) => {
          const existingKey = keysByService[serviceKey]
          const isEditing = editingService === serviceKey

          return (
            <div key={serviceKey} className="bg-white dark:bg-gray-800 p-3 rounded border dark:border-gray-700">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-3">
                  <span className="font-medium text-sm">{serviceName}</span>
                  {existingKey && (
                    <span className={`text-xs px-2 py-1 rounded ${existingKey.is_active ? 'bg-green-100 dark:bg-green-800/30 text-green-800 dark:text-green-200' : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400'}`}>
                      {existingKey.is_active ? 'Active' : 'Inactive'}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {existingKey && !isEditing && (
                    <>
                      <button
                        onClick={() => handleToggleActive(serviceKey, existingKey.is_active)}
                        className="text-xs px-2 py-1 rounded bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:bg-gray-700"
                      >
                        {existingKey.is_active ? 'Deactivate' : 'Activate'}
                      </button>
                      <button
                        onClick={() => {
                          setEditingService(serviceKey)
                          setNewApiKey('')
                        }}
                        className="text-xs px-2 py-1 rounded bg-blue-100 dark:bg-blue-800/30 hover:bg-blue-200 dark:hover:bg-blue-700 text-blue-700 dark:text-blue-300"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => handleDelete(serviceKey)}
                        className="text-xs px-2 py-1 rounded bg-red-100 dark:bg-red-800/30 hover:bg-red-200 dark:hover:bg-red-700 text-red-700 dark:text-red-300"
                      >
                        Delete
                      </button>
                    </>
                  )}
                  {!existingKey && !isEditing && (
                    <button
                      onClick={() => setEditingService(serviceKey)}
                      className="text-xs px-2 py-1 rounded bg-green-100 dark:bg-green-800/30 hover:bg-green-200 dark:hover:bg-green-700 dark:bg-green-700/40 text-green-700 dark:text-green-300"
                    >
                      + Add Key
                    </button>
                  )}
                </div>
              </div>

              {existingKey && !isEditing && (
                <div className="text-xs text-gray-500 dark:text-gray-400 font-mono">
                  Key: {existingKey.api_key_preview}
                </div>
              )}

              {isEditing && (
                <div className="mt-2 space-y-2">
                  <input
                    type="password"
                    value={newApiKey}
                    onChange={(e) => setNewApiKey(e.target.value)}
                    placeholder="Enter API key"
                    className="w-full px-2 py-1 text-sm border dark:border-gray-700 rounded font-mono text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleSave(serviceKey)}
                      disabled={saving}
                      className="text-xs px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                    >
                      {saving ? 'Saving...' : 'Save'}
                    </button>
                    <button
                      onClick={() => {
                        setEditingService(null)
                        setNewApiKey('')
                      }}
                      className="text-xs px-3 py-1 bg-gray-200 dark:bg-gray-700 rounded hover:bg-gray-300 dark:bg-gray-600"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>

      <div className="mt-4 bg-yellow-50 dark:bg-yellow-900/20 border dark:border-gray-700 border-yellow-200 dark:border-yellow-700 p-3 rounded">
        <p className="text-xs text-yellow-800 dark:text-yellow-200">
          <strong>💡 Priority:</strong> Database keys (configured here) take priority over environment variables (.env file).
          If no key is configured here, the system will fall back to environment variables.
        </p>
      </div>
    </div>
  )
}
