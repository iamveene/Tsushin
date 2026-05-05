import { NextRequest, NextResponse } from 'next/server'

type AuthRouteContext = {
  params: Promise<{
    path?: string[]
  }>
}

const HOP_BY_HOP_HEADERS = new Set([
  'connection',
  'content-encoding',
  'content-length',
  'host',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
])

function getBackendOrigin(): string {
  const stackName = process.env.TSN_STACK_NAME?.trim()
  return (
    process.env.BACKEND_INTERNAL_URL ||
    process.env.INTERNAL_API_URL ||
    (stackName ? `http://${stackName}-backend:8081` : '') ||
    process.env.NEXT_PUBLIC_API_URL ||
    'http://backend:8081'
  ).replace(/\/+$/, '')
}

function getForwardedProto(request: NextRequest): string {
  const sslMode = (process.env.TSN_SSL_MODE || process.env.SSL_MODE || '')
    .trim()
    .toLowerCase()
  const sslEnabled = !['', 'disabled', 'off', 'none'].includes(sslMode)
  if (!sslEnabled) {
    return 'http'
  }

  const proto = request.headers.get('x-forwarded-proto')
  if (proto) {
    return proto.split(',')[0]?.trim().replace(/:$/, '') || 'http'
  }
  return request.nextUrl.protocol.replace(/:$/, '') || 'http'
}

function getForwardedHost(request: NextRequest): string {
  return (
    request.headers.get('x-forwarded-host') ||
    request.headers.get('host') ||
    request.nextUrl.host
  )
}

function getForwardedFor(request: NextRequest): string {
  const existing = request.headers.get('x-forwarded-for')
  const connecting = request.headers.get('x-real-ip')
  if (existing && connecting) {
    return `${existing}, ${connecting}`
  }
  return existing || connecting || ''
}

function getSetCookieValues(headers: Headers): string[] {
  const withGetSetCookie = headers as Headers & {
    getSetCookie?: () => string[]
  }
  if (typeof withGetSetCookie.getSetCookie === 'function') {
    return withGetSetCookie.getSetCookie()
  }

  const singleHeader = headers.get('set-cookie')
  return singleHeader ? [singleHeader] : []
}

async function proxyAuthRequest(
  request: NextRequest,
  context: AuthRouteContext,
): Promise<NextResponse> {
  const params = await context.params
  const path = params.path?.map(encodeURIComponent).join('/') ?? ''
  const backendUrl = new URL(
    `/api/auth/${path}${request.nextUrl.search}`,
    getBackendOrigin(),
  )

  const headers = new Headers()
  request.headers.forEach((value, key) => {
    if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) {
      headers.set(key, value)
    }
  })
  headers.set('x-forwarded-proto', getForwardedProto(request))
  headers.set('x-forwarded-host', getForwardedHost(request))
  const forwardedFor = getForwardedFor(request)
  if (forwardedFor) {
    headers.set('x-forwarded-for', forwardedFor)
  }

  const body =
    request.method === 'GET' || request.method === 'HEAD'
      ? undefined
      : await request.arrayBuffer()

  const upstream = await fetch(backendUrl, {
    method: request.method,
    headers,
    body,
    redirect: 'manual',
    cache: 'no-store',
  })

  const responseHeaders = new Headers()
  upstream.headers.forEach((value, key) => {
    const normalizedKey = key.toLowerCase()
    if (normalizedKey !== 'set-cookie' && !HOP_BY_HOP_HEADERS.has(normalizedKey)) {
      responseHeaders.append(key, value)
    }
  })

  const responseBody =
    request.method === 'HEAD' || upstream.status === 204 || upstream.status === 304
      ? null
      : await upstream.arrayBuffer()
  const response = new NextResponse(responseBody, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  })

  for (const cookie of getSetCookieValues(upstream.headers)) {
    response.headers.append('set-cookie', cookie)
  }

  return response
}

export const GET = proxyAuthRequest
export const POST = proxyAuthRequest
export const PUT = proxyAuthRequest
export const PATCH = proxyAuthRequest
export const DELETE = proxyAuthRequest
export const OPTIONS = proxyAuthRequest
export const HEAD = proxyAuthRequest
