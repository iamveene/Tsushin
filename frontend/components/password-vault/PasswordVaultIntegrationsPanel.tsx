'use client'

import { useEffect, useState } from 'react'
import Modal from '@/components/ui/Modal'
import { LockIcon } from '@/components/ui/icons'
import { api } from '@/lib/client'
import type {
  PasswordVaultIntegration,
  PasswordVaultIntegrationCreateRequest,
  PasswordVaultIntegrationUpdateRequest,
  PasswordVaultSecretOverride,
} from '@/lib/client'

type PasswordVaultDraft = {
  integration_name: string
  provider: string
  service_account_token: string
  account_url: string
  account_email: string
  default_vault: string
  default_vault_id: string
  allowed_items_text: string
  allowed_fields_text: string
  allow_metadata_read: boolean
  allow_secret_read: boolean
  allow_totp_read: boolean
  is_active: boolean
}

export type PasswordVaultSaveDraft =
  | PasswordVaultIntegrationCreateRequest
  | PasswordVaultIntegrationUpdateRequest

function integrationName(integration: PasswordVaultIntegration): string {
  return integration.integration_name || integration.name || `Password Vault #${integration.id}`
}

function statusClasses(status?: string | null): string {
  const normalized = (status || '').toLowerCase()
  if (['healthy', 'success', 'ok', 'active', 'connected'].includes(normalized)) return 'border-green-500/30 bg-green-500/10 text-green-300'
  if (['unhealthy', 'error', 'failed'].includes(normalized)) return 'border-red-500/30 bg-red-500/10 text-red-300'
  if (['degraded', 'warning'].includes(normalized)) return 'border-yellow-500/30 bg-yellow-500/10 text-yellow-300'
  return 'border-tsushin-border bg-tsushin-slate/10 text-tsushin-slate'
}

function draftFromTarget(target: PasswordVaultIntegration | null): PasswordVaultDraft {
  return {
    integration_name: target ? integrationName(target) : '1Password',
    provider: target?.provider || 'onepassword',
    service_account_token: '',
    account_url: target?.account_url || '',
    account_email: target?.account_email || '',
    default_vault: target?.default_vault || target?.default_vault_name || '',
    default_vault_id: target?.default_vault_id || '',
    allowed_items_text: (target?.allowed_items || []).join('\n'),
    allowed_fields_text: (target?.allowed_fields || []).join('\n'),
    allow_metadata_read: target?.allow_metadata_read ?? true,
    allow_secret_read: target?.allow_secret_read ?? false,
    allow_totp_read: target?.allow_totp_read ?? false,
    is_active: target?.is_active ?? true,
  }
}

export function PasswordVaultIntegrationModal({
  isOpen,
  target,
  saving,
  onClose,
  onSave,
}: {
  isOpen: boolean
  target: PasswordVaultIntegration | null
  saving: boolean
  onClose: () => void
  onSave: (draft: PasswordVaultDraft) => void
}) {
  const [draft, setDraft] = useState<PasswordVaultDraft>(() => draftFromTarget(target))

  const canSave = Boolean(
    draft.integration_name.trim()
      && draft.provider.trim()
      && (target || draft.service_account_token.trim())
      && !saving
  )

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={target ? 'Edit Password Vault Connection' : 'Add Password Vault Connection'}
      footer={(
        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="rounded-lg border border-tsushin-border px-4 py-2 text-sm text-tsushin-slate hover:text-white disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onSave(draft)}
            disabled={!canSave}
            className="rounded-lg bg-teal-600 px-4 py-2 text-sm font-medium text-white hover:bg-teal-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      )}
    >
      <div className="space-y-4">
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="mb-2 block text-sm font-medium text-gray-300">Connection name</label>
            <input
              type="text"
              value={draft.integration_name}
              onChange={(event) => setDraft((current) => ({ ...current, integration_name: event.target.value }))}
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-white"
              placeholder="1Password production"
            />
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-gray-300">Provider</label>
            <select
              value={draft.provider}
              onChange={(event) => setDraft((current) => ({ ...current, provider: event.target.value }))}
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-white"
            >
              <option value="onepassword">1Password</option>
            </select>
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-gray-300">
              Service account token {target ? <span className="text-xs text-tsushin-slate">(leave blank to keep current)</span> : null}
            </label>
            <input
              type="password"
              value={draft.service_account_token}
              onChange={(event) => setDraft((current) => ({ ...current, service_account_token: event.target.value }))}
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 font-mono text-white"
              placeholder={target ? 'Enter a replacement token' : 'ops_...'}
              autoComplete="new-password"
            />
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-gray-300">Account email <span className="text-xs text-tsushin-slate">(optional)</span></label>
            <input
              type="email"
              value={draft.account_email}
              onChange={(event) => setDraft((current) => ({ ...current, account_email: event.target.value }))}
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-white"
              placeholder="ops@example.com"
            />
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-gray-300">Account URL <span className="text-xs text-tsushin-slate">(optional)</span></label>
            <input
              type="url"
              value={draft.account_url}
              onChange={(event) => setDraft((current) => ({ ...current, account_url: event.target.value }))}
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-white"
              placeholder="https://my.1password.com"
            />
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-gray-300">Default vault <span className="text-xs text-tsushin-slate">(optional)</span></label>
            <input
              type="text"
              value={draft.default_vault}
              onChange={(event) => setDraft((current) => ({ ...current, default_vault: event.target.value }))}
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-white"
              placeholder="FinanApp"
            />
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-gray-300">Default vault ID <span className="text-xs text-tsushin-slate">(optional)</span></label>
            <input
              type="text"
              value={draft.default_vault_id}
              onChange={(event) => setDraft((current) => ({ ...current, default_vault_id: event.target.value }))}
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 font-mono text-white"
              placeholder="Leave blank to choose in flows"
            />
          </div>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="mb-2 block text-sm font-medium text-gray-300">Allowed item IDs or titles <span className="text-xs text-tsushin-slate">(optional)</span></label>
            <textarea
              value={draft.allowed_items_text}
              onChange={(event) => setDraft((current) => ({ ...current, allowed_items_text: event.target.value }))}
              className="min-h-[88px] w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 font-mono text-xs text-white"
              placeholder="One item per line"
            />
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-gray-300">Allowed field names <span className="text-xs text-tsushin-slate">(optional)</span></label>
            <textarea
              value={draft.allowed_fields_text}
              onChange={(event) => setDraft((current) => ({ ...current, allowed_fields_text: event.target.value }))}
              className="min-h-[88px] w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 font-mono text-xs text-white"
              placeholder="password\nusername\notp"
            />
          </div>
        </div>
        <div className="rounded-lg border border-tsushin-border bg-tsushin-ink/40 p-3">
          <div className="mb-2 text-sm font-medium text-gray-300">Runtime permissions</div>
          <div className="grid gap-2 text-sm text-gray-300 md:grid-cols-3">
            <label className="flex items-start gap-2">
              <input
                type="checkbox"
                checked={draft.allow_metadata_read}
                onChange={(event) => setDraft((current) => ({ ...current, allow_metadata_read: event.target.checked }))}
                className="mt-1"
              />
              <span>List metadata</span>
            </label>
            <label className="flex items-start gap-2">
              <input
                type="checkbox"
                checked={draft.allow_secret_read}
                onChange={(event) => setDraft((current) => ({ ...current, allow_secret_read: event.target.checked }))}
                className="mt-1"
              />
              <span>Resolve fields</span>
            </label>
            <label className="flex items-start gap-2">
              <input
                type="checkbox"
                checked={draft.allow_totp_read}
                onChange={(event) => setDraft((current) => ({ ...current, allow_totp_read: event.target.checked }))}
                className="mt-1"
              />
              <span>Resolve TOTP</span>
            </label>
          </div>
        </div>
        <div className="rounded-lg border border-tsushin-border bg-tsushin-ink/40 p-3 text-xs text-tsushin-slate">
          Store the provider token here. Agents and flows use vault references such as <code className="text-tsushin-accent">op://vault/item/field</code>; secret values are never entered into flow prompts.
        </div>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={draft.is_active}
            onChange={(event) => setDraft((current) => ({ ...current, is_active: event.target.checked }))}
          />
          <span className="text-sm text-gray-300">Enable this password vault connection</span>
        </label>
      </div>
    </Modal>
  )
}

export function PasswordVaultIntegrationsPanel({
  integrations,
  loading,
  testingId,
  testResults,
  canWriteHub,
  onAdd,
  onEdit,
  onDelete,
  onTest,
}: {
  integrations: PasswordVaultIntegration[]
  loading: boolean
  testingId: number | null
  testResults: Record<number, { success: boolean; message: string }>
  canWriteHub: boolean
  onAdd: () => void
  onEdit: (integration: PasswordVaultIntegration) => void
  onDelete: (integration: PasswordVaultIntegration) => void
  onTest: (integration: PasswordVaultIntegration, reference: string) => void
}) {
  const [testReferenceById, setTestReferenceById] = useState<Record<number, string>>({})
  const [managedFieldsById, setManagedFieldsById] = useState<Record<number, PasswordVaultSecretOverride[]>>({})
  const [managedDraftById, setManagedDraftById] = useState<Record<number, {
    vault: string
    item_ref: string
    field_name: string
    value: string
  }>>({})
  const [managedSavingId, setManagedSavingId] = useState<number | null>(null)

  function baseManagedDraft(integration: PasswordVaultIntegration) {
    return {
      vault: integration.default_vault || integration.default_vault_name || '',
      item_ref: '',
      field_name: '',
      value: '',
    }
  }

  function updateManagedDraft(
    integration: PasswordVaultIntegration,
    patch: Partial<{ vault: string; item_ref: string; field_name: string; value: string }>
  ) {
    setManagedDraftById((current) => ({
      ...current,
      [integration.id]: {
        ...(current[integration.id] || baseManagedDraft(integration)),
        ...patch,
      },
    }))
  }

  useEffect(() => {
    if (integrations.length === 0) {
      setManagedFieldsById({})
      return
    }
    integrations.forEach((integration) => {
      loadManagedFields(integration.id)
      setManagedDraftById((current) => ({
        ...current,
        [integration.id]: current[integration.id] || baseManagedDraft(integration),
      }))
    })
  }, [integrations])

  async function loadManagedFields(integrationId: number) {
    try {
      const rows = await api.listPasswordVaultSecretOverrides(integrationId)
      setManagedFieldsById((current) => ({ ...current, [integrationId]: rows }))
    } catch (error) {
      console.error('Failed to load managed Password Vault fields:', error)
    }
  }

  async function saveManagedField(integration: PasswordVaultIntegration) {
    const draft = managedDraftById[integration.id]
    if (!draft || !draft.item_ref.trim() || !draft.field_name.trim() || !draft.value) return
    setManagedSavingId(integration.id)
    try {
      await api.createPasswordVaultSecretOverride(integration.id, {
        vault: draft.vault.trim() || null,
        item_ref: draft.item_ref.trim(),
        field_name: draft.field_name.trim(),
        field_type: 'CONCEALED',
        value: draft.value,
      })
      setManagedDraftById((current) => ({
        ...current,
        [integration.id]: {
          ...draft,
          value: '',
        },
      }))
      await loadManagedFields(integration.id)
    } catch (error) {
      console.error('Failed to save managed Password Vault field:', error)
    } finally {
      setManagedSavingId(null)
    }
  }

  async function deleteManagedField(integrationId: number, secretId: number) {
    setManagedSavingId(integrationId)
    try {
      await api.deletePasswordVaultSecretOverride(integrationId, secretId)
      await loadManagedFields(integrationId)
    } catch (error) {
      console.error('Failed to delete managed Password Vault field:', error)
    } finally {
      setManagedSavingId(null)
    }
  }

  return (
    <div className="card p-5 hover-glow group border-teal-700/30" data-testid="password-vault-integrations-card">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-teal-500/10 text-teal-300 transition-transform group-hover:scale-110">
            <LockIcon size={20} />
          </div>
          <div>
            <h3 className="font-semibold text-white">Password Vault</h3>
            <p className="text-xs text-tsushin-slate">Provider-backed secret references for agents, flows, and browser automation</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <span className="rounded-full border border-teal-500/25 bg-teal-500/10 px-2 py-0.5 text-[11px] text-teal-200">1Password provider</span>
              <span className="rounded-full border border-tsushin-border bg-tsushin-slate/10 px-2 py-0.5 text-[11px] text-tsushin-slate">Skill-ready</span>
              <span className="rounded-full border border-tsushin-border bg-tsushin-slate/10 px-2 py-0.5 text-[11px] text-tsushin-slate">Flow-ready</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={integrations.some((item) => item.is_active) ? 'badge badge-success' : 'badge badge-neutral'}>
            {integrations.length > 0 ? `${integrations.length} configured` : 'Not configured'}
          </span>
          {canWriteHub && (
            <button
              type="button"
              onClick={onAdd}
              className="rounded-lg bg-teal-500/20 px-3 py-1.5 text-xs font-medium text-teal-200 transition-colors hover:bg-teal-500/30 hover:text-white"
            >
              + Add provider
            </button>
          )}
        </div>
      </div>

      {loading ? (
        <div className="rounded-lg border border-white/5 bg-tsushin-ink/40 p-4 text-center text-xs text-tsushin-slate">Loading password vault connections...</div>
      ) : integrations.length === 0 ? (
        <div className="rounded-lg border border-dashed border-tsushin-border bg-tsushin-ink/30 p-5 text-center">
          <p className="text-sm text-tsushin-slate">
            {canWriteHub ? 'No password vault connections yet. Add 1Password here, then attach the Password Vault skill to agents or choose vault references in flows.' : 'No password vault connections configured.'}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {integrations.map((integration) => {
            const status = integration.health_status || integration.last_test_status || (integration.is_active ? 'active' : 'inactive')
            const result = testResults[integration.id]
            const testReference = testReferenceById[integration.id] ?? ''
            const managedFields = managedFieldsById[integration.id] || []
            const managedDraft = managedDraftById[integration.id] || baseManagedDraft(integration)
            const vaultLabel = integration.default_vault_name || integration.default_vault || 'No default vault'
            const vaultId = integration.default_vault_id || 'No vault ID'
            const accountHint = integration.account_email || integration.account_url || 'No account hint'
            const counts = [
              integration.vault_count !== null && integration.vault_count !== undefined ? `${integration.vault_count} vaults` : null,
              integration.item_count !== null && integration.item_count !== undefined ? `${integration.item_count} items` : null,
              integration.skill_attached_count !== null && integration.skill_attached_count !== undefined ? `${integration.skill_attached_count} skills` : null,
              integration.flow_reference_count !== null && integration.flow_reference_count !== undefined ? `${integration.flow_reference_count} flows` : null,
            ].filter(Boolean).join(' - ')

            return (
              <div key={integration.id} className="rounded-lg border border-white/5 bg-tsushin-ink/40 p-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0 space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="truncate text-sm font-medium text-white">{integrationName(integration)}</span>
                      <span className={`rounded-full border px-2 py-0.5 text-[11px] ${statusClasses(status)}`}>{status}</span>
                      <span className="rounded-full border border-tsushin-border bg-tsushin-slate/10 px-2 py-0.5 text-[11px] text-tsushin-slate">
                        {integration.provider_label || (integration.provider === 'onepassword' ? '1Password' : integration.provider)}
                      </span>
                    </div>
                    <div className="grid gap-2 text-xs text-tsushin-slate sm:grid-cols-2">
                      <span className="min-w-0 truncate">Vault: <span className="font-mono text-tsushin-accent">{vaultLabel}</span></span>
                      <span className="min-w-0 truncate">Vault ID: <span className="font-mono text-tsushin-accent">{vaultId}</span></span>
                      <span className="min-w-0 truncate">Account: <span className="font-mono text-tsushin-accent">{accountHint}</span></span>
                      <span>{counts || 'No usage counted yet'}</span>
                      <span>{integration.last_tested_at || integration.last_health_check ? `Checked ${new Date(integration.last_tested_at || integration.last_health_check || '').toLocaleString()}` : 'Not tested yet'}</span>
                    </div>
                    {integration.health_status_reason && (
                      <p className="text-xs text-yellow-200">{integration.health_status_reason}</p>
                    )}
                  </div>
                  {canWriteHub && (
                    <div className="flex shrink-0 gap-2">
                      <button
                        type="button"
                        onClick={() => onEdit(integration)}
                        className="rounded-lg border border-tsushin-border px-3 py-1.5 text-xs text-tsushin-slate hover:text-white"
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => onDelete(integration)}
                        className="rounded-lg border border-tsushin-vermilion/30 bg-tsushin-vermilion/10 px-3 py-1.5 text-xs text-tsushin-vermilion hover:bg-tsushin-vermilion/20"
                      >
                        Remove
                      </button>
                    </div>
                  )}
                </div>

                <div className="mt-3 grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
                  <input
                    type="text"
                    value={testReference}
                    onChange={(event) => setTestReferenceById((current) => ({ ...current, [integration.id]: event.target.value }))}
                    placeholder="Optional test reference: op://vault/item/field"
                    className="w-full rounded-lg border border-tsushin-border bg-black/25 px-3 py-2 font-mono text-xs text-white placeholder:text-tsushin-slate focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-500/30"
                  />
                  <button
                    type="button"
                    onClick={() => onTest(integration, testReference)}
                    disabled={testingId === integration.id}
                    className="inline-flex items-center justify-center rounded-lg border border-teal-400/40 bg-teal-500/10 px-4 py-2 text-xs text-teal-100 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {testingId === integration.id ? 'Testing...' : 'Test'}
                  </button>
                </div>
                {result && (
                  <div className={`mt-3 rounded-lg border px-3 py-2 text-xs ${
                    result.success ? 'border-green-500/30 bg-green-500/10 text-green-200' : 'border-red-500/30 bg-red-500/10 text-red-200'
                  }`}>
                    {result.message}
                  </div>
                )}

                <div className="mt-4 border-t border-white/10 pt-4">
                  <div className="mb-3 flex items-center justify-between gap-2">
                    <div className="text-xs font-semibold uppercase tracking-wide text-tsushin-slate">Managed fields</div>
                    <span className="rounded-full border border-tsushin-border px-2 py-0.5 text-[11px] text-tsushin-slate">
                      {managedFields.length}
                    </span>
                  </div>
                  {managedFields.length > 0 && (
                    <div className="mb-3 space-y-2">
                      {managedFields.map((field) => (
                        <div key={field.id} className="grid gap-2 rounded-lg border border-white/5 bg-black/20 px-3 py-2 text-xs text-tsushin-slate sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
                          <div className="min-w-0">
                            <div className="truncate font-mono text-teal-200">
                              {field.vault || integration.default_vault_name || integration.default_vault_id || 'default'} / {field.item_ref} / {field.field_name}
                            </div>
                            <div>{field.value_preview}</div>
                          </div>
                          {canWriteHub && (
                            <button
                              type="button"
                              onClick={() => deleteManagedField(integration.id, field.id)}
                              disabled={managedSavingId === integration.id}
                              className="rounded-lg border border-tsushin-vermilion/30 px-3 py-1.5 text-xs text-tsushin-vermilion hover:bg-tsushin-vermilion/10 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              Remove
                            </button>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                  {canWriteHub && (
                    <div className="grid gap-2 lg:grid-cols-[minmax(110px,0.9fr)_minmax(110px,1fr)_minmax(110px,0.8fr)_minmax(140px,1fr)_auto]">
                      <input
                        type="text"
                        value={managedDraft.vault}
                        onChange={(event) => updateManagedDraft(integration, { vault: event.target.value })}
                        placeholder="Vault"
                        aria-label={`Managed field vault for ${integrationName(integration)}`}
                        data-testid={`password-vault-${integration.id}-managed-vault`}
                        className="rounded-lg border border-tsushin-border bg-black/25 px-3 py-2 text-xs text-white placeholder:text-tsushin-slate"
                      />
                      <input
                        type="text"
                        value={managedDraft.item_ref}
                        onChange={(event) => updateManagedDraft(integration, { item_ref: event.target.value })}
                        placeholder="Item"
                        aria-label={`Managed field item for ${integrationName(integration)}`}
                        data-testid={`password-vault-${integration.id}-managed-item`}
                        className="rounded-lg border border-tsushin-border bg-black/25 px-3 py-2 text-xs text-white placeholder:text-tsushin-slate"
                      />
                      <input
                        type="text"
                        value={managedDraft.field_name}
                        onChange={(event) => updateManagedDraft(integration, { field_name: event.target.value })}
                        placeholder="Field"
                        aria-label={`Managed field name for ${integrationName(integration)}`}
                        data-testid={`password-vault-${integration.id}-managed-field`}
                        className="rounded-lg border border-tsushin-border bg-black/25 px-3 py-2 text-xs text-white placeholder:text-tsushin-slate"
                      />
                      <input
                        type="password"
                        value={managedDraft.value}
                        onChange={(event) => updateManagedDraft(integration, { value: event.target.value })}
                        placeholder="Secret value"
                        autoComplete="new-password"
                        aria-label={`Managed field secret value for ${integrationName(integration)}`}
                        data-testid={`password-vault-${integration.id}-managed-value`}
                        className="rounded-lg border border-tsushin-border bg-black/25 px-3 py-2 text-xs text-white placeholder:text-tsushin-slate"
                      />
                      <button
                        type="button"
                        onClick={() => saveManagedField(integration)}
                        disabled={managedSavingId === integration.id || !managedDraft.item_ref.trim() || !managedDraft.field_name.trim() || !managedDraft.value}
                        data-testid={`password-vault-${integration.id}-managed-save`}
                        className="inline-flex items-center justify-center rounded-lg border border-teal-400/40 bg-teal-500/10 px-4 py-2 text-xs text-teal-100 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {managedSavingId === integration.id ? 'Saving...' : 'Save field'}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export { integrationName as passwordVaultIntegrationName }
