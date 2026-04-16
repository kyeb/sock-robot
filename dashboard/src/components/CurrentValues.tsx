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
        <ValueDisplay label="YR" value={sample?.yr} unit="°/s" color={orientColors[2]} precision={1} />
      </div>
      {/* Controller */}
      <div className="flex gap-3">
        <ValueDisplay label="PID" value={sample?.pid} unit="%" color="#00ff88" precision={1} />
        <ValueDisplay label="TP" value={sample?.tp} unit="°" color="#00fff5" precision={2} />
        <ValueDisplay label="PC" value={sample?.pc} unit="" color="#bb66ff" precision={3} />
        <ValueDisplay label="YC" value={sample?.yc} unit="" color="#ffb000" precision={2} />
      </div>
      {/* Encoders */}
      <div className="flex gap-3">
        <ValueDisplay label="E1" value={sample?.e1} unit="ct" color={CHART_COLORS.encoders?.[0] ?? '#888'} precision={0} />
        <ValueDisplay label="E2" value={sample?.e2} unit="ct" color={CHART_COLORS.encoders?.[1] ?? '#888'} precision={0} />
        <ValueDisplay label="V1" value={sample?.v1} unit="r/s" color={CHART_COLORS.encoders?.[0] ?? '#888'} precision={1} />
        <ValueDisplay label="V2" value={sample?.v2} unit="r/s" color={CHART_COLORS.encoders?.[1] ?? '#888'} precision={1} />
      </div>
      {/* Temp */}
      <div className="flex gap-3">
        <ValueDisplay label="T" value={sample?.temp} unit="°C" color="#555" precision={1} />
      </div>
    </div>
  )
}
