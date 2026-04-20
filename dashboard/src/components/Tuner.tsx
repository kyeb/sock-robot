import { useState, useCallback, useEffect } from 'react'

interface TunerProps {
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

export function Tuner({ sendCommand, connected }: TunerProps) {
  // LQR gains (~half of computed; scale all four together as a single
  // aggressiveness knob)
  const [k1, setK1] = useState(9.5)
  const [k2, setK2] = useState(0.8)
  const [k3, setK3] = useState(2.0)
  const [k4, setK4] = useState(8.7)
  const [k5, setK5] = useState(5.0)
  const [kyaw, setKyaw] = useState(0.5)
  // Equilibrium angle (measured from fit_eq.py) / targets
  const [theq, setTheq] = useState(1.22)
  const [tvel, setTvel] = useState(0.0)
  const [tyaw, setTyaw] = useState(0.0)
  const [enabled, setEnabled] = useState(false)
  const [capturing, setCapturing] = useState(false)
  const [logFast, setLogFast] = useState(false)
  const [prbs, setPrbs] = useState(false)

  useEffect(() => {
    if (!connected) {
      setEnabled(false)
      setCapturing(false)
      setLogFast(false)
      setPrbs(false)
    }
  }, [connected])

  const updateParam = useCallback(
    (cmd: string, value: number, setter: (v: number) => void) => {
      setter(value)
      sendCommand(`${cmd} ${value}`)
    },
    [sendCommand],
  )

  const toggleEnable = useCallback(() => {
    if (enabled) {
      sendCommand('DISABLE')
      setEnabled(false)
    } else {
      // Send current gains before enabling
      sendCommand(`K1 ${k1}`)
      sendCommand(`K2 ${k2}`)
      sendCommand(`K3 ${k3}`)
      sendCommand(`K4 ${k4}`)
      sendCommand(`K5 ${k5}`)
      sendCommand(`KYAW ${kyaw}`)
      sendCommand(`THEQ ${theq}`)
      sendCommand(`TVEL ${tvel}`)
      sendCommand(`TYAW ${tyaw}`)
      sendCommand('ENABLE')
      setEnabled(true)
    }
  }, [enabled, k1, k2, k3, k4, k5, kyaw, theq, tvel, tyaw, sendCommand])

  const toggleCapture = useCallback(() => {
    if (capturing) {
      sendCommand('CAPTURE_STOP')
      setCapturing(false)
    } else {
      sendCommand('CAPTURE_START')
      setCapturing(true)
    }
  }, [capturing, sendCommand])

  const toggleLogFast = useCallback(() => {
    if (logFast) {
      sendCommand('LOG_SLOW')
      setLogFast(false)
    } else {
      sendCommand('LOG_FAST')
      setLogFast(true)
      setTimeout(() => setLogFast(false), 10000)
    }
  }, [logFast, sendCommand])

  const togglePrbs = useCallback(() => {
    if (prbs) {
      sendCommand('PRBS_OFF')
      setPrbs(false)
    } else {
      sendCommand('PRBS_ON')
      setPrbs(true)
    }
  }, [prbs, sendCommand])

  return (
    <div className="border border-[#181818] p-3 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-[10px] tracking-[0.3em] uppercase text-[#444]">
          lqr controller
        </span>
        <div className="flex gap-2">
        <button
          className={`px-2 py-2 text-[10px] tracking-widest uppercase border font-bold text-center ${
            !connected
              ? 'opacity-30 pointer-events-none bg-[#1a1a24] border-[#333] text-[#666]'
              : prbs
                ? 'bg-[#1a1a20] border-[#ff8800] text-[#ff8800]'
                : 'bg-[#1a1a24] border-[#333] text-[#666] hover:text-[#c0c0c0] hover:border-[#555]'
          }`}
          disabled={!connected}
          onClick={togglePrbs}
        >
          {prbs ? 'PRBS' : 'PRBS'}
        </button>
        <button
          className={`px-2 py-2 text-[10px] tracking-widest uppercase border font-bold text-center ${
            !connected
              ? 'opacity-30 pointer-events-none bg-[#1a1a24] border-[#333] text-[#666]'
              : logFast
                ? 'bg-[#001122] border-[#00aaff] text-[#00aaff] animate-pulse'
                : 'bg-[#1a1a24] border-[#333] text-[#666] hover:text-[#c0c0c0] hover:border-[#555]'
          }`}
          disabled={!connected}
          onClick={toggleLogFast}
        >
          {logFast ? '200Hz' : '200Hz'}
        </button>
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
          onClick={toggleEnable}
        >
          {enabled ? 'ON' : 'OFF'}
        </button>
        </div>
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-1">
        <ParamRow label="K1" value={k1} step={0.1} min={0} max={50} precision={2}
          disabled={!connected} onChange={(v) => updateParam('K1', v, setK1)} />
        <ParamRow label="K2" value={k2} step={0.02} min={0} max={50} precision={2}
          disabled={!connected} onChange={(v) => updateParam('K2', v, setK2)} />
        <ParamRow label="K3" value={k3} step={0.2} min={0} max={30} precision={2}
          disabled={!connected} onChange={(v) => updateParam('K3', v, setK3)} />
        <ParamRow label="K4" value={k4} step={0.1} min={0} max={20} precision={2}
          disabled={!connected} onChange={(v) => updateParam('K4', v, setK4)} />
        <ParamRow label="K5" value={k5} step={0.02} min={0} max={10} precision={2}
          disabled={!connected} onChange={(v) => updateParam('K5', v, setK5)} />
        <ParamRow label="KYAW" value={kyaw} step={0.2} min={0} max={10} precision={2}
          disabled={!connected} onChange={(v) => updateParam('KYAW', v, setKyaw)} />
        <ParamRow label="THEQ" value={theq} step={0.01} min={-5} max={5} precision={2}
          disabled={!connected} onChange={(v) => updateParam('THEQ', v, setTheq)} />
        <ParamRow label="TVEL" value={tvel} step={0.5} min={-5} max={5} precision={2}
          disabled={!connected} onChange={(v) => updateParam('TVEL', v, setTvel)} />
        <ParamRow label="TYAW" value={tyaw} step={0.5} min={-5} max={5} precision={2}
          disabled={!connected} onChange={(v) => updateParam('TYAW', v, setTyaw)} />
      </div>
    </div>
  )
}
