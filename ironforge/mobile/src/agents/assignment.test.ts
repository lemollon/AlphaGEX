import { describe, it, expect } from 'vitest'
import { assignedAgentLabels } from '@/agents/assignment'

describe('assignedAgentLabels', () => {
  it('returns null (not derivable) with zero connections', () => {
    expect(assignedAgentLabels(0, ['Spark'])).toBeNull()
  })

  it('returns null (not derivable) with more than one connection', () => {
    expect(assignedAgentLabels(2, ['Spark', 'Flame'])).toBeNull()
  })

  it('returns the owned agent labels with exactly one connection', () => {
    expect(assignedAgentLabels(1, ['Spark', 'Flame'])).toEqual(['Spark', 'Flame'])
  })

  it('returns an empty list, not null, when one connection owns no agents', () => {
    expect(assignedAgentLabels(1, [])).toEqual([])
  })
})
