import { useCallback, useEffect, useRef, useState } from 'react'

interface DriveProps {
  sendCommand: (cmd: string) => void
  connected: boolean
}

const MAX_TVEL = 1.5
const MAX_TYAW = 1.5
const RAMP_SECONDS = 0.8
const SEND_HZ = 20
const DEADBAND = 0.01

const ARROW_KEYS = new Set(['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'])

type KeyState = { up: boolean; down: boolean; left: boolean; right: boolean }

const EMPTY_KEYS: KeyState = { up: false, down: false, left: false, right: false }

export function Drive({ sendCommand, connected }: DriveProps) {
  const [focused, setFocused] = useState(false)
  const [display, setDisplay] = useState({ tvel: 0, tyaw: 0, ...EMPTY_KEYS })

  const keysRef = useRef<KeyState>({ ...EMPTY_KEYS })
  const curRef = useRef({ tvel: 0, tyaw: 0 })
  const lastSentRef = useRef({ tvel: 0, tyaw: 0 })
  const lastSendTimeRef = useRef(0)
  const lastTickTimeRef = useRef(0)

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape') {
      e.currentTarget.blur()
      return
    }
    if (!ARROW_KEYS.has(e.key)) return
    e.preventDefault()
    if (e.key === 'ArrowUp') keysRef.current.up = true
    else if (e.key === 'ArrowDown') keysRef.current.down = true
    else if (e.key === 'ArrowLeft') keysRef.current.left = true
    else if (e.key === 'ArrowRight') keysRef.current.right = true
  }, [])

  const handleKeyUp = useCallback((e: React.KeyboardEvent) => {
    if (!ARROW_KEYS.has(e.key)) return
    if (e.key === 'ArrowUp') keysRef.current.up = false
    else if (e.key === 'ArrowDown') keysRef.current.down = false
    else if (e.key === 'ArrowLeft') keysRef.current.left = false
    else if (e.key === 'ArrowRight') keysRef.current.right = false
  }, [])

  const handleBlur = useCallback(() => {
    setFocused(false)
    keysRef.current = { ...EMPTY_KEYS }
  }, [])

  useEffect(() => {
    let rafId = 0
    const tick = (now: number) => {
      const last = lastTickTimeRef.current || now
      const dt = Math.min((now - last) / 1000, 0.1)
      lastTickTimeRef.current = now

      const { up, down, left, right } = keysRef.current
      const targetTvel = (up ? MAX_TVEL : 0) + (down ? -MAX_TVEL : 0)
      const targetTyaw = (right ? MAX_TYAW : 0) + (left ? -MAX_TYAW : 0)

      const tvelStep = (MAX_TVEL / RAMP_SECONDS) * dt
      const tyawStep = (MAX_TYAW / RAMP_SECONDS) * dt
      const lerp = (cur: number, tgt: number, step: number) => {
        if (cur < tgt) return Math.min(cur + step, tgt)
        if (cur > tgt) return Math.max(cur - step, tgt)
        return cur
      }
      curRef.current.tvel = lerp(curRef.current.tvel, targetTvel, tvelStep)
      curRef.current.tyaw = lerp(curRef.current.tyaw, targetTyaw, tyawStep)

      if (now - lastSendTimeRef.current >= 1000 / SEND_HZ) {
        lastSendTimeRef.current = now
        const { tvel, tyaw } = curRef.current
        if (Math.abs(tvel - lastSentRef.current.tvel) > DEADBAND) {
          sendCommand(`TVEL ${tvel.toFixed(2)}`)
          lastSentRef.current.tvel = tvel
        }
        if (Math.abs(tyaw - lastSentRef.current.tyaw) > DEADBAND) {
          sendCommand(`TYAW ${tyaw.toFixed(2)}`)
          lastSentRef.current.tyaw = tyaw
        }
        setDisplay({ tvel, tyaw, up, down, left, right })
      }

      rafId = requestAnimationFrame(tick)
    }
    rafId = requestAnimationFrame(tick)

    return () => {
      cancelAnimationFrame(rafId)
      sendCommand('TVEL 0')
      sendCommand('TYAW 0')
    }
  }, [sendCommand])

  const arrowCls = (active: boolean) => {
    if (active) return 'w-14 h-14 border-2 flex items-center justify-center text-xl bg-[#3a1a55] border-[#bb66ff] text-white shadow-[0_0_16px_rgba(187,102,255,0.6)] transition-colors'
    if (focused) return 'w-14 h-14 border flex items-center justify-center text-xl bg-[#1a1024] border-[#5a3a7a] text-[#888] transition-colors'
    return 'w-14 h-14 border flex items-center justify-center text-xl bg-[#1a1a24] border-[#333] text-[#555] transition-colors'
  }

  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (document.activeElement === e.currentTarget) {
      e.preventDefault()
      e.currentTarget.blur()
    }
  }

  return (
    <div
      tabIndex={0}
      onFocus={() => setFocused(true)}
      onBlur={handleBlur}
      onKeyDown={handleKeyDown}
      onKeyUp={handleKeyUp}
      onMouseDown={handleMouseDown}
      className={`flex-1 min-h-0 flex flex-col items-center justify-center gap-8 outline-none cursor-pointer select-none transition-all ${
        !connected
          ? 'border-2 border-[#333] opacity-40'
          : focused
            ? 'border-4 border-[#bb66ff] shadow-[0_0_40px_rgba(187,102,255,0.35),inset_0_0_40px_rgba(187,102,255,0.08)]'
            : 'border-2 border-[#333] hover:border-[#555]'
      }`}
      style={{ background: focused ? 'rgba(187, 102, 255, 0.06)' : 'transparent' }}
    >
      <div
        className={`tracking-[0.3em] uppercase transition-all ${
          !connected
            ? 'text-[10px] text-[#666]'
            : focused
              ? 'text-sm text-[#bb66ff] font-bold animate-pulse'
              : 'text-[10px] text-[#666]'
        }`}
      >
        {!connected
          ? 'disconnected'
          : focused
            ? '● drive active — arrow keys · esc to exit'
            : 'click to focus'}
      </div>

      <div className="flex flex-col items-center gap-1">
        <div className={arrowCls(display.up)}>▲</div>
        <div className="flex gap-1">
          <div className={arrowCls(display.left)}>◀</div>
          <div className={arrowCls(display.down)}>▼</div>
          <div className={arrowCls(display.right)}>▶</div>
        </div>
      </div>

      <div className="flex gap-10 text-sm">
        <div>
          <span className="text-[#444] tracking-widest text-[10px] mr-2">TVEL</span>
          <span className="tabular-nums text-[#bb66ff]">{display.tvel.toFixed(2)}</span>
        </div>
        <div>
          <span className="text-[#444] tracking-widest text-[10px] mr-2">TYAW</span>
          <span className="tabular-nums text-[#bb66ff]">{display.tyaw.toFixed(2)}</span>
        </div>
      </div>

      <div className="text-[10px] text-[#444] tracking-widest uppercase">
        caps: ±{MAX_TVEL.toFixed(1)} tvel · ±{MAX_TYAW.toFixed(1)} tyaw
      </div>
    </div>
  )
}
