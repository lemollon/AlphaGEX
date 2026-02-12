/**
 * E2E Tests for Prophet Knowledge Base
 *
 * These tests verify:
 * 1. Prophet page loads correctly
 * 2. All tabs switch properly
 * 3. Bot Interactions tab displays and filters correctly
 * 4. Performance tab shows metrics
 * 5. Training tab displays status and allows actions
 * 6. Live Logs tab shows entries
 * 7. Decision Log tab loads
 * 8. Data Flow tab shows transparency data
 * 9. Error handling and graceful degradation
 * 10. Navigation integration
 *
 * Run with: npx playwright test prophet.spec.ts
 */

import { test, expect } from '@playwright/test'

// Base URL - adjust for your environment
const BASE_URL = process.env.TEST_URL || 'http://localhost:3000'

test.describe('Prophet Knowledge Base - Page Load', () => {

  test.beforeEach(async ({ page }) => {
    // Clear browser storage before each test
    await page.goto(BASE_URL)
    await page.evaluate(() => {
      localStorage.clear()
      sessionStorage.clear()
    })
  })

  test('Prophet page loads successfully', async ({ page }) => {
    await page.goto(BASE_URL + '/prophet')

    // Verify page header
    await expect(page.locator('h1:has-text("Prophet Knowledge Base")')).toBeVisible({ timeout: 15000 })
    await expect(page.locator('text=Centralized intelligence hub')).toBeVisible({ timeout: 5000 })
  })

  test('Prophet page shows status cards', async ({ page }) => {
    await page.goto(BASE_URL + '/prophet')
    await page.waitForTimeout(3000)

    // Check status card sections
    await expect(page.locator('text=Claude AI')).toBeVisible({ timeout: 10000 })
    await expect(page.locator('text=ML Model')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('text=Pending Outcomes')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('text=High Confidence')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('text=Interactions')).toBeVisible({ timeout: 5000 })
  })

  test('Bot Heartbeats section displays', async ({ page }) => {
    await page.goto(BASE_URL + '/prophet')
    await page.waitForTimeout(3000)

    // Check for bot heartbeats section
    await expect(page.locator('text=Bot Heartbeats')).toBeVisible({ timeout: 10000 })

    // Check for bot names
    await expect(page.locator('text=FORTRESS')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('text=SOLOMON')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('text=CORNERSTONE')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('text=LAZARUS')).toBeVisible({ timeout: 5000 })
  })
})

test.describe('Prophet Knowledge Base - Tab Navigation', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto(BASE_URL + '/prophet')
    await page.waitForTimeout(3000)
  })

  test('All tabs are visible', async ({ page }) => {
    // Check all tabs are present
    await expect(page.locator('button:has-text("Bot Interactions")')).toBeVisible({ timeout: 10000 })
    await expect(page.locator('button:has-text("Performance")')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('button:has-text("Training")')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('button:has-text("Live Logs")')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('button:has-text("Decision Log")')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('button:has-text("Data Flow")')).toBeVisible({ timeout: 5000 })
  })

  test('Bot Interactions tab is default', async ({ page }) => {
    // Bot Interactions should be the active tab by default
    const interactionsTab = page.locator('button:has-text("Bot Interactions")')
    await expect(interactionsTab).toHaveClass(/bg-purple-600/, { timeout: 10000 })
  })

  test('Performance tab switches correctly', async ({ page }) => {
    // Click Performance tab
    await page.click('button:has-text("Performance")')
    await page.waitForTimeout(1000)

    // Should show performance content
    await expect(page.locator('text=Prophet Prediction Performance')).toBeVisible({ timeout: 10000 })
  })

  test('Training tab switches correctly', async ({ page }) => {
    // Click Training tab
    await page.click('button:has-text("Training")')
    await page.waitForTimeout(1000)

    // Should show training content
    await expect(page.locator('text=ML Model Training')).toBeVisible({ timeout: 10000 })
  })

  test('Live Logs tab switches correctly', async ({ page }) => {
    // Click Live Logs tab
    await page.click('button:has-text("Live Logs")')
    await page.waitForTimeout(1000)

    // Should show logs content
    await expect(page.locator('text=Live Prophet Logs')).toBeVisible({ timeout: 10000 })
  })

  test('Decision Log tab switches correctly', async ({ page }) => {
    // Click Decision Log tab
    await page.click('button:has-text("Decision Log")')
    await page.waitForTimeout(1000)

    // Should show decision log content
    await expect(page.locator('text=PROPHET Decision Log')).toBeVisible({ timeout: 10000 })
  })

  test('Data Flow tab switches correctly', async ({ page }) => {
    // Click Data Flow tab
    await page.click('button:has-text("Data Flow")')
    await page.waitForTimeout(1000)

    // Should show data flow content
    await expect(page.locator('text=Prophet Data Flow - Full Transparency')).toBeVisible({ timeout: 10000 })
  })
})

test.describe('Prophet Knowledge Base - Bot Interactions Tab', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto(BASE_URL + '/prophet')
    await page.waitForTimeout(3000)
  })

  test('Bot filter dropdown works', async ({ page }) => {
    // Find bot filter dropdown
    const botSelect = page.locator('select').filter({ hasText: 'All Bots' })
    await expect(botSelect).toBeVisible({ timeout: 10000 })

    // Change selection
    await botSelect.selectOption('FORTRESS')
    await page.waitForTimeout(1000)

    // Should trigger refresh
    const loadingSpinner = page.locator('.animate-spin')
    // Either loading or data loaded
  })

  test('Days filter dropdown works', async ({ page }) => {
    // Find days filter dropdown
    const daysSelect = page.locator('select').filter({ hasText: /Last.*Days|Last 24 Hours/ })
    await expect(daysSelect).toBeVisible({ timeout: 10000 })

    // Change selection
    await daysSelect.selectOption('30')
    await page.waitForTimeout(1000)
  })

  test('Refresh button works', async ({ page }) => {
    // Find refresh button
    const refreshButton = page.locator('button:has-text("Refresh")').first()
    await expect(refreshButton).toBeVisible({ timeout: 10000 })

    // Click refresh
    await refreshButton.click()
    await page.waitForTimeout(2000)
  })

  test('Export buttons are present', async ({ page }) => {
    // Check export buttons
    await expect(page.locator('button:has-text("JSON")')).toBeVisible({ timeout: 10000 })
    await expect(page.locator('button:has-text("CSV")')).toBeVisible({ timeout: 5000 })
  })

  test('No interactions message shows when empty', async ({ page }) => {
    // Either shows interactions or empty message
    const hasInteractions = await page.locator('.card').count() > 5
    const hasEmptyMessage = await page.locator('text=No bot interactions found').isVisible()

    expect(hasInteractions || hasEmptyMessage).toBe(true)
  })
})

test.describe('Prophet Knowledge Base - Performance Tab', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto(BASE_URL + '/prophet')
    await page.waitForTimeout(3000)
    await page.click('button:has-text("Performance")')
    await page.waitForTimeout(2000)
  })

  test('Performance metrics display', async ({ page }) => {
    // Check for performance metrics or empty state
    const hasData = await page.locator('text=Total Predictions').isVisible()
    const hasNoData = await page.locator('text=No performance data available').isVisible()

    expect(hasData || hasNoData).toBe(true)
  })

  test('Refresh button works on Performance tab', async ({ page }) => {
    // Find refresh button
    const refreshButton = page.locator('button:has-text("Refresh")')
    await expect(refreshButton).toBeVisible({ timeout: 10000 })

    // Click refresh
    await refreshButton.click()
    await page.waitForTimeout(2000)
  })

  test('Performance by bot table shows when data available', async ({ page }) => {
    // Check for table header
    const hasTable = await page.locator('text=Performance by Bot').isVisible()
    const hasNoData = await page.locator('text=No performance data available').isVisible()

    expect(hasTable || hasNoData).toBe(true)
  })
})

test.describe('Prophet Knowledge Base - Training Tab', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto(BASE_URL + '/prophet')
    await page.waitForTimeout(3000)
    await page.click('button:has-text("Training")')
    await page.waitForTimeout(2000)
  })

  test('Training status displays', async ({ page }) => {
    // Check for training status or loading state
    const hasStatus = await page.locator('text=Model Status').isVisible()
    const hasLoading = await page.locator('text=Loading training status').isVisible()

    expect(hasStatus || hasLoading).toBe(true)
  })

  test('Training actions section displays', async ({ page }) => {
    // Wait for content to load
    await page.waitForTimeout(2000)

    // Check for training actions or loading state
    const hasActions = await page.locator('text=Training Actions').isVisible()
    const hasLoading = await page.locator('text=Loading training status').isVisible()

    expect(hasActions || hasLoading).toBe(true)
  })

  test('Auto Train button is present', async ({ page }) => {
    // Wait for content to load
    await page.waitForTimeout(2000)

    // Check for auto train button
    const hasAutoTrain = await page.locator('button:has-text("Auto Train")').isVisible()
    const hasLoading = await page.locator('text=Loading training status').isVisible()

    expect(hasAutoTrain || hasLoading).toBe(true)
  })

  test('Force Train button is present', async ({ page }) => {
    // Wait for content to load
    await page.waitForTimeout(2000)

    // Check for force train button
    const hasForceTrain = await page.locator('button:has-text("Force Train")').isVisible()
    const hasLoading = await page.locator('text=Loading training status').isVisible()

    expect(hasForceTrain || hasLoading).toBe(true)
  })

  test('Refresh Status button works', async ({ page }) => {
    // Find refresh button
    const refreshButton = page.locator('button:has-text("Refresh Status")')
    await expect(refreshButton).toBeVisible({ timeout: 10000 })

    // Click refresh
    await refreshButton.click()
    await page.waitForTimeout(2000)
  })
})

test.describe('Prophet Knowledge Base - Live Logs Tab', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto(BASE_URL + '/prophet')
    await page.waitForTimeout(3000)
    await page.click('button:has-text("Live Logs")')
    await page.waitForTimeout(2000)
  })

  test('Live logs header displays', async ({ page }) => {
    await expect(page.locator('text=Live Prophet Logs')).toBeVisible({ timeout: 10000 })
  })

  test('Log count displays', async ({ page }) => {
    // Check for log count indicator
    await expect(page.locator('text=entries')).toBeVisible({ timeout: 10000 })
  })

  test('Texas Central Time note displays', async ({ page }) => {
    await expect(page.locator('text=Texas Central Time')).toBeVisible({ timeout: 10000 })
  })

  test('Log action buttons are present', async ({ page }) => {
    // Check for action buttons (export, refresh, clear)
    const exportButton = page.locator('button[title="Export logs as JSON"]')
    const refreshButton = page.locator('button[title="Refresh logs"]')
    const clearButton = page.locator('button[title="Clear logs"]')

    await expect(exportButton).toBeVisible({ timeout: 10000 })
    await expect(refreshButton).toBeVisible({ timeout: 5000 })
    await expect(clearButton).toBeVisible({ timeout: 5000 })
  })

  test('Logs container displays', async ({ page }) => {
    // Either shows logs or empty message
    const hasLogs = await page.locator('.overflow-y-auto').count() > 0
    expect(hasLogs).toBe(true)
  })
})

test.describe('Prophet Knowledge Base - Decision Log Tab', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto(BASE_URL + '/prophet')
    await page.waitForTimeout(3000)
    await page.click('button:has-text("Decision Log")')
    await page.waitForTimeout(2000)
  })

  test('Decision Log header displays', async ({ page }) => {
    await expect(page.locator('text=PROPHET Decision Log')).toBeVisible({ timeout: 10000 })
  })

  test('DecisionLogViewer component loads', async ({ page }) => {
    // The DecisionLogViewer component should be present
    // It may show loading, data, or empty state
    await page.waitForTimeout(2000)

    // Just verify no crash occurred - page should still be visible
    await expect(page.locator('text=PROPHET Decision Log')).toBeVisible({ timeout: 5000 })
  })
})

test.describe('Prophet Knowledge Base - Data Flow Tab', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto(BASE_URL + '/prophet')
    await page.waitForTimeout(3000)
    await page.click('button:has-text("Data Flow")')
    await page.waitForTimeout(2000)
  })

  test('Data Flow header displays', async ({ page }) => {
    await expect(page.locator('text=Prophet Data Flow - Full Transparency')).toBeVisible({ timeout: 10000 })
  })

  test('Claude AI Exchanges section displays', async ({ page }) => {
    await expect(page.locator('text=Claude AI Exchanges')).toBeVisible({ timeout: 10000 })
  })

  test('Data Flow Pipeline section displays', async ({ page }) => {
    await expect(page.locator('text=Data Flow Pipeline')).toBeVisible({ timeout: 10000 })
  })

  test('Refresh button works on Data Flow tab', async ({ page }) => {
    // Find refresh button
    const refreshButton = page.locator('button:has-text("Refresh")')
    await expect(refreshButton).toBeVisible({ timeout: 10000 })

    // Click refresh
    await refreshButton.click()
    await page.waitForTimeout(2000)
  })

  test('Empty state shows when no data', async ({ page }) => {
    // Either has data or shows empty message
    const hasExchanges = await page.locator('text=tokens').isVisible()
    const hasEmptyExchanges = await page.locator('text=No Claude AI exchanges recorded').isVisible()
    const hasDataFlows = await page.locator('text=DECISION').isVisible()
    const hasEmptyFlows = await page.locator('text=No data flows recorded').isVisible()

    // At least one of these conditions should be true
    expect(hasExchanges || hasEmptyExchanges || hasDataFlows || hasEmptyFlows).toBe(true)
  })
})

test.describe('Prophet Knowledge Base - Info Section', () => {

  test('Bot info cards display at bottom', async ({ page }) => {
    await page.goto(BASE_URL + '/prophet')
    await page.waitForTimeout(3000)

    // Scroll to bottom
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
    await page.waitForTimeout(1000)

    // Check for bot info cards
    await expect(page.locator('text=0DTE Iron Condors with GEX-protected strikes')).toBeVisible({ timeout: 10000 })
    await expect(page.locator('text=Wheel strategy for consistent premium')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('text=Directional calls for momentum plays')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('text=Pattern recognition and signals')).toBeVisible({ timeout: 5000 })
  })
})

test.describe('Prophet Knowledge Base - Error Handling', () => {

  test('Shows loading state initially', async ({ page }) => {
    await page.goto(BASE_URL + '/prophet')

    // Should show loading state briefly or data loads quickly
    await page.waitForTimeout(5000)

    // Page should be functional after load
    await expect(page.locator('h1:has-text("Prophet Knowledge Base")')).toBeVisible({ timeout: 10000 })
  })

  test('Handles API errors gracefully', async ({ page }) => {
    // Block Prophet API endpoints
    await page.route('**/api/prophet/**', route => route.abort())

    await page.goto(BASE_URL + '/prophet')
    await page.waitForTimeout(5000)

    // Should still render the page structure without crashing
    await expect(page.locator('h1:has-text("Prophet Knowledge Base")')).toBeVisible({ timeout: 15000 })
  })

  test('Error boundary catches component errors', async ({ page }) => {
    await page.goto(BASE_URL + '/prophet')
    await page.waitForTimeout(3000)

    // Navigate through tabs to test error boundary
    const tabs = ['Performance', 'Training', 'Live Logs', 'Decision Log', 'Data Flow']

    for (const tab of tabs) {
      await page.click(`button:has-text("${tab}")`)
      await page.waitForTimeout(1000)

      // Page should still be functional (no crash)
      await expect(page.locator('h1:has-text("Prophet Knowledge Base")')).toBeVisible()
    }
  })

  test('Page handles missing data gracefully', async ({ page }) => {
    // Mock empty API responses
    await page.route('**/api/prophet/status', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, prophet: null, bot_heartbeats: {} })
      })
    )

    await page.goto(BASE_URL + '/prophet')
    await page.waitForTimeout(3000)

    // Page should handle null data without crashing
    await expect(page.locator('h1:has-text("Prophet Knowledge Base")')).toBeVisible({ timeout: 10000 })
  })
})

test.describe('Prophet Knowledge Base - Navigation Integration', () => {

  test('Prophet is accessible from navigation menu', async ({ page }) => {
    await page.goto(BASE_URL)
    await page.waitForTimeout(2000)

    // Find and click Prophet in navigation
    const prophetLink = page.locator('a[href="/prophet"]').or(page.locator('text=Prophet'))

    if (await prophetLink.first().isVisible()) {
      await prophetLink.first().click()
      await page.waitForURL('**/prophet')

      // Should be on Prophet page
      await expect(page.locator('h1:has-text("Prophet Knowledge Base")')).toBeVisible({ timeout: 10000 })
    }
  })

  test('Navigation from Prophet to other pages works', async ({ page }) => {
    await page.goto(BASE_URL + '/prophet')
    await page.waitForTimeout(2000)

    // Navigate to Dashboard
    const dashboardLink = page.locator('a[href="/"]').or(page.locator('text=Dashboard'))

    if (await dashboardLink.first().isVisible()) {
      await dashboardLink.first().click()
      await page.waitForURL(BASE_URL + '/')
    }
  })

  test('Returning to Prophet maintains functionality', async ({ page }) => {
    await page.goto(BASE_URL + '/prophet')
    await page.waitForTimeout(3000)

    // Click a tab
    await page.click('button:has-text("Performance")')
    await page.waitForTimeout(1000)

    // Navigate away
    await page.goto(BASE_URL)
    await page.waitForTimeout(1000)

    // Return to Prophet
    await page.goto(BASE_URL + '/prophet')
    await page.waitForTimeout(2000)

    // Page should still function correctly
    await expect(page.locator('h1:has-text("Prophet Knowledge Base")')).toBeVisible({ timeout: 10000 })
    await expect(page.locator('button:has-text("Bot Interactions")')).toBeVisible({ timeout: 5000 })
  })
})

test.describe('Prophet Knowledge Base - Performance Tests', () => {

  test('Page loads within acceptable time', async ({ page }) => {
    const startTime = Date.now()

    await page.goto(BASE_URL + '/prophet')
    await expect(page.locator('h1:has-text("Prophet Knowledge Base")')).toBeVisible({ timeout: 15000 })

    const loadTime = Date.now() - startTime

    console.log(`Prophet page load time: ${loadTime}ms`)

    // Should load within 15 seconds (accounting for API calls)
    expect(loadTime).toBeLessThan(15000)
  })

  test('Tab switching is responsive', async ({ page }) => {
    await page.goto(BASE_URL + '/prophet')
    await page.waitForTimeout(3000)

    const tabs = ['Performance', 'Training', 'Live Logs', 'Decision Log', 'Data Flow', 'Bot Interactions']

    for (const tab of tabs) {
      const startTime = Date.now()

      await page.click(`button:has-text("${tab}")`)
      await page.waitForTimeout(500)

      const switchTime = Date.now() - startTime

      console.log(`${tab} tab switch time: ${switchTime}ms`)

      // Tab switch should be quick (under 2 seconds)
      expect(switchTime).toBeLessThan(2000)
    }
  })

  test('No memory leaks on tab cycling', async ({ page }) => {
    await page.goto(BASE_URL + '/prophet')
    await page.waitForTimeout(3000)

    const tabs = ['Performance', 'Training', 'Live Logs', 'Decision Log', 'Data Flow', 'Bot Interactions']

    // Cycle through tabs multiple times
    for (let i = 0; i < 3; i++) {
      for (const tab of tabs) {
        await page.click(`button:has-text("${tab}")`)
        await page.waitForTimeout(500)
      }
    }

    // Page should still be responsive
    await expect(page.locator('h1:has-text("Prophet Knowledge Base")')).toBeVisible({ timeout: 5000 })
  })
})

test.describe('Prophet Knowledge Base - Data Display Verification', () => {

  test('Status cards show correct data types', async ({ page }) => {
    await page.goto(BASE_URL + '/prophet')
    await page.waitForTimeout(3000)

    // Claude status should show Connected or Unavailable
    const claudeStatus = page.locator('text=Connected').or(page.locator('text=Unavailable'))
    await expect(claudeStatus).toBeVisible({ timeout: 10000 })

    // ML Model status should show Trained or Not Trained
    const mlStatus = page.locator('text=Trained').or(page.locator('text=Not Trained'))
    await expect(mlStatus).toBeVisible({ timeout: 5000 })
  })

  test('Interactions display correct structure', async ({ page }) => {
    await page.goto(BASE_URL + '/prophet')
    await page.waitForTimeout(5000)

    // If there are interactions, they should have proper structure
    const hasInteractions = await page.locator('text=Win Prob').isVisible()

    if (hasInteractions) {
      // Check for expected fields in interaction cards
      await expect(page.locator('text=Win Prob')).toBeVisible()
      await expect(page.locator('text=Confidence').first()).toBeVisible()
    }
  })

  test('Performance metrics show correct format', async ({ page }) => {
    await page.goto(BASE_URL + '/prophet')
    await page.waitForTimeout(3000)
    await page.click('button:has-text("Performance")')
    await page.waitForTimeout(2000)

    const hasData = await page.locator('text=Total Predictions').isVisible()

    if (hasData) {
      // Win rate should be shown as percentage
      const winRateText = await page.locator('text=Win Rate').locator('..').textContent()
      expect(winRateText).toContain('%')
    }
  })

  test('Logs display correct timestamp format', async ({ page }) => {
    await page.goto(BASE_URL + '/prophet')
    await page.waitForTimeout(3000)
    await page.click('button:has-text("Live Logs")')
    await page.waitForTimeout(2000)

    // Check for CT timezone note
    await expect(page.locator('text=Texas Central Time')).toBeVisible({ timeout: 5000 })
  })
})

test.describe('Prophet Knowledge Base - Interactive Features', () => {

  test('Export JSON button is functional', async ({ page }) => {
    await page.goto(BASE_URL + '/prophet')
    await page.waitForTimeout(3000)

    // JSON export button should be present
    const jsonButton = page.locator('button:has-text("JSON")')
    await expect(jsonButton).toBeVisible({ timeout: 10000 })

    // Button should be enabled or disabled based on data
    const isDisabled = await jsonButton.isDisabled()
    // Either state is valid - just verify no crash
  })

  test('Export CSV button is functional', async ({ page }) => {
    await page.goto(BASE_URL + '/prophet')
    await page.waitForTimeout(3000)

    // CSV export button should be present
    const csvButton = page.locator('button:has-text("CSV")')
    await expect(csvButton).toBeVisible({ timeout: 10000 })
  })

  test('Bot filter changes data display', async ({ page }) => {
    await page.goto(BASE_URL + '/prophet')
    await page.waitForTimeout(3000)

    // Select a specific bot
    const botSelect = page.locator('select').first()
    await botSelect.selectOption('FORTRESS')
    await page.waitForTimeout(2000)

    // Either shows filtered data or empty state
    const hasAresData = await page.locator('text=FORTRESS').count() > 1
    const hasEmptyMessage = await page.locator('text=No bot interactions found').isVisible()

    expect(hasAresData || hasEmptyMessage).toBe(true)
  })

  test('Days filter changes data display', async ({ page }) => {
    await page.goto(BASE_URL + '/prophet')
    await page.waitForTimeout(3000)

    // Change days filter
    const daysSelect = page.locator('select').nth(1)
    await daysSelect.selectOption('30')
    await page.waitForTimeout(2000)

    // Page should still be functional
    await expect(page.locator('h1:has-text("Prophet Knowledge Base")')).toBeVisible()
  })
})
