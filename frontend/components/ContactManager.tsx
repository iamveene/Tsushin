'use client'

import { useState, useEffect } from 'react'
import Modal from './ui/Modal'
import { api } from '@/lib/client'
import { UsersIcon, SmartphoneIcon, LightbulbIcon } from '@/components/ui/icons'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'

// Phase 10.2: Channel Mapping
interface ChannelMapping {
  id: number
  channel_type: string
  channel_identifier: string
  channel_metadata?: { username?: string; [key: string]: any } | null
  created_at: string
  updated_at: string
}

export interface Contact {
  id: number
  friendly_name: string
  whatsapp_id: string | null
  phone_number: string | null
  telegram_id: string | null  // Phase 10.1.1: Telegram user ID
  telegram_username: string | null  // Phase 10.1.1: Telegram @username
  role: 'user' | 'agent'
  is_active: boolean
  is_dm_trigger: boolean  // Phase 4.3
  notes: string | null
  created_at: string
  updated_at: string
  channel_mappings?: ChannelMapping[]  // Phase 10.2
}

interface ContactFormData {
  friendly_name: string
  whatsapp_id: string
  phone_number: string
  telegram_id: string  // Phase 10.1.1
  telegram_username: string  // Phase 10.1.1
  role: 'user' | 'agent'
  is_dm_trigger: boolean  // Phase 4.3
  notes: string
}

export default function ContactManager() {
  const [contacts, setContacts] = useState<Contact[]>([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState<number | null>(null)
  const [creating, setCreating] = useState(false)
  const [formData, setFormData] = useState<ContactFormData>({
    friendly_name: '',
    whatsapp_id: '',
    phone_number: '',
    telegram_id: '',  // Phase 10.1.1
    telegram_username: '',  // Phase 10.1.1
    role: 'user',
    is_dm_trigger: true,  // Phase 4.3
    notes: ''
  })

  // Phase 10.2: Channel mapping state
  const [newChannelType, setNewChannelType] = useState('')
  const [newChannelIdentifier, setNewChannelIdentifier] = useState('')
  const [newChannelMetadata, setNewChannelMetadata] = useState('')

  useEffect(() => {
    loadContacts()
  }, [])

  const loadContacts = async () => {
    try {
      const data = await api.getContacts()
      setContacts(data)
    } catch (err) {
      console.error('Failed to load contacts:', err)
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
        notes: formData.notes || undefined
      })

      await loadContacts()
      setCreating(false)
      setFormData({ friendly_name: '', whatsapp_id: '', phone_number: '', telegram_id: '', telegram_username: '', role: 'user', is_dm_trigger: true, notes: '' })
      alert('Contact created successfully!')
    } catch (err) {
      console.error('Failed to create contact:', err)
      alert(err instanceof Error ? err.message : 'Failed to create contact')
    }
  }

  const handleUpdate = async (contactId: number) => {
    try {
      await api.updateContact(contactId, {
        ...formData,
        whatsapp_id: formData.whatsapp_id || undefined,
        phone_number: formData.phone_number || undefined,
        notes: formData.notes || undefined
      })

      await loadContacts()
      setEditing(null)
      setFormData({ friendly_name: '', whatsapp_id: '', phone_number: '', telegram_id: '', telegram_username: '', role: 'user', is_dm_trigger: true, notes: '' })
      alert('Contact updated successfully!')
    } catch (err) {
      console.error('Failed to update contact:', err)
      alert(err instanceof Error ? err.message : 'Failed to update contact')
    }
  }

  const handleDelete = async (contactId: number) => {
    if (!confirm('Are you sure you want to delete this contact?')) return

    try {
      await api.deleteContact(contactId)
      await loadContacts()
      alert('Contact deleted successfully!')
    } catch (err) {
      console.error('Failed to delete contact:', err)
      alert(err instanceof Error ? err.message : 'Failed to delete contact')
    }
  }

  // Phase 10.2: Channel mapping handlers
  const handleAddChannelMapping = async (contactId: number) => {
    if (!newChannelType || !newChannelIdentifier) {
      alert('Please provide channel type and identifier')
      return
    }

    try {
      const metadata = newChannelMetadata ? JSON.parse(newChannelMetadata) : undefined
      await api.addChannelMapping(contactId, {
        channel_type: newChannelType,
        channel_identifier: newChannelIdentifier,
        channel_metadata: metadata
      })
      await loadContacts()
      setNewChannelType('')
      setNewChannelIdentifier('')
      setNewChannelMetadata('')
      alert('Channel mapping added successfully!')
    } catch (err) {
      console.error('Failed to add channel mapping:', err)
      alert(err instanceof Error ? err.message : 'Failed to add channel mapping')
    }
  }

  const handleRemoveChannelMapping = async (contactId: number, mappingId: number) => {
    if (!confirm('Are you sure you want to remove this channel mapping?')) return

    try {
      await api.removeChannelMapping(contactId, mappingId)
      await loadContacts()
      alert('Channel mapping removed successfully!')
    } catch (err) {
      console.error('Failed to remove channel mapping:', err)
      alert(err instanceof Error ? err.message : 'Failed to remove channel mapping')
    }
  }

  const startEdit = (contact: Contact) => {
    setEditing(contact.id)
    setFormData({
      friendly_name: contact.friendly_name,
      whatsapp_id: contact.whatsapp_id || '',
      phone_number: contact.phone_number || '',
      telegram_id: contact.telegram_id || '',  // Phase 10.1.1
      telegram_username: contact.telegram_username || '',  // Phase 10.1.1
      role: contact.role,
      is_dm_trigger: contact.is_dm_trigger || false,  // Phase 4.3
      notes: contact.notes || ''
    })
  }

  const cancelEdit = () => {
    setEditing(null)
    setCreating(false)
    setFormData({ friendly_name: '', whatsapp_id: '', phone_number: '', telegram_id: '', telegram_username: '', role: 'user', is_dm_trigger: true, notes: '' })
  }

  if (loading) return <div>Loading contacts...</div>

  // Calculate DM trigger contacts
  const dmTriggerContacts = contacts.filter(c => c.is_dm_trigger && c.role === 'user')

  return (
    <div className="border dark:border-gray-700 p-4 rounded-md">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-lg font-semibold inline-flex items-center gap-2"><UsersIcon size={18} /> Contact Management</h2>
        {!creating && !editing && (
          <button
            onClick={() => setCreating(true)}
            className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 text-sm"
          >
            + Add Contact
          </button>
        )}
      </div>

      <p className="text-xs text-gray-600 dark:text-gray-400 mb-4">
        Manage users and agents. The agent can recognize users by their friendly names, WhatsApp IDs, or phone numbers.
        Mentions like @Alice, @123456789012345, or @5500000000000 will be detected.
      </p>

      {/* Phase 4.3: DM Triggers Summary */}
      {dmTriggerContacts.length > 0 && (
        <div className="mb-4 p-3 bg-green-50 dark:bg-green-900/20 border dark:border-gray-700 border-green-300 dark:border-green-600 rounded-md">
          <h3 className="text-sm font-semibold text-green-800 dark:text-green-200 mb-2 inline-flex items-center gap-1">
            <SmartphoneIcon size={14} /> DM Triggers ({dmTriggerContacts.length})
          </h3>
          <p className="text-xs text-green-700 dark:text-green-300 mb-2">
            The agent will automatically respond to direct messages from:
          </p>
          <div className="flex flex-wrap gap-2">
            {dmTriggerContacts.map(contact => (
              <span
                key={contact.id}
                className="text-xs px-2 py-1 bg-green-200 dark:bg-green-700/40 text-green-800 dark:text-green-200 rounded"
              >
                {contact.friendly_name} ({contact.phone_number})
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Contact Form Modal */}
      <Modal
        isOpen={creating || editing !== null}
        onClose={cancelEdit}
        title={creating ? 'Create New Contact' : 'Edit Contact'}
        size="lg"
        footer={
          <div className="flex justify-end gap-2">
            <button
              onClick={cancelEdit}
              className="px-4 py-2 bg-gray-300 dark:bg-gray-600 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-400 dark:hover:bg-gray-500 text-sm"
            >
              Cancel
            </button>
            <button
              onClick={() => creating ? handleCreate() : handleUpdate(editing!)}
              className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm"
            >
              {creating ? 'Create' : 'Save'}
            </button>
          </div>
        }
      >
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300">
                Friendly Name *
              </label>
              <input
                type="text"
                value={formData.friendly_name}
                onChange={(e) => setFormData({ ...formData, friendly_name: e.target.value })}
                placeholder="e.g., Alice, Agent1"
                className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300">
                Role *
              </label>
              <select
                value={formData.role}
                onChange={(e) => setFormData({ ...formData, role: e.target.value as 'user' | 'agent' })}
                className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500"
              >
                <option value="user">User</option>
                <option value="agent">Agent</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300">
                WhatsApp ID
              </label>
              <input
                type="text"
                value={formData.whatsapp_id}
                onChange={(e) => setFormData({ ...formData, whatsapp_id: e.target.value })}
                placeholder="e.g., 140127703679231"
                className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300">
                Phone Number
              </label>
              <input
                type="text"
                value={formData.phone_number}
                onChange={(e) => setFormData({ ...formData, phone_number: e.target.value })}
                placeholder="e.g., 5500000000001"
                className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {/* Phase 10.1.1: Telegram fields */}
            <div>
              <label className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300">
                Telegram ID
              </label>
              <input
                type="text"
                value={formData.telegram_id}
                onChange={(e) => setFormData({ ...formData, telegram_id: e.target.value })}
                placeholder="e.g., 123456789"
                className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500"
              />
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Numeric Telegram user ID</p>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300">
                Telegram Username
              </label>
              <input
                type="text"
                value={formData.telegram_username}
                onChange={(e) => setFormData({ ...formData, telegram_username: e.target.value })}
                placeholder="e.g., johndoe"
                className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500"
              />
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Telegram @username (without @)</p>
            </div>
          </div>

          {/* Phase 4.3: DM Trigger Checkbox (only for users) */}
          {formData.role === 'user' && (
            <div className="p-3 bg-green-50 dark:bg-green-900/20 border dark:border-gray-700 border-green-300 dark:border-green-600 rounded-md">
              <label className="flex items-start gap-3">
                <input
                  type="checkbox"
                  checked={formData.is_dm_trigger}
                  onChange={(e) => setFormData({ ...formData, is_dm_trigger: e.target.checked })}
                  className="mt-1 w-4 h-4 text-blue-600 border-gray-300 dark:border-gray-600 rounded"
                />
                <div>
                  <span className="font-medium text-sm text-gray-900 dark:text-gray-100">Enable DM Trigger</span>
                  <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                    Agent will automatically respond to direct messages from this contact
                  </p>
                </div>
              </label>
            </div>
          )}

          {/* Phase 10.2: Channel Mappings (only when editing) */}
          {editing && (
            <div className="p-3 bg-blue-50 dark:bg-blue-900/20 border dark:border-gray-700 border-blue-300 dark:border-blue-600 rounded-md">
              <h4 className="font-medium text-sm text-gray-900 dark:text-gray-100 mb-2">Add Channel Mapping</h4>
              <div className="grid grid-cols-3 gap-2 mb-2">
                <select
                  value={newChannelType}
                  onChange={(e) => setNewChannelType(e.target.value)}
                  className="px-2 py-1 border dark:border-gray-700 rounded text-xs text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
                >
                  <option value="">Select Channel</option>
                  <option value="whatsapp">WhatsApp</option>
                  <option value="telegram">Telegram</option>
                  <option value="phone">Phone</option>
                  <option value="discord">Discord</option>
                  <option value="slack">Slack</option>
                  <option value="email">Email</option>
                  <option value="sms">SMS</option>
                </select>
                <input
                  type="text"
                  placeholder="Identifier"
                  value={newChannelIdentifier}
                  onChange={(e) => setNewChannelIdentifier(e.target.value)}
                  className="px-2 py-1 border dark:border-gray-700 rounded text-xs text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
                />
                <input
                  type="text"
                  placeholder='Metadata (JSON)'
                  value={newChannelMetadata}
                  onChange={(e) => setNewChannelMetadata(e.target.value)}
                  className="px-2 py-1 border dark:border-gray-700 rounded text-xs text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
                />
              </div>
              <button
                onClick={() => handleAddChannelMapping(editing)}
                className="w-full px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 text-xs"
              >
                Add Mapping
              </button>
            </div>
          )}

          <div>
            <label className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300">
              Notes
            </label>
            <textarea
              value={formData.notes}
              onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
              placeholder="Optional notes about this contact"
              rows={3}
              className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>
      </Modal>

      {/* Contact List */}
      <div className="space-y-2">
        {contacts.length === 0 ? (
          <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">
            No contacts found. Add your first contact to get started!
          </p>
        ) : (
          contacts.map((contact) => (
            <div
              key={contact.id}
              className={`p-3 border dark:border-gray-700 rounded-md ${
                contact.role === 'agent' ? 'bg-purple-50 dark:bg-purple-900/20 border-purple-300 dark:border-purple-600' : 'bg-gray-50 dark:bg-gray-900'
              }`}
            >
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold">{contact.friendly_name}</span>
                    <span
                      className={`text-xs px-2 py-0.5 rounded ${
                        contact.role === 'agent'
                          ? 'bg-purple-200 dark:bg-purple-700/40 text-purple-800 dark:text-purple-200'
                          : 'bg-blue-200 text-blue-800 dark:text-blue-200'
                      }`}
                    >
                      {contact.role}
                    </span>
                    {!contact.is_active && (
                      <span className="text-xs px-2 py-0.5 rounded bg-gray-300 dark:bg-gray-600 text-gray-700 dark:text-gray-300">
                        inactive
                      </span>
                    )}
                    {contact.is_dm_trigger && (
                      <span className="text-xs px-2 py-0.5 rounded bg-green-200 dark:bg-green-700/40 text-green-800 dark:text-green-200">
                        DM trigger
                      </span>
                    )}
                  </div>

                  <div className="text-xs text-gray-600 dark:text-gray-400 space-y-0.5">
                    {contact.whatsapp_id && (
                      <div>WhatsApp ID: <code className="bg-gray-200 dark:bg-gray-700 px-1 rounded">{contact.whatsapp_id}</code></div>
                    )}
                    {contact.phone_number && (
                      <div>Phone: <code className="bg-gray-200 dark:bg-gray-700 px-1 rounded">{contact.phone_number}</code></div>
                    )}
                    {contact.telegram_id && (
                      <div>Telegram ID: <code className="bg-gray-200 dark:bg-gray-700 px-1 rounded">{contact.telegram_id}</code></div>
                    )}
                    {contact.telegram_username && (
                      <div>Telegram: <code className="bg-gray-200 dark:bg-gray-700 px-1 rounded">@{contact.telegram_username}</code></div>
                    )}
                    {contact.notes && (
                      <div className="text-gray-500 dark:text-gray-400 italic">{contact.notes}</div>
                    )}

                    {/* Phase 10.2: Channel Mappings */}
                    {contact.channel_mappings && contact.channel_mappings.length > 0 && (
                      <div className="mt-2 pt-2 border-t dark:border-gray-600">
                        <div className="font-semibold text-gray-700 dark:text-gray-300 mb-1">Channel Mappings:</div>
                        {contact.channel_mappings.map((mapping) => (
                          <div key={mapping.id} className="flex items-center justify-between mb-1">
                            <div>
                              <span className="text-xs px-1.5 py-0.5 bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-200 rounded mr-1">
                                {mapping.channel_type}
                              </span>
                              <code className="bg-gray-200 dark:bg-gray-700 px-1 rounded text-xs">{mapping.channel_identifier}</code>
                              {mapping.channel_metadata?.username && (
                                <span className="ml-1 text-gray-500">(@{mapping.channel_metadata.username})</span>
                              )}
                            </div>
                            {editing !== contact.id && !creating && (
                              <button
                                onClick={() => handleRemoveChannelMapping(contact.id, mapping.id)}
                                className="text-xs text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300"
                              >
                                Remove
                              </button>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                {editing !== contact.id && !creating && (
                  <div className="flex gap-2">
                    <button
                      onClick={() => startEdit(contact)}
                      className="px-3 py-1 bg-blue-500 text-white rounded hover:bg-blue-600 text-xs"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => handleDelete(contact.id)}
                      className="px-3 py-1 bg-red-500 text-white rounded hover:bg-red-600 text-xs"
                    >
                      Delete
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Example Mentions */}
      {contacts.length > 0 && (
        <div className="mt-4 p-3 bg-gray-100 dark:bg-gray-800 rounded text-xs">
          <p className="font-semibold mb-2 inline-flex items-center gap-1"><LightbulbIcon size={12} /> Example Mentions:</p>
          <div className="space-y-1 text-gray-700 dark:text-gray-300">
            {contacts.map((c) => (
              <div key={c.id}>
                @{c.friendly_name}
                {c.whatsapp_id && `, @${c.whatsapp_id}`}
                {c.phone_number && `, @${c.phone_number}`}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
