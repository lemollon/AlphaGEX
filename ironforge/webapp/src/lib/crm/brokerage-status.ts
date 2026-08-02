/**
 * Maps `brokerage_connections.status` (our internal pending|active|removed|disabled vocabulary)
 * onto the CRM's richer Connection Status (see schema.ts CONNECTION_STATUS). The internal column
 * cannot express "needs reauthorization" — disabled just means "not working" — but the Brokerage
 * Issues view exists specifically to surface that distinction, so `disabled` is the one status
 * that also flips `reauthorizationRequired`.
 */

export type InternalBrokerageStatus = 'pending' | 'active' | 'removed' | 'disabled'

export type CrmConnectionStatus = 'Pending' | 'Connected' | 'Disconnected' | 'Reauthorization Required'

export interface BrokerageCrmStatus {
  connectionStatus: CrmConnectionStatus
  reauthorizationRequired: boolean
}

const STATUS_MAP: Record<InternalBrokerageStatus, CrmConnectionStatus> = {
  pending: 'Pending',
  active: 'Connected',
  removed: 'Disconnected',
  disabled: 'Reauthorization Required',
}

function isInternalStatus(status: string): status is InternalBrokerageStatus {
  return status in STATUS_MAP
}

/**
 * An unrecognized status falls back to 'Pending' rather than throwing — a drifted or future
 * internal status value should degrade to "not yet resolved", not crash the emitter.
 */
export function mapBrokerageStatusToCrm(status: string): BrokerageCrmStatus {
  const known = isInternalStatus(status) ? status : null
  return {
    connectionStatus: known ? STATUS_MAP[known] : 'Pending',
    reauthorizationRequired: known === 'disabled',
  }
}
