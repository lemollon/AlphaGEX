import { describe, it, expect } from 'vitest'
import { splitSseFrames, parseSseFrame } from './sse-parse'

describe('splitSseFrames', () => {
  it('splits complete frames and keeps a trailing partial frame as the remainder', () => {
    const { frames, remainder } = splitSseFrames(
      'event: positions\ndata: {"a":1}\n\nevent: positions\ndata: {"a":2}\n\nevent: posi',
    )
    expect(frames).toEqual(['event: positions\ndata: {"a":1}', 'event: positions\ndata: {"a":2}'])
    expect(remainder).toBe('event: posi')
  })

  it('returns no frames and the whole buffer as remainder when nothing is complete yet', () => {
    const { frames, remainder } = splitSseFrames('event: posi')
    expect(frames).toEqual([])
    expect(remainder).toBe('event: posi')
  })

  it('a buffer ending exactly on a frame boundary leaves an empty remainder', () => {
    const { frames, remainder } = splitSseFrames('event: positions\ndata: {"a":1}\n\n')
    expect(frames).toEqual(['event: positions\ndata: {"a":1}'])
    expect(remainder).toBe('')
  })
})

describe('parseSseFrame', () => {
  it('parses an event + data frame', () => {
    expect(parseSseFrame('event: positions\ndata: {"a":1}')).toEqual({
      event: 'positions',
      data: '{"a":1}',
    })
  })

  it('defaults to event "message" when no event: line is present', () => {
    expect(parseSseFrame('data: {"a":1}')).toEqual({ event: 'message', data: '{"a":1}' })
  })

  it('ignores comment-only frames (heartbeats)', () => {
    expect(parseSseFrame(': heartbeat 1730000000000')).toBeNull()
  })

  it('returns null for a frame with no data: line', () => {
    expect(parseSseFrame('event: positions')).toBeNull()
  })

  it('reassembles a data: value that was itself split across multiple data: lines', () => {
    expect(parseSseFrame('event: positions\ndata: {"a":1,\ndata: "b":2}')).toEqual({
      event: 'positions',
      data: '{"a":1,"b":2}',
    })
  })
})
