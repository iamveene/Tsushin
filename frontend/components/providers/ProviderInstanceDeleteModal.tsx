'use client'

/**
 * ProviderInstanceDeleteModal — cascade-aware confirmation for deleting an
 * LLM provider instance from Hub.
 *
 * v0.7.0: previously the delete was a single window.confirm("Delete X?") that
 * silently soft-deleted the row and quietly nulled out provider_instance_id
 * on every dependent agent. The agents kept "working" only because the
 * AIClient legacy fallback masked the orphan state. Now the delete UI surfaces
 * the dependent agents, asks where to reassign them, and the backend refuses
 * the delete unless either reassign or unassign is explicitly chosen.
 */

import { useEffect, useMemo, useState } from 'react'
import {
  api,
  ProviderInstance,
  ProviderInstanceUsage,
  CascadeDeleteResult,
  LlmCatalogVendor,
} from '@/lib/client'
import Modal from '@/components/ui/Modal'

interface Props {
  isOpen: boolean
  instance: ProviderInstance | null
  onClose: () => void
  /** Called after a successful delete so the caller can refetch its list. */
  onDeleted: (result: CascadeDeleteResult) => void
}

export default function ProviderInstanceDeleteModal({
  isOpen,
  instance,
  onClose,
  onDeleted,
}: Props) {
  const [loadingUsage, setLoadingUsage] = useState(false)
  const [usage, setUsage] = useState<ProviderInstanceUsage | null>(null)
  const [catalog, setCatalog] = useState<LlmCatalogVendor[]>([])

  const [strategy, setStrategy] = useState<'reassign' | 'unassign'>('reassign')
  const [reassignTo, setReassignTo] = useState<number | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!isOpen || !instance) return
    let cancelled = false
    setLoadingUsage(true)
    setError(null)
    Promise.all([
      api.getProviderInstanceUsage(instance.id).catch(() => null),
      api.getLlmProvidersCatalog().catch(() => []),
    ]).then(([u, c]) => {
      if (cancelled) return
      setUsage(u)
      setCatalog(c)
      // Pick a sensible default reassign target: another active instance of
      // the same vendor, preferring the tenant default.
      const sameVendor = c.find((v) => v.vendor === instance.vendor)
      if (sameVendor) {
        const candidates = sameVendor.instances.filter((i) => i.id !== instance.id)
        const def = candidates.find((i) => i.is_default) || candidates[0]
        setReassignTo(def?.id ?? null)
        if (!def) setStrategy('unassign')
      } else {
        setStrategy('unassign')
      }
      setLoadingUsage(false)
    })
    return () => {
      cancelled = true
    }
  }, [isOpen, instance])

  const sameVendorOptions = useMemo(() => {
    if (!instance) return []
    const v = catalog.find((c) => c.vendor === instance.vendor)
    if (!v) return []
    return v.instances.filter((i) => i.id !== instance.id)
  }, [catalog, instance])

  const dependentCount = usage?.dependent_count ?? 0

  const handleConfirm = async () => {
    if (!instance) return
    setSubmitting(true)
    setError(null)
    try {
      const opts: { reassignToInstanceId?: number; unassign?: boolean } = {}
      if (dependentCount > 0) {
        if (strategy === 'reassign') {
          if (!reassignTo) {
            setError('Pick an instance to reassign dependents to, or switch to Unassign.')
            setSubmitting(false)
            return
          }
          opts.reassignToInstanceId = reassignTo
        } else {
          opts.unassign = true
        }
      }
      const result = await api.deleteProviderInstance(instance.id, opts)
      onDeleted(result)
      onClose()
    } catch (e: any) {
      setError(e?.message || 'Failed to delete instance')
    } finally {
      setSubmitting(false)
    }
  }

  if (!isOpen || !instance) return null

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={`Delete ${instance.instance_name}?`} size="lg">
      <div className="space-y-4">
        {loadingUsage ? (
          <div className="text-sm text-tsushin-slate">Checking dependents…</div>
        ) : (
          <>
            {dependentCount === 0 ? (
              <div className="px-3 py-2 rounded-md bg-emerald-500/10 border border-emerald-500/30 text-sm text-emerald-200">
                No agents are currently using this instance. Safe to delete.
              </div>
            ) : (
              <>
                <div className="px-3 py-2 rounded-md bg-amber-500/10 border border-amber-500/30 text-sm text-amber-200">
                  <strong>{dependentCount}</strong> agent{dependentCount !== 1 ? 's' : ''} currently
                  use{dependentCount === 1 ? 's' : ''} <strong>{instance.instance_name}</strong>.
                  Pick where to reassign them before deleting.
                </div>

                <ul
                  className="text-xs text-tsushin-slate max-h-32 overflow-y-auto rounded-md border border-tsushin-border bg-tsushin-ink/40 p-2 space-y-1"
                  data-testid="provider-delete-dependents-list"
                >
                  {usage?.agents.map((a) => (
                    <li key={a.id} className="flex items-center justify-between">
                      <span>
                        <span className="text-white font-medium">{a.name}</span>
                        <span className="ml-2 text-tsushin-slate">
                          ({a.model_provider} / {a.model_name})
                        </span>
                      </span>
                      {!a.is_active && <span className="text-amber-400">inactive</span>}
                    </li>
                  ))}
                </ul>

                <div className="space-y-2">
                  <label className="flex items-center gap-2 text-sm text-white">
                    <input
                      type="radio"
                      checked={strategy === 'reassign'}
                      onChange={() => setStrategy('reassign')}
                      data-testid="provider-delete-strategy-reassign"
                    />
                    <span>Reassign to another instance</span>
                  </label>
                  {strategy === 'reassign' && (
                    <select
                      value={reassignTo ?? ''}
                      onChange={(e) => setReassignTo(e.target.value ? parseInt(e.target.value, 10) : null)}
                      disabled={sameVendorOptions.length === 0}
                      className="ml-6 w-[calc(100%-1.5rem)] px-3 py-2 bg-tsushin-surface border border-tsushin-border rounded-md text-sm text-white"
                      data-testid="provider-delete-reassign-target"
                    >
                      {sameVendorOptions.length === 0 && (
                        <option value="">No other {instance.vendor} instance — switch to Unassign</option>
                      )}
                      {sameVendorOptions.map((opt) => (
                        <option key={opt.id} value={opt.id}>
                          {opt.instance_name}
                          {opt.is_default ? ' (default)' : ''}
                          {opt.health_status && opt.health_status !== 'healthy'
                            ? ` [${opt.health_status}]`
                            : ''}
                        </option>
                      ))}
                    </select>
                  )}

                  <label className="flex items-center gap-2 text-sm text-white">
                    <input
                      type="radio"
                      checked={strategy === 'unassign'}
                      onChange={() => setStrategy('unassign')}
                      data-testid="provider-delete-strategy-unassign"
                    />
                    <span>Unassign (agents will use the tenant default)</span>
                  </label>
                  {strategy === 'unassign' && (
                    <div className="ml-6 px-3 py-2 rounded-md bg-tsushin-ink/40 border border-tsushin-border text-xs text-tsushin-slate">
                      Dependents lose their bound instance. They will fall back to the tenant
                      default for their vendor (or the boot-migration auto-instance for Ollama).
                    </div>
                  )}
                </div>
              </>
            )}

            {error && (
              <div className="px-3 py-2 rounded-md bg-red-500/10 border border-red-500/30 text-sm text-red-200">
                {error}
              </div>
            )}
          </>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="px-4 py-2 text-sm text-tsushin-slate hover:text-white"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={submitting || loadingUsage}
            className="px-4 py-2 bg-tsushin-vermilion text-white rounded-md text-sm font-medium hover:bg-red-400 disabled:opacity-50"
            data-testid="provider-delete-confirm"
          >
            {submitting ? 'Deleting…' : 'Delete instance'}
          </button>
        </div>
      </div>
    </Modal>
  )
}
