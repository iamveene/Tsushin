'use client'

import { useState, useEffect } from 'react'
import Modal from '@/components/ui/Modal'
import MongoAtlasConfigForm from './MongoAtlasConfigForm'
import PineconeConfigForm from './PineconeConfigForm'
import QdrantConfigForm from './QdrantConfigForm'
import { api, VectorStoreInstance, VectorStoreInstanceCreate } from '@/lib/client'

interface SecurityConfig {
  pre_storage_block_threshold: number
  post_retrieval_block_threshold: number
  batch_max_documents: number
  max_writes_per_min_tenant: number
  max_reads_per_min_agent: number
  cross_tenant_check: boolean
}

const DEFAULT_SECURITY_CONFIG: SecurityConfig = {
  pre_storage_block_threshold: 0.7,
  post_retrieval_block_threshold: 0.5,
  batch_max_documents: 50,
  max_writes_per_min_tenant: 100,
  max_reads_per_min_agent: 30,
  cross_tenant_check: true,
}

const VENDORS = [
  { value: 'mongodb', label: 'MongoDB' },
  { value: 'pinecone', label: 'Pinecone' },
  { value: 'qdrant', label: 'Qdrant' },
]

interface VectorStoreConfigModalProps {
  isOpen: boolean
  onClose: () => void
  onSave: () => void
  instance?: VectorStoreInstance | null
}

export default function VectorStoreConfigModal({
  isOpen,
  onClose,
  onSave,
  instance,
}: VectorStoreConfigModalProps) {
  const isEditing = !!instance

  const [vendor, setVendor] = useState('mongodb')
  const [instanceName, setInstanceName] = useState('')
  const [description, setDescription] = useState('')
  const [connectionConfig, setConnectionConfig] = useState<Record<string, any>>({})
  const [isDefault, setIsDefault] = useState(false)
  const [autoProvision, setAutoProvision] = useState(false)
  const [memLimit, setMemLimit] = useState('1g')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{ success: boolean; message: string; latency_ms?: number; vector_count?: number } | null>(null)
  const [testing, setTesting] = useState(false)
  // Track whether user explicitly changed credentials (prevents silent wipe on edit)
  const [credentialsTouched, setCredentialsTouched] = useState(false)
  const [securityExpanded, setSecurityExpanded] = useState(false)
  const [securityConfig, setSecurityConfig] = useState<SecurityConfig>({ ...DEFAULT_SECURITY_CONFIG })

  // Wrap connectionConfig onChange to detect credential field changes
  const handleConfigChange = (config: Record<string, any>) => {
    const credFields = ['api_key', 'cluster_uri']
    const oldCreds = credFields.map(f => connectionConfig[f] || '')
    const newCreds = credFields.map(f => config[f] || '')
    if (oldCreds.some((v, i) => v !== newCreds[i])) {
      setCredentialsTouched(true)
    }
    setConnectionConfig(config)
  }

  // Reset form when modal opens/closes or instance changes
  useEffect(() => {
    if (isOpen) {
      if (instance) {
        setVendor(instance.vendor)
        setInstanceName(instance.instance_name)
        setDescription(instance.description || '')
        const config: Record<string, any> = { ...(instance.extra_config || {}) }
        // For qdrant, restore base_url into config for the form
        if (instance.base_url && instance.vendor === 'qdrant') {
          config.base_url = instance.base_url
        }
        // MongoDB: base_url may contain masked URI — don't populate cluster_uri from it in edit mode
        // The user must re-enter the URI if they want to change it
        setConnectionConfig(config)
        setIsDefault(instance.is_default)
        setCredentialsTouched(false)
        // Load security config from extra_config if present
        const storedSecurity = instance.extra_config?.security_config
        if (storedSecurity) {
          setSecurityConfig({ ...DEFAULT_SECURITY_CONFIG, ...storedSecurity })
        } else {
          setSecurityConfig({ ...DEFAULT_SECURITY_CONFIG })
        }
        setSecurityExpanded(false)
      } else {
        setVendor('mongodb')
        setInstanceName('')
        setDescription('')
        setConnectionConfig({})
        setIsDefault(false)
        setAutoProvision(false)
        setMemLimit('1g')
        setCredentialsTouched(false)
        setSecurityConfig({ ...DEFAULT_SECURITY_CONFIG })
        setSecurityExpanded(false)
      }
      setError(null)
      setTestResult(null)
    }
  }, [isOpen, instance])

  const handleSave = async () => {
    if (!instanceName.trim()) {
      setError('Instance name is required')
      return
    }

    setSaving(true)
    setError(null)

    try {
      // Separate credential fields from extra_config
      const { api_key, cluster_uri, base_url: configBaseUrl, ...extraConfig } = connectionConfig

      let baseUrl: string | undefined
      const credentials: Record<string, any> = {}

      if (vendor === 'mongodb') {
        // Never store raw MongoDB URI in base_url (may contain embedded credentials)
        // Route it exclusively through encrypted credentials
        if (cluster_uri) credentials.connection_string = cluster_uri
        if (api_key) credentials.api_key = api_key
      } else if (vendor === 'pinecone') {
        if (api_key) credentials.api_key = api_key
      } else if (vendor === 'qdrant') {
        baseUrl = configBaseUrl || undefined
        if (api_key) credentials.api_key = api_key
      }

      // Only include credentials in payload if user explicitly changed them (prevents silent wipe on edit)
      const hasNewCredentials = Object.keys(credentials).length > 0
      const shouldSendCredentials = isEditing ? (credentialsTouched && hasNewCredentials) : hasNewCredentials

      if (isEditing && instance) {
        await api.updateVectorStoreInstance(instance.id, {
          instance_name: instanceName,
          description: description || undefined,
          base_url: baseUrl,
          credentials: shouldSendCredentials ? credentials : undefined,
          extra_config: { ...extraConfig, security_config: securityConfig },
          is_default: isDefault,
        })
      } else {
        await api.createVectorStoreInstance({
          vendor,
          instance_name: instanceName,
          description: description || undefined,
          base_url: autoProvision ? undefined : baseUrl,
          credentials: autoProvision ? undefined : (hasNewCredentials ? credentials : undefined),
          extra_config: extraConfig,
          is_default: isDefault,
          auto_provision: autoProvision,
          mem_limit: autoProvision ? memLimit : undefined,
        })
      }

      onSave()
      onClose()
    } catch (err: any) {
      setError(err.message || 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async () => {
    if (!isEditing || !instance) return
    setTesting(true)
    setTestResult(null)
    try {
      const result = await api.testVectorStoreConnection(instance.id)
      setTestResult(result)
    } catch (err: any) {
      setTestResult({ success: false, message: err.message || 'Test failed' })
    } finally {
      setTesting(false)
    }
  }

  const footer = (
    <div className="flex items-center justify-between w-full">
      <div className="flex items-center gap-2">
        {isEditing && (
          <button
            onClick={handleTest}
            disabled={testing}
            className="px-3 py-1.5 text-sm rounded-lg border border-emerald-400/30 text-emerald-400 hover:bg-emerald-400/10 disabled:opacity-50 transition-colors"
          >
            {testing ? 'Testing...' : 'Test Connection'}
          </button>
        )}
        {testResult && (
          <span className={`text-xs ${testResult.success ? 'text-emerald-400' : 'text-red-400'}`}>
            {testResult.success ? 'Connected' : 'Failed'}: {testResult.message}
            {testResult.latency_ms !== undefined && testResult.success && (
              <span className="text-gray-400 ml-1">({testResult.latency_ms}ms)</span>
            )}
            {testResult.vector_count !== undefined && testResult.vector_count !== null && testResult.success && (
              <span className="text-gray-400 ml-1">- {testResult.vector_count} vectors</span>
            )}
          </span>
        )}
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={onClose}
          className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-4 py-2 text-sm bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg disabled:opacity-50 transition-colors"
        >
          {saving ? 'Saving...' : isEditing ? 'Update' : 'Create'}
        </button>
      </div>
    </div>
  )

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isEditing ? 'Edit Vector Store' : 'Add Vector Store'}
      footer={footer}
      size="lg"
    >
      <div className="space-y-5">
        {error && (
          <div className="px-3 py-2 bg-red-400/10 border border-red-400/20 rounded-lg text-red-400 text-sm">
            {error}
          </div>
        )}

        {/* Provider */}
        <div>
          <label className="block text-sm text-gray-300 mb-1">Provider</label>
          <select
            value={vendor}
            onChange={(e) => {
              setVendor(e.target.value)
              setConnectionConfig({})
            }}
            disabled={isEditing}
            className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm disabled:opacity-50"
          >
            {VENDORS.map((v) => (
              <option key={v.value} value={v.value}>
                {v.label}
              </option>
            ))}
          </select>
        </div>

        {/* Instance Name */}
        <div>
          <label className="block text-sm text-gray-300 mb-1">Instance Name <span className="text-red-400">*</span></label>
          <input
            type="text"
            value={instanceName}
            onChange={(e) => setInstanceName(e.target.value)}
            placeholder={`My ${VENDORS.find(v => v.value === vendor)?.label || ''} Store`}
            className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] placeholder:text-gray-600 text-sm"
          />
        </div>

        {/* Description */}
        <div>
          <label className="block text-sm text-gray-300 mb-1">Description</label>
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Optional description"
            className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] placeholder:text-gray-600 text-sm"
          />
        </div>

        {/* Auto-Provision Toggle (Qdrant/MongoDB only, create mode) */}
        {!isEditing && (vendor === 'qdrant' || vendor === 'mongodb') && (
          <div className="flex items-center gap-3 p-3 rounded-lg border border-white/5 bg-white/[0.02]">
            <button
              type="button"
              onClick={() => setAutoProvision(!autoProvision)}
              className={`relative w-10 h-5 rounded-full transition-colors ${
                autoProvision ? 'bg-teal-500/80' : 'bg-white/10'
              }`}
            >
              <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                autoProvision ? 'translate-x-5' : ''
              }`} />
            </button>
            <div>
              <span className="text-sm text-gray-300">Auto-Provision Container</span>
              <p className="text-xs text-gray-500">
                {autoProvision
                  ? `Tsushin will create and manage a local ${vendor === 'qdrant' ? 'Qdrant' : 'MongoDB'} Docker container for you`
                  : 'Connect to an existing external instance'}
              </p>
            </div>
          </div>
        )}

        {/* Resource Limits (auto-provision only) */}
        {autoProvision && !isEditing && (
          <div className="p-3 rounded-lg border border-white/5 bg-white/[0.02]">
            <label className="block text-sm text-gray-300 mb-2">Memory Limit</label>
            <select
              value={memLimit}
              onChange={(e) => setMemLimit(e.target.value)}
              className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm"
            >
              <option value="512m">512 MB</option>
              <option value="1g">1 GB (default)</option>
              <option value="2g">2 GB</option>
              <option value="4g">4 GB</option>
            </select>
          </div>
        )}

        {/* Provider-specific form (hidden when auto-provision) */}
        {!autoProvision && (
          <div className="pt-2 border-t border-white/5">
            <h3 className="text-sm font-medium text-gray-300 mb-3">Connection Settings</h3>
            {vendor === 'mongodb' && (
              <MongoAtlasConfigForm config={connectionConfig} onChange={handleConfigChange} isEditing={isEditing} />
            )}
            {vendor === 'pinecone' && (
              <PineconeConfigForm config={connectionConfig} onChange={handleConfigChange} isEditing={isEditing} />
            )}
            {vendor === 'qdrant' && (
              <QdrantConfigForm config={connectionConfig} onChange={handleConfigChange} isEditing={isEditing} />
            )}
          </div>
        )}

        {/* Security Section (edit mode only) */}
        {isEditing && (
          <div className="pt-2 border-t border-white/5">
            <button
              type="button"
              onClick={() => setSecurityExpanded(!securityExpanded)}
              className="flex items-center justify-between w-full text-left"
            >
              <h3 className="text-sm font-medium text-gray-300">Security</h3>
              <svg
                className={`w-4 h-4 text-gray-500 transition-transform ${securityExpanded ? 'rotate-180' : ''}`}
                fill="none" stroke="currentColor" viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {securityExpanded && (
              <div className="mt-3 space-y-4">
                {/* Pre-storage block threshold */}
                <div>
                  <label className="flex items-center justify-between text-xs text-gray-400 mb-1">
                    <span>Pre-storage block threshold</span>
                    <span className="font-mono text-gray-300">{securityConfig.pre_storage_block_threshold.toFixed(2)}</span>
                  </label>
                  <input
                    type="range"
                    min="0" max="1" step="0.05"
                    value={securityConfig.pre_storage_block_threshold}
                    onChange={(e) => setSecurityConfig({ ...securityConfig, pre_storage_block_threshold: parseFloat(e.target.value) })}
                    className="w-full h-1.5 bg-white/10 rounded-lg appearance-none cursor-pointer accent-teal-500"
                  />
                </div>

                {/* Post-retrieval block threshold */}
                <div>
                  <label className="flex items-center justify-between text-xs text-gray-400 mb-1">
                    <span>Post-retrieval block threshold</span>
                    <span className="font-mono text-gray-300">{securityConfig.post_retrieval_block_threshold.toFixed(2)}</span>
                  </label>
                  <input
                    type="range"
                    min="0" max="1" step="0.05"
                    value={securityConfig.post_retrieval_block_threshold}
                    onChange={(e) => setSecurityConfig({ ...securityConfig, post_retrieval_block_threshold: parseFloat(e.target.value) })}
                    className="w-full h-1.5 bg-white/10 rounded-lg appearance-none cursor-pointer accent-teal-500"
                  />
                </div>

                {/* Batch max documents */}
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Batch max documents</label>
                  <input
                    type="number"
                    min="1" max="500"
                    value={securityConfig.batch_max_documents}
                    onChange={(e) => setSecurityConfig({ ...securityConfig, batch_max_documents: parseInt(e.target.value) || 50 })}
                    className="w-full px-3 py-1.5 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm"
                  />
                </div>

                {/* Max writes/min/tenant */}
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Max writes/min/tenant</label>
                  <input
                    type="number"
                    min="1" max="1000"
                    value={securityConfig.max_writes_per_min_tenant}
                    onChange={(e) => setSecurityConfig({ ...securityConfig, max_writes_per_min_tenant: parseInt(e.target.value) || 100 })}
                    className="w-full px-3 py-1.5 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm"
                  />
                </div>

                {/* Max reads/min/agent */}
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Max reads/min/agent</label>
                  <input
                    type="number"
                    min="1" max="1000"
                    value={securityConfig.max_reads_per_min_agent}
                    onChange={(e) => setSecurityConfig({ ...securityConfig, max_reads_per_min_agent: parseInt(e.target.value) || 30 })}
                    className="w-full px-3 py-1.5 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm"
                  />
                </div>

                {/* Cross-tenant check toggle */}
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => setSecurityConfig({ ...securityConfig, cross_tenant_check: !securityConfig.cross_tenant_check })}
                    className={`relative w-10 h-5 rounded-full transition-colors ${
                      securityConfig.cross_tenant_check ? 'bg-teal-500/80' : 'bg-white/10'
                    }`}
                  >
                    <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                      securityConfig.cross_tenant_check ? 'translate-x-5' : ''
                    }`} />
                  </button>
                  <div>
                    <span className="text-sm text-gray-300">Cross-tenant check</span>
                    <p className="text-xs text-gray-500">Verify tenant isolation on every read/write operation</p>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Info note about default setting */}
        <div className="text-xs text-gray-500 pt-2 border-t border-white/5">
          Default vector store is configured in Settings &gt; Vector Stores.
        </div>
      </div>
    </Modal>
  )
}
