'use client'

interface IntegrationSummaryProps {
  providerCount: number
  whatsappCount: number
  telegramCount: number
  slackCount: number
  discordCount: number
  webhookCount: number
  onTabSelect: (tab: string) => void
}

const integrations = [
  { key: 'ai-providers', label: 'AI Providers', color: 'bg-purple-500', prop: 'providerCount' as const },
  { key: 'communication', label: 'WhatsApp', color: 'bg-green-500', prop: 'whatsappCount' as const },
  { key: 'communication', label: 'Telegram', color: 'bg-blue-500', prop: 'telegramCount' as const },
  { key: 'communication', label: 'Slack', color: 'bg-purple-400', prop: 'slackCount' as const },
  { key: 'communication', label: 'Discord', color: 'bg-indigo-500', prop: 'discordCount' as const },
  { key: 'communication', label: 'Webhooks', color: 'bg-cyan-500', prop: 'webhookCount' as const },
]

export default function IntegrationSummary(props: IntegrationSummaryProps) {
  const { onTabSelect } = props

  return (
    <div className="glass-card p-3 mb-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        {integrations.map((item, idx) => {
          const count = props[item.prop]
          const active = count > 0
          return (
            <button
              key={idx}
              onClick={() => onTabSelect(item.key)}
              className="flex items-center gap-1.5 text-xs hover:opacity-80 transition-opacity"
            >
              <span className={`w-2 h-2 rounded-full ${active ? item.color : 'bg-tsushin-slate/30'}`} />
              <span className={active ? 'text-white' : 'text-tsushin-slate'}>{item.label}</span>
              <span className={`font-mono ${active ? 'text-white' : 'text-tsushin-slate/50'}`}>{count}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
