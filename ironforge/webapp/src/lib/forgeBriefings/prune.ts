import { dbExecute, query } from '../db'

export async function pruneIfDue(): Promise<{ ranToday: boolean; soft: number; hard: number }> {
  const meta = await query<{ last_run_ts: Date | null }>(
    `SELECT last_run_ts FROM forge_briefings_meta WHERE bot='__system' AND brief_type='prune'`,
  ).catch(() => [])
  const last = meta[0]?.last_run_ts ? new Date(meta[0].last_run_ts) : null
  const todayCt = new Date().toLocaleDateString('en-CA', { timeZone: 'America/Chicago' })
  const lastCt = last ? last.toLocaleDateString('en-CA', { timeZone: 'America/Chicago' }) : null
  if (lastCt === todayCt) return { ranToday: false, soft: 0, hard: 0 }

  const soft = await dbExecute(`
    UPDATE forge_briefings SET is_active = FALSE, updated_at = NOW()
    WHERE is_active = TRUE
      AND brief_type IN ('daily_eod','weekly_synth','fomc_eve','post_event')
      AND brief_date < (CURRENT_DATE - INTERVAL '3 years')
  `).catch(() => 0)

  const hard = await dbExecute(`
    DELETE FROM forge_briefings
    WHERE is_active = FALSE
      AND brief_type IN ('daily_eod','weekly_synth','fomc_eve','post_event')
      AND updated_at < (NOW() - INTERVAL '30 days')
  `).catch(() => 0)

  await dbExecute(`
    INSERT INTO forge_briefings_meta (bot, brief_type, last_run_ts, last_run_status)
    VALUES ('__system', 'prune', NOW(), $1)
    ON CONFLICT (bot, brief_type) DO UPDATE SET
      last_run_ts = NOW(), last_run_status = $1
  `, [`soft=${soft} hard=${hard}`]).catch(() => {})

  return { ranToday: true, soft, hard }
}
