'use client'

/**
 * A single required-consent checkbox row. Shared by /signup (SignupClient) and
 * /signup/google-consent (GoogleConsentClient) so the SAME 3 consents render
 * identically no matter which path a visitor lands on — the whole point of this
 * change is that Google sign-up asks for exactly what the password form asks for.
 */
export default function ConsentCheckbox({
  checked,
  error,
  onChange,
  children,
}: {
  checked: boolean
  error?: string
  onChange: (v: boolean) => void
  children: React.ReactNode
}) {
  return (
    <label className="flex cursor-pointer items-start gap-2.5 text-xs leading-relaxed text-gray-400">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className={`mt-0.5 h-4 w-4 shrink-0 rounded border bg-black/40 accent-amber-600 ${error ? 'border-red-600' : 'border-white/20'}`}
      />
      <span>{children}</span>
    </label>
  )
}
