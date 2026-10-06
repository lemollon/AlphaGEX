import { describe, it, expect, beforeEach } from 'vitest'
import {
  isOffline,
  reportNetworkFailure,
  reportNetworkSuccess,
  subscribeConnectivity,
  __resetConnectivityForTest,
} from '@/live/connectivity'

describe('connectivity', () => {
  beforeEach(() => {
    __resetConnectivityForTest()
  })

  it('starts online', () => {
    expect(isOffline()).toBe(false)
  })

  it('does not flag offline on a single failure', () => {
    reportNetworkFailure()
    expect(isOffline()).toBe(false)
  })

  it('flags offline after consecutive failures', () => {
    reportNetworkFailure()
    reportNetworkFailure()
    expect(isOffline()).toBe(true)
  })

  it('a single success clears offline immediately', () => {
    reportNetworkFailure()
    reportNetworkFailure()
    expect(isOffline()).toBe(true)
    reportNetworkSuccess()
    expect(isOffline()).toBe(false)
  })

  it('a success in between failures resets the consecutive count', () => {
    reportNetworkFailure()
    reportNetworkSuccess()
    reportNetworkFailure()
    expect(isOffline()).toBe(false)
  })

  it('notifies subscribers only when the state actually changes', () => {
    const seen: boolean[] = []
    const unsubscribe = subscribeConnectivity((v) => seen.push(v))
    reportNetworkFailure() // below threshold, no change
    reportNetworkFailure() // now offline
    reportNetworkFailure() // still offline, no change
    reportNetworkSuccess() // back online
    unsubscribe()
    expect(seen).toEqual([true, false])
  })
})
