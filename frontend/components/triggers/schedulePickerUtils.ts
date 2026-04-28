import { formatInTimeZone } from 'date-fns-tz'

export type ScheduleFrequency =
  | 'hourly'
  | 'daily'
  | 'weekly'
  | 'monthly'
  | 'once'
  | 'custom'

export interface ScheduleState {
  frequency: ScheduleFrequency
  /** 0–59, used by `hourly` mode */
  minuteOffset: number
  /** "HH:MM" or "" — used by daily / weekly / monthly / once */
  time: string
  /** ISO weekday numbers: 1=Mon … 7=Sun. Cron Sunday is 0; we map at compile time. */
  daysOfWeek: number[]
  /** 1–28 (28 stands in for "last day" — see SchedulePicker docs) */
  dayOfMonth: number
  /** Sentinel preserved separately so the UI can show "Last day" while compiling to 28. */
  isLastDay: boolean
  /** "YYYY-MM-DD" or "" */
  date: string
  /** Free-text cron used by `custom` mode. */
  rawCron: string
}

export const DEFAULT_SCHEDULE_STATE: ScheduleState = {
  frequency: 'hourly',
  minuteOffset: 0,
  time: '09:00',
  daysOfWeek: [1],
  dayOfMonth: 1,
  isLastDay: false,
  date: '',
  rawCron: '',
}

export const ISO_DAY_NAMES: Record<number, string> = {
  1: 'Monday',
  2: 'Tuesday',
  3: 'Wednesday',
  4: 'Thursday',
  5: 'Friday',
  6: 'Saturday',
  7: 'Sunday',
}

export const ISO_DAY_SHORT: Record<number, string> = {
  1: 'Mon',
  2: 'Tue',
  3: 'Wed',
  4: 'Thu',
  5: 'Fri',
  6: 'Sat',
  7: 'Sun',
}

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

export interface CuratedTimezone {
  id: string
  label: string
}

export const CURATED_TIMEZONES: CuratedTimezone[] = [
  { id: 'UTC', label: 'UTC' },
  { id: 'America/New_York', label: 'New York (Eastern)' },
  { id: 'America/Chicago', label: 'Chicago (Central)' },
  { id: 'America/Denver', label: 'Denver (Mountain)' },
  { id: 'America/Los_Angeles', label: 'Los Angeles (Pacific)' },
  { id: 'America/Anchorage', label: 'Anchorage (Alaska)' },
  { id: 'America/Honolulu', label: 'Honolulu (Hawaii)' },
  { id: 'America/Toronto', label: 'Toronto' },
  { id: 'America/Mexico_City', label: 'Mexico City' },
  { id: 'America/Sao_Paulo', label: 'São Paulo' },
  { id: 'America/Argentina/Buenos_Aires', label: 'Buenos Aires' },
  { id: 'America/Bogota', label: 'Bogotá' },
  { id: 'America/Santiago', label: 'Santiago' },
  { id: 'Europe/London', label: 'London' },
  { id: 'Europe/Paris', label: 'Paris' },
  { id: 'Europe/Berlin', label: 'Berlin' },
  { id: 'Europe/Madrid', label: 'Madrid' },
  { id: 'Europe/Lisbon', label: 'Lisbon' },
  { id: 'Europe/Amsterdam', label: 'Amsterdam' },
  { id: 'Europe/Stockholm', label: 'Stockholm' },
  { id: 'Europe/Moscow', label: 'Moscow' },
  { id: 'Africa/Johannesburg', label: 'Johannesburg' },
  { id: 'Africa/Cairo', label: 'Cairo' },
  { id: 'Asia/Dubai', label: 'Dubai' },
  { id: 'Asia/Kolkata', label: 'Kolkata (India)' },
  { id: 'Asia/Singapore', label: 'Singapore' },
  { id: 'Asia/Shanghai', label: 'Shanghai' },
  { id: 'Asia/Tokyo', label: 'Tokyo' },
  { id: 'Asia/Seoul', label: 'Seoul' },
  { id: 'Australia/Sydney', label: 'Sydney' },
  { id: 'Australia/Melbourne', label: 'Melbourne' },
  { id: 'Pacific/Auckland', label: 'Auckland' },
]

const CRON_FIELD_REGEX = /^[0-9*/,\-LW#?]+$/i

export function cronLooksValid(cron: string): boolean {
  const trimmed = cron.trim()
  if (!trimmed) return false
  const parts = trimmed.split(/\s+/)
  if (parts.length < 5 || parts.length > 6) return false
  return parts.every((p) => p.length > 0 && CRON_FIELD_REGEX.test(p))
}

export function parseTime(t: string): { hour: number; minute: number } | null {
  if (!t) return null
  const m = t.match(/^(\d{1,2}):(\d{2})$/)
  if (!m) return null
  const hour = parseInt(m[1], 10)
  const minute = parseInt(m[2], 10)
  if (Number.isNaN(hour) || Number.isNaN(minute)) return null
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return null
  return { hour, minute }
}

function isoDayToCron(iso: number): number {
  return iso === 7 ? 0 : iso
}

function cronDayToIso(cronDay: string): number | null {
  const n = parseInt(cronDay, 10)
  if (Number.isNaN(n)) return null
  if (n < 0 || n > 7) return null
  return n === 0 ? 7 : n
}

/**
 * Returns true when the structured state holds enough data to emit a meaningful cron.
 * Custom mode requires `cronLooksValid(rawCron)`. Visual modes require their fields populated.
 */
export function isScheduleStateValid(state: ScheduleState): boolean {
  switch (state.frequency) {
    case 'hourly':
      return Number.isFinite(state.minuteOffset) && state.minuteOffset >= 0 && state.minuteOffset <= 59
    case 'daily':
      return parseTime(state.time) !== null
    case 'weekly':
      return state.daysOfWeek.length > 0 && parseTime(state.time) !== null
    case 'monthly':
      // UI clamps dayOfMonth to 28 for cross-month compatibility (Feb 29-31 etc.).
      // Validator must match the UI contract — accepting 29-31 here would let
      // sourceValid open while compileToCron silently clamps to 28, fooling
      // the user about which day fires.
      return parseTime(state.time) !== null && state.dayOfMonth >= 1 && state.dayOfMonth <= 28
    case 'once':
      return Boolean(state.date) && parseTime(state.time) !== null
    case 'custom':
      return cronLooksValid(state.rawCron)
  }
}

/**
 * Compile a structured schedule state to a 5-field cron expression.
 * Returns "" when the state is incomplete/invalid (caller should treat as "do not emit").
 * For `custom` mode, returns the raw text trimmed.
 */
export function compileToCron(state: ScheduleState): string {
  switch (state.frequency) {
    case 'hourly': {
      const minute = clampMinute(state.minuteOffset)
      return `${minute} * * * *`
    }
    case 'daily': {
      const t = parseTime(state.time)
      if (!t) return ''
      return `${t.minute} ${t.hour} * * *`
    }
    case 'weekly': {
      const t = parseTime(state.time)
      if (!t || state.daysOfWeek.length === 0) return ''
      const cronDays = Array.from(new Set(state.daysOfWeek.map(isoDayToCron)))
        .sort((a, b) => a - b)
        .join(',')
      return `${t.minute} ${t.hour} * * ${cronDays}`
    }
    case 'monthly': {
      const t = parseTime(state.time)
      if (!t) return ''
      const day = clampDayOfMonth(state.dayOfMonth)
      return `${t.minute} ${t.hour} ${day} * *`
    }
    case 'once': {
      const t = parseTime(state.time)
      if (!t || !state.date) return ''
      const dateMatch = state.date.match(/^(\d{4})-(\d{2})-(\d{2})$/)
      if (!dateMatch) return ''
      const month = parseInt(dateMatch[2], 10)
      const day = parseInt(dateMatch[3], 10)
      if (month < 1 || month > 12 || day < 1 || day > 31) return ''
      return `${t.minute} ${t.hour} ${day} ${month} *`
    }
    case 'custom':
      return state.rawCron.trim()
  }
}

function clampMinute(n: number): number {
  if (!Number.isFinite(n)) return 0
  return Math.max(0, Math.min(59, Math.floor(n)))
}

function clampDayOfMonth(n: number): number {
  if (!Number.isFinite(n)) return 1
  return Math.max(1, Math.min(28, Math.floor(n)))
}

/**
 * Best-effort round-trip from a cron string back to a structured state.
 * Returns null if the expression is too complex to decompose.
 */
export function parseFromCron(cron: string): Partial<ScheduleState> | null {
  const trimmed = cron.trim()
  if (!trimmed) return null
  const parts = trimmed.split(/\s+/)
  if (parts.length !== 5) return null
  const [min, hour, dom, month, dow] = parts

  const minNum = parseInt(min, 10)
  const hourNum = parseInt(hour, 10)
  const isPlainMin = !Number.isNaN(minNum) && /^\d+$/.test(min)
  const isPlainHour = !Number.isNaN(hourNum) && /^\d+$/.test(hour)

  // Hourly: `M * * * *`
  if (isPlainMin && hour === '*' && dom === '*' && month === '*' && dow === '*') {
    return { frequency: 'hourly', minuteOffset: clampMinute(minNum) }
  }

  // Daily: `M H * * *`
  if (isPlainMin && isPlainHour && dom === '*' && month === '*' && dow === '*') {
    return {
      frequency: 'daily',
      time: `${pad2(hourNum)}:${pad2(minNum)}`,
    }
  }

  // Weekly: `M H * * D[,D...]`
  if (isPlainMin && isPlainHour && dom === '*' && month === '*' && dow !== '*') {
    if (!/^[0-9]+(?:,[0-9]+)*$/.test(dow)) return null
    const isoDays: number[] = []
    for (const d of dow.split(',')) {
      const iso = cronDayToIso(d)
      if (iso == null) return null
      isoDays.push(iso)
    }
    const uniqDays = Array.from(new Set(isoDays)).sort((a, b) => a - b)
    return {
      frequency: 'weekly',
      daysOfWeek: uniqDays,
      time: `${pad2(hourNum)}:${pad2(minNum)}`,
    }
  }

  // Monthly: `M H D * *`
  if (isPlainMin && isPlainHour && dow === '*' && month === '*' && dom !== '*') {
    const domNum = parseInt(dom, 10)
    if (Number.isNaN(domNum) || !/^\d+$/.test(dom)) return null
    if (domNum < 1 || domNum > 31) return null
    return {
      frequency: 'monthly',
      dayOfMonth: clampDayOfMonth(domNum),
      isLastDay: domNum === 28,
      time: `${pad2(hourNum)}:${pad2(minNum)}`,
    }
  }

  // Once: `M H D MO *` — a 5-field cron does NOT carry the year, so we
  // cannot recover the user's intended year from the expression alone.
  // Returning null forces the caller to fall back to defaults rather than
  // silently fabricating the current year (which would lose the year the
  // user originally chose when they round-tripped through Custom mode).
  // Round-trip is best-effort by design.
  return null
}

function pad2(n: number): string {
  return String(n).padStart(2, '0')
}

function ordinal(n: number): string {
  const abs = Math.abs(n)
  const lastTwo = abs % 100
  if (lastTwo >= 11 && lastTwo <= 13) return `${n}th`
  switch (abs % 10) {
    case 1: return `${n}st`
    case 2: return `${n}nd`
    case 3: return `${n}rd`
    default: return `${n}th`
  }
}

function formatTime12(t: string): string {
  const parsed = parseTime(t)
  if (!parsed) return ''
  const period = parsed.hour >= 12 ? 'PM' : 'AM'
  const hour12 = parsed.hour % 12 === 0 ? 12 : parsed.hour % 12
  return `${hour12}:${pad2(parsed.minute)} ${period}`
}

function formatLongDate(iso: string): string {
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (!m) return iso
  const year = parseInt(m[1], 10)
  const month = parseInt(m[2], 10)
  const day = parseInt(m[3], 10)
  if (month < 1 || month > 12) return iso
  return `${MONTH_NAMES[month - 1]} ${day}, ${year}`
}

function joinHumanList(items: string[]): string {
  if (items.length === 0) return ''
  if (items.length === 1) return items[0]
  if (items.length === 2) return `${items[0]} and ${items[1]}`
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`
}

/**
 * Build a plain-English sentence describing the schedule.
 * Returns "" when state is too incomplete to describe.
 */
export function naturalLanguagePreview(state: ScheduleState, tz: string): string {
  const tzLabel = tz ? ` (${tz})` : ''
  switch (state.frequency) {
    case 'hourly': {
      const m = clampMinute(state.minuteOffset)
      return `Every hour at minute ${m}${tzLabel}`
    }
    case 'daily': {
      const t12 = formatTime12(state.time)
      if (!t12) return ''
      return `Every day at ${t12}${tzLabel}`
    }
    case 'weekly': {
      if (state.daysOfWeek.length === 0) return ''
      const t12 = formatTime12(state.time)
      if (!t12) return ''
      const sortedDays = [...state.daysOfWeek].sort((a, b) => a - b)
      const dayNames = sortedDays.map((d) => ISO_DAY_NAMES[d]).filter(Boolean)
      return `Every ${joinHumanList(dayNames)} at ${t12}${tzLabel}`
    }
    case 'monthly': {
      const t12 = formatTime12(state.time)
      if (!t12) return ''
      const day = state.isLastDay
        ? 'the last day'
        : `the ${ordinal(clampDayOfMonth(state.dayOfMonth))}`
      return `On ${day} of every month at ${t12}${tzLabel}`
    }
    case 'once': {
      const t12 = formatTime12(state.time)
      if (!state.date || !t12) return ''
      return `Once on ${formatLongDate(state.date)} at ${t12}${tzLabel}`
    }
    case 'custom':
      return state.rawCron.trim()
  }
}

/**
 * Format an ISO-like timestamp into a "Tue 28 Apr 2026, 09:00" string for the given IANA tz.
 *
 * Backend `/triggers/schedule/preview` emits **naive UTC** datetimes (no `Z` suffix). We
 * therefore treat any string without an offset as UTC by appending `Z` before parsing — that
 * way `formatInTimeZone` correctly converts to the requested zone. Strings that already carry
 * `Z` or a `±HH:MM` offset are passed through unchanged.
 */
export function formatPreviewTime(iso: string, tz: string): string {
  if (!iso) return ''
  const hasOffset = /([Zz]|[+-]\d{2}:?\d{2})$/.test(iso)
  const normalized = hasOffset ? iso : `${iso}Z`
  try {
    return formatInTimeZone(new Date(normalized), tz || 'UTC', 'EEE d MMM yyyy, HH:mm')
  } catch {
    return iso
  }
}
