/**
 * The arm receipt's whole job is to make "it's armed" unspeakable without a
 * broker order id. So the tests that matter are the ones proving a receipt
 * CANNOT claim customer-armed from a switch, a label, or an empty result —
 * the three ways the 2026-09-28 rollout got recorded as LIVE while reaching
 * sandbox only.
 */
import { describe, it, expect } from 'vitest'
import {
  isArmedForCustomers,
  describeReceipt,
  worstFirst,
  summarize,
  ARM_LAYER_RANK,
  type SleeveArmReceipt,
  type ArmProof,
} from '../arm-receipt'

const proof = (over: Partial<ArmProof> = {}): ArmProof => ({
  orderId: '987654',
  account: 'Flame',
  accountType: 'customer',
  filledAt: '2026-10-17T18:10:00Z',
  fillPrice: 0.42,
  ...over,
})

const receipt = (over: Partial<SleeveArmReceipt> = {}): SleeveArmReceipt => ({
  sleeve: 'TEST',
  products: ['flame'],
  switchName: 'TEST_MODE',
  switchValue: null,
  layer: 'OFF',
  proof: { internal: null, customer: null },
  blocker: 'no customer path',
  hasOrderPath: false,
  hasCustomerPath: false,
  ...over,
})

describe('isArmedForCustomers — the only gate that may say yes', () => {
  it('says YES only with a customer layer AND a real order id', () => {
    const r = receipt({ layer: 'CUSTOMER', proof: { internal: null, customer: proof() } })
    expect(isArmedForCustomers(r)).toBe(true)
  })

  it('REFUSES a CUSTOMER label with no proof object — a mislabel must not pass', () => {
    const r = receipt({ layer: 'CUSTOMER', proof: { internal: null, customer: null } })
    expect(isArmedForCustomers(r)).toBe(false)
  })

  it('REFUSES a CUSTOMER label whose proof carries an empty order id', () => {
    const r = receipt({ layer: 'CUSTOMER', proof: { internal: null, customer: proof({ orderId: '' }) } })
    expect(isArmedForCustomers(r)).toBe(false)
  })

  it('REFUSES an internal-only sleeve however it is switched on', () => {
    const r = receipt({
      layer: 'INTERNAL',
      switchValue: 'live',
      proof: { internal: proof({ accountType: 'production' }), customer: null },
    })
    expect(isArmedForCustomers(r)).toBe(false)
  })

  it('REFUSES a paper sleeve with its switch on — a switch is not a fill', () => {
    expect(isArmedForCustomers(receipt({ layer: 'PAPER', switchValue: 'on' }))).toBe(false)
  })
})

describe('describeReceipt — a reader must not be able to skim it wrong', () => {
  it('states the order id and account when customer-armed', () => {
    const line = describeReceipt(
      receipt({ sleeve: 'FLINT', layer: 'CUSTOMER', proof: { internal: null, customer: proof() } }),
    )
    expect(line).toContain('ARMED FOR CUSTOMERS')
    expect(line).toContain('987654')
  })

  it('says customers DO NOT get it when the sleeve is internal-only', () => {
    const line = describeReceipt(
      receipt({
        sleeve: 'STOKE',
        layer: 'INTERNAL',
        blocker: 'no customer mirror exists',
        proof: { internal: proof({ accountType: 'production' }), customer: null },
      }),
    )
    expect(line).toContain('INTERNAL ONLY')
    expect(line).toContain('customers DO NOT get this')
    expect(line).toContain('no customer mirror exists')
  })

  it('flags that no switch can arm a sleeve with no order path', () => {
    const line = describeReceipt(receipt({ sleeve: 'QUENCH', layer: 'OFF', hasOrderPath: false }))
    expect(line).toContain('NO ORDER PATH EXISTS')
  })

  it('never prints the word ARMED for anything below the customer layer', () => {
    for (const layer of ['OFF', 'PAPER', 'INTERNAL'] as const) {
      const line = describeReceipt(
        receipt({ layer, proof: { internal: layer === 'INTERNAL' ? proof() : null, customer: null } }),
      )
      expect(line).not.toContain('ARMED FOR CUSTOMERS')
    }
  })
})

describe('worstFirst — a report must lead with what is NOT armed', () => {
  it('orders OFF before PAPER before INTERNAL before CUSTOMER', () => {
    const sorted = worstFirst([
      receipt({ sleeve: 'd', layer: 'CUSTOMER', proof: { internal: null, customer: proof() } }),
      receipt({ sleeve: 'c', layer: 'INTERNAL' }),
      receipt({ sleeve: 'a', layer: 'OFF' }),
      receipt({ sleeve: 'b', layer: 'PAPER' }),
    ])
    expect(sorted.map((r) => r.sleeve)).toEqual(['a', 'b', 'c', 'd'])
  })

  it('ranks the layers in ascending order of what they prove', () => {
    expect(ARM_LAYER_RANK.OFF).toBeLessThan(ARM_LAYER_RANK.PAPER)
    expect(ARM_LAYER_RANK.PAPER).toBeLessThan(ARM_LAYER_RANK.INTERNAL)
    expect(ARM_LAYER_RANK.INTERNAL).toBeLessThan(ARM_LAYER_RANK.CUSTOMER)
  })
})

describe('summarize — the one line to read at a glance', () => {
  it('counts only proven customer arms, not labels', () => {
    const s = summarize([
      receipt({
        sleeve: 'main', layer: 'CUSTOMER', hasOrderPath: true,
        proof: { internal: null, customer: proof() },
      }),
      receipt({
        sleeve: 'mislabelled', layer: 'CUSTOMER', hasOrderPath: true,
        proof: { internal: null, customer: null },
      }),
      receipt({ sleeve: 'stoke', layer: 'INTERNAL', hasOrderPath: true }),
      receipt({ sleeve: 'quench', layer: 'OFF', hasOrderPath: false }),
    ])
    expect(s.total).toBe(4)
    expect(s.customer).toBe(1) // the mislabelled one does NOT count
    expect(s.internalOnly).toBe(1)
    expect(s.noOrderPath).toBe(1)
    expect(s.headline).toContain('1 of 4 sleeves reach customer accounts')
  })

  it('reports zero rather than throwing on an empty set', () => {
    const s = summarize([])
    expect(s.customer).toBe(0)
    expect(s.headline).toContain('0 of 0')
  })
})
