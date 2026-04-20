/**
 * Playground Mini — session storage helper.
 *
 * Persists only small selection state across route changes and hard refreshes.
 * Messages are NEVER persisted here — they are re-fetched from the backend
 * which also re-validates tenant ownership on every `api.getThread` call.
 *
 * Keyed by userId so stale state from a previous user on the same tab is
 * ignored after a logout/login cycle.
 */

const STORAGE_PREFIX = 'tsushin:playground-mini:v1'

export interface PlaygroundMiniPersistedState {
  isOpen: boolean
  selectedAgentId: number | null
  selectedProjectId: number | null
  activeThreadId: number | null
}

const EMPTY_STATE: PlaygroundMiniPersistedState = {
  isOpen: false,
  selectedAgentId: null,
  selectedProjectId: null,
  activeThreadId: null,
}

function getKey(userId: number | null | undefined): string | null {
  if (!userId && userId !== 0) return null
  return `${STORAGE_PREFIX}:${userId}`
}

export function load(userId: number | null | undefined): PlaygroundMiniPersistedState {
  if (typeof window === 'undefined') return EMPTY_STATE
  const key = getKey(userId)
  if (!key) return EMPTY_STATE
  try {
    const raw = sessionStorage.getItem(key)
    if (!raw) return EMPTY_STATE
    const parsed = JSON.parse(raw) as Partial<PlaygroundMiniPersistedState>
    return {
      isOpen: Boolean(parsed.isOpen),
      selectedAgentId: typeof parsed.selectedAgentId === 'number' ? parsed.selectedAgentId : null,
      selectedProjectId: typeof parsed.selectedProjectId === 'number' ? parsed.selectedProjectId : null,
      activeThreadId: typeof parsed.activeThreadId === 'number' ? parsed.activeThreadId : null,
    }
  } catch {
    return EMPTY_STATE
  }
}

export function save(userId: number | null | undefined, patch: Partial<PlaygroundMiniPersistedState>): void {
  if (typeof window === 'undefined') return
  const key = getKey(userId)
  if (!key) return
  try {
    const current = load(userId)
    const next: PlaygroundMiniPersistedState = { ...current, ...patch }
    sessionStorage.setItem(key, JSON.stringify(next))
  } catch {
    // quota exceeded or disabled — ignore, the Mini still works in-memory
  }
}

export function clear(userId: number | null | undefined): void {
  if (typeof window === 'undefined') return
  const key = getKey(userId)
  if (!key) return
  try {
    sessionStorage.removeItem(key)
  } catch {
    /* no-op */
  }
}

export function clearAll(): void {
  if (typeof window === 'undefined') return
  try {
    const toRemove: string[] = []
    for (let i = 0; i < sessionStorage.length; i++) {
      const k = sessionStorage.key(i)
      if (k && k.startsWith(STORAGE_PREFIX)) toRemove.push(k)
    }
    toRemove.forEach(k => sessionStorage.removeItem(k))
  } catch {
    /* no-op */
  }
}
