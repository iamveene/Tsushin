'use client'

import { useEffect, useId, useMemo, useState } from 'react'
import { api, type PasswordVaultIntegration, type PasswordVaultItem, type PasswordVaultSecretOverride, type PasswordVaultVault } from '@/lib/client'
import { AlertTriangleIcon, CheckIcon, LockIcon } from '@/components/ui/icons'

export type PasswordVaultReferenceValue = {
  password_vault_integration_id?: number | null
  password_vault_provider?: string | null
  password_vault_vault_id?: string | null
  password_vault_vault_name?: string | null
  password_vault_item_id?: string | null
  password_vault_item_title?: string | null
  password_vault_field_name?: string | null
  password_vault_reference?: string | null
}

function safeSegment(value?: string | null): string {
  return (value || '').trim().replace(/\//g, '-')
}

function buildOnePasswordReference(vaultName?: string | null, itemTitle?: string | null, fieldName?: string | null): string {
  const vault = safeSegment(vaultName)
  const item = safeSegment(itemTitle)
  const field = safeSegment(fieldName)
  if (!vault || !item || !field) return ''
  return `op://${vault}/${item}/${field}`
}

function integrationLabel(integration: PasswordVaultIntegration): string {
  return integration.integration_name || integration.name || `Password Vault #${integration.id}`
}

export default function PasswordVaultReferencePicker({
  value,
  onChange,
  compact = false,
}: {
  value: PasswordVaultReferenceValue
  onChange: (value: PasswordVaultReferenceValue) => void
  compact?: boolean
}) {
  const [integrations, setIntegrations] = useState<PasswordVaultIntegration[]>([])
  const [vaults, setVaults] = useState<PasswordVaultVault[]>([])
  const [items, setItems] = useState<PasswordVaultItem[]>([])
  const [managedFields, setManagedFields] = useState<PasswordVaultSecretOverride[]>([])
  const [loading, setLoading] = useState(false)
  const [loadingVaults, setLoadingVaults] = useState(false)
  const [loadingItems, setLoadingItems] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null)
  const [testing, setTesting] = useState(false)
  const pickerId = useId()

  const selectedIntegration = useMemo(
    () => integrations.find((integration) => integration.id === Number(value.password_vault_integration_id)) || null,
    [integrations, value.password_vault_integration_id],
  )
  const selectedVault = useMemo(
    () => vaults.find((vault) =>
      vault.id === value.password_vault_vault_id ||
      vault.name === value.password_vault_vault_name ||
      vault.name === value.password_vault_vault_id
    ) || null,
    [vaults, value.password_vault_vault_id, value.password_vault_vault_name],
  )
  const selectedItem = useMemo(
    () => items.find((item) =>
      item.id === value.password_vault_item_id ||
      item.title === value.password_vault_item_title ||
      item.title === value.password_vault_item_id
    ) || null,
    [items, value.password_vault_item_id, value.password_vault_item_title],
  )
  const selectedFieldOptions = useMemo(() => {
    const itemRef = selectedItem?.title || value.password_vault_item_title || value.password_vault_item_id || null
    const vaultRef = selectedVault?.name || selectedVault?.id || value.password_vault_vault_name || value.password_vault_vault_id || null
    const byFieldName = new Map<string, { id?: string; name?: string; label?: string }>()
    for (const field of selectedItem?.fields || []) {
      const fieldName = field.name || field.label || field.id || ''
      if (fieldName) byFieldName.set(fieldName, field)
    }
    for (const field of managedFields) {
      if (!itemRef || field.item_ref !== itemRef) continue
      if (field.vault && vaultRef && field.vault !== vaultRef && field.vault !== selectedVault?.name && field.vault !== selectedVault?.id) continue
      if (field.field_name && !byFieldName.has(field.field_name)) {
        byFieldName.set(field.field_name, {
          id: `managed:${field.id}`,
          name: field.field_name,
          label: `${field.field_name} (managed)`,
        })
      }
    }
    if (value.password_vault_field_name && !byFieldName.has(value.password_vault_field_name)) {
      byFieldName.set(value.password_vault_field_name, {
        id: `current:${value.password_vault_field_name}`,
        name: value.password_vault_field_name,
        label: value.password_vault_field_name,
      })
    }
    return Array.from(byFieldName.values())
  }, [
    managedFields,
    selectedItem,
    selectedVault,
    value.password_vault_field_name,
    value.password_vault_item_id,
    value.password_vault_item_title,
    value.password_vault_vault_id,
    value.password_vault_vault_name,
  ])
  const vaultSelectValue = selectedVault?.id || value.password_vault_vault_id || ''
  const itemSelectValue = selectedItem?.id || value.password_vault_item_id || ''
  const vaultForItems = selectedVault?.id || value.password_vault_vault_id || value.password_vault_vault_name || null
  const canPickItem = Boolean(selectedVault || value.password_vault_vault_id || value.password_vault_vault_name)
  const canEditField = Boolean(selectedItem || value.password_vault_item_id || value.password_vault_item_title)

  useEffect(() => {
    let mounted = true
    setLoading(true)
    setError(null)
    api.listPasswordVaultIntegrations()
      .then((data) => {
        if (!mounted) return
        const active = data.filter((integration) => integration.is_active)
        setIntegrations(active)
      })
      .catch((err) => {
        if (mounted) setError(err instanceof Error ? err.message : 'Failed to load password vault connections')
      })
      .finally(() => {
        if (mounted) setLoading(false)
      })
    return () => { mounted = false }
  }, [])

  useEffect(() => {
    if (!value.password_vault_integration_id) {
      setVaults([])
      setManagedFields([])
      return
    }
    let mounted = true
    setLoadingVaults(true)
    setError(null)
    api.listPasswordVaultVaults(Number(value.password_vault_integration_id))
      .then((data) => {
        if (!mounted) return
        setVaults(data)
      })
      .catch((err) => {
        if (mounted) setError(err instanceof Error ? err.message : 'Failed to load password vault vaults')
      })
      .finally(() => {
        if (mounted) setLoadingVaults(false)
      })
    return () => { mounted = false }
  }, [value.password_vault_integration_id])

  useEffect(() => {
    if (!value.password_vault_integration_id) {
      setManagedFields([])
      return
    }
    let mounted = true
    api.listPasswordVaultSecretOverrides(Number(value.password_vault_integration_id))
      .then((data) => {
        if (mounted) setManagedFields(data)
      })
      .catch(() => {
        if (mounted) setManagedFields([])
      })
    return () => { mounted = false }
  }, [value.password_vault_integration_id])

  useEffect(() => {
    if (!value.password_vault_integration_id || !vaultForItems) {
      setItems([])
      return
    }
    let mounted = true
    setLoadingItems(true)
    setError(null)
    api.listPasswordVaultItems(Number(value.password_vault_integration_id), vaultForItems)
      .then((data) => {
        if (!mounted) return
        setItems(data)
      })
      .catch((err) => {
        if (mounted) setError(err instanceof Error ? err.message : 'Failed to load password vault items')
      })
      .finally(() => {
        if (mounted) setLoadingItems(false)
      })
    return () => { mounted = false }
  }, [value.password_vault_integration_id, vaultForItems])

  function updateReference(next: PasswordVaultReferenceValue) {
    const reference = next.password_vault_reference
      || buildOnePasswordReference(next.password_vault_vault_name, next.password_vault_item_title, next.password_vault_field_name)
    onChange({
      ...next,
      password_vault_reference: reference || null,
    })
    setTestResult(null)
  }

  async function testReference() {
    if (!value.password_vault_integration_id) return
    setTesting(true)
    setTestResult(null)
    try {
      const result = await api.testPasswordVaultItem(Number(value.password_vault_integration_id), {
        vault: value.password_vault_vault_id || value.password_vault_vault_name || null,
        vault_id: value.password_vault_vault_id || null,
        item_ref: value.password_vault_item_id || value.password_vault_item_title || null,
        item_id: value.password_vault_item_id || null,
        field_name: value.password_vault_field_name || null,
        reference: value.password_vault_reference || null,
        mode: value.password_vault_field_name ? 'field' : 'metadata',
      })
      setTestResult({
        success: result.success,
        message: result.success ? (result.message || 'Reference resolved successfully.') : (result.error || result.message || 'Reference test failed.'),
      })
    } catch (err) {
      setTestResult({
        success: false,
        message: err instanceof Error ? err.message : 'Reference test failed.',
      })
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className={`rounded-lg border border-slate-700 bg-slate-800/50 ${compact ? 'p-3' : 'p-4'} space-y-3`}>
      <div className="flex items-start gap-2">
        <LockIcon size={16} className="mt-0.5 text-cyan-300" />
        <div>
          <div className="text-sm font-medium text-slate-200">Password vault reference</div>
          <p className="text-xs text-slate-400">
            Select a stored item and pass only its reference into this flow step.
          </p>
        </div>
      </div>

      {loading ? (
        <div className="text-xs text-slate-400">Loading password vault connections...</div>
      ) : integrations.length === 0 ? (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">
          <span className="inline-flex items-center gap-1"><AlertTriangleIcon size={12} /> Add a Password Vault connection in Hub &gt; Tool APIs before selecting vault items.</span>
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <label htmlFor={`${pickerId}-connection`} className="mb-1.5 block text-xs font-medium text-slate-300">Connection</label>
            <select
              id={`${pickerId}-connection`}
              value={value.password_vault_integration_id || ''}
              onChange={(event) => {
                const integration = integrations.find((item) => item.id === Number(event.target.value))
                updateReference({
                  password_vault_integration_id: integration?.id || null,
                  password_vault_provider: integration?.provider || null,
                  password_vault_vault_id: null,
                  password_vault_vault_name: null,
                  password_vault_item_id: null,
                  password_vault_item_title: null,
                  password_vault_field_name: null,
                  password_vault_reference: null,
                })
              }}
              className="w-full rounded-lg border border-slate-600 bg-slate-700/50 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500"
            >
              <option value="">Select connection...</option>
              {integrations.map((integration) => (
                <option key={integration.id} value={integration.id}>{integrationLabel(integration)}</option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor={`${pickerId}-vault`} className="mb-1.5 block text-xs font-medium text-slate-300">Vault</label>
            <select
              id={`${pickerId}-vault`}
              value={vaultSelectValue}
              disabled={!selectedIntegration || loadingVaults}
              onChange={(event) => {
                const vault = vaults.find((item) => item.id === event.target.value)
                updateReference({
                  ...value,
                  password_vault_vault_id: vault?.id || null,
                  password_vault_vault_name: vault?.name || null,
                  password_vault_item_id: null,
                  password_vault_item_title: null,
                  password_vault_field_name: null,
                  password_vault_reference: null,
                })
              }}
              className="w-full rounded-lg border border-slate-600 bg-slate-700/50 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <option value="">{loadingVaults ? 'Loading vaults...' : 'Select vault...'}</option>
              {value.password_vault_vault_name && !selectedVault && (
                <option value={value.password_vault_vault_name}>{value.password_vault_vault_name}</option>
              )}
              {vaults.map((vault) => (
                <option key={vault.id} value={vault.id}>{vault.name}</option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor={`${pickerId}-item`} className="mb-1.5 block text-xs font-medium text-slate-300">Item</label>
            <select
              id={`${pickerId}-item`}
              value={itemSelectValue}
              disabled={!canPickItem || loadingItems}
              onChange={(event) => {
                const item = items.find((entry) => entry.id === event.target.value)
                updateReference({
                  ...value,
                  password_vault_item_id: item?.id || null,
                  password_vault_item_title: item?.title || null,
                  password_vault_field_name: null,
                  password_vault_reference: null,
                })
              }}
              className="w-full rounded-lg border border-slate-600 bg-slate-700/50 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <option value="">{loadingItems ? 'Loading items...' : 'Select item...'}</option>
              {value.password_vault_item_title && !selectedItem && (
                <option value={value.password_vault_item_title}>{value.password_vault_item_title}</option>
              )}
              {items.map((item) => (
                <option key={item.id} value={item.id}>{item.title}</option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor={`${pickerId}-field`} className="mb-1.5 block text-xs font-medium text-slate-300">Field</label>
            {selectedFieldOptions.length > 0 ? (
              <select
                id={`${pickerId}-field`}
                value={value.password_vault_field_name || ''}
                disabled={!canEditField}
                onChange={(event) => updateReference({
                  ...value,
                  password_vault_field_name: event.target.value || null,
                  password_vault_reference: null,
                })}
                className="w-full rounded-lg border border-slate-600 bg-slate-700/50 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <option value="">Select field...</option>
                {selectedFieldOptions.map((field) => {
                  const fieldName = field.name || field.label || field.id || ''
                  return <option key={field.id || fieldName} value={fieldName}>{field.label || field.name || field.id}</option>
                })}
              </select>
            ) : (
              <input
                id={`${pickerId}-field`}
                type="text"
                value={value.password_vault_field_name || ''}
                disabled={!canEditField}
                onChange={(event) => updateReference({
                  ...value,
                  password_vault_field_name: event.target.value || null,
                  password_vault_reference: null,
                })}
                placeholder="password, username, otp..."
                className="w-full rounded-lg border border-slate-600 bg-slate-700/50 px-3 py-2 text-sm text-white outline-none placeholder:text-slate-500 focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 disabled:cursor-not-allowed disabled:opacity-60"
              />
            )}
          </div>
        </div>
      )}

      {value.password_vault_reference && (
        <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
          <div className="rounded-lg border border-slate-700 bg-black/20 px-3 py-2 font-mono text-xs text-cyan-200">
            {value.password_vault_reference}
          </div>
          <button
            type="button"
            onClick={testReference}
            disabled={testing || !value.password_vault_integration_id}
            className="rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-3 py-2 text-xs font-medium text-cyan-100 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {testing ? 'Testing...' : 'Test Reference'}
          </button>
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-200">{error}</div>
      )}
      {testResult && (
        <div className={`rounded-lg border p-3 text-xs ${
          testResult.success ? 'border-green-500/30 bg-green-500/10 text-green-200' : 'border-red-500/30 bg-red-500/10 text-red-200'
        }`}>
          <span className="inline-flex items-center gap-1">{testResult.success && <CheckIcon size={12} />}{testResult.message}</span>
        </div>
      )}
    </div>
  )
}
