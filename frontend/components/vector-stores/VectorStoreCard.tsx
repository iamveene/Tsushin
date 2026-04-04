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

interface VectorStoreCardProps {
  instance: VectorStoreInstance
  onEdit: (instance: VectorStoreInstance) => void
  onDelete: (instance: VectorStoreInstance) => void
  onTest: (instance: VectorStoreInstance) => void
  testLoading: boolean
}

export default function VectorStoreCard({
  instance,
  onEdit,
  onDelete,
  onTest,
  testLoading,
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
        <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-400/10 text-emerald-400 flex-shrink-0 ml-2">
          {badge}
        </span>
      </div>

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
      <div className="flex items-center gap-2 pt-2 border-t border-white/5">
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
