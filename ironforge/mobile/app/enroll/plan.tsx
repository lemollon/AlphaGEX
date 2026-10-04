import { useEffect, useMemo, useState } from 'react'
import { View, Text, Pressable, StyleSheet } from 'react-native'
import { ApiError } from '@/api/client'
import { space, radius, type, font } from '@/theme/tokens'
import { useTheme } from '@/theme/ThemeContext'
import type { ColorTokens } from '@/theme/palette'
import { Loading } from '@/components/ui'
import { EnrollShell } from '@/enroll/Shell'
import { useEnrollment } from '@/enroll/useEnrollment'
import { choosePlan, getPlanCatalog } from '@/enroll/api'
import { routeForNextStep } from '@/enroll/steps'
import type { PlanCatalog } from '@/enroll/types'
import { EMBER_LIMITS } from '@/agents/copy'
import { color as staticColor } from '@/theme/tokens'

/**
 * Choose a plan (step 3 of 8) — PUT /api/v1/enrollments/{id}/plan.
 *
 * Prices come from GET /api/public/plans (additive route added in this PR — see
 * webapp/src/app/api/public/plans/route.ts), which serves lib/billing/plans.ts
 * directly — this screen never hardcodes a price, it only renders whatever that
 * route returns. Leron confirmed (2026-10-04, follow-up) to leave the actual price
 * amounts unchanged from main for this task — only the "Both" bundle and Ember are
 * in scope here, not a price change.
 *
 * PRICING CHANGE (Leron, 2026-10-04, binding): no "Both" bundle any more — Spark
 * and Flame are each sold as their own separate subscription, chosen and purchased
 * independently (the second bot is added afterward through the existing /live
 * upsell path, same as before, just never framed here as "one bundle price"). The
 * "Both agents" tile that used to live on this screen is removed.
 *
 * Ember (10.4 redesign, design-spec §3/§5) is added as a fourth tile: free, one
 * account per person, $500–$2,000 trading capital. Not in the server's
 * PlanCatalog (that type only carries the two paid bots + Community), so its
 * copy/limits are the product facts from EMBER_LIMITS, not a fetched price.
 */
export default function PlanScreen() {
  const { colors: color } = useTheme()
  const { enrollment, busy, setBusy, error, setError, router } = useEnrollment('plan')
  const [catalog, setCatalog] = useState<PlanCatalog | null>(null)
  const [catalogError, setCatalogError] = useState<string | null>(null)

  useEffect(() => {
    getPlanCatalog()
      .then(setCatalog)
      .catch((e) => setCatalogError(e instanceof ApiError ? e.humanMessage : (e as Error).message))
  }, [])

  async function choose(plan: string) {
    if (!enrollment || busy) return
    setBusy(true)
    setError(null)
    try {
      const d = await choosePlan(enrollment.id, plan)
      const canonical = routeForNextStep(d.next_step, d.selected_plan)
      router.push(canonical.route as never)
    } catch (e) {
      setError(e instanceof ApiError ? e.humanMessage : (e as Error).message)
      setBusy(false)
    }
  }

  const spark = catalog?.bots.find((b) => b.slug === 'spark')
  const flame = catalog?.bots.find((b) => b.slug === 'flame')

  return (
    <EnrollShell title="Choose your plan" step={3} error={error ?? catalogError}>
      <Text style={[type.body, { color: color.textDim, marginBottom: space.lg }]}>
        Select the experience that fits how you want to use IronForge.
      </Text>

      {!catalog && !catalogError ? <Loading label="Loading plans…" /> : null}

      {catalog ? (
        <View style={{ gap: space.md }}>
          <PlanTile
            name={catalog.community.name}
            blurb="Chat, education, and market commentary. No trading bot."
            price={catalog.community.price_monthly}
            accent={color.accent}
            onPress={() => choose('community')}
            disabled={busy}
          />
          {spark ? (
            <PlanTile
              name={spark.name}
              blurb={spark.blurb}
              price={spark.price_monthly}
              accent={color.spark}
              onPress={() => choose('spark')}
              disabled={busy}
            />
          ) : null}
          {flame ? (
            <PlanTile
              name={flame.name}
              blurb={flame.blurb}
              price={flame.price_monthly}
              accent={color.flame}
              onPress={() => choose('flame')}
              disabled={busy}
            />
          ) : null}
          <PlanTile
            name="Ember"
            blurb="Built for smaller accounts and first-time investors. One account per person, $500–$2,000 trading capital."
            priceLabel={EMBER_LIMITS.priceLabel}
            accent={staticColor.ember}
            onPress={() => choose('ember')}
            disabled={busy}
          />
        </View>
      ) : null}
    </EnrollShell>
  )
}

function PlanTile({
  name,
  blurb,
  price,
  priceLabel,
  accent,
  onPress,
  disabled,
}: {
  name: string
  blurb: string
  /** Monthly dollar price — ignored when `priceLabel` is given (e.g. Ember's "Free"). */
  price?: number
  priceLabel?: string
  accent: string
  onPress: () => void
  disabled: boolean
}) {
  const { colors: color } = useTheme()
  const s = useMemo(() => makeStyles(color), [color])
  return (
    <Pressable onPress={onPress} disabled={disabled} style={[s.tile, { borderColor: accent, opacity: disabled ? 0.6 : 1 }]}>
      <View style={{ flex: 1 }}>
        <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, fontSize: 17 }]}>{name}</Text>
        <Text style={[type.label, { color: color.textDim, marginTop: 2 }]}>{blurb}</Text>
      </View>
      <Text style={[type.body, { color: accent, fontFamily: font.bodyBold, fontSize: 17 }]}>
        {priceLabel ?? `$${price}/mo`}
      </Text>
    </Pressable>
  )
}

const makeStyles = (color: ColorTokens) =>
  StyleSheet.create({
    tile: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: space.md,
      borderWidth: 1.5,
      borderRadius: radius.lg,
      padding: space.lg,
      backgroundColor: color.card,
    },
  })
