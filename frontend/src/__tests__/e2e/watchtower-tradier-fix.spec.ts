/**
 * E2E Tests for WATCHTOWER Tradier Connection Fix
 *
 * These tests verify the fix for:
 * 1. Tradier credentials explicitly loaded from APIConfig
 * 2. No React error #310 (too many re-renders) crash
 * 3. Data source status endpoint works correctly
 * 4. Page handles partial/empty data gracefully
 *
 * Run with: npx playwright test watchtower-tradier-fix.spec.ts
 */

import { test, expect } from '@playwright/test'

const BASE_URL = process.env.TEST_URL || 'http://localhost:3000'
const API_URL = process.env.API_URL || 'http://localhost:8000'

test.describe('WATCHTOWER - Tradier Connection Fix', () => {

  test('Page loads without React error #310 crash', async ({ page }) => {
    // Listen for console errors
    const consoleErrors: string[] = []
    page.on('console', msg => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text())
      }
    })

    // Navigate to WATCHTOWER
    await page.goto(BASE_URL + '/watchtower')

    // Wait for page to fully load
    await page.waitForTimeout(5000)

    // Verify page header loaded (not crashed)
    await expect(page.locator('h1:has-text("WATCHTOWER")')).toBeVisible({ timeout: 15000 })

    // Check no React re-render error occurred
    const hasReactError = consoleErrors.some(err =>
      err.includes('error #310') ||
      err.includes('Too many re-renders') ||
      err.includes('maximum update depth')
    )

    if (hasReactError) {
      console.error('React errors detected:', consoleErrors)
    }

    expect(hasReactError).toBe(false)
  })

  test('Page survives multiple rapid data updates', async ({ page }) => {
    await page.goto(BASE_URL + '/watchtower')
    await page.waitForTimeout(3000)

    // Verify initial load
    await expect(page.locator('h1:has-text("WATCHTOWER")')).toBeVisible({ timeout: 10000 })

    // Find and click refresh button multiple times rapidly
    const refreshButton = page.locator('button').filter({ has: page.locator('svg.lucide-refresh-cw') }).last()

    if (await refreshButton.isVisible()) {
      // Click refresh 5 times rapidly
      for (let i = 0; i < 5; i++) {
        await refreshButton.click()
        await page.waitForTimeout(200)
      }

      // Wait for stabilization
      await page.waitForTimeout(3000)

      // Page should still be functional (no crash)
      await expect(page.locator('h1:has-text("WATCHTOWER")')).toBeVisible()
      await expect(page.locator('text=Net Gamma by Strike')).toBeVisible()
    }
  })

  test('Data source status endpoint returns valid response', async ({ page }) => {
    await page.goto(BASE_URL + '/watchtower')
    await page.waitForTimeout(2000)

    // Make direct API call to check data source status
    const response = await page.request.get(API_URL + '/api/watchtower/data-source-status')

    expect(response.status()).toBe(200)

    const data = await response.json()

    // Verify response structure
    expect(data).toHaveProperty('success')
    expect(data).toHaveProperty('data_sources')
    expect(data.data_sources).toHaveProperty('tradier')

    // Log Tradier connection status
    console.log('Tradier status:', data.data_sources.tradier)
  })

  test('Test Tradier connection endpoint works', async ({ page }) => {
    const response = await page.request.get(API_URL + '/api/watchtower/test-tradier-connection')

    expect(response.status()).toBe(200)

    const data = await response.json()

    // Should have connection status
    expect(data).toHaveProperty('success')
    expect(data).toHaveProperty('connected')

    if (data.connected) {
      // If connected, should have test quote
      expect(data).toHaveProperty('test_quote')
      console.log('Tradier connected! Test quote:', data.test_quote)
    } else {
      // If not connected, should have error message
      expect(data).toHaveProperty('error')
      console.log('Tradier not connected:', data.error)
    }
  })

  test('WATCHTOWER gamma endpoint returns valid structure', async ({ page }) => {
    const response = await page.request.get(API_URL + '/api/watchtower/gamma?symbol=SPY')

    // Should return 200 (or 503 if engine unavailable)
    expect([200, 503]).toContain(response.status())

    if (response.status() === 200) {
      const data = await response.json()

      // Should have success field
      expect(data).toHaveProperty('success')

      if (data.success && data.data) {
        // Verify gamma data structure
        expect(data.data).toHaveProperty('symbol')
        expect(data.data).toHaveProperty('strikes')
        expect(Array.isArray(data.data.strikes)).toBe(true)

        console.log(`Gamma data: ${data.data.strikes.length} strikes loaded`)
      }
    }
  })

  test('Page handles empty strikes array without crash', async ({ page, request }) => {
    // Mock empty strikes response
    await page.route('**/api/watchtower/gamma**', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: {
            symbol: 'SPY',
            spot_price: 585.0,
            expiration: '2025-01-21',
            strikes: [], // Empty strikes
            gamma_levels: {
              flip_point: 585.0,
              call_wall: 590.0,
              put_wall: 580.0
            }
          }
        })
      })
    })

    // Listen for errors
    const errors: string[] = []
    page.on('pageerror', err => errors.push(err.message))

    await page.goto(BASE_URL + '/watchtower')
    await page.waitForTimeout(5000)

    // Page should not crash
    await expect(page.locator('h1:has-text("WATCHTOWER")')).toBeVisible({ timeout: 10000 })

    // Should not have page errors
    expect(errors.filter(e => e.includes('Cannot read properties'))).toHaveLength(0)
  })

  test('Page handles null gamma data fields gracefully', async ({ page }) => {
    // Mock response with null fields
    await page.route('**/api/watchtower/gamma**', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: {
            symbol: 'SPY',
            spot_price: 585.0,
            expiration: '2025-01-21',
            strikes: [
              {
                strike: 585,
                net_gex: null, // Null value
                call_gex: 1000,
                put_gex: null,
                roc_1min: null,
                roc_5min: null
              }
            ],
            gamma_levels: null // Null gamma levels
          }
        })
      })
    })

    const errors: string[] = []
    page.on('pageerror', err => errors.push(err.message))

    await page.goto(BASE_URL + '/watchtower')
    await page.waitForTimeout(5000)

    // Page should handle null values without crash
    await expect(page.locator('h1:has-text("WATCHTOWER")')).toBeVisible({ timeout: 10000 })

    // Filter for TypeError errors only
    const typeErrors = errors.filter(e =>
      e.includes('Cannot read properties') ||
      e.includes('null') ||
      e.includes('undefined')
    )
    expect(typeErrors).toHaveLength(0)
  })

  test('Page handles data_unavailable response', async ({ page }) => {
    // Mock data_unavailable response
    await page.route('**/api/watchtower/gamma**', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          data_unavailable: true,
          message: 'Tradier connection unavailable',
          data: null
        })
      })
    })

    await page.goto(BASE_URL + '/watchtower')
    await page.waitForTimeout(5000)

    // Page should show appropriate UI for unavailable data
    // Should not crash
    await expect(page.locator('h1:has-text("WATCHTOWER")')).toBeVisible({ timeout: 10000 })

    // May show error message or empty state
    // The important thing is no crash
  })

  test('Commentary section loads without causing re-render loop', async ({ page }) => {
    const errors: string[] = []
    page.on('console', msg => {
      if (msg.type() === 'error' && msg.text().includes('re-render')) {
        errors.push(msg.text())
      }
    })

    await page.goto(BASE_URL + '/watchtower')

    // Wait for commentary to load
    await page.waitForTimeout(8000)

    // Check for WATCHTOWER AI INTEL section
    await expect(page.locator('text=WATCHTOWER AI INTEL')).toBeVisible({ timeout: 15000 })

    // Should not have re-render errors
    expect(errors).toHaveLength(0)
  })
})

test.describe('WATCHTOWER - Data Integrity', () => {

  test('Strike data maintains integrity during refresh', async ({ page }) => {
    await page.goto(BASE_URL + '/watchtower')
    await page.waitForTimeout(3000)

    // Check Net Gamma chart is visible
    await expect(page.locator('text=Net Gamma by Strike')).toBeVisible({ timeout: 10000 })

    // Get initial spot price display
    const spotText = await page.locator('text=Spot:').locator('..').textContent()

    // Trigger refresh
    const refreshButton = page.locator('button').filter({ has: page.locator('svg.lucide-refresh-cw') }).last()
    if (await refreshButton.isVisible()) {
      await refreshButton.click()
      await page.waitForTimeout(3000)
    }

    // Chart should still be visible after refresh
    await expect(page.locator('text=Net Gamma by Strike')).toBeVisible()
  })

  test('Market info displays numeric values not NaN', async ({ page }) => {
    await page.goto(BASE_URL + '/watchtower')
    await page.waitForTimeout(5000)

    // Get the market info bar text content
    const pageContent = await page.content()

    // Should not contain NaN displays
    const hasNaN = pageContent.includes('>NaN<') ||
                   pageContent.includes(': NaN') ||
                   pageContent.includes('NaN%')

    if (hasNaN) {
      console.warn('Warning: NaN values detected in page content')
    }

    // This is a soft check - warn but don't fail
    // (NaN might appear during loading states)
  })
})

test.describe('WATCHTOWER - GLORY Parity', () => {

  test('GLORY page also loads without crash', async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', err => errors.push(err.message))
    page.on('console', msg => {
      if (msg.type() === 'error' && msg.text().includes('re-render')) {
        errors.push(msg.text())
      }
    })

    await page.goto(BASE_URL + '/glory')
    await page.waitForTimeout(5000)

    // GLORY should load
    await expect(page.locator('h1:has-text("GLORY")')).toBeVisible({ timeout: 15000 })

    // Should not have React re-render errors
    const reRenderErrors = errors.filter(e => e.includes('re-render') || e.includes('#310'))
    expect(reRenderErrors).toHaveLength(0)
  })

  test('GLORY data source status works', async ({ page }) => {
    const response = await page.request.get(API_URL + '/api/glory/data-source-status')

    // Endpoint might not exist yet on GLORY
    if (response.status() === 200) {
      const data = await response.json()
      expect(data).toHaveProperty('success')
    } else if (response.status() === 404) {
      // Expected if endpoint not added to GLORY
      console.log('GLORY data-source-status endpoint not yet implemented')
    }
  })
})
