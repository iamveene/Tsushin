'use client'

import {
  type KeyboardEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { api } from '@/lib/client'
import {
  CURATED_TIMEZONES,
  DEFAULT_SCHEDULE_STATE,
  ISO_DAY_SHORT,
  type ScheduleFrequency,
  type ScheduleState,
  compileToCron,
  cronLooksValid,
  formatPreviewTime,
  isScheduleStateValid,
  naturalLanguagePreview,
  parseFromCron,
  parseTime,
} from './schedulePickerUtils'

interface SchedulePickerProps {
  /** Current structured schedule state (controlled). */
  value: ScheduleState
  /** Receives every structured update — including invalid intermediate states. */
  onChange: (next: ScheduleState) => void
  /**
   * Receives the compiled 5-field cron string whenever the structured state changes.
   * Called with "" when the state is incomplete/invalid.
   */
  cronOnChange?: (cron: string) => void
  /** IANA timezone identifier. */
  timezoneId: string
  /** Receives the new IANA timezone identifier. */
  onTimezoneIdChange: (tz: string) => void
  /** Optional outer wrapper className. */
  className?: string
}

interface FrequencyOption {
  id: ScheduleFrequency
  label: string
}

const FREQUENCY_OPTIONS: FrequencyOption[] = [
  { id: 'hourly', label: 'Every hour' },
  { id: 'daily', label: 'Every day' },
  { id: 'weekly', label: 'Every week' },
  { id: 'monthly', label: 'Every month' },
  { id: 'once', label: 'Once' },
  { id: 'custom', label: 'Custom (cron)' },
]

const ISO_DAY_ORDER = [1, 2, 3, 4, 5, 6, 7]

const inputBaseClass =
  'w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-500/30'

const monoInputClass =
  'w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 font-mono text-sm text-white placeholder:text-tsushin-slate focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-500/30'

const FOCUS_TARGET_ID: Record<ScheduleFrequency, string> = {
  hourly: 'sched-minute-offset',
  daily: 'sched-daily-time',
  weekly: 'sched-weekly-day-1',
  monthly: 'sched-monthly-dom',
  once: 'sched-once-date',
  custom: 'sched-custom-cron',
}

export default function SchedulePicker({
  value,
  onChange,
  cronOnChange,
  timezoneId,
  onTimezoneIdChange,
  className = '',
}: SchedulePickerProps) {
  const [previewLines, setPreviewLines] = useState<string[]>([])
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)

  const compiledCron = useMemo(() => compileToCron(value), [value])
  const valid = useMemo(() => isScheduleStateValid(value), [value])

  const previousCronRef = useRef<string>(compiledCron)
  useEffect(() => {
    if (compiledCron === previousCronRef.current) return
    previousCronRef.current = compiledCron
    cronOnChange?.(compiledCron)
  }, [compiledCron, cronOnChange])

  const focusTargetRef = useRef<ScheduleFrequency | null>(null)
  useEffect(() => {
    if (focusTargetRef.current !== value.frequency) return
    const id = FOCUS_TARGET_ID[value.frequency]
    if (!id) return
    const el = document.getElementById(id) as HTMLElement | null
    el?.focus?.()
    focusTargetRef.current = null
  }, [value.frequency])

  // Debounced preview fetch
  useEffect(() => {
    if (!valid || !compiledCron) {
      setPreviewLines([])
      setPreviewError(null)
      setPreviewLoading(false)
      return
    }
    let cancelled = false
    setPreviewLoading(true)
    setPreviewError(null)
    const handle = window.setTimeout(async () => {
      try {
        const result = await api.previewScheduleTrigger({
          cron_expression: compiledCron,
          timezone: timezoneId || 'UTC',
          payload_template: null,
        })
        if (cancelled) return
        const times =
          result.next_fire_preview ??
          result.next_fire_times ??
          result.next_runs ??
          []
        if (result.error) {
          setPreviewError(result.error)
          setPreviewLines([])
        } else {
          setPreviewLines(
            times
              .slice(0, 3)
              .map((iso) => formatPreviewTime(iso, timezoneId || 'UTC')),
          )
        }
      } catch (err) {
        if (cancelled) return
        const message =
          err instanceof Error ? err.message : 'Preview unavailable'
        setPreviewError(message)
        setPreviewLines([])
      } finally {
        if (!cancelled) setPreviewLoading(false)
      }
    }, 400)
    return () => {
      cancelled = true
      window.clearTimeout(handle)
    }
  }, [compiledCron, timezoneId, valid])

  const handleSelectFrequency = useCallback(
    (next: ScheduleFrequency) => {
      if (next === value.frequency) return
      focusTargetRef.current = next

      // Custom -> visual: try to round-trip parse the textarea so visual fields
      // are populated. If parse fails, keep the visual fields at defaults but
      // still switch (rawCron stays preserved in case the user comes back).
      if (value.frequency === 'custom' && next !== 'custom') {
        const parsed = parseFromCron(value.rawCron)
        if (parsed) {
          onChange({
            ...value,
            ...parsed,
            frequency: next,
          })
          return
        }
        // Couldn't decompose — switch frequency but don't pretend we restored state.
        onChange({
          ...DEFAULT_SCHEDULE_STATE,
          rawCron: value.rawCron,
          frequency: next,
        })
        return
      }

      // Visual -> custom: prefill the textarea with the compiled cron so the
      // user can tweak it instead of starting from blank.
      if (next === 'custom') {
        const seed = compileToCron(value) || value.rawCron || ''
        onChange({ ...value, frequency: next, rawCron: seed })
        return
      }

      onChange({ ...value, frequency: next })
    },
    [onChange, value],
  )

  const handleDayToggle = useCallback(
    (iso: number) => {
      const has = value.daysOfWeek.includes(iso)
      const next = has
        ? value.daysOfWeek.filter((d) => d !== iso)
        : [...value.daysOfWeek, iso]
      onChange({ ...value, daysOfWeek: next })
    },
    [onChange, value],
  )

  const handleDayKey = useCallback(
    (event: KeyboardEvent<HTMLButtonElement>, iso: number) => {
      if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
        event.preventDefault()
        const idx = ISO_DAY_ORDER.indexOf(iso)
        const delta = event.key === 'ArrowRight' ? 1 : -1
        const nextIso =
          ISO_DAY_ORDER[(idx + delta + ISO_DAY_ORDER.length) % ISO_DAY_ORDER.length]
        const target = document.getElementById(`sched-weekly-day-${nextIso}`)
        target?.focus()
      } else if (event.key === ' ' || event.key === 'Enter') {
        event.preventDefault()
        handleDayToggle(iso)
      }
    },
    [handleDayToggle],
  )

  const naturalLanguage = useMemo(
    () => naturalLanguagePreview(value, timezoneId || 'UTC'),
    [value, timezoneId],
  )

  const customCronValid = value.frequency === 'custom' ? cronLooksValid(value.rawCron) : true

  return (
    <div className={`space-y-5 ${className}`}>
      {/* Frequency mode selector */}
      <div
        role="tablist"
        aria-label="Schedule frequency"
        className="flex flex-wrap gap-2"
      >
        {FREQUENCY_OPTIONS.map((opt) => {
          const active = value.frequency === opt.id
          return (
            <button
              key={opt.id}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => handleSelectFrequency(opt.id)}
              className={`rounded-full border px-3.5 py-1.5 text-xs font-medium transition-colors ${
                active
                  ? 'border-amber-500/60 bg-amber-500/15 text-amber-100'
                  : 'border-tsushin-border bg-tsushin-slate/10 text-tsushin-slate hover:border-amber-500/30 hover:text-amber-100'
              }`}
            >
              {opt.label}
            </button>
          )
        })}
      </div>

      {/* Per-mode controls */}
      <div className="rounded-2xl border border-amber-500/20 bg-amber-500/5 p-4">
        {value.frequency === 'hourly' && (
          <HourlyControls
            value={value}
            onChange={onChange}
          />
        )}
        {value.frequency === 'daily' && (
          <DailyControls
            value={value}
            onChange={onChange}
          />
        )}
        {value.frequency === 'weekly' && (
          <WeeklyControls
            value={value}
            onChange={onChange}
            onDayToggle={handleDayToggle}
            onDayKey={handleDayKey}
          />
        )}
        {value.frequency === 'monthly' && (
          <MonthlyControls
            value={value}
            onChange={onChange}
          />
        )}
        {value.frequency === 'once' && (
          <OnceControls
            value={value}
            onChange={onChange}
          />
        )}
        {value.frequency === 'custom' && (
          <CustomControls
            value={value}
            onChange={onChange}
            looksValid={customCronValid}
          />
        )}

        {/* Natural language sentence (live region) */}
        <p
          role="status"
          aria-live="polite"
          aria-atomic="true"
          className="mt-4 text-xs text-tsushin-slate"
        >
          {valid
            ? naturalLanguage
            : value.frequency === 'custom'
            ? '5 fields: minute hour day month weekday'
            : 'Fill in the fields above to preview the schedule.'}
        </p>
      </div>

      {/* Timezone + cron chip row */}
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <label
            htmlFor="sched-timezone"
            className="block text-sm font-medium text-white"
          >
            Timezone <span className="text-red-400">*</span>
          </label>
          <select
            id="sched-timezone"
            aria-label="Timezone"
            value={timezoneId || 'UTC'}
            onChange={(event) => onTimezoneIdChange(event.target.value)}
            className={inputBaseClass}
          >
            {!CURATED_TIMEZONES.some((tz) => tz.id === timezoneId) && timezoneId && (
              <option value={timezoneId}>{timezoneId}</option>
            )}
            {CURATED_TIMEZONES.map((tz) => (
              <option key={tz.id} value={tz.id}>
                {tz.label}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-2">
          <span className="block text-sm font-medium text-white">Compiled cron</span>
          <div
            className="rounded-xl border border-tsushin-border bg-[#0a0a0f] px-3 py-2 font-mono text-sm text-amber-100"
            aria-label="Compiled cron expression"
          >
            {compiledCron || <span className="text-tsushin-slate">—</span>}
          </div>
        </div>
      </div>

      {/* Preview block */}
      <div className="rounded-2xl border border-amber-500/20 bg-amber-500/5 p-4">
        <div className="text-xs uppercase tracking-[0.18em] text-amber-200">
          Next 3 runs ({timezoneId || 'UTC'})
        </div>
        {!valid && (
          <p className="mt-2 text-xs text-tsushin-slate">
            Set a valid schedule to see upcoming run times.
          </p>
        )}
        {valid && previewLoading && (
          <ul className="mt-3 space-y-1.5">
            {[0, 1, 2].map((i) => (
              <li
                key={i}
                className="h-3 w-2/3 animate-pulse rounded bg-amber-500/15"
              />
            ))}
          </ul>
        )}
        {valid && !previewLoading && previewError && (
          <p
            role="alert"
            className="mt-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100"
          >
            Preview failed — expression may still be valid. ({previewError})
          </p>
        )}
        {valid && !previewLoading && !previewError && previewLines.length > 0 && (
          <ul className="mt-3 space-y-1 text-xs text-amber-100">
            {previewLines.map((line, idx) => (
              <li key={`${line}-${idx}`}>• {line}</li>
            ))}
          </ul>
        )}
        {valid && !previewLoading && !previewError && previewLines.length === 0 && (
          <p className="mt-2 text-xs text-tsushin-slate">
            No upcoming runs returned for this expression.
          </p>
        )}
      </div>

      {value.frequency === 'once' && (
        <p className="text-xs text-amber-200">
          Heads up: the underlying cron repeats annually on this date. Deactivate the trigger
          after the first run if you want it to fire only once.
        </p>
      )}
    </div>
  )
}

// ---------- Per-mode controls ----------

interface ModeControlProps {
  value: ScheduleState
  onChange: (next: ScheduleState) => void
}

function HourlyControls({ value, onChange }: ModeControlProps) {
  const minute = value.minuteOffset
  const valid = Number.isFinite(minute) && minute >= 0 && minute <= 59
  return (
    <div className="space-y-2">
      <label
        htmlFor="sched-minute-offset"
        className="block text-sm font-medium text-white"
      >
        At minute
      </label>
      <input
        id="sched-minute-offset"
        type="number"
        inputMode="numeric"
        min={0}
        max={59}
        value={Number.isFinite(minute) ? minute : 0}
        onChange={(event) => {
          const parsed = parseInt(event.target.value, 10)
          onChange({ ...value, minuteOffset: Number.isNaN(parsed) ? 0 : parsed })
        }}
        aria-label="Minute offset (0–59)"
        aria-invalid={!valid}
        className={`${monoInputClass} max-w-xs ${valid ? '' : 'border-red-500/60'}`}
      />
      {!valid && (
        <p role="alert" className="text-xs text-red-300">
          Minute must be between 0 and 59.
        </p>
      )}
    </div>
  )
}

function DailyControls({ value, onChange }: ModeControlProps) {
  const valid = parseTime(value.time) !== null
  return (
    <div className="space-y-2">
      <label
        htmlFor="sched-daily-time"
        className="block text-sm font-medium text-white"
      >
        Time of day
      </label>
      <input
        id="sched-daily-time"
        type="time"
        value={value.time}
        onChange={(event) => onChange({ ...value, time: event.target.value })}
        aria-label="Trigger time"
        aria-invalid={!valid}
        className={`${inputBaseClass} max-w-xs ${valid ? '' : 'border-red-500/60'}`}
      />
      {!valid && (
        <p role="alert" className="text-xs text-red-300">
          Pick a time.
        </p>
      )}
    </div>
  )
}

interface WeeklyControlsProps extends ModeControlProps {
  onDayToggle: (iso: number) => void
  onDayKey: (event: KeyboardEvent<HTMLButtonElement>, iso: number) => void
}

function WeeklyControls({ value, onChange, onDayToggle, onDayKey }: WeeklyControlsProps) {
  const timeValid = parseTime(value.time) !== null
  const daysValid = value.daysOfWeek.length > 0
  return (
    <div className="space-y-3">
      <div>
        <span
          id="sched-weekly-days-label"
          className="block text-sm font-medium text-white"
        >
          Days of week
        </span>
        <div
          role="group"
          aria-labelledby="sched-weekly-days-label"
          className="mt-2 flex flex-wrap gap-2"
        >
          {ISO_DAY_ORDER.map((iso) => {
            const selected = value.daysOfWeek.includes(iso)
            return (
              <button
                key={iso}
                id={`sched-weekly-day-${iso}`}
                type="button"
                aria-pressed={selected}
                onClick={() => onDayToggle(iso)}
                onKeyDown={(event) => onDayKey(event, iso)}
                className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                  selected
                    ? 'border-amber-500/60 bg-amber-500/20 text-amber-100'
                    : 'border-tsushin-border bg-tsushin-slate/10 text-tsushin-slate hover:border-amber-500/30 hover:text-amber-100'
                }`}
              >
                {ISO_DAY_SHORT[iso]}
              </button>
            )
          })}
        </div>
        {!daysValid && (
          <p role="alert" className="mt-1 text-xs text-red-300">
            Select at least one day.
          </p>
        )}
      </div>
      <div className="space-y-2">
        <label
          htmlFor="sched-weekly-time"
          className="block text-sm font-medium text-white"
        >
          Time of day
        </label>
        <input
          id="sched-weekly-time"
          type="time"
          value={value.time}
          onChange={(event) => onChange({ ...value, time: event.target.value })}
          aria-label="Trigger time"
          aria-invalid={!timeValid}
          className={`${inputBaseClass} max-w-xs ${timeValid ? '' : 'border-red-500/60'}`}
        />
        {!timeValid && (
          <p role="alert" className="text-xs text-red-300">
            Pick a time.
          </p>
        )}
      </div>
    </div>
  )
}

function MonthlyControls({ value, onChange }: ModeControlProps) {
  const timeValid = parseTime(value.time) !== null
  return (
    <div className="space-y-3">
      <div className="space-y-2">
        <label
          htmlFor="sched-monthly-dom"
          className="block text-sm font-medium text-white"
        >
          Day of month
        </label>
        <select
          id="sched-monthly-dom"
          value={value.isLastDay ? 'last' : String(value.dayOfMonth)}
          onChange={(event) => {
            const v = event.target.value
            if (v === 'last') {
              onChange({ ...value, isLastDay: true, dayOfMonth: 28 })
            } else {
              const n = parseInt(v, 10)
              onChange({
                ...value,
                isLastDay: false,
                dayOfMonth: Number.isNaN(n) ? 1 : n,
              })
            }
          }}
          className={`${inputBaseClass} max-w-xs`}
        >
          {Array.from({ length: 28 }, (_, i) => i + 1).map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
          <option value="last">Last day (28th)</option>
        </select>
        <p className="text-xs text-tsushin-slate">
          Day 28 is used as &ldquo;last day&rdquo; for full month compatibility. For 29–31 use
          Custom (cron).
        </p>
      </div>
      <div className="space-y-2">
        <label
          htmlFor="sched-monthly-time"
          className="block text-sm font-medium text-white"
        >
          Time of day
        </label>
        <input
          id="sched-monthly-time"
          type="time"
          value={value.time}
          onChange={(event) => onChange({ ...value, time: event.target.value })}
          aria-label="Trigger time"
          aria-invalid={!timeValid}
          className={`${inputBaseClass} max-w-xs ${timeValid ? '' : 'border-red-500/60'}`}
        />
        {!timeValid && (
          <p role="alert" className="text-xs text-red-300">
            Pick a time.
          </p>
        )}
      </div>
    </div>
  )
}

function OnceControls({ value, onChange }: ModeControlProps) {
  const timeValid = parseTime(value.time) !== null
  const dateValid = Boolean(value.date && /^\d{4}-\d{2}-\d{2}$/.test(value.date))
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <div className="space-y-2">
        <label
          htmlFor="sched-once-date"
          className="block text-sm font-medium text-white"
        >
          Date
        </label>
        <input
          id="sched-once-date"
          type="date"
          value={value.date}
          onChange={(event) => onChange({ ...value, date: event.target.value })}
          aria-label="Trigger date"
          aria-invalid={!dateValid}
          className={`${inputBaseClass} ${dateValid ? '' : 'border-red-500/60'}`}
        />
        {!dateValid && (
          <p role="alert" className="text-xs text-red-300">
            Pick a date.
          </p>
        )}
      </div>
      <div className="space-y-2">
        <label
          htmlFor="sched-once-time"
          className="block text-sm font-medium text-white"
        >
          Time
        </label>
        <input
          id="sched-once-time"
          type="time"
          value={value.time}
          onChange={(event) => onChange({ ...value, time: event.target.value })}
          aria-label="Trigger time"
          aria-invalid={!timeValid}
          className={`${inputBaseClass} ${timeValid ? '' : 'border-red-500/60'}`}
        />
        {!timeValid && (
          <p role="alert" className="text-xs text-red-300">
            Pick a time.
          </p>
        )}
      </div>
    </div>
  )
}

interface CustomControlsProps extends ModeControlProps {
  looksValid: boolean
}

function CustomControls({ value, onChange, looksValid }: CustomControlsProps) {
  return (
    <div className="space-y-2">
      <label
        htmlFor="sched-custom-cron"
        className="block text-sm font-medium text-white"
      >
        Cron expression
      </label>
      <textarea
        id="sched-custom-cron"
        rows={2}
        value={value.rawCron}
        onChange={(event) => onChange({ ...value, rawCron: event.target.value })}
        placeholder="*/15 9-17 * * 1-5"
        aria-label="Custom cron expression"
        aria-invalid={!looksValid}
        className={`${monoInputClass} ${looksValid ? '' : 'border-amber-500/60'}`}
      />
      <p
        className={`text-xs ${
          looksValid ? 'text-tsushin-slate' : 'text-amber-300'
        }`}
      >
        Use 5 or 6 cron fields (minute hour day month weekday [year]).
      </p>
    </div>
  )
}
