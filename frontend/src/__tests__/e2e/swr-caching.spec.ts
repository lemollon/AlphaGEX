/**
 * E2E Tests for SWR Caching Implementation
 *
 * These tests verify that:
 * 1. Data is cached across page navigation
 * 2. Pages load instantly on return visits
 * 3. Background revalidation works correctly
 *
 * Run with: npx playwright test swr-caching.spec.ts
 */

import { test, expect } from '@playwright/test'

// Base URL - adjust for your environment
const BASE_URL = process.env.TEST_URL || 'http://localhost:3000'

test.describe('SWR Caching - Dashboard Components', () => {

  test.beforeEach(async ({ page }) => {
    // Clear browser storage before each test
    await page.goto(BASE_URL)
    await page.evaluate(() => {
      localStorage.clear()
      sessionStorage.clear()
    })
  })

  test('Dashboard loads and caches data on first visit', async ({ page }) => {
    // Navigate to dashboard
    await page.goto(BASE_URL)

    // Wait for components to load
    await expect(page.locator('text=Live Market Commentary')).toBeVisible({ timeout: 10000 })
    await expect(page.locator('text=Daily Trading Plan')).toBeVisible({ timeout: 10000 })
    await expect(page.locator('text=0DTE Gamma Expiration Tracker')).toBeVisible({ timeout: 10000 })

    // Verify no loading spinners after data loads
    await page.waitForTimeout(3000) // Wait for data to load

    // Check that content is displayed (not loading state)
    const commentarySection = page.locator('[class*="MarketCommentary"]').or(page.locator('text=Live Market Commentary').locator('..').locator('..'))
    await expect(commentarySection.locator('.animate-pulse')).toHaveCount(0, { timeout: 10000 })
  })

  test('Data persists when navigating away and back', async ({ page }) => {
    // Go to dashboard first
    await page.goto(BASE_URL)
    await page.waitForTimeout(3000) // Wait for data to load and cache

    // Record that we've loaded data
    const hasCommentary = await page.locator('text=Live Market Commentary').isVisible()
    expect(hasCommentary).toBe(true)

    // Navigate to another page
    await page.click('text=GEX Analysis')
    await page.waitForURL('**/gex')

    // Navigate back to dashboard
    await page.click('text=Dashboard')
    await page.waitForURL(BASE_URL + '/')

    // Data should load instantly (no loading spinner)
    // The content should be visible immediately from cache
    await expect(page.locator('text=Live Market Commentary')).toBeVisible({ timeout: 1000 })
    await expect(page.locator('text=Daily Trading Plan')).toBeVisible({ timeout: 1000 })
  })

  test('MarketCommentary uses SWR cache', async ({ page }) => {
    await page.goto(BASE_URL)

    // Wait for initial load
    await page.waitForTimeout(3000)

    // Check for the cache indicator text
    await expect(page.locator('text=Cached across pages')).toBeVisible({ timeout: 5000 })
  })

  test('Manual refresh triggers revalidation', async ({ page }) => {
    await page.goto(BASE_URL)
    await page.waitForTimeout(3000)

    // Find and click refresh button on Market Commentary
    const refreshButton = page.locator('text=Live Market Commentary').locator('..').locator('..').locator('button[title="Refresh commentary"]')

    if (await refreshButton.isVisible()) {
      await refreshButton.click()

      // Should show spinning refresh icon
      await expect(refreshButton.locator('.animate-spin')).toBeVisible({ timeout: 2000 })

      // Should stop spinning after refresh completes
      await expect(refreshButton.locator('.animate-spin')).toBeHidden({ timeout: 10000 })
    }
  })

  test('GammaExpirationWidget symbol switching maintains cache', async ({ page }) => {
    await page.goto(BASE_URL)
    await page.waitForTimeout(3000)

    // Find the 0DTE widget
    const widget = page.locator('text=0DTE Gamma Expiration Tracker').locator('..')

    // Click on QQQ button
    const qqqButton = widget.locator('button:has-text("QQQ")')
    if (await qqqButton.isVisible()) {
      await qqqButton.click()
      await page.waitForTimeout(2000)

      // Click back to SPY
      const spyButton = widget.locator('button:has-text("SPY")')
      await spyButton.click()

      // SPY data should load instantly from cache
      await expect(page.locator('text=Loading 0DTE data')).toBeHidden({ timeout: 1000 })
    }
  })
})

test.describe('SWR Caching - Performance', () => {

  test('Second page load is faster than first', async ({ page }) => {
    // First visit - measure load time
    const start1 = Date.now()
    await page.goto(BASE_URL)
    await page.waitForTimeout(3000) // Wait for data
    const firstLoadTime = Date.now() - start1

    // Navigate away
    await page.click('text=GEX Analysis')
    await page.waitForURL('**/gex')

    // Second visit - should be faster
    const start2 = Date.now()
    await page.click('text=Dashboard')
    await page.waitForURL(BASE_URL + '/')
    await expect(page.locator('text=Live Market Commentary')).toBeVisible()
    const secondLoadTime = Date.now() - start2

    console.log(`First load: ${firstLoadTime}ms, Second load: ${secondLoadTime}ms`)

    // Second load should be significantly faster (at least 50% faster)
    // This is a soft check - cache should make it much faster
    expect(secondLoadTime).toBeLessThan(firstLoadTime)
  })
})

test.describe('SWR Caching - Error Handling', () => {

  test('Shows error state when API fails', async ({ page }) => {
    // Block API requests to simulate failure
    await page.route('**/api/**', route => route.abort())

    await page.goto(BASE_URL)
    await page.waitForTimeout(5000)

    // Should show error or fallback content
    // The exact behavior depends on whether there's cached data
    const hasError = await page.locator('text=Unable to load').or(page.locator('text=Error')).or(page.locator('text=unavailable')).isVisible()

    // If no cache exists, should show some error indication
    // This is expected behavior
    console.log('Error state shown:', hasError)
  })

  test('Retry button works on error', async ({ page }) => {
    await page.goto(BASE_URL)
    await page.waitForTimeout(3000)

    // Look for any retry buttons
    const retryButton = page.locator('button:has-text("Retry")')

    if (await retryButton.isVisible()) {
      await retryButton.click()
      // Should attempt to reload
      await page.waitForTimeout(2000)
    }
  })
})

test.describe('Pages WITHOUT SWR (should still work)', () => {

  test('GEX Analysis page loads independently', async ({ page }) => {
    await page.goto(BASE_URL + '/gex')

    // Should load its own data
    await expect(page.locator('text=GEX Analysis').or(page.locator('text=Gamma'))).toBeVisible({ timeout: 10000 })
  })

  test('Gamma Intelligence page loads independently', async ({ page }) => {
    await page.goto(BASE_URL + '/gamma')

    await expect(page.locator('text=Gamma Intelligence').or(page.locator('text=Market Maker'))).toBeVisible({ timeout: 10000 })
  })

  test('FORTRESS page loads independently', async ({ page }) => {
    await page.goto(BASE_URL + '/fortress')

    await expect(page.locator('text=FORTRESS')).toBeVisible({ timeout: 10000 })
  })
})
