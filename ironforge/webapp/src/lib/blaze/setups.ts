/**
 * BLAZE — 3-setup directional stack. Pure functions, no I/O.
 * Mirrors trading/helios/setups/{wall_fade,wall_break,flip_cross}.py.
 */
import {
  BlazeConfig, DailyState, GexSnapshot, SetupAction, isCapped,
} from './types'

const POSITIVE_REGIMES = new Set(['MODERATE_POSITIVE', 'HIGH_POSITIVE', 'EXTREME_POSITIVE'])
const NEGATIVE_REGIMES = new Set(['MODERATE_NEGATIVE', 'HIGH_NEGATIVE', 'EXTREME_NEGATIVE'])

/** Setup 1: wall_fade (positive-gamma mean-reversion). */
export function evaluateWallFade(snap: GexSnapshot, config: BlazeConfig): SetupAction | null {
  if (!POSITIVE_REGIMES.has(snap.regime)) return null
  if (snap.sigma_1d_band_width <= 0) return null

  const { spot, call_wall: cw, put_wall: pw, sigma_1d_band_width: sigma } = snap
  const thr = config.wall_fade_em_threshold

  const nearCall = cw > 0 && spot < cw && (cw - spot) / sigma < thr
  const nearPut = pw > 0 && spot > pw && (spot - pw) / sigma < thr

  if (!nearCall && !nearPut) return null

  let useCall = nearCall
  let usePut = nearPut

  if (nearCall && nearPut) {
    const dCall = cw - spot
    const dPut = spot - pw
    if (dCall <= dPut) { usePut = false } else { useCall = false }
  }

  const longStrike = Math.round(spot)
  if (useCall) {
    // Fade down → bear put vertical (long ATM put, short ATM-1 put)
    return {
      setup: 'wall_fade',
      direction: 'put',
      long_strike: longStrike,
      short_strike: longStrike - config.spread_width,
      reason: `call_wall within ${((cw - spot) / sigma).toFixed(2)}sigma overhead`,
    }
  }
  // usePut — fade up → bull call vertical
  return {
    setup: 'wall_fade',
    direction: 'call',
    long_strike: longStrike,
    short_strike: longStrike + config.spread_width,
    reason: `put_wall within ${((spot - pw) / sigma).toFixed(2)}sigma below`,
  }
}

/** Setup 2: wall_break (negative-gamma momentum). */
export function evaluateWallBreak(snap: GexSnapshot, config: BlazeConfig): SetupAction | null {
  if (!NEGATIVE_REGIMES.has(snap.regime)) return null
  if (snap.sigma_1d_band_width <= 0) return null

  const { spot, call_wall: cw, put_wall: pw, sigma_1d_band_width: sigma } = snap
  const thr = config.wall_break_em_threshold

  const brokeCall = cw > 0 && spot > cw && (spot - cw) / sigma > thr
  const brokePut = pw > 0 && spot < pw && (pw - spot) / sigma > thr

  if (!brokeCall && !brokePut) return null

  const longStrike = Math.round(spot)
  if (brokeCall) {
    return {
      setup: 'wall_break',
      direction: 'call',
      long_strike: longStrike,
      short_strike: longStrike + config.spread_width,
      reason: `spot ${((spot - cw) / sigma).toFixed(2)}sigma above call_wall`,
    }
  }
  return {
    setup: 'wall_break',
    direction: 'put',
    long_strike: longStrike,
    short_strike: longStrike - config.spread_width,
    reason: `spot ${((pw - spot) / sigma).toFixed(2)}sigma below put_wall`,
  }
}

/** 5-min rolling buffer for flip_cross. */
export class FlipBuffer {
  private snaps: GexSnapshot[] = []
  constructor(public maxMinutes: number = 5) {}

  add(snap: GexSnapshot): void {
    this.snaps.push(snap)
    const cutoff = snap.snapshot_at.getTime() - this.maxMinutes * 60_000
    while (this.snaps.length > 0 && this.snaps[0].snapshot_at.getTime() < cutoff) {
      this.snaps.shift()
    }
  }

  earliestWithin(now: Date, minutes: number): GexSnapshot | null {
    const cutoff = now.getTime() - minutes * 60_000
    for (const s of this.snaps) {
      if (s.snapshot_at.getTime() >= cutoff) return s
    }
    return null
  }

  hasBuffer(now: Date, minutes: number): boolean {
    const e = this.earliestWithin(now, minutes)
    if (!e) return false
    return (now.getTime() - e.snapshot_at.getTime()) / 1000 >= (minutes - 1) * 60
  }
}

/** Setup 3: flip_cross (regime-transition with hysteresis). */
export function evaluateFlipCross(
  snap: GexSnapshot,
  buffer: FlipBuffer,
  config: BlazeConfig,
): SetupAction | null {
  const now = snap.snapshot_at
  if (!buffer.hasBuffer(now, config.flip_buffer_minutes)) return null
  const past = buffer.earliestWithin(now, config.flip_buffer_minutes)
  if (!past) return null

  const flip = snap.flip_point
  if (flip <= 0) return null
  const hyst = flip * config.flip_hysteresis_pct
  const upper = flip + hyst
  const lower = flip - hyst

  const crossedUp = past.spot < lower && snap.spot > upper
  const crossedDown = past.spot > upper && snap.spot < lower
  if (!crossedUp && !crossedDown) return null

  const regimeFlipToPos = past.net_gex < 0 && snap.net_gex > 0
  const regimeFlipToNeg = past.net_gex > 0 && snap.net_gex < 0

  const longStrike = Math.round(snap.spot)
  if (crossedUp && regimeFlipToPos) {
    return {
      setup: 'flip_cross',
      direction: 'call',
      long_strike: longStrike,
      short_strike: longStrike + config.spread_width,
      reason: 'upward flip cross with net_gex sign-flip',
    }
  }
  if (crossedDown && regimeFlipToNeg) {
    return {
      setup: 'flip_cross',
      direction: 'put',
      long_strike: longStrike,
      short_strike: longStrike - config.spread_width,
      reason: 'downward flip cross with net_gex sign-flip',
    }
  }
  return null
}

/** Dispatcher: flip_cross > wall_break > wall_fade, with per-setup cap. */
export function dispatch(
  snap: GexSnapshot,
  state: DailyState,
  buffer: FlipBuffer,
  config: BlazeConfig,
): SetupAction | null {
  const cap = config.max_trades_per_setup_per_day

  if (!isCapped(state, 'flip_cross', cap)) {
    const a = evaluateFlipCross(snap, buffer, config)
    if (a) return a
  }
  if (!isCapped(state, 'wall_break', cap)) {
    const a = evaluateWallBreak(snap, config)
    if (a) return a
  }
  if (!isCapped(state, 'wall_fade', cap)) {
    const a = evaluateWallFade(snap, config)
    if (a) return a
  }
  return null
}
