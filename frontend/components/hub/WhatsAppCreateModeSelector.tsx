'use client'

import Modal from '@/components/ui/Modal'
import { BeakerIcon, BotIcon, LightningIcon, WrenchIcon } from '@/components/ui/icons'
import type { WhatsAppWizardInstanceType } from '@/contexts/WhatsAppWizardContext'

interface WhatsAppCreateModeSelectorProps {
  isOpen: boolean
  onClose: () => void
  onSelectWizard: (instanceType: WhatsAppWizardInstanceType) => void
  onSelectAdvanced: () => void
}

export default function WhatsAppCreateModeSelector({
  isOpen,
  onClose,
  onSelectWizard,
  onSelectAdvanced
}: WhatsAppCreateModeSelectorProps) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Create WhatsApp Instance" size="sm">
      <div className="space-y-4">
        {/* Wizard card */}
        <div className="relative w-full text-left p-5 rounded-xl border-2 border-teal-500/30 bg-teal-500/5">
          <span className="absolute top-3 right-3 bg-teal-500/20 text-teal-300 text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wide">
            Recommended
          </span>
          <div className="flex items-start gap-4">
            <div className="w-11 h-11 bg-teal-500/15 rounded-xl flex items-center justify-center flex-shrink-0">
              <LightningIcon size={22} className="text-teal-400" />
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="text-base font-semibold text-white mb-1">Guided Setup</h3>
              <p className="text-sm text-tsushin-slate leading-relaxed">
                Step-by-step wizard that configures your instance, contacts, filters, and agent binding.
              </p>
              <div className="flex flex-wrap gap-2 mt-3">
                <span className="text-[11px] text-teal-300/80 bg-teal-500/10 px-2 py-0.5 rounded-md">8 guided steps</span>
                <span className="text-[11px] text-teal-300/80 bg-teal-500/10 px-2 py-0.5 rounded-md">Auto-configures filters</span>
                <span className="text-[11px] text-teal-300/80 bg-teal-500/10 px-2 py-0.5 rounded-md">Binds agent automatically</span>
              </div>
            </div>
          </div>
          <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
            <button
              type="button"
              onClick={() => onSelectWizard('agent')}
              className="group rounded-lg border border-teal-500/30 bg-tsushin-deep/50 px-3 py-3 text-left hover:border-teal-400/60 hover:bg-teal-500/10 transition-all"
            >
              <div className="flex items-center gap-2 text-sm font-semibold text-white">
                <BotIcon size={17} className="text-teal-300" />
                Bot instance
              </div>
              <p className="mt-1 text-xs leading-relaxed text-tsushin-slate">
                Full setup with contacts, filters, and agent binding.
              </p>
            </button>
            <button
              type="button"
              onClick={() => onSelectWizard('tester')}
              className="group rounded-lg border border-orange-500/30 bg-tsushin-deep/50 px-3 py-3 text-left hover:border-orange-400/60 hover:bg-orange-500/10 transition-all"
            >
              <div className="flex items-center gap-2 text-sm font-semibold text-white">
                <BeakerIcon size={17} className="text-orange-300" />
                Tester instance
              </div>
              <p className="mt-1 text-xs leading-relaxed text-tsushin-slate">
                QR-only QA bridge for tester-to-bot validation.
              </p>
            </button>
          </div>
        </div>

        {/* Divider */}
        <div className="relative flex items-center">
          <div className="flex-1 border-t border-tsushin-border" />
          <span className="px-3 text-xs text-tsushin-slate">or</span>
          <div className="flex-1 border-t border-tsushin-border" />
        </div>

        {/* Advanced card */}
        <button
          onClick={onSelectAdvanced}
          className="group w-full text-left p-5 rounded-xl border border-tsushin-border bg-tsushin-deep/50 hover:border-tsushin-muted hover:bg-tsushin-surface transition-all cursor-pointer"
        >
          <div className="flex items-start gap-4">
            <div className="w-11 h-11 bg-tsushin-muted/15 rounded-xl flex items-center justify-center flex-shrink-0 group-hover:bg-tsushin-muted/25 transition-colors">
              <WrenchIcon size={20} className="text-tsushin-slate" />
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="text-base font-semibold text-white mb-1">Advanced Setup</h3>
              <p className="text-sm text-tsushin-slate leading-relaxed">
                Create an instance directly with phone number and type. Configure everything else manually afterwards.
              </p>
            </div>
          </div>
        </button>
      </div>
    </Modal>
  )
}
