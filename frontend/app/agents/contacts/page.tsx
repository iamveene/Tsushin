'use client'

/**
 * Studio - Contacts Management Page
 * Manages contacts and agent assignments
 */

import { useState, useEffect, useRef } from 'react'
import { useGlobalRefresh } from '@/hooks/useGlobalRefresh'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import StudioTabs from '@/components/studio/StudioTabs'
import { api, Agent, Contact, ContactAgentMapping, TeamMember, ChannelMapping } from '@/lib/client'
import Modal from '@/components/ui/Modal'
import InfoTooltip from '@/components/ui/InfoTooltip'
import { useToast } from '@/contexts/ToastContext'
import { SmartphoneIcon, WhatsAppIcon, TelegramIcon, UserIcon, FileTextIcon, SlackIcon, DiscordIcon } from '@/components/ui/icons'

interface ContactFormData {
  friendly_name: string
  phone_number: string
  telegram_id: string
  telegram_username: string
  role: 'user' | 'agent' | 'external'
  is_dm_trigger: boolean
  slash_commands_enabled: boolean | null
  notes: string
  linked_user_id: number | null
  // Default agent assignment (persists as a ContactAgentMapping on save)
  default_agent_id: number | null
}

export default function ContactsPage() {
  const toast = useToast()
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
    phone_number: '',
    telegram_id: '',
    telegram_username: '',
    role: 'user',
    is_dm_trigger: true,
    slash_commands_enabled: null,
    notes: '',
    linked_user_id: null,
    default_agent_id: null
  })

  // Channel mapping management
  const [showAddMappingForm, setShowAddMappingForm] = useState(false)
  const [addMappingType, setAddMappingType] = useState('slack')
  const [addMappingIdentifier, setAddMappingIdentifier] = useState('')
  const [addMappingLoading, setAddMappingLoading] = useState(false)

  // Tracks deferred loadData() timers so they can be cancelled on unmount.
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    loadData()
    return () => {
      if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current)
    }
  }, [])

  useGlobalRefresh(() => loadData())

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
      const created = await api.createContact({
        friendly_name: formData.friendly_name,
        role: formData.role,
        is_dm_trigger: formData.is_dm_trigger,
        phone_number: formData.phone_number || undefined,
        telegram_id: formData.telegram_id || undefined,
        telegram_username: formData.telegram_username || undefined,
        slash_commands_enabled: formData.slash_commands_enabled,
        notes: formData.notes || undefined,
        linked_user_id: formData.linked_user_id || undefined
      })

      // Persist default agent mapping if selected
      if (formData.default_agent_id && formData.role === 'user') {
        try {
          await api.setContactAgentMapping(created.id, formData.default_agent_id)
        } catch (err) {
          console.error('Failed to set default agent mapping:', err)
        }
      }

      await loadData()
      setCreating(false)
      resetForm()
      // Background WhatsApp ID resolution runs server-side after create;
      // refresh again shortly to surface the auto-resolved WA ID without user action.
      if (created.phone_number) {
        if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current)
        refreshTimerRef.current = setTimeout(() => { loadData() }, 2500)
      }
    } catch (err) {
      console.error('Failed to create contact:', err)
      toast.error('Creation Failed', err instanceof Error ? err.message : 'Failed to create contact')
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
        friendly_name: formData.friendly_name,
        role: formData.role,
        is_dm_trigger: formData.is_dm_trigger,
        phone_number: formData.phone_number || undefined,
        telegram_id: formData.telegram_id || undefined,
        telegram_username: formData.telegram_username || undefined,
        slash_commands_enabled: formData.slash_commands_enabled,
        notes: formData.notes || undefined,
        linked_user_id: linkedUserIdToSend
      })

      // Sync default agent mapping: create/update or delete based on form state
      const existingMapping = mappings.find(m => m.contact_id === contactId)
      const targetAgentId = formData.role === 'user' ? formData.default_agent_id : null
      if (targetAgentId && targetAgentId !== existingMapping?.agent_id) {
        try {
          await api.setContactAgentMapping(contactId, targetAgentId)
        } catch (err) {
          console.error('Failed to update default agent mapping:', err)
        }
      } else if (!targetAgentId && existingMapping) {
        try {
          await api.deleteContactAgentMapping(contactId)
        } catch (err) {
          console.error('Failed to remove default agent mapping:', err)
        }
      }

      await loadData()
      setEditing(null)
      resetForm()
      // Refresh after background WhatsApp resolution finishes
      if (formData.phone_number) {
        if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current)
        refreshTimerRef.current = setTimeout(() => { loadData() }, 2500)
      }
    } catch (err) {
      console.error('Failed to update contact:', err)
      toast.error('Update Failed', err instanceof Error ? err.message : 'Failed to update contact')
    }
  }

  const handleDelete = async (contactId: number) => {
    if (!confirm('Are you sure you want to delete this contact?')) return

    try {
      await api.deleteContact(contactId)
      await loadData()
    } catch (err) {
      console.error('Failed to delete contact:', err)
      toast.error('Delete Failed', err instanceof Error ? err.message : 'Failed to delete contact')
    }
  }

  const handleAssignAgent = async (contactId: number, agentId: number) => {
    try {
      await api.setContactAgentMapping(contactId, agentId)
      await loadData()
    } catch (err: any) {
      toast.error('Assignment Failed', err.message || 'Failed to assign agent')
    }
  }

  const handleRemoveMapping = async (contactId: number) => {
    if (!confirm('Remove this agent assignment? The contact will use the default agent.')) return

    try {
      await api.deleteContactAgentMapping(contactId)
      await loadData()
    } catch (err: any) {
      toast.error('Removal Failed', err.message || 'Failed to remove mapping')
    }
  }

  const startEdit = (contact: Contact) => {
    setEditing(contact.id)
    const mapping = mappings.find(m => m.contact_id === contact.id)
    setFormData({
      friendly_name: contact.friendly_name,
      phone_number: contact.phone_number || '',
      telegram_id: contact.telegram_id || '',
      telegram_username: contact.telegram_username || '',
      role: contact.role as 'user' | 'agent' | 'external',
      is_dm_trigger: contact.is_dm_trigger || false,
      slash_commands_enabled: contact.slash_commands_enabled ?? null,
      notes: contact.notes || '',
      linked_user_id: contact.linked_user_id || null,
      default_agent_id: mapping?.agent_id ?? null
    })
  }

  const resetForm = () => {
    setFormData({
      friendly_name: '',
      phone_number: '',
      telegram_id: '',
      telegram_username: '',
      role: 'user',
      is_dm_trigger: true,
      slash_commands_enabled: null,
      notes: '',
      linked_user_id: null,
      default_agent_id: null
    })
  }

  const cancelEdit = () => {
    setEditing(null)
    setCreating(false)
    resetForm()
    setShowAddMappingForm(false)
    setAddMappingIdentifier('')
    setAddMappingType('slack')
  }

  const handleAddChannelMapping = async (contactId: number) => {
    if (!addMappingIdentifier.trim()) return
    setAddMappingLoading(true)
    try {
      await api.addChannelMapping(contactId, {
        channel_type: addMappingType,
        channel_identifier: addMappingIdentifier.trim(),
      })
      toast.success('Channel Added', `${addMappingType} channel link added`)
      setAddMappingIdentifier('')
      setShowAddMappingForm(false)
      await loadData()
    } catch (err) {
      toast.error('Add Failed', err instanceof Error ? err.message : 'Failed to add channel mapping')
    } finally {
      setAddMappingLoading(false)
    }
  }

  const handleRemoveChannelMapping = async (contactId: number, mappingId: number) => {
    try {
      await api.removeChannelMapping(contactId, mappingId)
      toast.success('Channel Removed', 'Channel link removed')
      await loadData()
    } catch (err) {
      toast.error('Remove Failed', err instanceof Error ? err.message : 'Failed to remove channel mapping')
    }
  }

  const renderChannelBadge = (mapping: ChannelMapping) => {
    const meta = mapping.channel_metadata || {}
    switch (mapping.channel_type) {
      case 'slack':
        return (
          <span key={mapping.id} className="inline-flex items-center gap-1 text-purple-400">
            <SlackIcon size={14} />{meta.display_name || meta.username || mapping.channel_identifier}
          </span>
        )
      case 'discord':
        return (
          <span key={mapping.id} className="inline-flex items-center gap-1 text-indigo-400">
            <DiscordIcon size={14} />{meta.display_name || (meta.username ? `@${meta.username}` : mapping.channel_identifier)}
          </span>
        )
      case 'email':
        return (
          <span key={mapping.id} className="inline-flex items-center gap-1 text-yellow-400">
            {mapping.channel_identifier}
          </span>
        )
      default:
        return (
          <span key={mapping.id} className="inline-flex items-center gap-1 text-tsushin-slate">
            <SmartphoneIcon size={14} />{mapping.channel_type}: {mapping.channel_identifier}
          </span>
        )
    }
  }

  const userContacts = contacts.filter(c => c.role === 'user')
  const agentContacts = contacts.filter(c => c.role === 'agent')
  const dmTriggerContacts = contacts.filter(c => c.is_dm_trigger && c.role === 'user') // Used for stats

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-lg text-tsushin-slate">Loading contacts...</div>
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
        <StudioTabs />

        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-tsushin-surface border border-tsushin-border rounded-lg shadow p-5 border-l-4 border-l-tsushin-indigo">
            <p className="text-sm font-medium text-tsushin-slate">Total Contacts</p>
            <p className="text-2xl font-bold text-white mt-1">{contacts.length}</p>
          </div>
          <div className="bg-tsushin-surface border border-tsushin-border rounded-lg shadow p-5 border-l-4 border-l-blue-500">
            <p className="text-sm font-medium text-tsushin-slate">Users</p>
            <p className="text-2xl font-bold text-white mt-1">{userContacts.length}</p>
          </div>
          <div className="bg-tsushin-surface border border-tsushin-border rounded-lg shadow p-5 border-l-4 border-l-purple-500">
            <p className="text-sm font-medium text-tsushin-slate">Agent Contacts</p>
            <p className="text-2xl font-bold text-white mt-1">{agentContacts.length}</p>
          </div>
          <div className="bg-tsushin-surface border border-tsushin-border rounded-lg shadow p-5 border-l-4 border-l-green-500">
            <p className="text-sm font-medium text-tsushin-slate">DM Triggers</p>
            <p className="text-2xl font-bold text-white mt-1">{dmTriggerContacts.length}</p>
          </div>
        </div>

        {/* Contact List */}
        <div className="bg-tsushin-surface border border-tsushin-border rounded-lg shadow">
          <div className="px-6 py-4 border-b border-tsushin-border">
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
            <div className="divide-y divide-tsushin-border">
              {contacts.map((contact) => (
                <div key={contact.id} className="px-6 py-4 hover:bg-white/5 transition-colors">
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
                          <span className="px-2 py-1 text-xs font-medium bg-gray-500/10 text-tsushin-slate border border-gray-500/20 rounded-full">
                            Inactive
                          </span>
                        )}
                        {contact.slash_commands_enabled === true && (
                          <span className="px-2 py-1 text-xs font-medium bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 rounded-full">
                            Slash Cmds
                          </span>
                        )}
                        {contact.slash_commands_enabled === false && (
                          <span className="px-2 py-1 text-xs font-medium bg-orange-500/10 text-orange-400 border border-orange-500/20 rounded-full">
                            No Slash Cmds
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
                        {/* Channel mappings (Slack, Discord, etc. — skip legacy types already shown above) */}
                        {contact.channel_mappings?.filter(m => !['whatsapp', 'telegram', 'phone'].includes(m.channel_type)).map(m => renderChannelBadge(m))}
                        {contact.notes && <span className="inline-flex items-center gap-1 italic"><FileTextIcon size={14} />{contact.notes}</span>}
                      </div>
                    </div>
                    <div className="flex gap-2 ml-4">
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
        <div className="bg-tsushin-surface border border-tsushin-border rounded-lg shadow">
          <div className="px-6 py-4 border-b border-tsushin-border">
            <h2 className="text-lg font-semibold text-white">Agent Assignments</h2>
            <p className="text-sm text-tsushin-slate mt-1">
              Assign specific agents to contacts for personalized responses in DMs
            </p>
          </div>

          <div className="p-6">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b-2 border-tsushin-border">
                    <th className="text-left py-3 px-4 text-sm font-semibold text-tsushin-slate">Contact</th>
                    <th className="text-left py-3 px-4 text-sm font-semibold text-tsushin-slate">Phone</th>
                    <th className="text-left py-3 px-4 text-sm font-semibold text-tsushin-slate">Assigned Agent</th>
                    <th className="text-right py-3 px-4 text-sm font-semibold text-tsushin-slate">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {userContacts.map((contact) => {
                    const mapping = mappings.find(m => m.contact_id === contact.id)
                    return (
                      <tr key={contact.id} className="border-b border-tsushin-border hover:bg-white/5">
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
                            className="px-3 py-1.5 text-sm border border-tsushin-border rounded-md bg-tsushin-elevated text-white focus:ring-2 focus:ring-tsushin-indigo"
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
              className="px-4 py-2 bg-tsushin-muted text-white rounded hover:bg-tsushin-muted/80 text-sm"
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
              <label className="block text-sm font-medium mb-2 text-tsushin-slate">
                Friendly Name *
              </label>
              <input
                type="text"
                value={formData.friendly_name}
                onChange={(e) => setFormData({ ...formData, friendly_name: e.target.value })}
                placeholder="e.g., Alice, Agent1"
                className="w-full px-3 py-2 border border-tsushin-border rounded-md bg-tsushin-elevated text-white focus:ring-2 focus:ring-tsushin-indigo"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-2 text-tsushin-slate">
                Role *
              </label>
              <select
                value={formData.role}
                onChange={(e) => setFormData({ ...formData, role: e.target.value as 'user' | 'agent' | 'external' })}
                className="w-full px-3 py-2 border border-tsushin-border rounded-md bg-tsushin-elevated text-white focus:ring-2 focus:ring-tsushin-indigo"
              >
                <option value="user">User</option>
                <option value="agent">Agent</option>
                <option value="external">External</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2 text-tsushin-slate">
                Phone Number
              </label>
              <input
                type="text"
                value={formData.phone_number}
                onChange={(e) => setFormData({ ...formData, phone_number: e.target.value })}
                placeholder="+5500000000001"
                className="w-full px-3 py-2 border border-tsushin-border rounded-md bg-tsushin-elevated text-white focus:ring-2 focus:ring-tsushin-indigo"
              />
              <p className="text-xs text-tsushin-slate mt-1">
                WhatsApp ID will be auto-detected from the phone number after saving.
              </p>
            </div>

            {formData.role === 'user' && (
              <div>
                <label className="block text-sm font-medium mb-2 text-tsushin-slate">
                  Default Agent
                </label>
                <select
                  value={formData.default_agent_id ?? ''}
                  onChange={(e) => setFormData({
                    ...formData,
                    default_agent_id: e.target.value ? Number(e.target.value) : null
                  })}
                  className="w-full px-3 py-2 border border-tsushin-border rounded-md bg-tsushin-elevated text-white focus:ring-2 focus:ring-tsushin-indigo"
                >
                  <option value="">— Use system default —</option>
                  {agents.filter(a => a.is_active).map(agent => (
                    <option key={agent.id} value={agent.id}>
                      {agent.contact_name}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-tsushin-slate mt-1">
                  Agent that responds to this contact&apos;s DMs. Also editable in the Agent Assignments table below.
                </p>
              </div>
            )}

            <div>
              <label className="block text-sm font-medium mb-2 text-tsushin-slate">
                Telegram ID
              </label>
              <input
                type="text"
                value={formData.telegram_id}
                onChange={(e) => setFormData({ ...formData, telegram_id: e.target.value })}
                placeholder="e.g., 123456789"
                className="w-full px-3 py-2 border border-tsushin-border rounded-md bg-tsushin-elevated text-white focus:ring-2 focus:ring-tsushin-indigo"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-2 text-tsushin-slate">
                Telegram Username
              </label>
              <input
                type="text"
                value={formData.telegram_username}
                onChange={(e) => setFormData({ ...formData, telegram_username: e.target.value })}
                placeholder="e.g., @johndoe"
                className="w-full px-3 py-2 border border-tsushin-border rounded-md bg-tsushin-elevated text-white focus:ring-2 focus:ring-tsushin-indigo"
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
                  className="mt-1 w-4 h-4 text-tsushin-indigo border-tsushin-border rounded"
                />
                <div>
                  <span className="font-medium text-sm text-white flex items-center gap-2">
                    Enable DM Trigger
                    <InfoTooltip text="When enabled, direct messages from this contact will trigger an AI agent response, even when DM Auto Mode is off on the WhatsApp instance." position="right" />
                  </span>
                  <p className="text-xs text-tsushin-slate mt-1">
                    Agent will automatically respond to direct messages from this contact
                  </p>
                </div>
              </label>
            </div>
          )}

          {formData.role === 'user' && (
            <div className="p-3 bg-indigo-900/20 border border-indigo-700/50 rounded-md">
              <label className="block text-sm font-medium mb-2 text-tsushin-slate">
                Slash Commands
              </label>
              <select
                value={formData.slash_commands_enabled === null ? 'default' : formData.slash_commands_enabled ? 'enabled' : 'disabled'}
                onChange={(e) => {
                  const val = e.target.value
                  setFormData({
                    ...formData,
                    slash_commands_enabled: val === 'default' ? null : val === 'enabled'
                  })
                }}
                className="w-full px-3 py-2 border border-tsushin-border rounded-md bg-tsushin-elevated text-white focus:ring-2 focus:ring-tsushin-indigo"
              >
                <option value="default">Use tenant default</option>
                <option value="enabled">Enabled</option>
                <option value="disabled">Disabled</option>
              </select>
              <p className="text-xs text-tsushin-slate mt-2">
                Control whether this contact can use slash commands (e.g., /help, /tool). Tenant default applies when set to &quot;Use tenant default&quot;.
              </p>
            </div>
          )}

          <div>
            <label className="block text-sm font-medium mb-2 text-tsushin-slate">
              Notes
            </label>
            <textarea
              value={formData.notes}
              onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
              placeholder="Optional notes about this contact"
              rows={3}
              className="w-full px-3 py-2 border border-tsushin-border rounded-md bg-tsushin-elevated text-white focus:ring-2 focus:ring-tsushin-indigo"
            />
          </div>

          {/* Linked System User */}
          {teamMembers.length > 0 && (
            <div className="p-3 bg-blue-900/20 border border-blue-700/50 rounded-md">
              <label className="block text-sm font-medium mb-2 text-tsushin-slate">
                Linked System User
              </label>
              <select
                value={formData.linked_user_id || ''}
                onChange={(e) => setFormData({
                  ...formData,
                  linked_user_id: e.target.value ? Number(e.target.value) : null
                })}
                className="w-full px-3 py-2 border border-tsushin-border rounded-md bg-tsushin-elevated text-white focus:ring-2 focus:ring-tsushin-indigo"
              >
                <option value="">-- None --</option>
                {teamMembers.map(user => (
                  <option key={user.id} value={user.id}>
                    {user.full_name || user.email}
                  </option>
                ))}
              </select>
              <p className="text-xs text-tsushin-slate mt-2">
                Link this contact to a system user for unified identity across WhatsApp and the Playground.
              </p>
            </div>
          )}

          {/* Channel Identities (edit mode only) */}
          {editing !== null && (() => {
            const contact = contacts.find(c => c.id === editing)
            const channelMappings = contact?.channel_mappings || []
            return (
              <div className="p-3 bg-tsushin-elevated/50 border border-tsushin-border rounded-md">
                <label className="block text-sm font-medium mb-2 text-tsushin-slate">
                  Channel Identities
                </label>

                {channelMappings.length > 0 ? (
                  <div className="space-y-2 mb-3">
                    {channelMappings.map(m => (
                      <div key={m.id} className="flex items-center justify-between px-3 py-2 bg-tsushin-surface rounded border border-tsushin-border">
                        <div className="flex items-center gap-2 text-sm">
                          {m.channel_type === 'slack' && <SlackIcon size={14} className="text-purple-400" />}
                          {m.channel_type === 'discord' && <DiscordIcon size={14} className="text-indigo-400" />}
                          {m.channel_type === 'whatsapp' && <WhatsAppIcon size={14} className="text-green-400" />}
                          {m.channel_type === 'telegram' && <TelegramIcon size={14} className="text-blue-400" />}
                          {!['slack', 'discord', 'whatsapp', 'telegram'].includes(m.channel_type) && <SmartphoneIcon size={14} className="text-tsushin-slate" />}
                          <span className="text-white font-medium">{m.channel_type}</span>
                          <span className="text-tsushin-slate">{m.channel_identifier}</span>
                          {m.channel_metadata?.display_name && (
                            <span className="text-tsushin-slate italic">({m.channel_metadata.display_name})</span>
                          )}
                        </div>
                        <button
                          onClick={() => handleRemoveChannelMapping(editing, m.id)}
                          className="text-red-400 hover:text-red-300 text-xs px-2 py-1"
                        >
                          Remove
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-tsushin-slate mb-3">No channel identities linked.</p>
                )}

                {!showAddMappingForm ? (
                  <button
                    onClick={() => setShowAddMappingForm(true)}
                    className="text-sm text-tsushin-indigo hover:text-tsushin-indigo/80"
                  >
                    + Add Channel Link
                  </button>
                ) : (
                  <div className="space-y-2 p-3 bg-tsushin-surface rounded border border-tsushin-border">
                    <div className="grid grid-cols-2 gap-2">
                      <select
                        value={addMappingType}
                        onChange={(e) => setAddMappingType(e.target.value)}
                        className="px-3 py-2 text-sm border border-tsushin-border rounded-md bg-tsushin-elevated text-white"
                      >
                        <option value="slack">Slack</option>
                        <option value="discord">Discord</option>
                        <option value="telegram">Telegram</option>
                        <option value="whatsapp">WhatsApp</option>
                        <option value="email">Email</option>
                        <option value="phone">Phone</option>
                      </select>
                      <input
                        type="text"
                        value={addMappingIdentifier}
                        onChange={(e) => setAddMappingIdentifier(e.target.value)}
                        placeholder={addMappingType === 'slack' ? 'T123ABC:U456DEF' : addMappingType === 'discord' ? 'Discord user ID' : 'Identifier'}
                        className="px-3 py-2 text-sm border border-tsushin-border rounded-md bg-tsushin-elevated text-white"
                      />
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleAddChannelMapping(editing)}
                        disabled={addMappingLoading || !addMappingIdentifier.trim()}
                        className="px-3 py-1.5 text-sm bg-tsushin-indigo text-white rounded hover:bg-tsushin-indigo/90 disabled:opacity-50"
                      >
                        {addMappingLoading ? 'Adding...' : 'Add'}
                      </button>
                      <button
                        onClick={() => { setShowAddMappingForm(false); setAddMappingIdentifier('') }}
                        className="px-3 py-1.5 text-sm text-tsushin-slate hover:text-white"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )
          })()}
        </div>
      </Modal>
    </div>
  )
}
