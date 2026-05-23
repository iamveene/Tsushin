'use client'

/**
 * Tool palette overlay for the recorder. Three modes — capture captcha,
 * capture output text, and (Phase 4) wire a vault entry — translate
 * directly into FlowNode `selectors[]` row shapes when the recorder
 * compiles the session.
 *
 * The palette itself is stateless; the parent (RecorderDialog) owns the
 * current marker mode and forwards user gestures to the StreamCanvas.
 */

export type MarkerMode = 'captcha' | 'extract' | null

interface ToolPaletteProps {
  markerMode: MarkerMode
  onModeChange: (mode: MarkerMode) => void
  /** Triggered when the user explicitly opens the vault picker without
   * targeting an existing fill row. Phase 4 leaves this disabled for
   * now (the chip-on-row flow inside StepLedger covers the common case). */
  onOpenVaultPicker?: () => void
}

const baseBtn = 'px-2.5 py-1 rounded-md border text-xs font-medium transition-colors'

export default function ToolPalette({
  markerMode,
  onModeChange,
  onOpenVaultPicker,
}: ToolPaletteProps) {
  const captchaActive = markerMode === 'captcha'
  const extractActive = markerMode === 'extract'

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <button
        type="button"
        onClick={() => onModeChange(captchaActive ? null : 'captcha')}
        className={
          `${baseBtn} ` +
          (captchaActive
            ? 'border-amber-400 bg-amber-500/20 text-amber-200'
            : 'border-slate-600 bg-slate-800/50 text-slate-300 hover:border-amber-500/50 hover:text-amber-200')
        }
        title="Drag a box over a captcha image — the runtime will OCR it via LLM vision and fill the linked input."
      >
        ▣ Mark captcha
      </button>

      <button
        type="button"
        onClick={() => onModeChange(extractActive ? null : 'extract')}
        className={
          `${baseBtn} ` +
          (extractActive
            ? 'border-fuchsia-400 bg-fuchsia-500/20 text-fuchsia-200'
            : 'border-slate-600 bg-slate-800/50 text-slate-300 hover:border-fuchsia-500/50 hover:text-fuchsia-200')
        }
        title="Drag a box over text on the page — its content is extracted into a named variable for downstream steps."
      >
        👁 Capture output
      </button>

      {onOpenVaultPicker && (
        <button
          type="button"
          onClick={onOpenVaultPicker}
          className={`${baseBtn} border-slate-600 bg-slate-800/50 text-slate-300 hover:border-yellow-500/50 hover:text-yellow-200`}
          title="Pick a Password Vault entry. The matching field on the latest fill row gets its plaintext value swapped for a secret reference."
        >
          🔑 Inject vault
        </button>
      )}

      {markerMode && (
        <span className="text-xs text-slate-400 italic">
          Drag a box over the {markerMode === 'captcha' ? 'captcha image' : 'text to capture'}…
        </span>
      )}
    </div>
  )
}
