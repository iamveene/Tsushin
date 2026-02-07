'use client'

/**
 * Studio - Contacts Management Page
 * Manages contacts and agent assignments
 */

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { api, Agent, Contact, ContactAgentMapping, TeamMember } from '@/lib/client'
import Modal from '@/components/ui/Modal'
import { SmartphoneIcon, WhatsAppIcon, TelegramIcon, UserIcon, FileTextIcon, RefreshIcon } from '@/components/ui/icons'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'

interface ContactFormData {
  friendly_name: string
  whatsapp_id: string
  phone_number: string
  telegram_id: string
  telegram_username: string
  role: 'user' | 'agent'
  is_dm_trigger: boolean
  notes: string
  linked_user_id: number | null
}

export default function ContactsPage() {
  const pathname = usePathname()
  const [contacts, setContacts] = useState<Contact[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [mappings, setMappings] = useState<ContactAgentMapping[]>([])
  const [teamMembers, setTeamMembers] = useState<TeamMember[]>([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState<number | null>(null)
  const [creating, setCreating] = useState(false)
  const [formData, setFormData] = useState<ContactFormData>({
    friendly_name: '',
    whatsapp_id: '',
    phone_number: '',
    telegram_id: '',
    telegram_username: '',
    role: 'user',
    is_dm_trigger: true,
    notes: '',
    linked_user_id: null
  })
  const [resolvingWhatsApp, setResolvingWhatsApp] = useState<number | null>(null)
  const [resolvingAll, setResolvingAll] = useState(false)

  useEffect(() => {
    loadData()
  }, [])

  useEffect(() => {
    const handleRefresh = () => {
      loadData()
    }
    window.addEventListener('tsushin:refresh', handleRefresh)
    return () => window.removeEventListener('tsushin:refresh', handleRefresh)
  }, [])

  const loadData = async () => {
    try {
      const [contactsData, agentsData, mappingsData, teamData] = await Promise.all([
        api.getContacts(),
        api.getAgents(),
        api.getContactAgentMappings(),
        api.getTeamMembers({ is_active: true }).catch(() => ({ members: [] })) // Gracefully handle if user doesn't have permission
      ])
      setContacts(contactsData)
      setAgents(agentsData)
      setMappings(mappingsData)
      setTeamMembers(teamData.members || [])
    } catch (err) {
      console.error('Failed to load data:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async () => {
    try {
      await api.createContact({
        ...formData,
        whatsapp_id: formData.whatsapp_id || undefined,
        phone_number: formData.phone_number || undefined,
        telegram_id: formData.telegram_id || undefined,
        telegram_username: formData.telegram_username || undefined,
        notes: formData.notes || undefined,
        linked_user_id: formData.linked_user_id || undefined
      })

      await loadData()
      setCreating(false)
      resetForm()
    } catch (err) {
      console.error('Failed to create contact:', err)
      alert(err instanceof Error ? err.message : 'Failed to create contact')
    }
  }

  const handleUpdate = async (contactId: number) => {
    try {
      // Find the current contact to check if linked_user_id changed
      const currentContact = contacts.find(c => c.id === contactId)
      const currentLinkedUserId = currentContact?.linked_user_id || null

      // Determine what to send for linked_user_id:
      // - If user selected "None" (null) and there was a previous mapping, send -1 to unlink
      // - If user selected a user, send that user's ID
      // - If no change, don't send anything
      let linkedUserIdToSend: number | undefined = undefined
      if (formData.linked_user_id !== currentLinkedUserId) {
        if (formData.linked_user_id === null && currentLinkedUserId !== null) {
          linkedUserIdToSend = -1  // Unlink
        } else if (formData.linked_user_id !== null) {
          linkedUserIdToSend = formData.linked_user_id  // Link to new user
        }
      }

      await api.updateContact(contactId, {
        ...formData,
        whatsapp_id: formData.whatsapp_id || undefined,
        phone_number: formData.phone_number || undefined,
        telegram_id: formData.telegram_id || undefined,
        telegram_username: formData.telegram_username || undefined,
        notes: formData.notes || undefined,
        linked_user_id: linkedUserIdToSend
      })

      await loadData()
      setEditing(null)
      resetForm()
    } catch (err) {
      console.error('Failed to update contact:', err)
      alert(err instanceof Error ? err.message : 'Failed to update contact')
    }
  }

  const handleDelete = async (contactId: number) => {
    if (!confirm('Are you sure you want to delete this contact?')) return

    try {
      await api.deleteContact(contactId)
      await loadData()
    } catch (err) {
      console.error('Failed to delete contact:', err)
      alert(err instanceof Error ? err.message : 'Failed to delete contact')
    }
  }

  const handleAssignAgent = async (contactId: number, agentId: number) => {
    try {
      await api.setContactAgentMapping(contactId, agentId)
      await loadData()
    } catch (err: any) {
      alert(err.message || 'Failed to assign agent')
    }
  }

  const handleRemoveMapping = async (contactId: number) => {
    if (!confirm('Remove this agent assignment? The contact will use the default agent.')) return

    try {
      await api.deleteContactAgentMapping(contactId)
      await loadData()
    } catch (err: any) {
      alert(err.message || 'Failed to remove mapping')
    }
  }

  const startEdit = (contact: Contact) => {
    setEditing(contact.id)
    setFormData({
      friendly_name: contact.friendly_name,
      whatsapp_id: contact.whatsapp_id || '',
      phone_number: contact.phone_number || '',
      telegram_id: contact.telegram_id || '',
      telegram_username: contact.telegram_username || '',
      role: contact.role as 'user' | 'agent',
      is_dm_trigger: contact.is_dm_trigger || false,
      notes: contact.notes || '',
      linked_user_id: contact.linked_user_id || null
    })
  }

  const resetForm = () => {
    setFormData({
      friendly_name: '',
      whatsapp_id: '',
      phone_number: '',
      telegram_id: '',
      telegram_username: '',
      role: 'user',
      is_dm_trigger: true,
      notes: '',
      linked_user_id: null
    })
  }

  const handleResolveWhatsApp = async (contactId: number) => {
    setResolvingWhatsApp(contactId)
    try {
      const result = await api.resolveContactWhatsApp(contactId, true)
      if (result.success) {
        alert(result.message)
        await loadData()
      } else {
        alert(result.message)
      }
    } catch (err) {
      console.error('Failed to resolve WhatsApp ID:', err)
      alert(err instanceof Error ? err.message : 'Failed to resolve WhatsApp ID')
    } finally {
      setResolvingWhatsApp(null)
    }
  }

  const handleResolveAllWhatsApp = async () => {
    if (!confirm('Resolve WhatsApp IDs for all contacts with phone numbers? This may take a moment.')) return
    setResolvingAll(true)
    try {
      const result = await api.resolveAllContactsWhatsApp()
      alert(`Resolved: ${result.resolved}, Failed: ${result.failed}, Skipped: ${result.skipped}`)
      await loadData()
    } catch (err) {
      console.error('Failed to resolve all WhatsApp IDs:', err)
      alert(err instanceof Error ? err.message : 'Failed to resolve WhatsApp IDs')
    } finally {
      setResolvingAll(false)
    }
  }

  const cancelEdit = () => {
    setEditing(null)
    setCreating(false)
    resetForm()
  }

  const userContacts = contacts.filter(c => c.role === 'user')
  const agentContacts = contacts.filter(c => c.role === 'agent')
  const dmTriggerContacts = contacts.filter(c => c.is_dm_trigger && c.role === 'user') // Used for stats

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-lg text-gray-600 dark:text-gray-400">Loading contacts...</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      {/* Header */}
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8 flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold text-white mb-2">Agent Studio</h1>
            <p className="text-tsushin-slate">Manage contacts and agent assignments</p>
          </div>
          <div className="flex gap-3">
            <button
              onClick={handleResolveAllWhatsApp}
              disabled={resolvingAll}
              className="px-4 py-2 bg-green-600/20 text-green-400 border border-green-600/30 rounded-lg hover:bg-green-600/30 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {resolvingAll ? <><RefreshIcon size={16} className="animate-spin" /> Resolving...</> : <><RefreshIcon size={16} /> Resolve All WhatsApp</>}
            </button>
            <button
              onClick={() => setCreating(true)}
              className="px-4 py-2 bg-tsushin-indigo text-white rounded-lg hover:bg-tsushin-indigo/90 transition-colors font-medium"
            >
              + Add Contact
            </button>
          </div>
        </div>
      </div>

      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-0 space-y-6">
        {/* Sub Navigation */}
        <div className="bg-gray-900/50 border border-gray-800 rounded-lg shadow">
          <div className="border-b border-gray-800">
            <nav className="flex">
              <Link
                href="/agents"
                className={`px-6 py-3 font-medium text-sm border-b-2 transition-colors ${
                  pathname === '/agents'
                    ? 'border-tsushin-indigo text-tsushin-indigo'
                    : 'border-transparent text-tsushin-slate hover:text-white'
                }`}
              >
                Agents
              </Link>
              <Link
                href="/agents/contacts"
                className={`px-6 py-3 font-medium text-sm border-b-2 transition-colors ${
                  pathname === '/agents/contacts'
                    ? 'border-tsushin-indigo text-tsushin-indigo'
                    : 'border-transparent text-tsushin-slate hover:text-white'
                }`}
              >
                Contacts
              </Link>
              <Link
                href="/agents/personas"
                className={`px-6 py-3 font-medium text-sm border-b-2 transition-colors ${
                  pathname === '/agents/personas'
                    ? 'border-tsushin-indigo text-tsushin-indigo'
                    : 'border-transparent text-tsushin-slate hover:text-white'
                }`}
              >
                Personas
              </Link>
              <Link
                href="/agents/projects"
                className={`px-6 py-3 font-medium text-sm border-b-2 transition-colors ${
                  pathname?.startsWith('/agents/projects')
                    ? 'border-tsushin-indigo text-tsushin-indigo'
                    : 'border-transparent text-tsushin-slate hover:text-white'
                }`}
              >
                Projects
              </Link>
              <Link
                href="/agents/security"
                className={`px-6 py-3 font-medium text-sm border-b-2 transition-colors ${
                  pathname?.startsWith('/agents/security')
                    ? 'border-tsushin-indigo text-tsushin-indigo'
                    : 'border-transparent text-tsushin-slate hover:text-white'
                }`}
              >
                Security
              </Link>
              <Link
                href="/agents/builder"
                className={`px-6 py-3 font-medium text-sm border-b-2 transition-colors ${
                  pathname === '/agents/builder'
                    ? 'border-tsushin-indigo text-tsushin-indigo'
                    : 'border-transparent text-tsushin-slate hover:text-white'
                }`}
              >
                Builder
              </Link>
            </nav>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-gray-900/50 border border-gray-800 rounded-lg shadow p-5 border-l-4 border-l-tsushin-indigo">
            <p className="text-sm font-medium text-tsushin-slate">Total Contacts</p>
            <p className="text-2xl font-bold text-white mt-1">{contacts.length}</p>
          </div>
          <div className="bg-gray-900/50 border border-gray-800 rounded-lg shadow p-5 border-l-4 border-l-blue-500">
            <p className="text-sm font-medium text-tsushin-slate">Users</p>
            <p className="text-2xl font-bold text-white mt-1">{userContacts.length}</p>
          </div>
          <div className="bg-gray-900/50 border border-gray-800 rounded-lg shadow p-5 border-l-4 border-l-purple-500">
            <p className="text-sm font-medium text-tsushin-slate">Agent Contacts</p>
            <p className="text-2xl font-bold text-white mt-1">{agentContacts.length}</p>
          </div>
          <div className="bg-gray-900/50 border border-gray-800 rounded-lg shadow p-5 border-l-4 border-l-green-500">
            <p className="text-sm font-medium text-tsushin-slate">DM Triggers</p>
            <p className="text-2xl font-bold text-white mt-1">{dmTriggerContacts.length}</p>
          </div>
        </div>

        {/* Contact List */}
        <div className="bg-gray-900/50 border border-gray-800 rounded-lg shadow">
          <div className="px-6 py-4 border-b border-gray-800">
            <h2 className="text-lg font-semibold text-white">All Contacts</h2>
            <p className="text-sm text-tsushin-slate mt-1">
              Manage users and agent contacts. Contacts can be referenced in conversations.
            </p>
          </div>

          {contacts.length === 0 ? (
            <div className="px-6 py-12 text-center">
              <p className="text-tsushin-slate mb-4">No contacts found</p>
              <button
                onClick={() => setCreating(true)}
                className="px-4 py-2 bg-tsushin-indigo text-white rounded-lg hover:bg-tsushin-indigo/90"
              >
                Add Your First Contact
              </button>
            </div>
          ) : (
            <div className="divide-y divide-gray-800">
              {contacts.map((contact) => (
                <div key={contact.id} className="px-6 py-4 hover:bg-gray-800/30 transition-colors">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-3">
                        <h3 className="text-lg font-semibold text-white">
                          {contact.friendly_name}
                        </h3>
                        <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                          contact.role === 'agent'
                            ? 'bg-purple-500/10 text-purple-400 border border-purple-500/20'
                            : 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                        }`}>
                          {contact.role}
                        </span>
                        {contact.is_dm_trigger && (
                          <span className="px-2 py-1 text-xs font-medium bg-green-500/10 text-green-400 border border-green-500/20 rounded-full">
                            DM Trigger
                          </span>
                        )}
                        {!contact.is_active && (
                          <span className="px-2 py-1 text-xs font-medium bg-gray-500/10 text-gray-400 border border-gray-500/20 rounded-full">
                            Inactive
                          </span>
                        )}
                      </div>
                      <div className="mt-2 flex flex-wrap gap-4 text-sm text-tsushin-slate">
                        {contact.phone_number && <span className="inline-flex items-center gap-1"><SmartphoneIcon size={14} />{contact.phone_number}</span>}
                        {contact.whatsapp_id && <span className="inline-flex items-center gap-1 text-green-400"><WhatsAppIcon size={14} />WA: {contact.whatsapp_id}</span>}
                        {contact.telegram_id && <span className="inline-flex items-center gap-1 text-blue-400"><TelegramIcon size={14} />TG: {contact.telegram_id}</span>}
                        {contact.telegram_username && <span className="text-blue-400">@{contact.telegram_username.replace('@', '')}</span>}
                        {contact.linked_user_email && (
                          <span className="inline-flex items-center gap-1 text-purple-400">
                            <UserIcon size={14} />{contact.linked_user_name || contact.linked_user_email}
                          </span>
                        )}
                        {contact.notes && <span className="inline-flex items-center gap-1 italic"><FileTextIcon size={14} />{contact.notes}</span>}
                      </div>
                    </div>
                    <div className="flex gap-2 ml-4">
                      {contact.phone_number && !contact.whatsapp_id && (
                        <button
                          onClick={() => handleResolveWhatsApp(contact.id)}
                          disabled={resolvingWhatsApp === contact.id}
                          className="px-3 py-1.5 text-sm bg-green-600/10 text-green-400 border border-green-600/20 rounded-md hover:bg-green-600/20 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
                        >
                          {resolvingWhatsApp === contact.id ? <RefreshIcon size={14} className="animate-spin" /> : <><RefreshIcon size={14} /> Resolve WA</>}
                        </button>
                      )}
                      <button
                        onClick={() => startEdit(contact)}
                        className="px-3 py-1.5 text-sm bg-tsushin-indigo/10 text-tsushin-indigo border border-tsushin-indigo/20 rounded-md hover:bg-tsushin-indigo/20"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => handleDelete(contact.id)}
                        className="px-3 py-1.5 text-sm bg-red-500/10 text-red-400 border border-red-500/20 rounded-md hover:bg-red-500/20"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Agent Assignments */}
        <div className="bg-gray-900/50 border border-gray-800 rounded-lg shadow">
          <div className="px-6 py-4 border-b border-gray-800">
            <h2 className="text-lg font-semibold text-white">Agent Assignments</h2>
            <p className="text-sm text-tsushin-slate mt-1">
              Assign specific agents to contacts for personalized responses in DMs
            </p>
          </div>

          <div className="p-6">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b-2 border-gray-700">
                    <th className="text-left py-3 px-4 text-sm font-semibold text-gray-300">Contact</th>
                    <th className="text-left py-3 px-4 text-sm font-semibold text-gray-300">Phone</th>
                    <th className="text-left py-3 px-4 text-sm font-semibold text-gray-300">Assigned Agent</th>
                    <th className="text-right py-3 px-4 text-sm font-semibold text-gray-300">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {userContacts.map((contact) => {
                    const mapping = mappings.find(m => m.contact_id === contact.id)
                    return (
                      <tr key={contact.id} className="border-b border-gray-800 hover:bg-gray-800/30">
                        <td className="py-3 px-4">
                          <div className="font-medium text-white">{contact.friendly_name}</div>
                          {contact.is_dm_trigger && (
                            <span className="inline-block px-2 py-0.5 text-xs bg-green-500/10 text-green-400 rounded mt-1">
                              DM Trigger
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-4 text-sm text-tsushin-slate">{contact.phone_number || 'N/A'}</td>
                        <td className="py-3 px-4">
                          <select
                            value={mapping?.agent_id || ''}
                            onChange={(e) => {
                              const agentId = Number(e.target.value)
                              if (agentId) {
                                handleAssignAgent(contact.id, agentId)
                              }
                            }}
                            className="px-3 py-1.5 text-sm border border-gray-700 rounded-md bg-gray-800 text-white focus:ring-2 focus:ring-tsushin-indigo"
                          >
                            <option value="">Default Agent</option>
                            {agents.filter(a => a.is_active).map(agent => (
                              <option key={agent.id} value={agent.id}>
                                {agent.contact_name}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td className="py-3 px-4 text-right">
                          {mapping && (
                            <button
                              onClick={() => handleRemoveMapping(contact.id)}
                              className="px-3 py-1 text-xs bg-red-500/10 text-red-400 rounded-md hover:bg-red-500/20"
                            >
                              Remove
                            </button>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {userContacts.length === 0 && (
              <div className="text-center py-8">
                <p className="text-tsushin-slate">No user contacts to assign agents to</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Create/Edit Modal */}
      <Modal
        isOpen={creating || editing !== null}
        onClose={cancelEdit}
        title={creating ? 'Create New Contact' : 'Edit Contact'}
        size="lg"
        footer={
          <div className="flex justify-end gap-2">
            <button
              onClick={cancelEdit}
              className="px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600 text-sm"
            >
              Cancel
            </button>
            <button
              onClick={() => creating ? handleCreate() : handleUpdate(editing!)}
              className="px-4 py-2 bg-tsushin-indigo text-white rounded hover:bg-tsushin-indigo/90 text-sm"
            >
              {creating ? 'Create' : 'Save'}
            </button>
          </div>
        }
      >
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-2 text-gray-300">
                Friendly Name *
              </label>
              <input
                type="text"
                value={formData.friendly_name}
                onChange={(e) => setFormData({ ...formData, friendly_name: e.target.value })}
                placeholder="e.g., Alice, Agent1"
                className="w-full px-3 py-2 border border-gray-700 rounded-md bg-gray-800 text-white focus:ring-2 focus:ring-tsushin-indigo"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-2 text-gray-300">
                Role *
              </label>
              <select
                value={formData.role}
                onChange={(e) => setFormData({ ...formData, role: e.target.value as 'user' | 'agent' })}
                className="w-full px-3 py-2 border border-gray-700 rounded-md bg-gray-800 text-white focus:ring-2 focus:ring-tsushin-indigo"
              >
                <option value="user">User</option>
                <option value="agent">Agent</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2 text-gray-300">
                WhatsApp ID
              </label>
              <input
                type="text"
                value={formData.whatsapp_id}
                onChange={(e) => setFormData({ ...formData, whatsapp_id: e.target.value })}
                placeholder="e.g., 140127703679231"
                className="w-full px-3 py-2 border border-gray-700 rounded-md bg-gray-800 text-white focus:ring-2 focus:ring-tsushin-indigo"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-2 text-gray-300">
                Phone Number
              </label>
              <input
                type="text"
                value={formData.phone_number}
                onChange={(e) => setFormData({ ...formData, phone_number: e.target.value })}
                placeholder="e.g., 5500000000001"
                className="w-full px-3 py-2 border border-gray-700 rounded-md bg-gray-800 text-white focus:ring-2 focus:ring-tsushin-indigo"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-2 text-gray-300">
                Telegram ID
              </label>
              <input
                type="text"
                value={formData.telegram_id}
                onChange={(e) => setFormData({ ...formData, telegram_id: e.target.value })}
                placeholder="e.g., 123456789"
                className="w-full px-3 py-2 border border-gray-700 rounded-md bg-gray-800 text-white focus:ring-2 focus:ring-tsushin-indigo"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-2 text-gray-300">
                Telegram Username
              </label>
              <input
                type="text"
                value={formData.telegram_username}
                onChange={(e) => setFormData({ ...formData, telegram_username: e.target.value })}
                placeholder="e.g., @johndoe"
                className="w-full px-3 py-2 border border-gray-700 rounded-md bg-gray-800 text-white focus:ring-2 focus:ring-tsushin-indigo"
              />
            </div>
          </div>

          {formData.role === 'user' && (
            <div className="p-3 bg-green-900/20 border border-green-700/50 rounded-md">
              <label className="flex items-start gap-3">
                <input
                  type="checkbox"
                  checked={formData.is_dm_trigger}
                  onChange={(e) => setFormData({ ...formData, is_dm_trigger: e.target.checked })}
                  className="mt-1 w-4 h-4 text-tsushin-indigo border-gray-600 rounded"
                />
                <div>
                  <span className="font-medium text-sm text-white">Enable DM Trigger</span>
                  <p className="text-xs text-gray-400 mt-1">
                    Agent will automatically respond to direct messages from this contact
                  </p>
                </div>
              </label>
            </div>
          )}

          <div>
            <label className="block text-sm font-medium mb-2 text-gray-300">
              Notes
            </label>
            <textarea
              value={formData.notes}
              onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
              placeholder="Optional notes about this contact"
              rows={3}
              className="w-full px-3 py-2 border border-gray-700 rounded-md bg-gray-800 text-white focus:ring-2 focus:ring-tsushin-indigo"
            />
          </div>

          {/* Linked System User */}
          {teamMembers.length > 0 && (
            <div className="p-3 bg-blue-900/20 border border-blue-700/50 rounded-md">
              <label className="block text-sm font-medium mb-2 text-gray-300">
                Linked System User
              </label>
              <select
                value={formData.linked_user_id || ''}
                onChange={(e) => setFormData({
                  ...formData,
                  linked_user_id: e.target.value ? Number(e.target.value) : null
                })}
                className="w-full px-3 py-2 border border-gray-700 rounded-md bg-gray-800 text-white focus:ring-2 focus:ring-tsushin-indigo"
              >
                <option value="">-- None --</option>
                {teamMembers.map(user => (
                  <option key={user.id} value={user.id}>
                    {user.full_name || user.email}
                  </option>
                ))}
              </select>
              <p className="text-xs text-gray-400 mt-2">
                Link this contact to a system user for unified identity across WhatsApp and the Playground.
              </p>
            </div>
          )}
        </div>
      </Modal>
    </div>
  )
}
