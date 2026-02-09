/**
 * WATCHTOWER Frontend Test Script
 *
 * Run this in browser console on the ARGUS page to verify features work.
 *
 * Usage:
 * 1. Open browser DevTools (F12)
 * 2. Go to Console tab
 * 3. Paste this entire script and press Enter
 */

(async function testWatchtowerFrontend() {
  console.log('='.repeat(60));
  console.log('WATCHTOWER Frontend Feature Tests');
  console.log('='.repeat(60));

  const API_BASE = window.location.origin;
  let passed = 0;
  let failed = 0;

  async function test(name, fn) {
    try {
      console.log(`\nTEST: ${name}`);
      await fn();
      console.log(`  ✅ PASS`);
      passed++;
    } catch (e) {
      console.log(`  ❌ FAIL: ${e.message}`);
      failed++;
    }
  }

  // Test 1: Strike Trends API
  await test('Strike Trends API', async () => {
    const res = await fetch(`${API_BASE}/api/watchtower/strike-trends`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (!data.success) throw new Error('success=false');
    console.log(`    Trends for ${Object.keys(data.data.trends).length} strikes`);
  });

  // Test 2: Gamma Flips API
  await test('Gamma Flips API', async () => {
    const res = await fetch(`${API_BASE}/api/watchtower/gamma-flips`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (!data.success) throw new Error('success=false');
    console.log(`    Found ${data.data.count} flips in last 30 mins`);
  });

  // Test 3: Main Gamma API
  await test('Main Gamma API', async () => {
    const res = await fetch(`${API_BASE}/api/watchtower/gamma`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (!data.success) throw new Error('success=false');
    console.log(`    SPY $${data.data.spot_price}, ${data.data.strikes.length} strikes`);
  });

  // Test 4: Check Time to Expiry element exists
  await test('Time to Expiry Display', async () => {
    // Look for the time to expiry text
    const found = document.body.innerText.includes('Time to Expiry');
    if (!found) throw new Error('Time to Expiry element not found on page');
    console.log('    Time to Expiry section found');
  });

  // Test 5: Check Strike Analysis table has new columns
  await test('Strike Analysis Table Columns', async () => {
    const headers = Array.from(document.querySelectorAll('th')).map(th => th.innerText);
    const requiredHeaders = ['Strike', 'Dist', 'Net Gamma', '30m Trend', 'Status'];
    const missing = requiredHeaders.filter(h => !headers.some(th => th.includes(h)));
    if (missing.length > 0) throw new Error(`Missing columns: ${missing.join(', ')}`);
    console.log('    All required columns present');
  });

  // Test 6: Check Key Metrics cards count
  await test('Key Metrics Cards', async () => {
    // Look for metric labels
    const labels = ['SPY Spot', 'Expected Move', 'VIX', 'Net GEX', 'Gamma Regime', 'Top Magnet', 'Pin Strike', 'Time to Expiry'];
    const text = document.body.innerText;
    const found = labels.filter(l => text.includes(l));
    if (found.length < 7) throw new Error(`Only ${found.length}/8 metric cards found`);
    console.log(`    ${found.length}/8 metric cards visible`);
  });

  // Summary
  console.log('\n' + '='.repeat(60));
  console.log('SUMMARY');
  console.log('='.repeat(60));
  console.log(`  Passed: ${passed}`);
  console.log(`  Failed: ${failed}`);
  console.log(`  Total:  ${passed + failed}`);

  if (failed === 0) {
    console.log('\n🎉 ALL FRONTEND TESTS PASSED!');
  } else {
    console.log('\n⚠️  SOME TESTS FAILED - Check errors above');
  }

  return { passed, failed };
})();
