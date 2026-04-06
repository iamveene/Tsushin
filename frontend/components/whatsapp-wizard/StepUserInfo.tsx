'use client'

import { useState } from 'react'
import { api } from '@/lib/client'
import { useWhatsAppWizard } from '@/contexts/WhatsAppWizardContext'
import { useAuth } from '@/contexts/AuthContext'
import InfoTooltip from '@/components/ui/InfoTooltip'
import ToggleSwitch from '@/components/ui/ToggleSwitch'

export default function StepUserInfo() {
  const { state, setUserContact, addContact, markStepComplete, nextStep } = useWhatsAppWizard()
  const { user } = useAuth()

  const [userName, setUserName] = useState(user?.full_name || '')
  const [userPhone, setUserPhone] = useState('')
  const [isDmTrigger, setIsDmTrigger] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSave = async () => {
    if (!userName.trim()) {
      setError('Please enter your name')
      return
    }
    if (!userPhone.trim()) {
      setError('Please enter your phone number')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const contact = await api.createContact({
        friendly_name: userName.trim(),
        phone_number: userPhone.trim(),
        role: 'user',
        is_dm_trigger: isDmTrigger,
        is_active: true,
      })
      setUserContact(contact)
      addContact(contact)
      markStepComplete(3)
      nextStep()
    } catch (e: any) {
      const msg = e.message || 'Failed to create contact'
      if (msg.includes('409') || msg.toLowerCase().includes('already exists') || msg.toLowerCase().includes('conflict')) {
        setError('A contact with this name or number already exists. You can skip this step and manage contacts later.')
      } else {
        setError(msg)
      }
    } finally {
      setSaving(false)
    }
  }

  const handleSkip = () => {
    markStepComplete(3)
    nextStep()
  }

  // Already completed
  if (state.userContact) {
    return (
      <div className="text-center py-8">
        <div className="w-16 h-16 bg-green-500 rounded-full flex items-center justify-center mx-auto mb-4">
          <svg className="w-10 h-10 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <p className="text-green-400 font-medium text-lg">Your contact is registered!</p>
        <p className="text-white text-sm mt-2 font-medium">{state.userContact.friendly_name}</p>
        <p className="text-tsushin-slate text-xs mt-1">{state.userContact.phone_number}</p>
        <button
          onClick={nextStep}
          className="mt-6 px-6 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg transition-colors"
        >
          Continue to DM Settings
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <p className="text-tsushin-slate text-sm">
        Register yourself as a contact so the agent knows who you are when you message it on WhatsApp.
      </p>

      <div className="bg-tsushin-deep/50 rounded-xl p-4 space-y-4">
        <div>
          <label className="block text-sm font-medium text-white mb-2">Your Name</label>
          <input
            type="text"
            value={userName}
            onChange={(e) => setUserName(e.target.value)}
            placeholder="Your full name"
            className="w-full px-3 py-2 bg-tsushin-deep border border-tsushin-border rounded-lg text-white placeholder-tsushin-slate/50"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-white mb-2">Your Phone Number</label>
          <input
            type="text"
            value={userPhone}
            onChange={(e) => setUserPhone(e.target.value)}
            placeholder="+5500000000001"
            className="w-full px-3 py-2 bg-tsushin-deep border border-tsushin-border rounded-lg text-white placeholder-tsushin-slate/50"
          />
          <p className="mt-1 text-xs text-tsushin-slate">
            Include the country code (e.g., +55 for Brazil, +1 for US). This should be your personal WhatsApp number.
          </p>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ToggleSwitch checked={isDmTrigger} onChange={setIsDmTrigger} size="sm" />
            <span className="text-sm text-white">DM Trigger</span>
            <InfoTooltip
              text="When enabled, your AI agent will automatically respond when you send it a direct message on WhatsApp."
              position="right"
            />
          </div>
          <span className="text-xs text-tsushin-slate">
            {isDmTrigger ? 'Agent responds to your DMs' : 'Agent ignores your DMs'}
          </span>
        </div>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3">
          <p className="text-sm text-red-400">{error}</p>
        </div>
      )}

      <button
        onClick={handleSave}
        disabled={saving}
        className="w-full py-2 bg-teal-600 hover:bg-teal-700 disabled:opacity-50 text-white font-medium rounded-lg transition-colors"
      >
        {saving ? 'Saving...' : 'Save & Continue'}
      </button>

      <button
        onClick={handleSkip}
        className="w-full py-2 text-tsushin-slate hover:text-white text-sm transition-colors"
      >
        Skip — Add Later
      </button>
    </div>
  )
}
