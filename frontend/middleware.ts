import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export function middleware(request: NextRequest) {
  const { nextUrl } = request

  // Redirect /login to /auth/login (or straight to / if already authenticated)
  if (nextUrl.pathname === '/login') {
    const hasSession = request.cookies.has('tsushin_session')
    const target = hasSession ? '/' : '/auth/login'
    return NextResponse.redirect(new URL(target, request.url))
  }

  // Redirect authenticated users away from login page
  if (nextUrl.pathname === '/auth/login' && request.cookies.has('tsushin_session')) {
    return NextResponse.redirect(new URL('/', request.url))
  }

  const sslMode = (process.env.TSN_SSL_MODE || '').toLowerCase()
  // BUG-444: SSL redirect depends solely on the runtime TSN_SSL_MODE env var.
  // Previously also checked NEXT_PUBLIC_API_URL.startsWith('https://'), but
  // that is a build-time value and can be stale from a cached Docker layer.
  const sslEnabled = !['', 'disabled', 'off', 'none'].includes(sslMode)

  // Only act on HTTP (non-HTTPS) requests, and only when the deployment
  // actually expects HTTPS. HTTP-only installs must remain reachable on
  // localhost/127.0.0.1 without a redirect loop.
  if (!sslEnabled) {
    return NextResponse.next()
  }

  const proto = request.headers.get('x-forwarded-proto') || nextUrl.protocol
  const isHttps = proto === 'https' || proto === 'https:'

  if (!isHttps) {
    const host = request.headers.get('host') || nextUrl.host

    // Skip redirect for Docker/internal health checks from the numeric loopback
    // address. Docker health check uses wget to http://127.0.0.1:3030 — we
    // must not redirect those or the container will be marked unhealthy.
    // NOTE: 'localhost:3030' browser access IS redirected (see below).
    if (host.startsWith('127.0.0.1') || host.startsWith('[::1]')) {
      return NextResponse.next()
    }

    // BUG-438 FIX: Redirect localhost direct-port access to HTTPS regardless
    // of which published frontend port the stack is using. Remote HTTP installs
    // (e.g. http://10.x.x.x:13032) must still remain reachable.
    if (host.startsWith('localhost:')) {
      // Redirect localhost HTTP to https://localhost preserving path and query
      const httpsUrl = new URL(request.url)
      httpsUrl.protocol = 'https:'
      httpsUrl.host = 'localhost'
      httpsUrl.port = ''
      return NextResponse.redirect(httpsUrl.toString(), 301)
    }
  }

  return NextResponse.next()
}

export const config = {
  /*
   * Match all routes except:
   * - _next/static  (static assets)
   * - _next/image   (image optimizer)
   * - favicon.ico
   * - public files  (images, icons, etc.)
   */
  matcher: ['/((?!_next/static|_next/image|favicon.ico|.*\\.(?:png|jpg|jpeg|gif|svg|ico|webp|woff2?|ttf|eot|otf|css|js|json)$).*)'],
}
