import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

async function stabilize(page: Page) {
  await page.addStyleTag({
    content: `
      *, *::before, *::after {
        animation-duration: 0s !important;
        animation-delay: 0s !important;
        transition-duration: 0s !important;
        transition-delay: 0s !important;
      }
    `,
  })
}

test.describe('v0.7.0 Phase 0 visual baselines', () => {
  test('login screen baseline', async ({ page }) => {
    await page.goto('/auth/login?force=1')
    await stabilize(page)
    await expect(page.getByPlaceholder('you@example.com')).toBeVisible()
    await expect(page.getByRole('button', { name: /^sign in$/i })).toBeVisible()
    await expect(page).toHaveScreenshot('auth-login.png', { fullPage: true })
  })

  test('hub communication baseline', async ({ page }) => {
    await page.goto('/hub?tab=communication')
    await stabilize(page)
    await expect(page.getByRole('heading', { name: 'Communication Channels' })).toBeVisible({ timeout: 15000 })
    await expect(page).toHaveScreenshot('hub-communication.png', { fullPage: true })
  })

  test('hub channel wizard baseline', async ({ page }) => {
    await page.goto('/hub?tab=communication')
    await stabilize(page)
    await expect(page.getByRole('heading', { name: 'Communication Channels' })).toBeVisible({ timeout: 15000 })
    await page.getByRole('button', { name: /add channel/i }).first().click()
    await expect(page.getByRole('heading', { name: 'Add Channel' })).toBeVisible()
    await expect(page).toHaveScreenshot('hub-channel-wizard.png', { fullPage: true })
  })

  test('hub provider wizard baseline', async ({ page }) => {
    await page.goto('/hub?tab=ai-providers')
    await stabilize(page)
    const newInstanceButton = page.getByRole('button', { name: /new instance/i }).first()
    await expect(newInstanceButton).toBeVisible({ timeout: 15000 })
    await newInstanceButton.click()
    await expect(page.getByRole('heading', { name: 'What are you adding?' })).toBeVisible()
    await expect(page).toHaveScreenshot('hub-provider-wizard.png', { fullPage: true })
  })
})
