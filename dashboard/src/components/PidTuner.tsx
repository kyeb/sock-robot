import { useState, useCallback, useEffect } from 'react'

interface PidTunerProps {
  sendCommand: (cmd: string) => void
  connected: boolean
}

interface ParamRowProps {
  label: string
  value: number
  step: number
  min: number
  max: number
  precision: number
  onChange: (v: number) => void
  disabled: boolean
}

function ParamRow({ label, value, step, min, max, precision, onChange, disabled }: ParamRowProps) {
  return (
    <div className={`flex items-center gap-2 ${disabled ? 'opacity-30 pointer-events-none' : ''}`}>
      <span className="text-[10px] tracking-widest text-[#444] w-16">{label}</span>
      <button
        className="w-7 h-7 bg-[#1a1a24] border border-[#333] text-[#00fff5] hover:bg-[#252535] active:bg-[#333] text-sm"
        disabled={disabled}
        onClick={() => onChange(Math.max(min, +(value - step).toFixed(precision + 1)))}
      >
        −
      </button>
      <span className="text-sm tabular-nums text-[#00fff5] w-16 text-center">
        {value.toFixed(precision)}
      </span>
      <button
        className="w-7 h-7 bg-[#1a1a24] border border-[#333] text-[#00fff5] hover:bg-[#252535] active:bg-[#333] text-sm"
        disabled={disabled}
        onClick={() => onChange(Math.min(max, +(value + step).toFixed(precision + 1)))}
      >
        +
      </button>
    </div>
  )
}

export function PidTuner({ sendCommand, connected }: PidTunerProps) {
  const [kp, setKp] = useState(15.0)
  const [ki, setKi] = useState(40.0)
  const [kd, setKd] = useState(0.55)
  const [target, setTarget] = useState(0.0)
  const [enabled, setEnabled] = useState(false)
  const [capturing, setCapturing] = useState(false)

  useEffect(() => {
    if (!connected) {
      setEnabled(false)
      setCapturing(false)
    }
  }, [connected])

  const updateParam = useCallback(
    (cmd: string, value: number, setter: (v: number) => void) => {
      setter(value)
      sendCommand(`${cmd} ${value}`)
    },
    [sendCommand],
  )

  const togglePid = useCallback(() => {
    if (enabled) {
      sendCommand('PID_OFF')
      setEnabled(false)
    } else {
      // Send current gains before enabling
      sendCommand(`KP ${kp}`)
      sendCommand(`KI ${ki}`)
      sendCommand(`KD ${kd}`)
      sendCommand(`TARGET ${target}`)
      sendCommand('PID_ON')
      setEnabled(true)
    }
  }, [enabled, kp, ki, kd, target, sendCommand])

  const toggleCapture = useCallback(() => {
    if (capturing) {
      sendCommand('CAPTURE_STOP')
      setCapturing(false)
    } else {
      sendCommand('CAPTURE_START')
      setCapturing(true)
    }
  }, [capturing, sendCommand])

  return (
    <div className="border border-[#181818] p-3 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-[10px] tracking-[0.3em] uppercase text-[#444]">
          pid controller
        </span>
        <div className="flex gap-2">
        <button
          className={`w-24 py-2 text-sm tracking-widest uppercase border font-bold text-center ${
            !connected
              ? 'opacity-30 pointer-events-none bg-[#1a1a24] border-[#333] text-[#666]'
              : capturing
                ? 'bg-[#221100] border-[#ff4444] text-[#ff4444] animate-pulse'
                : 'bg-[#1a1a24] border-[#333] text-[#666] hover:text-[#c0c0c0] hover:border-[#555]'
          }`}
          disabled={!connected}
          onClick={toggleCapture}
        >
          {capturing ? 'REC' : 'CAPTURE'}
        </button>
        <button
          className={`w-20 py-2 text-sm tracking-widest uppercase border font-bold text-center ${
            !connected
              ? 'opacity-30 pointer-events-none bg-[#1a1a24] border-[#333] text-[#666]'
              : enabled
                ? 'bg-[#002211] border-[#00ff88] text-[#00ff88]'
                : 'bg-[#1a1a24] border-[#333] text-[#666] hover:text-[#c0c0c0] hover:border-[#555]'
          }`}
          disabled={!connected}
          onClick={togglePid}
        >
          {enabled ? 'ON' : 'OFF'}
        </button>
        </div>
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-1">
        <ParamRow label="KP" value={kp} step={0.5} min={0} max={50} precision={1}
          disabled={!connected} onChange={(v) => updateParam('KP', v, setKp)} />
        <ParamRow label="KI" value={ki} step={1} min={0} max={200} precision={1}
          disabled={!connected} onChange={(v) => updateParam('KI', v, setKi)} />
        <ParamRow label="KD" value={kd} step={0.05} min={0} max={50} precision={2}
          disabled={!connected} onChange={(v) => updateParam('KD', v, setKd)} />
        <ParamRow label="TARGET" value={target} step={0.1} min={-15} max={15} precision={1}
          disabled={!connected} onChange={(v) => updateParam('TARGET', v, setTarget)} />
      </div>
    </div>
  )
}
