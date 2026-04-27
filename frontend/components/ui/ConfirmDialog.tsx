'use client'

/**
 * ConfirmDialog — styled in-app confirmation modal.
 *
 * Replaces the unstyled native `window.confirm()` for destructive
 * actions (trigger deletion, webhook secret rotation, binding unbind,
 * etc.). Caught by the v0.7.0 release-finishing exhaustive QA pass —
 * native confirm broke visual consistency on the Danger Zone tab.
 *
 * Usage:
 *
 *   const [open, setOpen] = useState(false)
 *   <ConfirmDialog
 *     isOpen={open}
 *     title="Delete Jira trigger?"
 *     message="This permanently removes the trigger and its history."
 *     confirmLabel="Delete trigger"
 *     danger
 *     requireType={trigger.integration_name}
 *     onConfirm={async () => { await api.deleteJiraTrigger(id); setOpen(false) }}
 *     onCancel={() => setOpen(false)}
 *   />
 */

import { useEffect, useRef, useState } from 'react'

interface Props {
  isOpen: boolean
  title: string
  message?: string | React.ReactNode
  confirmLabel?: string
  cancelLabel?: string
  danger?: boolean
  /** When set, the user must type this exact string to enable the confirm button. */
  requireType?: string | null
  /** Called when the user clicks the confirm button. Should set isOpen=false on success. */
  onConfirm: () => void | Promise<void>
  /** Called on backdrop click, Escape key, or Cancel button. */
  onCancel: () => void
  /** Disabled when the calling parent is mid-flight (e.g. delete API in progress). */
  isBusy?: boolean
}

export default function ConfirmDialog({
  isOpen,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  danger = false,
  requireType = null,
  onConfirm,
  onCancel,
  isBusy = false,
}: Props) {
  const [typeInput, setTypeInput] = useState('')
  const inputRef = useRef<HTMLInputElement | null>(null)
  const cancelRef = useRef<HTMLButtonElement | null>(null)

  // Reset typed value whenever the dialog opens.
  useEffect(() => {
    if (isOpen) setTypeInput('')
  }, [isOpen])

  // Escape key + autofocus.
  useEffect(() => {
    if (!isOpen) return
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.preventDefault()
        if (!isBusy) onCancel()
      }
    }
    document.addEventListener('keydown', handleKey)
    // Autofocus the type-to-confirm input if present, else the cancel button
    // (so Enter doesn't trigger a destructive default).
    setTimeout(() => {
      if (requireType && inputRef.current) inputRef.current.focus()
      else if (cancelRef.current) cancelRef.current.focus()
    }, 50)
    return () => document.removeEventListener('keydown', handleKey)
  }, [isOpen, isBusy, onCancel, requireType])

  if (!isOpen) return null

  const typeMatches = !requireType || typeInput.trim() === requireType
  const confirmDisabled = isBusy || !typeMatches

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      onClick={() => { if (!isBusy) onCancel() }}
      onMouseDown={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
    >
      <div
        className="w-full max-w-md rounded-2xl border border-tsushin-border bg-tsushin-surface p-6 shadow-2xl shadow-black/50"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="confirm-dialog-title" className="text-lg font-semibold text-white">
          {title}
        </h2>

        {message && (
          <div className="mt-3 text-sm text-tsushin-fog">
            {message}
          </div>
        )}

        {requireType && (
          <div className="mt-4">
            <label className="block text-xs uppercase tracking-wide text-tsushin-slate mb-1.5">
              Type <span className="font-mono text-tsushin-fog">{requireType}</span> to confirm
            </label>
            <input
              ref={inputRef}
              type="text"
              value={typeInput}
              onChange={(e) => setTypeInput(e.target.value)}
              disabled={isBusy}
              className="w-full rounded-lg border border-tsushin-border bg-black/30 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500/30 disabled:opacity-50"
              placeholder=""
            />
          </div>
        )}

        <div className="mt-6 flex justify-end gap-2">
          <button
            ref={cancelRef}
            type="button"
            onClick={onCancel}
            disabled={isBusy}
            className="rounded-lg border border-tsushin-border bg-black/20 px-4 py-2 text-sm text-tsushin-fog hover:bg-tsushin-border/40 hover:text-white disabled:opacity-50"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={() => { if (!confirmDisabled) onConfirm() }}
            disabled={confirmDisabled}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
              danger
                ? 'bg-red-500/20 text-red-200 border border-red-500/40 hover:bg-red-500/30 hover:text-white'
                : 'bg-cyan-500/20 text-cyan-200 border border-cyan-500/40 hover:bg-cyan-500/30 hover:text-white'
            } disabled:opacity-40 disabled:cursor-not-allowed`}
          >
            {isBusy ? 'Working…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
