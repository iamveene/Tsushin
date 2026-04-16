/**
 * Public path predicate shared between AuthContext (client) and middleware (Edge).
 *
 * Kept in a framework-agnostic module (no `'use client'`, no `next/*` imports)
 * so it can be safely imported from both the client AuthContext and the Edge
 * middleware runtime.
 *
 * BUG-4: unauthenticated users on protected routes must be redirected to
 * `/auth/login`. Both the client-side AuthContext (hard redirect on 401) and
 * the server-side middleware (belt-and-braces redirect when the session
 * cookie is absent) use this predicate to decide which paths are exempt
 * from that redirect.
 */

export const PUBLIC_PATH_PREFIXES = ['/auth', '/setup'] as const

export function isPublicPath(pathname: string | null | undefined): boolean {
  if (!pathname) return false
  return PUBLIC_PATH_PREFIXES.some((p) => pathname.startsWith(p))
}
