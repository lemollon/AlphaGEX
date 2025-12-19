#!/usr/bin/env node
/**
 * Quick API Test for SWR-cached endpoints
 *
 * Run with: node scripts/test-swr-api.js
 *
 * This verifies the backend endpoints that SWR hooks depend on are working.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const endpoints = [
  { name: 'Market Commentary', path: '/api/ai-intelligence/market-commentary' },
  { name: 'Daily Trading Plan', path: '/api/ai-intelligence/daily-trading-plan' },
  { name: 'Gamma Expiration (SPY)', path: '/api/gamma/SPY/expiration-intel' },
  { name: 'Gamma Expiration (QQQ)', path: '/api/gamma/QQQ/expiration-intel' },
  { name: 'GEX (SPY)', path: '/api/gex/SPY' },
  { name: 'VIX Current', path: '/api/vix/current' },
]

async function testEndpoint(name, path) {
  const url = `${API_URL}${path}`
  const start = Date.now()

  try {
    const response = await fetch(url)
    const elapsed = Date.now() - start

    if (!response.ok) {
      return { name, status: 'FAIL', error: `HTTP ${response.status}`, elapsed }
    }

    const data = await response.json()
    const hasData = data.success !== false && (data.data || data)

    return {
      name,
      status: hasData ? 'PASS' : 'WARN',
      elapsed,
      dataKeys: Object.keys(data.data || data).slice(0, 3).join(', ')
    }
  } catch (error) {
    return { name, status: 'FAIL', error: error.message, elapsed: Date.now() - start }
  }
}

async function main() {
  console.log('\n🧪 SWR API Endpoint Tests')
  console.log('='.repeat(60))
  console.log(`API URL: ${API_URL}\n`)

  const results = []

  for (const { name, path } of endpoints) {
    process.stdout.write(`Testing ${name}... `)
    const result = await testEndpoint(name, path)
    results.push(result)

    const statusIcon = result.status === 'PASS' ? '✅' : result.status === 'WARN' ? '⚠️' : '❌'
    console.log(`${statusIcon} ${result.status} (${result.elapsed}ms)`)

    if (result.error) {
      console.log(`   Error: ${result.error}`)
    }
  }

  console.log('\n' + '='.repeat(60))

  const passed = results.filter(r => r.status === 'PASS').length
  const failed = results.filter(r => r.status === 'FAIL').length

  console.log(`Results: ${passed} passed, ${failed} failed, ${results.length - passed - failed} warnings`)

  if (failed > 0) {
    console.log('\n⚠️  Some endpoints failed. SWR caching may not work correctly.')
    console.log('   Make sure the backend is running: cd backend && python -m uvicorn main:app')
    process.exit(1)
  } else {
    console.log('\n✅ All SWR-dependent endpoints are working!')
  }
}

main()
