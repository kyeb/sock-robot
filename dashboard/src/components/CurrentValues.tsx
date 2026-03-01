import type { IMUSample } from '~/lib/types'
import { CHART_COLORS, CHART_UNITS } from '~/lib/colors'

interface CurrentValuesProps {
  sample: IMUSample | null
}

interface ValueDisplayProps {
  label: string
  value: number | undefined
  unit: string
  color: string
  precision?: number
}

function ValueDisplay({ label, value, unit, color, precision = 2 }: ValueDisplayProps) {
  const formatted = value != null ? value.toFixed(precision) : '—'
  return (
    <div className="flex items-baseline gap-2 min-w-[140px]">
      <span className="text-[10px] tracking-widest text-[#444] w-6">{label}</span>
      <span
        className="text-sm tabular-nums transition-colors duration-100"
        style={{ color }}
      >
        {formatted}
      </span>
      <span className="text-[10px] text-[#333]">{unit}</span>
    </div>
  )
}

export function CurrentValues({ sample }: CurrentValuesProps) {
  const accelColors = CHART_COLORS.accel
  const gyroColors = CHART_COLORS.gyro
  const orientColors = CHART_COLORS.orientation

  return (
    <div className="flex flex-wrap gap-x-6 gap-y-1 py-2 border-b border-[#181818]">
      {/* Accel */}
      <div className="flex gap-3">
        <ValueDisplay label="AX" value={sample?.ax} unit={CHART_UNITS.accel} color={accelColors[0]} />
        <ValueDisplay label="AY" value={sample?.ay} unit={CHART_UNITS.accel} color={accelColors[1]} />
        <ValueDisplay label="AZ" value={sample?.az} unit={CHART_UNITS.accel} color={accelColors[2]} />
      </div>
      {/* Gyro */}
      <div className="flex gap-3">
        <ValueDisplay label="GX" value={sample?.gx} unit={CHART_UNITS.gyro} color={gyroColors[0]} precision={3} />
        <ValueDisplay label="GY" value={sample?.gy} unit={CHART_UNITS.gyro} color={gyroColors[1]} precision={3} />
        <ValueDisplay label="GZ" value={sample?.gz} unit={CHART_UNITS.gyro} color={gyroColors[2]} precision={3} />
      </div>
      {/* Orientation */}
      <div className="flex gap-3">
        <ValueDisplay label="R" value={sample?.roll} unit={CHART_UNITS.orientation} color={orientColors[0]} precision={1} />
        <ValueDisplay label="P" value={sample?.pitch} unit={CHART_UNITS.orientation} color={orientColors[1]} precision={1} />
        <ValueDisplay label="Y" value={sample?.yaw} unit={CHART_UNITS.orientation} color={orientColors[2]} precision={1} />
      </div>
      {/* Temp */}
      <div className="flex gap-3">
        <ValueDisplay label="T" value={sample?.temp} unit="°C" color="#555" precision={1} />
      </div>
    </div>
  )
}
