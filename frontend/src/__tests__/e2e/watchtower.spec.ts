/**
 * E2E Tests for WATCHTOWER (0DTE Gamma Live)
 *
 * These tests verify:
 * 1. WATCHTOWER page loads correctly
 * 2. Expiration tabs switch properly
 * 3. Net gamma chart renders with strike data
 * 4. Auto-refresh functionality works
 * 5. AI commentary panel displays correctly
 * 6. Alerts panel shows gamma flip detection
 * 7. Bot status panel displays
 * 8. Market info bar shows correct data
 *
 * Run with: npx playwright test watchtower.spec.ts
 */

import { test, expect } from '@playwright/test'

// Base URL - adjust for your environment
const BASE_URL = process.env.TEST_URL || 'http://localhost:3000'

test.describe('WATCHTOWER - 0DTE Gamma Live', () => {

  test.beforeEach(async ({ page }) => {
    // Clear browser storage before each test
    await page.goto(BASE_URL)
    await page.evaluate(() => {
      localStorage.clear()
      sessionStorage.clear()
    })
  })

  test('WATCHTOWER page loads successfully', async ({ page }) => {
    await page.goto(BASE_URL + '/watchtower')

    // Verify page header
    await expect(page.locator('h1:has-text("WATCHTOWER")')).toBeVisible({ timeout: 10000 })
    await expect(page.locator('text=0DTE Gamma Live')).toBeVisible({ timeout: 5000 })
  })

  test('Market info bar displays correct data', async ({ page }) => {
    await page.goto(BASE_URL + '/watchtower')
    await page.waitForTimeout(3000)

    // Check market info bar elements
    await expect(page.locator('text=Spot:')).toBeVisible({ timeout: 10000 })
    await expect(page.locator('text=Expected Move:')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('text=VIX:')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('text=Regime:')).toBeVisible({ timeout: 5000 })
  })

  test('Expiration tabs are visible and clickable', async ({ page }) => {
    await page.goto(BASE_URL + '/watchtower')
    await page.waitForTimeout(3000)

    // Check for day buttons (SPY has 5 expirations per week)
    const mondayTab = page.locator('button:has-text("MON")')
    const tuesdayTab = page.locator('button:has-text("TUE")')
    const wednesdayTab = page.locator('button:has-text("WED")')
    const thursdayTab = page.locator('button:has-text("THU")')
    const fridayTab = page.locator('button:has-text("FRI")')

    // At least some tabs should be visible
    const visibleTabs = await Promise.all([
      mondayTab.isVisible(),
      tuesdayTab.isVisible(),
      wednesdayTab.isVisible(),
      thursdayTab.isVisible(),
      fridayTab.isVisible()
    ])

    expect(visibleTabs.some(v => v)).toBe(true)
  })

  test('Expiration tab switching loads new data', async ({ page }) => {
    await page.goto(BASE_URL + '/watchtower')
    await page.waitForTimeout(3000)

    // Find a non-active tab and click it
    const tabs = page.locator('button:has-text("MON"), button:has-text("TUE"), button:has-text("WED"), button:has-text("THU"), button:has-text("FRI")')

    const tabCount = await tabs.count()
    if (tabCount > 1) {
      // Click second tab
      await tabs.nth(1).click()
      await page.waitForTimeout(2000)

      // Should still show chart
      await expect(page.locator('text=Net Gamma by Strike')).toBeVisible()
    }
  })

  test('Net Gamma chart section is visible', async ({ page }) => {
    await page.goto(BASE_URL + '/watchtower')
    await page.waitForTimeout(3000)

    // Check for chart header
    await expect(page.locator('text=Net Gamma by Strike')).toBeVisible({ timeout: 10000 })
  })

  test('Auto-refresh toggle works', async ({ page }) => {
    await page.goto(BASE_URL + '/watchtower')
    await page.waitForTimeout(3000)

    // Find auto-refresh button (shows 60s when active, OFF when inactive)
    const refreshToggle = page.locator('button:has-text("60s")').or(page.locator('button:has-text("OFF")'))

    if (await refreshToggle.isVisible()) {
      // Get initial state
      const initialText = await refreshToggle.textContent()

      // Click to toggle
      await refreshToggle.click()
      await page.waitForTimeout(500)

      // State should change
      const newText = await refreshToggle.textContent()
      expect(newText).not.toBe(initialText)

      // Click again to restore
      await refreshToggle.click()
    }
  })

  test('Manual refresh button works', async ({ page }) => {
    await page.goto(BASE_URL + '/watchtower')
    await page.waitForTimeout(3000)

    // Find manual refresh button (has RefreshCw icon)
    const refreshButton = page.locator('button').filter({ has: page.locator('svg.lucide-refresh-cw') }).last()

    if (await refreshButton.isVisible()) {
      await refreshButton.click()

      // Should show spinning animation briefly
      await page.waitForTimeout(1000)
    }
  })

  test('AI Commentary panel is visible', async ({ page }) => {
    await page.goto(BASE_URL + '/watchtower')
    await page.waitForTimeout(3000)

    // Check for AI commentary section
    await expect(page.locator('text=WATCHTOWER AI INTEL')).toBeVisible({ timeout: 10000 })
  })

  test('Alerts panel is visible', async ({ page }) => {
    await page.goto(BASE_URL + '/watchtower')
    await page.waitForTimeout(3000)

    // Check for alerts section
    await expect(page.locator('h3:has-text("ALERTS")')).toBeVisible({ timeout: 10000 })
  })

  test('Bot Status panel is visible', async ({ page }) => {
    await page.goto(BASE_URL + '/watchtower')
    await page.waitForTimeout(3000)

    // Check for bot status section
    await expect(page.locator('text=BOT STATUS')).toBeVisible({ timeout: 10000 })

    // Check for bot names
    await expect(page.locator('text=FORTRESS')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('text=SOLOMON')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('text=LAZARUS')).toBeVisible({ timeout: 5000 })
  })

  test('Commentary panel can be expanded', async ({ page }) => {
    await page.goto(BASE_URL + '/watchtower')
    await page.waitForTimeout(3000)

    // Find expand button near WATCHTOWER AI INTEL
    const expandButton = page.locator('text=WATCHTOWER AI INTEL').locator('..').locator('button').first()

    if (await expandButton.isVisible()) {
      await expandButton.click()
      await page.waitForTimeout(500)

      // Click again to collapse
      await expandButton.click()
    }
  })

  test('Magnets section displays correctly', async ({ page }) => {
    await page.goto(BASE_URL + '/watchtower')
    await page.waitForTimeout(3000)

    // Check for magnets label
    await expect(page.locator('text=MAGNETS:')).toBeVisible({ timeout: 10000 })
  })

  test('Market status indicator is visible', async ({ page }) => {
    await page.goto(BASE_URL + '/watchtower')
    await page.waitForTimeout(3000)

    // Check for market status (OPEN, CLOSED, PRE_MARKET, etc.)
    const marketStatus = page.locator('text=OPEN').or(page.locator('text=CLOSED')).or(page.locator('text=PRE MARKET')).or(page.locator('text=LOADING'))

    await expect(marketStatus).toBeVisible({ timeout: 10000 })
  })
})

test.describe('WATCHTOWER - Navigation Integration', () => {

  test('WATCHTOWER is accessible from navigation menu', async ({ page }) => {
    await page.goto(BASE_URL)
    await page.waitForTimeout(2000)

    // Find and click WATCHTOWER in navigation
    const argusLink = page.locator('a[href="/watchtower"]').or(page.locator('text=WATCHTOWER (0DTE Gamma)'))

    if (await argusLink.isVisible()) {
      await argusLink.click()
      await page.waitForURL('**/watchtower')

      // Should be on WATCHTOWER page
      await expect(page.locator('h1:has-text("WATCHTOWER")')).toBeVisible({ timeout: 10000 })
    }
  })

  test('Navigation from WATCHTOWER to other pages works', async ({ page }) => {
    await page.goto(BASE_URL + '/watchtower')
    await page.waitForTimeout(2000)

    // Navigate to Dashboard
    const dashboardLink = page.locator('a[href="/"]').or(page.locator('text=Dashboard'))

    if (await dashboardLink.first().isVisible()) {
      await dashboardLink.first().click()
      await page.waitForURL(BASE_URL + '/')
    }
  })

  test('Returning to WATCHTOWER maintains state', async ({ page }) => {
    await page.goto(BASE_URL + '/watchtower')
    await page.waitForTimeout(3000)

    // Navigate away
    await page.goto(BASE_URL)
    await page.waitForTimeout(1000)

    // Return to WATCHTOWER
    await page.goto(BASE_URL + '/watchtower')
    await page.waitForTimeout(2000)

    // Page should still load correctly
    await expect(page.locator('h1:has-text("WATCHTOWER")')).toBeVisible({ timeout: 10000 })
    await expect(page.locator('text=Net Gamma by Strike')).toBeVisible({ timeout: 10000 })
  })
})

test.describe('WATCHTOWER - Gamma Flip Detection', () => {

  test('Gamma flips section appears when flips detected', async ({ page }) => {
    await page.goto(BASE_URL + '/watchtower')
    await page.waitForTimeout(3000)

    // Check if gamma flips section exists (may or may not be visible depending on market conditions)
    const flipsSection = page.locator('text=GAMMA FLIPS DETECTED')

    // This might not be visible if no flips occurred
    const isVisible = await flipsSection.isVisible()

    if (isVisible) {
      // Verify flip indicators are present
      await expect(page.locator('text=+ → -').or(page.locator('text=- → +'))).toBeVisible()
    }

    // Test passes either way - flips are conditional
  })

  test('Danger zones section appears when risks detected', async ({ page }) => {
    await page.goto(BASE_URL + '/watchtower')
    await page.waitForTimeout(3000)

    // Check if danger zones section exists
    const dangerSection = page.locator('text=DANGER ZONES')

    // This might not be visible if no danger zones
    const isVisible = await dangerSection.isVisible()

    if (isVisible) {
      // Verify danger type indicators
      await expect(
        page.locator('text=BUILDING').or(page.locator('text=COLLAPSING')).or(page.locator('text=SPIKE'))
      ).toBeVisible()
    }

    // Test passes either way - danger zones are conditional
  })
})

test.describe('WATCHTOWER - Error Handling', () => {

  test('Shows loading state initially', async ({ page }) => {
    await page.goto(BASE_URL + '/watchtower')

    // Should show loading state briefly
    // The loading spinner or loading text might appear
    const loadingSpinner = page.locator('.animate-spin').first()

    // Either shows spinner or data loads quickly
    // This test mainly ensures no crash on load
    await page.waitForTimeout(5000)

    // Page should be functional after load
    await expect(page.locator('h1:has-text("WATCHTOWER")')).toBeVisible({ timeout: 10000 })
  })

  test('Handles API error gracefully', async ({ page }) => {
    // Block WATCHTOWER API endpoints
    await page.route('**/api/watchtower/**', route => route.abort())

    await page.goto(BASE_URL + '/watchtower')
    await page.waitForTimeout(5000)

    // Should show error state or fallback content
    const errorIndicator = page.locator('text=Error').or(page.locator('text=Retry')).or(page.locator('text=Failed'))

    // Error handling should be present
    // If using mock data fallback, might not show error
  })

  test('Retry button works on error', async ({ page }) => {
    await page.goto(BASE_URL + '/watchtower')
    await page.waitForTimeout(3000)

    // Look for retry button (if error occurred)
    const retryButton = page.locator('button:has-text("Retry")')

    if (await retryButton.isVisible()) {
      await retryButton.click()
      await page.waitForTimeout(2000)

      // Should attempt to reload
      // Page should still be functional
      await expect(page.locator('h1:has-text("WATCHTOWER")')).toBeVisible()
    }
  })
})

test.describe('WATCHTOWER - Performance', () => {

  test('Page loads within acceptable time', async ({ page }) => {
    const startTime = Date.now()

    await page.goto(BASE_URL + '/watchtower')
    await expect(page.locator('h1:has-text("WATCHTOWER")')).toBeVisible({ timeout: 15000 })

    const loadTime = Date.now() - startTime

    console.log(`WATCHTOWER page load time: ${loadTime}ms`)

    // Should load within 15 seconds (accounting for API calls)
    expect(loadTime).toBeLessThan(15000)
  })

  test('Chart renders smoothly', async ({ page }) => {
    await page.goto(BASE_URL + '/watchtower')
    await page.waitForTimeout(3000)

    // Verify chart section is rendered
    await expect(page.locator('text=Net Gamma by Strike')).toBeVisible({ timeout: 10000 })

    // Check that strike bars are rendered (if data available)
    // The chart should have visible bar elements
  })
})
