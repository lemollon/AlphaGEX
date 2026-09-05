import { useEffect } from 'react'
import { View, Text } from 'react-native'
import { useLocalSearchParams, useRouter } from 'expo-router'
import Ionicons from '@expo/vector-icons/Ionicons'
import { color, space, type, font } from '@/theme/tokens'
import { Button } from '@/components/ui'
import { EnrollShell } from '@/enroll/Shell'
import { confirmationSeen } from '@/enroll/api'
import { AGENT_LABEL } from '@/agents/copy'
import { agentDetailHref, type AgentBot } from '@/agents/routes'

/**
 * Done (UAT #6, screen 9 of 9) — POST /api/v1/activations/{id}/confirmation-seen,
 * then into the app. Mirrors webapp/src/app/enroll/done/page.tsx's "You're in" copy.
 */
export default function EnrollDoneScreen() {
  const router = useRouter()
  const params = useLocalSearchParams<{ activationId?: string; agent?: string }>()
  const agent = (params.agent as AgentBot | undefined) ?? null

  useEffect(() => {
    if (params.activationId) confirmationSeen(params.activationId).catch(() => {})
    // Best-effort — a confirmation-seen failure must never block entering the app.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.activationId])

  function enter() {
    router.replace(agent ? (agentDetailHref(agent) as never) : '/')
  }

  return (
    <EnrollShell title="Welcome to the Forge">
      <View style={{ alignItems: 'center', paddingTop: space.xxl }}>
        <Ionicons name="checkmark-circle" size={56} color={color.pos} />
        <Text style={[type.title, { color: color.text, fontFamily: font.display, marginTop: space.lg, textAlign: 'center' }]}>
          You&rsquo;re in.
        </Text>
        <Text style={[type.body, { color: color.textDim, textAlign: 'center', marginTop: space.sm }]}>
          {agent
            ? `${AGENT_LABEL[agent]} is set up and ready to trade under the configuration you just reviewed.`
            : 'Your Forge Community membership is live.'}
        </Text>
        <View style={{ marginTop: space.xxl, width: '100%' }}>
          <Button label="Enter the Forge" onPress={enter} />
        </View>
      </View>
    </EnrollShell>
  )
}
