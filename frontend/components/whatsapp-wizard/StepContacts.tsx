'use client'

import { useState, useEffect } from 'react'
import { api, Agent } from '@/lib/client'
import { useWhatsAppWizard } from '@/contexts/WhatsAppWizardContext'

export default function StepContacts() {
  const { state, addContact, markStepComplete, nextStep } = useWhatsAppWizard()

  const [agents, setAgents] = useState<Agent[]>([])
  const [friendlyName, setFriendlyName] = useState('')
  const [phoneNumber, setPhoneNumber] = useState('')
  const [isDmTrigger, setIsDmTrigger] = useState(true)
  const [defaultAgentId, setDefaultAgentId] = useState<number | null>(null)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.getAgents().then(setAgents).catch(() => {})
  }, [])

  const handleAdd = async () => {
    if (!friendlyName.trim()) {
      setError('Please enter a name')
      return
    }
    if (!phoneNumber.trim()) {
      setError('Please enter a phone number')
      return
    }
    setCreating(true)
    setError(null)
    try {
      const contact = await api.createContact({
        friendly_name: friendlyName.trim(),
        phone_number: phoneNumber.trim(),
        role: 'contact',
        is_dm_trigger: isDmTrigger,
        is_active: true,
      })
      addContact(contact)
      // Reset form
      setFriendlyName('')
      setPhoneNumber('')
      setIsDmTrigger(true)
      setDefaultAgentId(null)
    } catch (e: any) {
      setError(e.message || 'Failed to create contact')
    } finally {
      setCreating(false)
    }
  }

  const handleContinue = async () => {
    // Resolve WhatsApp IDs in background if contacts were created
    if (state.createdContacts.length > 0) {
      try {
        await api.resolveAllContactsWhatsApp()
      } catch {}
    }
    markStepComplete(5)
    nextStep()
  }

  return (
    <div className="space-y-6">
      <p className="text-tsushin-slate text-sm">
        Add people your agent should recognize. Contacts let you control who gets responses, assign default agents, and personalize interactions.
      </p>

      {/* Contact creation form */}
      <div className="bg-tsushin-deep/50 rounded-xl p-4 space-y-3">
        <h4 className="text-sm font-semibold text-white">Add a Contact</h4>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-tsushin-slate mb-1">Name</label>
            <input
              type="text"
              value={friendlyName}
              onChange={(e) => setFriendlyName(e.target.value)}
              placeholder="John Doe"
              className="w-full px-3 py-2 bg-tsushin-deep border border-tsushin-border rounded-lg text-white text-sm placeholder-tsushin-slate/50"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-tsushin-slate mb-1">Phone Number</label>
            <input
              type="text"
              value={phoneNumber}
              onChange={(e) => setPhoneNumber(e.target.value)}
              placeholder="+5500000000001"
              className="w-full px-3 py-2 bg-tsushin-deep border border-tsushin-border rounded-lg text-white text-sm placeholder-tsushin-slate/50"
            />
          </div>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button
              type="button"
              role="switch"
              aria-checked={isDmTrigger}
              onClick={() => setIsDmTrigger(!isDmTrigger)}
              className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${
                isDmTrigger ? 'bg-teal-500' : 'bg-tsushin-slate/40'
              }`}
            >
              <span
                className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow transition ${
                  isDmTrigger ? 'translate-x-4' : 'translate-x-0'
                }`}
              />
            </button>
            <span className="text-xs text-tsushin-slate">
              DM Trigger
              <span className="text-tsushin-slate/60 ml-1">(agent responds to their DMs)</span>
            </span>
          </div>
        </div>

        {error && (
          <p className="text-xs text-red-400">{error}</p>
        )}

        <button
          onClick={handleAdd}
          disabled={creating}
          className="w-full py-2 bg-teal-600 hover:bg-teal-700 disabled:opacity-50 text-white font-medium rounded-lg text-sm transition-colors"
        >
          {creating ? 'Adding...' : 'Add Contact'}
        </button>
      </div>

      {/* Created contacts list */}
      {state.createdContacts.length > 0 && (
        <div>
          <h4 className="text-sm font-medium text-white mb-2">
            Contacts added ({state.createdContacts.length})
          </h4>
          <div className="space-y-2">
            {state.createdContacts.map((c) => (
              <div
                key={c.id}
                className="flex items-center justify-between bg-tsushin-deep/50 border border-tsushin-border rounded-lg px-3 py-2"
              >
                <div className="flex items-center gap-2">
                  <svg className="w-4 h-4 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  <span className="text-sm text-white">{c.friendly_name}</span>
                  <span className="text-xs text-tsushin-slate">{c.phone_number}</span>
                </div>
                {c.is_dm_trigger && (
                  <span className="text-xs bg-teal-500/20 text-teal-300 px-2 py-0.5 rounded">DM Trigger</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex gap-3">
        <button
          onClick={handleContinue}
          className="flex-1 py-2 bg-teal-600 hover:bg-teal-700 text-white font-medium rounded-lg transition-colors"
        >
          {state.createdContacts.length > 0 ? 'Continue' : 'Skip — Add Contacts Later'}
        </button>
      </div>
    </div>
  )
}
