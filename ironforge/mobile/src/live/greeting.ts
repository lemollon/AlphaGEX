/**
 * Forge tab greeting (mobile addendum §2 Forge tab step 1: "Good morning/
 * afternoon/evening, {FirstName}"). Pure so the noon/5pm boundaries are
 * tested rather than eyeballed — `hour` is the VIEWER's local hour, passed in
 * rather than read from `Date` here, so the boundary cases are reachable
 * without mocking the clock.
 */
export function greetingForHour(hour: number): 'Good morning' | 'Good afternoon' | 'Good evening' {
  if (hour < 12) return 'Good morning'
  if (hour < 17) return 'Good afternoon'
  return 'Good evening'
}
