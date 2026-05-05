import { redirect } from 'next/navigation'

type SearchParams = Record<string, string | string[] | undefined>

export default async function AgentsTeamsRedirectPage({
  searchParams,
}: {
  searchParams?: SearchParams | Promise<SearchParams>
}) {
  const resolved = searchParams ? await searchParams : {}
  const params = new URLSearchParams()
  Object.entries(resolved).forEach(([key, value]) => {
    if (Array.isArray(value)) {
      value.forEach((item) => params.append(key, item))
    } else if (value !== undefined) {
      params.set(key, value)
    }
  })
  const query = params.toString()
  redirect(query ? `/studio/teams?${query}` : '/studio/teams')
}
