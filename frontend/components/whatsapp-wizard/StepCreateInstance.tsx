'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { api, WhatsAppMCPInstance } from '@/lib/client'
import { useWhatsAppWizard } from '@/contexts/WhatsAppWizardContext'

export default function StepCreateInstance() {
  const { state, setInstanceData, setInstanceDisplayName, setBotContact, addContact, nextStep, markStepComplete } = useWhatsAppWizard()

  const [displayName, setDisplayName] = useState('')
  const [phoneNumber, setPhoneNumber] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Existing instances (for re-run case)
  const [existingInstances, setExistingInstances] = useState<WhatsAppMCPInstance[]>([])
  const [useExisting, setUseExisting] = useState(false)
  const [selectedExistingId, setSelectedExistingId] = useState<number | null>(null)

  // QR code state
  const [qrCode, setQrCode] = useState<string | null>(null)
  const [authenticated, setAuthenticated] = useState(false)
  const [instanceId, setInstanceId] = useState<number | null>(state.createdInstanceId)

  const healthIntervalRef = useRef<NodeJS.Timeout | null>(null)
  const qrIntervalRef = useRef<NodeJS.Timeout | null>(null)

  // Load existing instances on mount
  useEffect(() => {
    api.getMCPInstances().then(setExistingInstances).catch(() => {})
  }, [])

  // If we already have an instance from a previous wizard run, re-verify
  // health before flipping into the success state. BUG-591: previously we
  // trusted `state.stepsCompleted[2]` alone, but that flag could be set by
  // `setInstanceData()` before the QR was ever scanned, causing the UI to
  // flash "WhatsApp Connected!" on the creation step.
  useEffect(() => {
    if (!state.createdInstance) return
    const cachedInstanceId = state.createdInstance.id
    setInstanceId(cachedInstanceId)
    if (!state.stepsCompleted[2]) return
    let cancelled = false
    api.getMCPHealth(cachedInstanceId).then(health => {
      if (cancelled) return
      if (health.authenticated) {
        setAuthenticated(true)
      } else {
        // Health says not authenticated — fall back to the QR scan UI.
        setAuthenticated(false)
        startPolling(cachedInstanceId)
      }
    }).catch(() => {
      if (cancelled) return
      // Health endpoint unavailable — resume polling instead of flashing
      // a false success.
      setAuthenticated(false)
      startPolling(cachedInstanceId)
    })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.createdInstance, state.stepsCompleted])

  // QR polling
  const startPolling = useCallback((id: number) => {
    setInstanceId(id)

    // Fetch QR immediately
    api.getMCPQRCode(id).then(res => {
      if (res.qr_code) setQrCode(res.qr_code)
    }).catch(() => {})

    // Poll health every 3s
    healthIntervalRef.current = setInterval(async () => {
      try {
        const health = await api.getMCPHealth(id)
        if (health.authenticated) {
          setAuthenticated(true)
          clearInterval(healthIntervalRef.current!)
          clearInterval(qrIntervalRef.current!)
          // Fetch full instance data
          const inst = await api.getMCPInstance(id)
          setInstanceData(inst)
          setInstanceDisplayName(displayName.trim() || 'Tsushin Bot')
          markStepComplete(2)
          // Auto-create bot contact
          try {
            const botName = displayName.trim() || 'Tsushin Bot'
            const botContact = await api.createContact({
              friendly_name: botName,
              phone_number: inst.phone_number,
              role: 'agent',
              is_dm_trigger: false,
              is_active: true,
            })
            setBotContact(botContact)
            addContact(botContact)
          } catch (e) {
            console.warn('Failed to auto-create bot contact:', e)
          }
          // Auto-advance after 1.5s
          setTimeout(() => nextStep(), 1500)
        }
      } catch {}
    }, 3000)

    // Refresh QR every 15s
    qrIntervalRef.current = setInterval(async () => {
      try {
        const res = await api.getMCPQRCode(id)
        if (res.qr_code) setQrCode(res.qr_code)
      } catch {}
    }, 15000)
  }, [setInstanceData, setInstanceDisplayName, setBotContact, addContact, markStepComplete, nextStep, displayName])

  // Cleanup intervals on unmount
  useEffect(() => {
    return () => {
      if (healthIntervalRef.current) clearInterval(healthIntervalRef.current)
      if (qrIntervalRef.current) clearInterval(qrIntervalRef.current)
    }
  }, [])

  const handleCreate = async () => {
    if (!phoneNumber.trim()) {
      setError('Please enter a phone number')
      return
    }
    setCreating(true)
    setError(null)
    try {
      const instance = await api.createMCPInstance(phoneNumber.trim(), 'agent', displayName.trim() || undefined)
      setInstanceData(instance)
      startPolling(instance.id)
    } catch (e: any) {
      setError(e.message || 'Failed to create instance')
    } finally {
      setCreating(false)
    }
  }

  const handleSelectExisting = async () => {
    if (!selectedExistingId) return
    setError(null)
    try {
      const inst = await api.getMCPInstance(selectedExistingId)
      setInstanceData(inst)

      // Check if already authenticated
      const health = await api.getMCPHealth(selectedExistingId)
      if (health.authenticated) {
        setAuthenticated(true)
        markStepComplete(2)
      } else {
        startPolling(selectedExistingId)
      }
    } catch (e: any) {
      setError(e.message || 'Failed to load instance')
    }
  }

  // Already authenticated state
  if (authenticated) {
    return (
      <div className="text-center py-8">
        <div className="w-16 h-16 bg-green-500 rounded-full flex items-center justify-center mx-auto mb-4">
          <svg className="w-10 h-10 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <p className="text-green-400 font-medium text-lg">WhatsApp Connected!</p>
        <p className="text-white text-sm mt-2 font-medium">
          {state.instanceDisplayName || state.createdInstance?.phone_number}
        </p>
        {state.instanceDisplayName && (
          <p className="text-tsushin-slate text-xs mt-1">
            {state.createdInstance?.phone_number}
          </p>
        )}
        <button
          onClick={nextStep}
          className="mt-6 px-6 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg transition-colors"
        >
          Continue to About You
        </button>
      </div>
    )
  }

  // QR code display (instance created, waiting for scan)
  if (instanceId && !authenticated) {
    return (
      <div className="text-center space-y-4">
        {qrCode ? (
          <>
            <div className="relative inline-block">
              <img
                src={`data:image/png;base64,${qrCode}`}
                alt="WhatsApp QR Code"
                className="mx-auto max-w-xs border-4 border-tsushin-border rounded-lg"
              />
              <div className="absolute top-2 right-2 flex items-center gap-1 bg-gray-800/80 px-2 py-1 rounded text-xs text-gray-400">
                <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                <span>Live</span>
              </div>
            </div>
            <p className="text-tsushin-slate">Scan this QR code with WhatsApp on your phone</p>
            <div className="text-left max-w-xs mx-auto">
              <ol className="text-sm text-tsushin-slate space-y-2">
                <li>1. Open WhatsApp on your phone</li>
                <li>2. Tap <span className="text-white">Menu</span> &rarr; <span className="text-white">Linked Devices</span></li>
                <li>3. Tap <span className="text-white">Link a Device</span></li>
                <li>4. Point your phone camera at this QR code</li>
              </ol>
            </div>
            <p className="text-xs text-tsushin-slate/60">QR refreshes automatically every 15 seconds</p>
          </>
        ) : (
          <div className="py-8">
            <div className="w-16 h-16 border-4 border-teal-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
            <p className="text-tsushin-slate">Loading QR code...</p>
          </div>
        )}
      </div>
    )
  }

  // Create or select instance form
  return (
    <div className="space-y-6">
      <p className="text-tsushin-slate text-sm">
        Connect a phone number to WhatsApp. This creates a dedicated bridge so your AI agent can send and receive messages through it.
      </p>

      {existingInstances.length > 0 && (
        <div className="flex gap-2 mb-4">
          <button
            onClick={() => setUseExisting(false)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              !useExisting
                ? 'bg-teal-600 text-white'
                : 'bg-tsushin-deep border border-tsushin-border text-tsushin-slate hover:text-white'
            }`}
          >
            New Number
          </button>
          <button
            onClick={() => setUseExisting(true)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              useExisting
                ? 'bg-teal-600 text-white'
                : 'bg-tsushin-deep border border-tsushin-border text-tsushin-slate hover:text-white'
            }`}
          >
            Use Existing ({existingInstances.length})
          </button>
        </div>
      )}

      {useExisting ? (
        <div className="space-y-4">
          <label className="block text-sm font-medium text-white">Select an instance</label>
          <select
            value={selectedExistingId || ''}
            onChange={(e) => setSelectedExistingId(Number(e.target.value) || null)}
            className="w-full px-3 py-2 bg-tsushin-deep border border-tsushin-border rounded-lg text-white"
          >
            <option value="">Choose...</option>
            {existingInstances.map((inst) => (
              <option key={inst.id} value={inst.id}>
                {inst.phone_number} ({inst.status})
              </option>
            ))}
          </select>
          <button
            onClick={handleSelectExisting}
            disabled={!selectedExistingId}
            className="w-full py-2 bg-teal-600 hover:bg-teal-700 disabled:opacity-50 text-white font-medium rounded-lg transition-colors"
          >
            Use This Instance
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-white mb-2">Instance Name <span className="text-tsushin-slate font-normal">(optional)</span></label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="e.g., Support Bot, Sales Line"
              className="w-full px-3 py-2 bg-tsushin-deep border border-tsushin-border rounded-lg text-white placeholder-tsushin-slate/50"
            />
            <p className="mt-1 text-xs text-tsushin-slate">
              A friendly label for this WhatsApp number. If blank, the phone number is used.
            </p>
          </div>
          <div>
            <label className="block text-sm font-medium text-white mb-2">Phone Number</label>
            <input
              type="text"
              value={phoneNumber}
              onChange={(e) => setPhoneNumber(e.target.value)}
              placeholder="+5500000000001"
              className="w-full px-3 py-2 bg-tsushin-deep border border-tsushin-border rounded-lg text-white placeholder-tsushin-slate/50"
            />
            <p className="mt-1 text-xs text-tsushin-slate">
              Include country code (e.g., +55 for Brazil, +1 for US)
            </p>
          </div>
          <button
            onClick={handleCreate}
            disabled={creating}
            className="w-full py-2 bg-teal-600 hover:bg-teal-700 disabled:opacity-50 text-white font-medium rounded-lg transition-colors"
          >
            {creating ? 'Creating...' : 'Create & Connect'}
          </button>
        </div>
      )}

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3">
          <p className="text-sm text-red-400">{error}</p>
        </div>
      )}
    </div>
  )
}
