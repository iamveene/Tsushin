'use client'

/**
 * ChannelsWizard — guided entry point for the Hub > Communication tab.
 *
 * Replaces the six scattered per-channel CTAs ("+ Create WhatsApp Instance"
 * at tab level, "+ Create Bot" / "+ Connect Workspace" / "+ Connect Bot" /
 * "Add Another Gmail" per-section, plus duplicate empty-
 * state body buttons) with a single "+ Add Channel" launcher. The wizard
 * shows the channel catalog as a picker, then hands off to the existing
 * per-channel setup modal (WhatsAppSetupWizard, Telegram modal,
 * SlackSetupWizard, DiscordSetupWizard, GmailSetupWizard).
 *
 * Catalog source: /api/channels (see backend/api/routes_channels.py and
 * backend/channels/catalog.py). The frontend keeps a static fallback so
 * the picker works offline / pre-catalog.
 *
 * backend/tests/test_wizard_drift.py cross-checks every backend catalog
 * entry against the fallback array below (Guard 5).
 */

import { useEffect, useMemo, useState } from 'react'
import Modal from '@/components/ui/Modal'
import { api, type ChannelCatalogEntry } from '@/lib/client'

export type ChannelId =
  | 'whatsapp'
  | 'telegram'
  | 'slack'
  | 'discord'
  | 'gmail'

interface Props {
  isOpen: boolean
  onClose: () => void
  /** Invoked when the user picks a channel and clicks Continue. The Hub
   *  page is responsible for opening the appropriate sub-wizard or modal.
   *  The wizard closes itself before the callback fires. */
  onChannelSelected: (channelId: ChannelId) => void
}

// Fallback catalog — matches CHANNEL_CATALOG in
// backend/channels/catalog.py plus a 'gmail' entry that doubles as an
// inbound email channel in the Communication tab. Drift guard:
// backend/tests/test_wizard_drift.py Guard 5.
const FALLBACK_CHANNELS: Array<ChannelCatalogEntry & { channel_id: ChannelId }> = [
  {
    channel_id: 'whatsapp',
    id: 'whatsapp',
    display_name: 'WhatsApp',
    description: 'Per-tenant WhatsApp Business instance (via MCP).',
    requires_setup: true,
    setup_hint: 'Scans a QR code and pairs a phone number to the tenant.',
    icon_hint: 'whatsapp',
    tenant_has_configured: false,
  },
  {
    channel_id: 'telegram',
    id: 'telegram',
    display_name: 'Telegram',
    description: 'Route Telegram messages to one or more agents.',
    requires_setup: true,
    setup_hint: 'Provide a bot token from @BotFather.',
    icon_hint: 'telegram',
    tenant_has_configured: false,
  },
  {
    channel_id: 'slack',
    id: 'slack',
    display_name: 'Slack',
    description: 'Respond to mentions, DMs, or channel messages.',
    requires_setup: true,
    setup_hint: 'Install the Slack app or paste bot/signing tokens.',
    icon_hint: 'slack',
    tenant_has_configured: false,
  },
  {
    channel_id: 'discord',
    id: 'discord',
    display_name: 'Discord',
    description: 'Bridge a Discord bot to an agent.',
    requires_setup: true,
    setup_hint: 'Provide the bot token and application id.',
    icon_hint: 'discord',
    tenant_has_configured: false,
  },
  {
    channel_id: 'gmail',
    id: 'gmail',
    display_name: 'Gmail (inbound)',
    description: 'Treat a Gmail inbox as a message channel.',
    requires_setup: true,
    setup_hint: 'Uses the same Google OAuth as Productivity Gmail.',
    icon_hint: 'gmail',
    tenant_has_configured: false,
  },
]

export default function ChannelsWizard({ isOpen, onClose, onChannelSelected }: Props) {
  const [channels, setChannels] = useState(FALLBACK_CHANNELS)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [selectedChannel, setSelectedChannel] = useState<ChannelId | null>(null)

  useEffect(() => {
    if (!isOpen) return
    setSelectedChannel(null)
    setLoadError(null)
    let cancelled = false
    api.getChannelCatalog()
      .then(list => {
        if (cancelled) return
        if (!Array.isArray(list) || list.length === 0) return
        // Merge live catalog with fallback. Live rows provide the
        // per-tenant `tenant_has_configured` flag; the fallback supplies
        // channel_id (typed union) and the Gmail entry the backend
        // catalog doesn't currently ship.
        const liveById = new Map(list.map(r => [r.id, r]))
        const merged = FALLBACK_CHANNELS.map(fb => {
          const live = liveById.get(fb.id)
          if (!live) return fb
          return {
            ...fb,
            ...live,
            channel_id: fb.channel_id,
          }
        })
        // Drop 'playground' — it's not actionable from this wizard.
        setChannels(merged.filter(c => c.channel_id !== ('playground' as ChannelId)))
      })
      .catch(err => {
        if (!cancelled) setLoadError(err?.message || 'Could not load live catalog')
      })
    return () => { cancelled = true }
  }, [isOpen])

  const actionable = useMemo(() => channels.filter(c => c.requires_setup), [channels])

  const handleContinue = () => {
    if (!selectedChannel) return
    // Close outer modal before opening the sub-wizard to avoid stacked modals.
    onClose()
    onChannelSelected(selectedChannel)
  }

  if (!isOpen) return null

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Add Channel" size="lg">
      <div className="space-y-5">
        <div className="flex items-center gap-2 text-xs text-tsushin-slate">
          <span className="px-2 py-0.5 rounded-full border bg-tsushin-accent/20 border-tsushin-accent/40 text-tsushin-accent">
            1. Channel
          </span>
          <span>→</span>
          <span className="px-2 py-0.5 rounded-full border border-tsushin-slate/20 opacity-60">
            2. Connect
          </span>
        </div>

        {loadError && (
          <div className="text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded px-3 py-2">
            Using offline catalog — {loadError}
          </div>
        )}

        <p className="text-sm text-tsushin-slate">
          Pick the channel to connect. We'll hand you off to the channel-specific setup wizard with the
          fields it needs (tokens, OAuth, webhook secret, etc.). You can add multiple instances of any
          channel — e.g. two Slack workspaces, two Telegram bots.
        </p>

        <div className="grid gap-3 md:grid-cols-2">
          {actionable.map(ch => {
            const selected = selectedChannel === ch.channel_id
            return (
              <button
                key={ch.channel_id}
                type="button"
                onClick={() => setSelectedChannel(ch.channel_id)}
                className={`text-left p-4 rounded-xl border transition-all ${
                  selected
                    ? 'bg-tsushin-accent/10 border-tsushin-accent/50'
                    : 'bg-tsushin-slate/5 border-tsushin-slate/20 hover:bg-tsushin-slate/10'
                }`}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-semibold text-white">{ch.display_name}</span>
                  {ch.tenant_has_configured && (
                    <span className="ml-auto text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                      Already connected
                    </span>
                  )}
                </div>
                <p className="text-xs text-tsushin-slate">{ch.description}</p>
                <p className="text-[10px] text-tsushin-slate/70 mt-2">{ch.setup_hint}</p>
              </button>
            )
          })}
        </div>

        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="btn-ghost px-4 py-2 text-sm">Cancel</button>
          <button
            type="button"
            disabled={!selectedChannel}
            onClick={handleContinue}
            className={`btn-primary px-4 py-2 text-sm ${!selectedChannel ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            Continue to Connect
          </button>
        </div>
      </div>
    </Modal>
  )
}
