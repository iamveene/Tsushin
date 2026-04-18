import LoginClient from './LoginClient'

type SearchParamValue = string | string[] | undefined
type SearchParams = Record<string, SearchParamValue>

function readSearchParam(value: SearchParamValue): string | null {
  if (Array.isArray(value)) {
    return value[0] ?? null
  }
  return value ?? null
}

function getServerApiCandidates(): string[] {
  const seen = new Set<string>()
  const candidates: string[] = []

  for (const rawCandidate of [
    process.env.INTERNAL_API_URL,
    process.env.NEXT_PUBLIC_API_URL,
    'http://backend:8081',
  ]) {
    if (!rawCandidate) {
      continue
    }

    try {
      const candidateUrl = new URL(rawCandidate)
      const normalizedOrigin = candidateUrl.origin

      if (!seen.has(normalizedOrigin)) {
        seen.add(normalizedOrigin)
        candidates.push(normalizedOrigin)
      }

      if (candidateUrl.hostname === 'localhost' || candidateUrl.hostname === '127.0.0.1') {
        const dockerOrigin = 'http://backend:8081'
        if (!seen.has(dockerOrigin)) {
          seen.add(dockerOrigin)
          candidates.push(dockerOrigin)
        }
      }
    } catch {
      // Ignore malformed env values and try the next candidate.
    }
  }

  return candidates
}

async function getInitialGoogleSSOEnabled(): Promise<boolean | null> {
  for (const origin of getServerApiCandidates()) {
    try {
      const response = await fetch(`${origin}/api/auth/google/status`, {
        cache: 'no-store',
        signal: AbortSignal.timeout(3000),
      })
      if (!response.ok) {
        continue
      }

      const payload = await response.json()
      if (typeof payload?.enabled === 'boolean') {
        return payload.enabled
      }
    } catch {
      // Fall through to the next candidate and let the client-side refresh
      // recover if the server lookup cannot reach the backend directly.
    }
  }

  return null
}

export default async function LoginPage({
  searchParams,
}: {
  searchParams?: Promise<SearchParams>
}) {
  const resolvedSearchParams = await Promise.resolve(searchParams ?? {})
  const errorParam = readSearchParam(resolvedSearchParams.error)
  const recoveryReason = readSearchParam(resolvedSearchParams.reason)
  const forceLogin = readSearchParam(resolvedSearchParams.force) === '1'
  const initialGoogleSSOEnabled = await getInitialGoogleSSOEnabled()

  return (
    <LoginClient
      errorParam={errorParam}
      forceLogin={forceLogin}
      initialGoogleSSOEnabled={initialGoogleSSOEnabled}
      recoveryReason={recoveryReason}
    />
  )
}
