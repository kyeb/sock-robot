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
  // Inner loop (angle)
  const [kp, setKp] = useState(10.0)
  const [kd, setKd] = useState(0.4)
  // Outer loop (velocity)
  const [vkp, setVkp] = useState(0.05)
  const [vki, setVki] = useState(0.0)
  const [vkd, setVkd] = useState(0.0)
  const [vilim, setVilim] = useState(4.0)
  // Position hold
  const [pkp, setPkp] = useState(0.3)
  const [pkd, setPkd] = useState(0.2)
  // Yaw correction
  const [ykp, setYkp] = useState(0.5)
  // Bias / target
  const [pbias, setPbias] = useState(1.35)
  const [tvel, setTvel] = useState(0.0)
  const [tyaw, setTyaw] = useState(0.0)
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
      sendCommand(`KD ${kd}`)
      sendCommand(`VKP ${vkp}`)
      sendCommand(`VKI ${vki}`)
      sendCommand(`VKD ${vkd}`)
      sendCommand(`VILIM ${vilim}`)
      sendCommand(`PKP ${pkp}`)
      sendCommand(`PKD ${pkd}`)
      sendCommand(`YKP ${ykp}`)
      sendCommand(`PBIAS ${pbias}`)
      sendCommand(`TVEL ${tvel}`)
      sendCommand(`TYAW ${tyaw}`)
      sendCommand('PID_ON')
      setEnabled(true)
    }
  }, [enabled, kp, kd, vkp, vki, vkd, vilim, pkp, pkd, ykp, pbias, tvel, tyaw, sendCommand])

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
        <ParamRow label="KP" value={kp} step={1.0} min={0} max={50} precision={1}
          disabled={!connected} onChange={(v) => updateParam('KP', v, setKp)} />
        <ParamRow label="KD" value={kd} step={0.1} min={0} max={50} precision={2}
          disabled={!connected} onChange={(v) => updateParam('KD', v, setKd)} />
        <ParamRow label="VKP" value={vkp} step={0.1} min={0} max={50} precision={2}
          disabled={!connected} onChange={(v) => updateParam('VKP', v, setVkp)} />
        <ParamRow label="VKI" value={vki} step={0.1} min={0} max={200} precision={2}
          disabled={!connected} onChange={(v) => updateParam('VKI', v, setVki)} />
        <ParamRow label="VKD" value={vkd} step={0.02} min={0} max={50} precision={2}
          disabled={!connected} onChange={(v) => updateParam('VKD', v, setVkd)} />
        <ParamRow label="VILIM" value={vilim} step={1.0} min={0.1} max={20} precision={1}
          disabled={!connected} onChange={(v) => updateParam('VILIM', v, setVilim)} />
        <ParamRow label="PKP" value={pkp} step={0.1} min={0} max={10} precision={2}
          disabled={!connected} onChange={(v) => updateParam('PKP', v, setPkp)} />
        <ParamRow label="PKD" value={pkd} step={0.02} min={0} max={10} precision={2}
          disabled={!connected} onChange={(v) => updateParam('PKD', v, setPkd)} />
        <ParamRow label="YKP" value={ykp} step={0.2} min={0} max={10} precision={2}
          disabled={!connected} onChange={(v) => updateParam('YKP', v, setYkp)} />
        <ParamRow label="PBIAS" value={pbias} step={0.01} min={-5} max={5} precision={2}
          disabled={!connected} onChange={(v) => updateParam('PBIAS', v, setPbias)} />
        <ParamRow label="TVEL" value={tvel} step={0.5} min={-5} max={5} precision={2}
          disabled={!connected} onChange={(v) => updateParam('TVEL', v, setTvel)} />
        <ParamRow label="TYAW" value={tyaw} step={0.5} min={-5} max={5} precision={2}
          disabled={!connected} onChange={(v) => updateParam('TYAW', v, setTyaw)} />
      </div>
    </div>
  )
}
