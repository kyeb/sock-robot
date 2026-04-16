import type { ConnectionStatus } from '~/lib/types'

interface StatusBarProps {
  status: ConnectionStatus
  hz: number
  samples: number
  loopHz: number | null
}

const STATUS_COLORS: Record<ConnectionStatus, string> = {
  connecting: '#ffb000',
  connected: '#00ff88',
  disconnected: '#ff4444',
}

const STATUS_LABELS: Record<ConnectionStatus, string> = {
  connecting: 'CONNECTING',
  connected: 'CONNECTED',
  disconnected: 'DISCONNECTED',
}

export function StatusBar({ status, hz, samples, loopHz }: StatusBarProps) {
  const color = STATUS_COLORS[status]
  const label = STATUS_LABELS[status]

  const loopColor =
    loopHz == null ? '#555' : loopHz >= 190 ? '#00ff88' : loopHz >= 150 ? '#ffb000' : '#ff4444'

  return (
    <div className="flex items-center gap-4 py-2 text-[10px] tracking-widest uppercase text-[#444] border-t border-[#181818]">
      <div className="flex items-center gap-2">
        <span
          className={`inline-block w-2 h-2 ${status === 'connected' ? 'pulse-indicator' : ''}`}
          style={{ backgroundColor: color }}
        />
        <span style={{ color }}>{label}</span>
      </div>
      <span className="text-[#555]">|</span>
      <span>
        tele <span className="text-[#00fff5]">{hz}</span> Hz
      </span>
      <span className="text-[#555]">|</span>
      <span>
        loop <span style={{ color: loopColor }}>{loopHz != null ? loopHz.toFixed(0) : '—'}</span> Hz
      </span>
      <span className="text-[#555]">|</span>
      <span>
        <span className="text-[#c0c0c0]">{samples.toLocaleString()}</span> samples
      </span>
    </div>
  )
}
