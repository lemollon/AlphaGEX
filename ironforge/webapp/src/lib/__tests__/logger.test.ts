/**
 * Tests for logger.ts — structured logging utility.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { log, setRequestId, clearRequestId, getRequestId } from '../logger'

beforeEach(() => {
  clearRequestId()
  vi.restoreAllMocks()
})

describe('log()', () => {
  it('info level calls console.log with JSON', () => {
    const spy = vi.spyOn(console, 'log').mockImplementation(() => {})
    log('info', 'scanner', 'scan started')
    expect(spy).toHaveBeenCalledOnce()
    const parsed = JSON.parse(spy.mock.calls[0][0])
    expect(parsed.level).toBe('info')
    expect(parsed.module).toBe('scanner')
    expect(parsed.msg).toBe('scan started')
    expect(parsed.ts).toBeDefined()
  })

  it('error level calls console.error', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    log('error', 'tradier', 'API timeout')
    expect(spy).toHaveBeenCalledOnce()
    const parsed = JSON.parse(spy.mock.calls[0][0])
    expect(parsed.level).toBe('error')
  })

  it('warn level calls console.warn', () => {
    const spy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    log('warn', 'api', 'slow query')
    expect(spy).toHaveBeenCalledOnce()
    const parsed = JSON.parse(spy.mock.calls[0][0])
    expect(parsed.level).toBe('warn')
  })

  it('includes extra fields in output', () => {
    const spy = vi.spyOn(console, 'log').mockImplementation(() => {})
    log('info', 'scanner', 'position opened', {
      bot: 'flame',
      position_id: 'FLAME-20260322-abc',
      duration_ms: 150,
    })
    const parsed = JSON.parse(spy.mock.calls[0][0])
    expect(parsed.bot).toBe('flame')
    expect(parsed.position_id).toBe('FLAME-20260322-abc')
    expect(parsed.duration_ms).toBe(150)
  })
})

describe('request ID propagation', () => {
  it('setRequestId adds request_id to all logs', () => {
    const spy = vi.spyOn(console, 'log').mockImplementation(() => {})
    setRequestId('abc12345')
    log('info', 'api', 'request received')
    const parsed = JSON.parse(spy.mock.calls[0][0])
    expect(parsed.request_id).toBe('abc12345')
  })

  it('clearRequestId removes request_id from logs', () => {
    const spy = vi.spyOn(console, 'log').mockImplementation(() => {})
    setRequestId('abc12345')
    clearRequestId()
    log('info', 'api', 'next request')
    const parsed = JSON.parse(spy.mock.calls[0][0])
    expect(parsed.request_id).toBeUndefined()
  })

  it('getRequestId returns current value', () => {
    expect(getRequestId()).toBeNull()
    setRequestId('test123')
    expect(getRequestId()).toBe('test123')
    clearRequestId()
    expect(getRequestId()).toBeNull()
  })
})
