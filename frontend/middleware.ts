import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

/**
 * BUG-324: Redirect http://localhost:3030 (direct port) to https://localhost
 *
 * When the app is served behind Caddy's TLS reverse proxy, NEXT_PUBLIC_API_URL
 * is set to https://localhost. If a user accesses the frontend directly at
 * http://localhost:3030, the browser sends API requests to https://localhost
 * from an HTTP origin, triggering CORS failures and mixed-content blocks.
 *
 * This middleware detects that scenario and issues a 301 redirect to the
 * canonical HTTPS origin so auth and API calls work correctly.
 *
 * Detection logic:
 *   - If the request comes in over HTTP (x-forwarded-proto != "https" AND the
 *     URL scheme is http), AND the host has a port that looks like a direct
 *     Next.js port (3030, 3000, 3001), we redirect to https://localhost.
 *   - Requests already coming through Caddy (https://localhost) are untouched.
 */
export function middleware(request: NextRequest) {
  const { nextUrl } = request

  // Only act on HTTP (non-HTTPS) requests
  const proto = request.headers.get('x-forwarded-proto') || nextUrl.protocol
  const isHttps = proto === 'https' || proto === 'https:'

  if (!isHttps) {
    const host = request.headers.get('host') || nextUrl.host

    // Skip redirect for Docker/internal health checks from the numeric loopback
    // address. Docker health check uses wget to http://127.0.0.1:3030 — we
    // must not redirect those or the container will be marked unhealthy.
    // NOTE: 'localhost:3030' browser access IS redirected (see below).
    if (host.startsWith('127.0.0.1')) {
      return NextResponse.next()
    }

    // BUG-348 FIX: Only redirect localhost direct-port access to HTTPS.
    // Remote HTTP installs (e.g. http://10.x.x.x:3030) must be preserved
    // so users without a TLS proxy can still access the app.
    const directPortPattern = /:(3030|3000|3001)$/
    if (directPortPattern.test(host) && host.startsWith('localhost')) {
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
