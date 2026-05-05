export default function BriefingWisdom({ wisdom }: { wisdom: string | null }) {
  if (!wisdom) return null
  return (
    <blockquote
      className="border-l-4 border-amber-400 pl-5 my-4 text-amber-300 italic"
      style={{ fontFamily: 'Georgia, "Times New Roman", serif', fontSize: '1.4rem', lineHeight: 1.4 }}
    >
      &ldquo;{wisdom}&rdquo;
    </blockquote>
  )
}
