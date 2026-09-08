/**
 * Waitlist drip — the approved copy for Emails 1-6, VERBATIM from
 * "IronForge Waitlist Communication Kit — Emails 1-6" (September 2026, prepared for
 * Logan Pennington & Leron Mollon).
 *
 * GENERATED from the kit docx (zipfile + word/document.xml) so nothing was retyped. Curly
 * apostrophes, the straight apostrophe in the Email 6 subject, and the bold lead-ins are all
 * as the kit has them. Do not "fix" wording here — the kit is the source of truth; a copy
 * change is a new kit, not an edit.
 *
 * `title` is the headline split at the kit's line break. `paragraphs[].lead` is the bold
 * lead-in ("The build.") the kit renders inline before the sentence. `disclosure` is the
 * per-email approved disclosure footer.
 */

export interface DripParagraph {
  /** Bold inline lead-in, e.g. "The build." — absent for plain paragraphs. */
  lead?: string
  text: string
}

export interface DripEmail {
  /** 1-6. */
  stage: number
  subject: string
  /** Inbox preview text (hidden preheader in the HTML, first line of the plain-text part). */
  preview: string
  /** Headline lines, rendered one per line. */
  title: readonly string[]
  /** Secondary headline (Emails 3 and 4 only). */
  subtitle?: string
  paragraphs: readonly DripParagraph[]
  /** The per-email approved disclosure footer. */
  disclosure: string
}

/** Header kicker under the wordmark, identical on every email. */
export const DRIP_KICKER = "AUTOMATED TRADING BUILT FOR BUSY PEOPLE."

/** Greeting word; the first name follows it when known ("Hello Ada,"), else "Hello,". */
export const DRIP_GREETING = 'Hello'

export const DRIP_SIGNOFF_NAME = "Logan Pennington & Leron Mollon"
export const DRIP_SIGNOFF_ROLE = "Co-Founders, IronForge"

/** Number of emails in the sequence. A subscriber is `completed` after this stage sends. */
export const DRIP_FINAL_STAGE = 6

export const DRIP_EMAILS: readonly DripEmail[] = [
  {
    stage: 1,
    subject: "Welcome to IronForge—you’re on the list.",
    preview: "Build updates, trading strategy, and next steps—straight from the founders.",
    title: ["You’re on the list.", "Thanks for being here."],
    paragraphs: [
      { text: "Thank you for joining the IronForge waitlist. We’re pleased to welcome you and look forward to sharing our progress as we prepare for launch." },
      { text: "We’re creating automated options trading built for busy people, with visibility into what your trade agents are doing and your funds held in your own brokerage account." },
      { text: "In the coming days and weeks, you’ll hear from us about:" },
      { lead: "The build.", text: "A look at what we’re working on, product previews, and improvements along the way." },
      { lead: "The trading strategy.", text: "How our agents work, the rules they follow, and the risks and requirements to understand." },
      { lead: "What comes next.", text: "Launch progress, early-access details, and what you’ll need to get started." },
      { text: "In the coming weeks, we’ll also share a survey to learn more about your interests and expectations for IronForge." },
      { text: "Thank you for your interest and support. We’re excited to have you with us from the start." },
    ],
    disclosure: "Options trading involves risk and can result in substantial losses. Automation does not guarantee profits or prevent losses.",
  },
  {
    stage: 2,
    subject: "Meet the neighbors behind IronForge",
    preview: "Two busy families, a shared faith, and complementary experience.",
    title: ["Neighbors first.", "Co-founders next."],
    paragraphs: [
      { text: "Before we share more about IronForge, we wanted to introduce the people behind it." },
      { text: "We’re Logan and Leron—neighbors, a couple of corporate guys, and family men with full calendars. Between work, family commitments, and everyday life, we know how quickly a day fills up." },
      { text: "We’re also strong in our faith. It’s an important part of who we are and how we approach our families, our work, and the responsibility of building something together." },
      { text: "As neighbors, we discovered that our professional experience complemented each other’s. Between us, we bring experience in trading, solution architecture, and applying AI to practical problems. That combination gave us a foundation for IronForge." },
      { text: "The idea was straightforward: build a way to automate a defined trading approach for people whose lives don’t revolve around watching the market." },
      { text: "For us, that means bringing together clear trading rules, thoughtfully designed technology, and visibility into what the system is doing. Automation can reduce the manual work, but it doesn’t remove the risks of trading." },
      { text: "We’re building IronForge alongside the same careers and family commitments that inspired it. That keeps the purpose close to home: making the experience easier to understand and use for busy people like us." },
      { text: "In our next email, we’ll introduce the trading approach behind IronForge and explain how our agents put defined rules into action." },
      { text: "Thank you for getting to know us and being part of the journey." },
    ],
    disclosure: "Options trading involves risk and can result in substantial losses. Automation does not guarantee profits or prevent losses.",
  },
  {
    stage: 3,
    subject: "Meet Spark: morning setups. Juicy premium.",
    preview: "A look at Spark’s same-day options strategy and the rules behind it.",
    title: ["Meet Spark."],
    subtitle: "Morning setups. Juicy premium. Defined rules.",
    paragraphs: [
      { text: "Meet Spark, our morning trade agent. While your day gets moving, Spark looks for qualifying options setups with a focus on collecting premium—the credit received when a position is opened." },
      { text: "Spark seeks attractive premium while staying disciplined about entry conditions. Premium collected at entry is not guaranteed profit; the outcome depends on how the position closes." },
      { lead: "The morning approach.", text: "Spark evaluates opportunities during its morning trading window. Market conditions help determine entry, so a morning session does not automatically mean a trade." },
      { lead: "The strategy.", text: "Spark uses 0DTE bull put spreads: options that expire the same day, pairing a sold put with a purchased put at a lower strike. The structure collects a net credit and has a defined maximum loss at entry. It has a bullish outlook and can lose money if the market falls." },
      { lead: "The filters.", text: "Volatility-aware entry rules help determine when a setup qualifies." },
      { lead: "The sizing.", text: "Contract quantity varies by account size, within the strategy’s position-sizing rules." },
      { lead: "The exit plan.", text: "Predefined targets and stops guide position management. Stop orders do not guarantee an exit at the intended price, especially in fast-moving markets." },
      { text: "Spark brings a rules-based approach to the morning session, with visibility into its activity through IronForge." },
      { text: "In the coming weeks, we’ll share more about Spark’s account requirements and the steps to get started." },
      { text: "Thank you for following along as we bring IronForge to life." },
    ],
    disclosure: "Options trading involves risk, including loss of capital. Same-day options can change value rapidly. Automation does not guarantee profits or prevent losses.",
  },
  {
    stage: 4,
    subject: "Meet Flame: our afternoon trade agent",
    preview: "An afternoon approach designed with smaller accounts in mind.",
    title: ["Meet Flame."],
    subtitle: "Afternoon opportunities. A measured approach.",
    paragraphs: [
      { text: "You’ve met Spark. Now meet Flame, our afternoon trade agent, designed with smaller accounts and a more measured approach to trading in mind." },
      { text: "Flame looks for qualifying bull put spread opportunities later in the trading day. Its intended profile is lower risk and lower return potential than Spark, with an emphasis on more gradual account growth. That is a design objective, not a promise of steady gains or protection from losses." },
      { lead: "The afternoon approach.", text: "Flame evaluates setups during its afternoon trading window and enters only when its strategy conditions are met. Some sessions may not produce a qualifying trade." },
      { lead: "The strategy.", text: "A bull put spread pairs a sold put with a purchased put at a lower strike. It collects a net credit and establishes a defined maximum loss for the spread at entry. The strategy has a bullish outlook and can lose money if the market falls." },
      { lead: "The account fit.", text: "Flame is built with smaller accounts in mind. Contract quantity scales with account size under its position-sizing rules, subject to minimum capital and brokerage requirements." },
      { lead: "The exit plan.", text: "Predefined targets and stops guide each position. Execution prices can differ from the intended exit, particularly when markets move quickly." },
      { text: "Flame brings the same focus on automation and visibility to a different part of the trading day. You’ll be able to follow its activity and review completed trades through IronForge." },
      { text: "In the coming weeks, we’ll share the account requirements and next steps so you can understand what’s needed before getting started." },
      { text: "Thank you for following along as we build." },
    ],
    disclosure: "Options trading involves risk, including loss of capital. Lower intended risk does not make a strategy risk-free. Automation and stop rules do not guarantee profits or prevent losses.",
  },
  {
    stage: 5,
    subject: "Your money stays in your brokerage.",
    preview: "How IronForge connects trading, account visibility, and your authorization.",
    title: ["Connected trading.", "Clear visibility."],
    paragraphs: [
      { text: "You’ve met Spark and Flame. Now we want to explain how IronForge works with your brokerage account—and where your money stays." },
      { text: "Your funds remain in your own brokerage account. You don’t transfer your trading capital to IronForge. Instead, you authorize a connection that allows your selected trade agent to place and manage trades within that account." },
      { lead: "Your brokerage holds your funds.", text: "Your cash and positions remain with your broker. IronForge provides the technology that connects your account to automated trading." },
      { lead: "Your authorization enables trading.", text: "Once connected and enabled, your selected agent can execute trades according to its predefined rules. Those trades affect your real account balance and can result in gains or losses." },
      { lead: "Your activity stays visible.", text: "The Forge brings your connected account’s performance and agent activity into view. You can follow open positions and review completed trades and results in the Ledger. Your brokerage statements remain the official record of your account." },
      { lead: "Your setup starts with a choice.", text: "Before enabling an agent, you’ll review its strategy, requirements, and trading authorization. We’ll also explain the available trading controls and how they affect new entries and positions already open." },
      { text: "Our goal is to make automated trading easier to follow, with a clear view of what your agent is doing and how those trades affect your account." },
      { text: "Thank you for following along as we build IronForge." },
    ],
    disclosure: "Options trading involves risk, including loss of capital. Keeping funds in your brokerage account does not eliminate trading risk. Automation does not guarantee profits or prevent losses.",
  },
  {
    stage: 6,
    subject: "Meet Tradier, IronForge's brokerage partner",
    preview: "The brokerage platform connecting your account to IronForge automation.",
    title: ["Your account.", "Connected through Tradier."],
    paragraphs: [
      { text: "As we prepare IronForge for launch, we’re excited to introduce Tradier Brokerage, our brokerage platform partner." },
      { text: "Tradier provides the brokerage connection that allows eligible IronForge users to keep their funds in their own brokerage account while an authorized trade agent places and manages trades through the IronForge experience." },
      { lead: "Your funds stay with your broker.", text: "You won’t deposit trading capital with IronForge. Your cash, positions, and account activity remain in your Tradier brokerage account." },
      { lead: "One secure connection powers the experience.", text: "During onboarding, eligible users will connect and authorize their Tradier account. That connection allows the selected IronForge agent to submit and manage trades according to its predefined strategy rules." },
      { lead: "IronForge makes the activity easier to follow.", text: "The Forge provides a clear view of agent activity and account performance, while the Ledger organizes completed trades and results. Tradier’s records and statements remain the official record of the brokerage account." },
      { lead: "You remain responsible for your account.", text: "You’ll review the strategy, risks, account requirements, and trading authorization before enabling automation. Trades placed through the connection affect your real account and may produce gains or losses." },
      { text: "Tradier gives IronForge the brokerage foundation needed to connect automated execution with the visibility we’re building for busy traders." },
      { text: "Thank you for following along as we build IronForge." },
    ],
    disclosure: "Brokerage services are provided by Tradier Brokerage. Options trading involves risk, including loss of capital. Account approval and trading permissions are determined by the brokerage. Automation does not guarantee profits or prevent losses.",
  },
]

/** The copy for one stage (1-6), or undefined when out of range. */
export function dripEmailForStage(stage: number): DripEmail | undefined {
  return DRIP_EMAILS.find((e) => e.stage === stage)
}
