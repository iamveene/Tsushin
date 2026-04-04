'use client'

import { VectorStoreInstance } from '@/lib/client'

const VENDOR_LABELS: Record<string, string> = {
  mongodb: 'MongoDB',
  pinecone: 'Pinecone',
  qdrant: 'Qdrant',
}

function getVendorBadge(instance: VectorStoreInstance): string {
  if (instance.vendor === 'mongodb') {
    return instance.extra_config?.use_native_search === false ? 'MongoDB' : 'Atlas'
  }
  const badges: Record<string, string> = { pinecone: 'Pinecone', qdrant: 'Qdrant' }
  return badges[instance.vendor] || instance.vendor
}

const STATUS_STYLES: Record<string, { dot: string; dotColor: string; label: string }> = {
  healthy: { dot: 'bg-emerald-400 animate-pulse', dotColor: 'bg-emerald-400', label: 'Connected' },
  unknown: { dot: 'bg-gray-400', dotColor: 'bg-gray-400', label: 'Not tested' },
  unavailable: { dot: 'bg-red-400', dotColor: 'bg-red-400', label: 'Error' },
  degraded: { dot: 'bg-yellow-400 animate-pulse', dotColor: 'bg-yellow-400', label: 'Degraded' },
}

const CONTAINER_STATUS_STYLES: Record<string, { dot: string; label: string }> = {
  running: { dot: 'bg-emerald-400 animate-pulse', label: 'Running' },
  stopped: { dot: 'bg-gray-400', label: 'Stopped' },
  exited: { dot: 'bg-gray-400', label: 'Stopped' },
  creating: { dot: 'bg-yellow-400 animate-pulse', label: 'Creating' },
  error: { dot: 'bg-red-400', label: 'Error' },
  none: { dot: 'bg-gray-600', label: '' },
  not_found: { dot: 'bg-red-400', label: 'Not Found' },
}

interface VectorStoreCardProps {
  instance: VectorStoreInstance
  onEdit: (instance: VectorStoreInstance) => void
  onDelete: (instance: VectorStoreInstance) => void
  onTest: (instance: VectorStoreInstance) => void
  testLoading: boolean
  onContainerAction?: (instance: VectorStoreInstance, action: 'start' | 'stop' | 'restart') => void
  containerActionLoading?: boolean
}

export default function VectorStoreCard({
  instance,
  onEdit,
  onDelete,
  onTest,
  testLoading,
  onContainerAction,
  containerActionLoading,
}: VectorStoreCardProps) {
  const status = STATUS_STYLES[instance.health_status] || STATUS_STYLES.unknown
  const vendorLabel = VENDOR_LABELS[instance.vendor] || instance.vendor
  const badge = getVendorBadge(instance)

  return (
    <div className="bg-[#12121a] border border-white/5 rounded-xl p-4 hover:border-white/15 transition-colors">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <div className={`w-2 h-2 rounded-full flex-shrink-0 ${status.dot}`} />
          <span className="text-white font-medium text-sm truncate">
            {instance.instance_name}
          </span>
          {instance.is_default && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-400/20 text-emerald-400 flex-shrink-0">
              DEFAULT
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0 ml-2">
          {instance.is_auto_provisioned && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-purple-400/10 text-purple-400">
              Provisioned
            </span>
          )}
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-400/10 text-emerald-400">
            {badge}
          </span>
        </div>
      </div>

      {/* Container Status (auto-provisioned only) */}
      {instance.is_auto_provisioned && instance.container_status && instance.container_status !== 'none' && (
        <div className="flex items-center gap-2 mb-2 px-2 py-1.5 rounded-lg bg-white/[0.02] border border-white/5">
          <div className={`w-1.5 h-1.5 rounded-full ${(CONTAINER_STATUS_STYLES[instance.container_status] || CONTAINER_STATUS_STYLES.none).dot}`} />
          <span className="text-xs text-gray-400">
            Container: {(CONTAINER_STATUS_STYLES[instance.container_status] || CONTAINER_STATUS_STYLES.none).label}
          </span>
          {instance.container_port && (
            <span className="text-xs text-gray-500 ml-auto">Port {instance.container_port}</span>
          )}
        </div>
      )}

      {/* Info */}
      <div className="space-y-1.5 mb-3">
        {instance.base_url && (
          <div className="text-xs text-gray-400 truncate" title={instance.base_url}>
            {instance.base_url}
          </div>
        )}
        {instance.extra_config?.collection_name && (
          <div className="text-xs text-gray-500">
            Collection: {instance.extra_config.collection_name}
          </div>
        )}
        {instance.extra_config?.index_name && (
          <div className="text-xs text-gray-500">
            Index: {instance.extra_config.index_name}
          </div>
        )}
        {instance.credentials_configured && (
          <div className="text-xs text-gray-500">
            Key: {instance.credentials_preview || 'configured'}
          </div>
        )}
        <div className="text-xs text-gray-500 flex items-center gap-1">
          <div className={`w-1.5 h-1.5 rounded-full ${status.dotColor}`} />
          {status.label}
          {instance.health_status_reason && instance.health_status === 'unavailable' && (
            <span className="text-red-400/70 ml-1 truncate" title={instance.health_status_reason}>
              - {instance.health_status_reason.slice(0, 50)}
            </span>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 pt-2 border-t border-white/5 flex-wrap">
        <button
          onClick={() => onEdit(instance)}
          className="text-xs text-gray-400 hover:text-white transition-colors"
        >
          Edit
        </button>
        <span className="text-gray-600">|</span>
        <button
          onClick={() => onTest(instance)}
          disabled={testLoading}
          className="text-xs text-emerald-400 hover:text-emerald-300 transition-colors disabled:opacity-50"
        >
          {testLoading ? 'Testing...' : 'Test'}
        </button>
        {instance.is_auto_provisioned && onContainerAction && (
          <>
            <span className="text-gray-600">|</span>
            {(instance.container_status === 'stopped' || instance.container_status === 'exited') && (
              <button
                onClick={() => onContainerAction(instance, 'start')}
                disabled={containerActionLoading}
                className="text-xs text-teal-400 hover:text-teal-300 transition-colors disabled:opacity-50"
              >
                Start
              </button>
            )}
            {instance.container_status === 'running' && (
              <>
                <button
                  onClick={() => onContainerAction(instance, 'stop')}
                  disabled={containerActionLoading}
                  className="text-xs text-yellow-400 hover:text-yellow-300 transition-colors disabled:opacity-50"
                >
                  Stop
                </button>
                <span className="text-gray-600">|</span>
                <button
                  onClick={() => onContainerAction(instance, 'restart')}
                  disabled={containerActionLoading}
                  className="text-xs text-blue-400 hover:text-blue-300 transition-colors disabled:opacity-50"
                >
                  Restart
                </button>
              </>
            )}
          </>
        )}
        <span className="text-gray-600">|</span>
        <button
          onClick={() => onDelete(instance)}
          className="text-xs text-red-400/70 hover:text-red-400 transition-colors"
        >
          Delete
        </button>
      </div>
    </div>
  )
}
