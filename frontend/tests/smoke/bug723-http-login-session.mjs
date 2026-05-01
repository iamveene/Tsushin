import { chromium } from 'playwright'

const baseURL = (
  process.env.TSUSHIN_SMOKE_BASE_URL ||
  process.env.PLAYWRIGHT_BASE_URL ||
  'http://localhost:3030'
).replace(/\/$/, '')

const email = process.env.TSUSHIN_SMOKE_EMAIL
const password = process.env.TSUSHIN_SMOKE_PASSWORD

if (!email || !password) {
  console.error(
    'Missing TSUSHIN_SMOKE_EMAIL or TSUSHIN_SMOKE_PASSWORD. ' +
      'Example: TSUSHIN_SMOKE_BASE_URL=http://localhost:3030 ' +
      'TSUSHIN_SMOKE_EMAIL=admin@example.com TSUSHIN_SMOKE_PASSWORD=... ' +
      'node frontend/tests/smoke/bug723-http-login-session.mjs'
  )
  process.exit(2)
}

const browser = await chromium.launch()
const page = await browser.newPage()

let logoutCompleted = false
let sawLoginRequest = false
let loginSubmittedBeforeLogoutCompleted = false

page.on('request', (request) => {
  const url = new URL(request.url())
  if (request.method() === 'POST' && url.pathname === '/api/auth/login') {
    sawLoginRequest = true
    if (!logoutCompleted) {
      loginSubmittedBeforeLogoutCompleted = true
    }
  }
})

await page.route('**/api/auth/logout', async (route) => {
  await new Promise((resolve) => setTimeout(resolve, 1500))
  const response = await route.fetch()
  logoutCompleted = true
  await route.fulfill({ response })
})

try {
  await page.goto(`${baseURL}/auth/login?force=1&reason=session-recovery`, {
    waitUntil: 'domcontentloaded',
  })

  await page.getByLabel('Email address').fill(email)
  await page.getByLabel('Password').fill(password)

  await page.getByRole('button', { name: /^sign in$/i }).click()

  if (loginSubmittedBeforeLogoutCompleted) {
    throw new Error('BUG-723 regression: login was submitted before recovery logout completed')
  }

  await page.waitForURL((url) => !url.pathname.startsWith('/auth'), {
    timeout: 15000,
  })

  if (loginSubmittedBeforeLogoutCompleted) {
    throw new Error('BUG-723 regression: login was submitted before recovery logout completed')
  }

  if (!sawLoginRequest) {
    throw new Error('BUG-723 regression: login request was not observed')
  }

  const me = await page.evaluate(async () => {
    const response = await fetch('/api/auth/me', { credentials: 'include' })
    return { status: response.status, body: await response.text() }
  })

  if (me.status !== 200) {
    throw new Error(`BUG-723 regression: /api/auth/me returned ${me.status}: ${me.body}`)
  }

  console.log(`BUG-723 HTTP login smoke passed at ${baseURL}`)
} finally {
  await browser.close()
}
