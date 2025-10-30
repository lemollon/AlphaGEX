import { LucideIcon } from 'lucide-react'

interface StatusCardProps {
  icon: LucideIcon
  label: string
  value: string | number
  change?: string
  changeType?: 'positive' | 'negative' | 'neutral'
  subtitle?: string
}

export default function StatusCard({
  icon: Icon,
  label,
  value,
  change,
  changeType = 'neutral',
  subtitle,
}: StatusCardProps) {
  const changeColors = {
    positive: 'text-success',
    negative: 'text-danger',
    neutral: 'text-text-secondary',
  }

  return (
    <div className="card card-hover">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center space-x-2 mb-2">
            <Icon className="w-4 h-4 text-primary" />
            <span className="text-xs font-medium text-text-secondary uppercase tracking-wide">
              {label}
            </span>
          </div>

          <div className="text-2xl font-bold text-text-primary font-mono mb-1">
            {value}
          </div>

          {subtitle && (
            <div className="text-sm text-text-muted">
              {subtitle}
            </div>
          )}

          {change && (
            <div className={`text-sm font-medium ${changeColors[changeType]}`}>
              {change}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
