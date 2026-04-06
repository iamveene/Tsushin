'use client'

import { useWhatsAppWizard } from '@/contexts/WhatsAppWizardContext'

export default function StepWelcome() {
  const { nextStep } = useWhatsAppWizard()

  return (
    <div className="space-y-6">
      <div className="text-center">
        <div className="w-16 h-16 bg-green-500/20 rounded-2xl flex items-center justify-center mx-auto mb-4">
          <svg className="w-8 h-8 text-green-400" viewBox="0 0 24 24" fill="currentColor">
            <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z" />
          </svg>
        </div>
        <h3 className="text-xl font-bold text-white mb-2">Connect WhatsApp</h3>
        <p className="text-tsushin-slate max-w-md mx-auto">
          This wizard will guide you through connecting your WhatsApp number so your AI agents can send and receive messages automatically.
        </p>
      </div>

      <div className="bg-tsushin-deep/50 rounded-xl p-5 space-y-4">
        <h4 className="text-sm font-semibold text-white">What we'll set up:</h4>
        <div className="space-y-3">
          {[
            {
              icon: '1',
              title: 'Link your phone',
              desc: 'Scan a QR code to connect your WhatsApp number',
            },
            {
              icon: '2',
              title: 'Configure direct messages',
              desc: 'Choose who can message your agent privately',
            },
            {
              icon: '3',
              title: 'Set up group monitoring',
              desc: 'Pick which groups your agent listens to and what triggers it',
            },
            {
              icon: '4',
              title: 'Add contacts',
              desc: 'Register people your agent should recognize',
            },
            {
              icon: '5',
              title: 'Connect to an agent',
              desc: 'Choose which AI agent handles this WhatsApp number',
            },
          ].map((item) => (
            <div key={item.icon} className="flex items-start gap-3">
              <div className="w-6 h-6 rounded-full bg-teal-500/20 text-teal-400 flex items-center justify-center text-xs font-bold flex-shrink-0 mt-0.5">
                {item.icon}
              </div>
              <div>
                <p className="text-sm font-medium text-white">{item.title}</p>
                <p className="text-xs text-tsushin-slate">{item.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-teal-500/10 border border-teal-500/20 rounded-lg p-3">
        <p className="text-xs text-teal-300">
          <span className="font-semibold">Tip:</span> You can skip any step and come back later. Each step saves your progress immediately.
        </p>
      </div>

      <button
        onClick={nextStep}
        className="w-full py-3 bg-gradient-to-r from-teal-500 to-cyan-500 text-white font-semibold rounded-lg hover:from-teal-600 hover:to-cyan-600 transition-all"
      >
        Let's Get Started
      </button>
    </div>
  )
}
