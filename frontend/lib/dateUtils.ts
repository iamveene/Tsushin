/**
 * Shared date/time formatting utilities.
 *
 * Backend stores all timestamps in UTC. Older records may lack a timezone
 * indicator ("Z" or "+00:00"), so parseUTCTimestamp defensively appends "Z"
 * when the suffix is missing, ensuring JavaScript always interprets the
 * value as UTC and converts to the browser's local timezone on display.
 */

/**
 * Parse a backend timestamp string as UTC.
 * If the string has no timezone indicator, append "Z" so JS treats it as UTC.
 */
export function parseUTCTimestamp(timestamp: string): Date {
  if (!timestamp) return new Date()
  const trimmed = timestamp.trim()
  // Already has timezone info
  if (trimmed.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(trimmed)) {
    return new Date(trimmed)
  }
  // Naive string — treat as UTC
  return new Date(trimmed + 'Z')
}

/** Format as time only: "02:30 PM" */
export function formatTime(timestamp: string): string {
  try {
    return parseUTCTimestamp(timestamp).toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return ''
  }
}

/** Format as short date + time: "Feb 6, 02:30 PM" */
export function formatDateTime(timestamp: string): string {
  try {
    return parseUTCTimestamp(timestamp).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return ''
  }
}

/** Format as full locale date + time string */
export function formatDateTimeFull(timestamp: string): string {
  try {
    return parseUTCTimestamp(timestamp).toLocaleString()
  } catch {
    return ''
  }
}

/** Format as relative time: "Just now", "5m ago", "2h ago", "3d ago", or a date */
export function formatRelative(timestamp: string): string {
  try {
    const date = parseUTCTimestamp(timestamp)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    if (diffMs < 0) return formatDateTime(timestamp)
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)
    if (diffMins < 1) return 'Just now'
    if (diffMins < 60) return `${diffMins}m ago`
    if (diffHours < 24) return `${diffHours}h ago`
    if (diffDays < 7) return `${diffDays}d ago`
    return date.toLocaleDateString()
  } catch {
    return ''
  }
}

/** Format as date only: "Feb 6, 2026" */
export function formatDate(timestamp: string): string {
  try {
    return parseUTCTimestamp(timestamp).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return ''
  }
}
