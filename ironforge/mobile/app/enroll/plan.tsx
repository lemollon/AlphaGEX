import { useEffect, useState } from 'react'
import { View, Text, Pressable, StyleSheet } from 'react-native'
import { ApiError } from '@/api/client'
import { color, space, radius, type, font } from '@/theme/tokens'
import { Loading } from '@/components/ui'
import { EnrollShell } from '@/enroll/Shell'
import { useEnrollment } from '@/enroll/useEnrollment'
import { choosePlan, getPlanCatalog } from '@/enroll/api'
import { routeForNextStep } from '@/enroll/steps'
import type { PlanCatalog } from '@/enroll/types'

/**
 * Choose a plan (UAT #6, screen 3 of 9) — PUT /api/v1/enrollments/{id}/plan.
 *
 * Prices come from GET /api/public/plans (additive route added in this PR — see
 * webapp/src/app/api/public/plans/route.ts), which serves lib/billing/plans.ts
 * directly. Never the mock's "Paper free / Live $49" — Leron corrected that 9/5:
 * Community $10/mo, Spark or Flame $50/mo each, both $75/mo.
 *
 * JUDGMENT CALL (flagged in the PR body): "Both" is a valid `plan` value server-side,
 * but POST /api/v1/agent-configs and /api/v1/activations can each only configure and
 * activate ONE bot per enrollment pass. Picking Both here still only sets up one agent
 * at the Agents screen; the second bot is added afterward through the existing /live
 * upsell (bundle-upgrade) path, not through this funnel. The Agents screen says so.
 */
export default function PlanScreen() {
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
            name="Both agents"
            blurb="Spark and Flame together, one bundle price."
            price={catalog.both.price_monthly}
            accent={color.accent}
            onPress={() => choose('both')}
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
  accent,
  onPress,
  disabled,
}: {
  name: string
  blurb: string
  price: number
  accent: string
  onPress: () => void
  disabled: boolean
}) {
  return (
    <Pressable onPress={onPress} disabled={disabled} style={[s.tile, { borderColor: accent, opacity: disabled ? 0.6 : 1 }]}>
      <View style={{ flex: 1 }}>
        <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, fontSize: 17 }]}>{name}</Text>
        <Text style={[type.label, { color: color.textDim, marginTop: 2 }]}>{blurb}</Text>
      </View>
      <Text style={[type.body, { color: accent, fontFamily: font.bodyBold, fontSize: 17 }]}>${price}/mo</Text>
    </Pressable>
  )
}

const s = StyleSheet.create({
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
