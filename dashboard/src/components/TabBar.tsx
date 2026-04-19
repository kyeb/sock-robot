import type { ViewTab } from '~/lib/types'
import { CHART_COLORS, CYAN, PURPLE } from '~/lib/colors'

interface TabBarProps {
  active: ViewTab
  onChange: (tab: ViewTab) => void
}

const TABS: { id: ViewTab; label: string; color: string; separated?: boolean }[] = [
  { id: 'all', label: 'ALL', color: CYAN },
  { id: 'accel', label: 'ACCEL', color: CHART_COLORS.accel[0] },
  { id: 'gyro', label: 'GYRO', color: CHART_COLORS.gyro[0] },
  { id: 'orientation', label: 'ORIENT', color: CHART_COLORS.orientation[0] },
  { id: 'encoders', label: 'ENCODERS', color: CHART_COLORS.encoders[0] },
  { id: 'control', label: 'CONTROL', color: CHART_COLORS.control[0] },
  { id: 'drive', label: 'DRIVE', color: PURPLE, separated: true },
]

export function TabBar({ active, onChange }: TabBarProps) {
  return (
    <div className="flex gap-1 border-b border-[#222]">
      {TABS.map(({ id, label, color, separated }) => {
        const isActive = active === id
        return (
          <button
            key={id}
            onClick={() => onChange(id)}
            className={`px-6 py-2 text-xs tracking-widest uppercase transition-colors duration-150 cursor-pointer ${separated ? 'ml-auto' : ''}`}
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
