import { useCallback, useEffect, useRef, useState } from 'react'
import type { IMUSample, ConnectionStatus } from '~/lib/types'
import { NUM_COLUMNS } from '~/lib/types'

const MAX_POINTS = 6000 // 2 minutes at 50Hz
const LATEST_THROTTLE_MS = 50 // update React state at ~20Hz

function createEmptyBuffer(): number[][] {
  return Array.from({ length: NUM_COLUMNS }, () => [])
}

function appendToBuffer(buf: number[][], sample: IMUSample) {
  const values = [
    sample.t / 1000,
    sample.ax, sample.ay, sample.az,
    sample.gx, sample.gy, sample.gz,
    sample.roll, sample.pitch, sample.ap ?? 0, sample.yr ?? 0,
    sample.v1 ?? 0, sample.v2 ?? 0,
    sample.pid ?? 0, sample.tp ?? 0, sample.pc ?? 0, sample.yc ?? 0,
  ]
  for (let i = 0; i < NUM_COLUMNS; i++) {
    buf[i].push(values[i])
    if (buf[i].length > MAX_POINTS) {
      buf[i].shift()
    }
  }
}

export function useIMUSocket() {
  const dataRef = useRef<number[][]>(createEmptyBuffer())
  const wsRef = useRef<WebSocket | null>(null)
  const [latest, setLatest] = useState<IMUSample | null>(null)
  const [status, setStatus] = useState<ConnectionStatus>('connecting')
  const [sampleCount, setSampleCount] = useState(0)
  const [hz, setHz] = useState(0)

  const sendCommand = useCallback((cmd: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(cmd)
    }
  }, [])

  useEffect(() => {
    let rawCount = 0
    let hzPrevCount = 0
    let hzPrevTime = performance.now()
    let lastLatestTime = 0
    let wsOpen = false

    const ws = new WebSocket(`ws://${location.host}/ws`)
    wsRef.current = ws

    ws.onclose = () => setStatus('disconnected')
    ws.onerror = () => ws.close()

    ws.onmessage = (e) => {
      if (e.data[0] !== '{') return
      const msg = JSON.parse(e.data)

      // Bridge status messages are the source of truth
      if ('bridge' in msg) {
        setStatus(msg.bridge === 'connected' ? 'connected' : 'disconnected')
        return
      }

      // IMU data — receiving data means bridge is connected
      if (!wsOpen) {
        wsOpen = true
        setStatus('connected')
      }
      const d = msg as IMUSample
      appendToBuffer(dataRef.current, d)
      rawCount++

      const now = performance.now()
      if (now - lastLatestTime >= LATEST_THROTTLE_MS) {
        lastLatestTime = now
        setLatest(d)
        setSampleCount(rawCount)
      }
    }

    // Hz calculation at 1Hz
    const tick = setInterval(() => {
      const now = performance.now()
      const dt = (now - hzPrevTime) / 1000
      if (dt >= 0.9) {
        setHz(Math.round((rawCount - hzPrevCount) / dt))
        hzPrevCount = rawCount
        hzPrevTime = now
      }
    }, 1000)

    return () => {
      ws.close()
      clearInterval(tick)
    }
  }, [])

  return { dataRef, latest, status, sampleCount, hz, sendCommand }
}
