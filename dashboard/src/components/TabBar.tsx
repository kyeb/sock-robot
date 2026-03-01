import type { ChartTab } from '~/lib/types'
import { CHART_COLORS, CYAN } from '~/lib/colors'

interface TabBarProps {
  active: ChartTab
  onChange: (tab: ChartTab) => void
}

const TABS: { id: ChartTab; label: string; color: string }[] = [
  { id: 'all', label: 'ALL', color: CYAN },
  { id: 'accel', label: 'ACCEL', color: CHART_COLORS.accel[0] },
  { id: 'gyro', label: 'GYRO', color: CHART_COLORS.gyro[0] },
  { id: 'orientation', label: 'ORIENT', color: CHART_COLORS.orientation[0] },
]

export function TabBar({ active, onChange }: TabBarProps) {
  return (
    <div className="flex gap-1 border-b border-[#222]">
      {TABS.map(({ id, label, color }) => {
        const isActive = active === id
        return (
          <button
            key={id}
            onClick={() => onChange(id)}
            className="px-6 py-2 text-xs tracking-widest uppercase transition-colors duration-150 cursor-pointer"
            style={{
              color: isActive ? color : '#555',
              borderBottom: isActive ? `2px solid ${color}` : '2px solid transparent',
              background: isActive ? 'rgba(255,255,255,0.02)' : 'transparent',
            }}
          >
            {label}
          </button>
        )
      })}
    </div>
  )
}
