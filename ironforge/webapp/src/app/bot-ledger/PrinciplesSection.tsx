import { BoltIcon, EyeIcon, ShieldIcon } from '../_home/icons'

/** Static copy; no data dependency, so this stays a server component. */
const PRINCIPLES = [
  {
    title: 'It never flinches',
    body: 'No revenge trades. No hesitation. Just the same rules, every time.',
    Icon: ShieldIcon,
  },
  {
    title: 'It never sits out',
    body: 'It takes the setup when fear, greed, or fatigue would make you hesitate.',
    Icon: BoltIcon,
  },
  {
    title: 'Nothing is hidden',
    body: 'Every paper trade is logged—including the losses.',
    Icon: EyeIcon,
  },
] as const

export default function PrinciplesSection() {
  return (
    <section aria-labelledby="ledger-principles-heading" className="mt-16 md:mt-20">
      <h2
        id="ledger-principles-heading"
        className="text-center font-display text-2xl text-white md:text-3xl"
      >
        Why the bot beats you at your own strategy
      </h2>
      <p className="mt-2 text-center text-sm text-gray-400 md:text-base">
        It follows the rules when emotion gets in the way.
      </p>

      <ul className="mt-8 grid grid-cols-1 gap-4 md:grid-cols-3">
        {PRINCIPLES.map(({ title, body, Icon }) => (
          <li
            key={title}
            className="flex items-start gap-4 rounded-2xl border border-white/10 bg-forge-card p-5 md:flex-col md:items-center md:gap-3 md:p-6 md:text-center"
          >
            <Icon className="h-8 w-8 shrink-0 text-amber-500" />
            <div>
              <h3 className="font-semibold text-amber-500">{title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-gray-300">{body}</p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}
