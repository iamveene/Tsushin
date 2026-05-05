import { expect, test } from '@playwright/test'
import fs from 'fs'

const authStatePath = '../.private/qa/v0.7.0/playwright-auth.json'

test('authenticate tenant owner for visual baselines', async ({ page }) => {
  const email = process.env.TSUSHIN_E2E_EMAIL || 'test@example.com'
  const password = process.env.TSUSHIN_E2E_PASSWORD || 'test1234'

  fs.mkdirSync('../.private/qa/v0.7.0', { recursive: true })
  await page.goto('/auth/login?force=1')
  await page.getByPlaceholder('you@example.com').fill(email)
  await page.getByPlaceholder('••••••••').fill(password)
  await page.getByRole('button', { name: /^sign in$/i }).click()
  await page.waitForURL(url => !url.pathname.startsWith('/auth/login'), { timeout: 15000 })
  await expect(page.locator('body')).toBeVisible()
  await page.evaluate(() => {
    window.localStorage.setItem('tsushin_onboarding_completed', 'true')
  })
  await page.context().storageState({ path: authStatePath })
})
