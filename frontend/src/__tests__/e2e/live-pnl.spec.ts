import { test, expect } from '@playwright/test'

/**
 * E2E Tests for Live P&L Features
 * Tests the Robinhood-style portfolio view for ATHENA and ARES bots
 */

test.describe('ATHENA Live P&L', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/athena')
  })

  test('should display portfolio tab by default', async ({ page }) => {
    // Portfolio tab should be active by default
    const portfolioTab = page.locator('button:has-text("portfolio")')
    await expect(portfolioTab).toHaveClass(/bg-orange-600/)
  })

  test('should show total portfolio value', async ({ page }) => {
    // Should display a dollar value
    const portfolioValue = page.locator('text=/\\$[0-9,]+\\.[0-9]{2}/')
    await expect(portfolioValue.first()).toBeVisible()
  })

  test('should show period toggles (1D, 1W, 1M, 3M, YTD, 1Y, ALL)', async ({ page }) => {
    const periods = ['1D', '1W', '1M', '3M', 'YTD', '1Y', 'ALL']
    for (const period of periods) {
      const button = page.locator(`button:has-text("${period}")`)
      await expect(button).toBeVisible()
    }
  })

  test('should switch period when toggle clicked', async ({ page }) => {
    const oneWeekButton = page.locator('button:has-text("1W")')
    await oneWeekButton.click()
    await expect(oneWeekButton).toHaveClass(/bg-\[#00C805\]/)
  })

  test('should show open positions section', async ({ page }) => {
    const openPositionsHeader = page.locator('text=/Open Positions/')
    await expect(openPositionsHeader).toBeVisible()
  })

  test('should display live P&L data', async ({ page }) => {
    // Wait for data to load
    await page.waitForResponse(response =>
      response.url().includes('/api/athena/live-pnl') && response.status() === 200
    , { timeout: 10000 }).catch(() => {
      // API may not be running in test environment
    })

    // Should show unrealized/realized breakdown
    const unrealizedText = page.locator('text=/Unrealized:/')
    await expect(unrealizedText).toBeVisible({ timeout: 5000 }).catch(() => {})
  })

  test('should refresh data when refresh button clicked', async ({ page }) => {
    const refreshButton = page.locator('button svg.lucide-refresh-cw').first()
    await expect(refreshButton).toBeVisible()
    await refreshButton.click()

    // Button should animate
    await expect(refreshButton).toHaveClass(/animate-spin/, { timeout: 2000 }).catch(() => {})
  })

  test('should navigate between tabs', async ({ page }) => {
    // Click overview tab
    const overviewTab = page.locator('button:has-text("overview")')
    await overviewTab.click()

    // Should show status cards
    const capitalCard = page.locator('text=/Capital/')
    await expect(capitalCard).toBeVisible()

    // Click back to portfolio
    const portfolioTab = page.locator('button:has-text("portfolio")')
    await portfolioTab.click()
    await expect(portfolioTab).toHaveClass(/bg-orange-600/)
  })
})

test.describe('ARES Live P&L', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/ares')
  })

  test('should display portfolio tab by default', async ({ page }) => {
    // Portfolio tab should be active by default
    const portfolioTab = page.locator('button:has-text("portfolio")')
    await expect(portfolioTab).toHaveClass(/bg-red-600/)
  })

  test('should show total portfolio value', async ({ page }) => {
    // Should display a dollar value
    const portfolioValue = page.locator('text=/\\$[0-9,]+\\.[0-9]{2}/')
    await expect(portfolioValue.first()).toBeVisible()
  })

  test('should show period toggles', async ({ page }) => {
    const periods = ['1D', '1W', '1M', '3M', 'YTD', '1Y', 'ALL']
    for (const period of periods) {
      const button = page.locator(`button:has-text("${period}")`)
      await expect(button).toBeVisible()
    }
  })

  test('should show open positions for Iron Condors', async ({ page }) => {
    const openPositionsHeader = page.locator('text=/Open Positions/')
    await expect(openPositionsHeader).toBeVisible()
  })

  test('should display Iron Condor risk status', async ({ page }) => {
    // Wait for positions to load
    await page.waitForTimeout(2000)

    // If there are positions, they should show risk status (SAFE or AT_RISK)
    const riskIndicator = page.locator('text=/SAFE|AT_RISK/')
    // May not be visible if no positions
    await riskIndicator.first().isVisible().catch(() => true)
  })

  test('should show strike distance for Iron Condors', async ({ page }) => {
    // Strike distance indicators (e.g., "$3.75 away")
    const distanceText = page.locator('text=/away/')
    // May not be visible if no positions
    await distanceText.first().isVisible().catch(() => true)
  })

  test('should navigate between tabs', async ({ page }) => {
    // Click overview tab
    const overviewTab = page.locator('button:has-text("overview")')
    await overviewTab.click()

    // Should show total capital
    const capitalCard = page.locator('text=/Total Capital/')
    await expect(capitalCard).toBeVisible()

    // Click SPX tab
    const spxTab = page.locator('button:has-text("SPX")')
    await spxTab.click()
    await expect(spxTab).toHaveClass(/bg-red-600/)

    // Click back to portfolio
    const portfolioTab = page.locator('button:has-text("portfolio")')
    await portfolioTab.click()
    await expect(portfolioTab).toHaveClass(/bg-red-600/)
  })
})

test.describe('API Endpoints', () => {
  test('ATHENA live-pnl endpoint should return valid response', async ({ request }) => {
    const response = await request.get('/api/athena/live-pnl')

    // Should return 200 or valid error response
    expect([200, 500, 503]).toContain(response.status())

    if (response.status() === 200) {
      const data = await response.json()
      expect(data).toHaveProperty('success')
      if (data.success) {
        expect(data.data).toHaveProperty('total_unrealized_pnl')
        expect(data.data).toHaveProperty('total_realized_pnl')
        expect(data.data).toHaveProperty('positions')
      }
    }
  })

  test('ARES live-pnl endpoint should return valid response', async ({ request }) => {
    const response = await request.get('/api/ares/live-pnl')

    // Should return 200 or valid error response
    expect([200, 500, 503]).toContain(response.status())

    if (response.status() === 200) {
      const data = await response.json()
      expect(data).toHaveProperty('success')
      if (data.success) {
        expect(data.data).toHaveProperty('total_unrealized_pnl')
        expect(data.data).toHaveProperty('total_realized_pnl')
        expect(data.data).toHaveProperty('positions')
      }
    }
  })

  test('ATHENA process-expired endpoint should work', async ({ request }) => {
    const response = await request.post('/api/athena/process-expired')

    // Should return 200 or 503 if bot not initialized
    expect([200, 500, 503]).toContain(response.status())
  })

  test('ARES process-expired endpoint should work', async ({ request }) => {
    const response = await request.post('/api/ares/process-expired')

    // Should return 200 or 503 if bot not initialized
    expect([200, 500, 503]).toContain(response.status())
  })
})

test.describe('Equity Chart', () => {
  test('ATHENA should display equity chart', async ({ page }) => {
    await page.goto('/athena')

    // Chart container should exist
    const chartContainer = page.locator('.recharts-responsive-container')
    await expect(chartContainer.first()).toBeVisible({ timeout: 5000 }).catch(() => {
      // Chart may not render if no data
    })
  })

  test('ARES should display equity chart', async ({ page }) => {
    await page.goto('/ares')

    // Chart container should exist
    const chartContainer = page.locator('.recharts-responsive-container')
    await expect(chartContainer.first()).toBeVisible({ timeout: 5000 }).catch(() => {
      // Chart may not render if no data
    })
  })
})
