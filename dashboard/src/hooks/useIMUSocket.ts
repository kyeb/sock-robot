import { useEffect, useRef, useState } from 'react'
import type { IMUSample, ConnectionStatus } from '~/lib/types'

const NUM_COLUMNS = 10 // t, ax, ay, az, gx, gy, gz, roll, pitch, yaw
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
    sample.roll, sample.pitch, sample.yaw,
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
  const [latest, setLatest] = useState<IMUSample | null>(null)
  const [status, setStatus] = useState<ConnectionStatus>('connecting')
  const [sampleCount, setSampleCount] = useState(0)
  const [hz, setHz] = useState(0)

  useEffect(() => {
    let rawCount = 0
    let hzPrevCount = 0
    let hzPrevTime = performance.now()
    let lastLatestTime = 0

    const ws = new WebSocket(`ws://${location.host}/ws`)

    ws.onopen = () => setStatus('connected')

    ws.onclose = () => {
      setStatus('disconnected')
      // TODO: reconnect
    }

    ws.onerror = () => ws.close()

    ws.onmessage = (e) => {
      const d: IMUSample = JSON.parse(e.data)
      appendToBuffer(dataRef.current, d)
      rawCount++

      // Throttle React state updates to ~20Hz
      const now = performance.now()
      if (now - lastLatestTime >= LATEST_THROTTLE_MS) {
        lastLatestTime = now
        setLatest(d)
        setSampleCount(rawCount)
      }
    }

    // Hz calculation at 1Hz
    const hzInterval = setInterval(() => {
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
      clearInterval(hzInterval)
    }
  }, [])

  return { dataRef, latest, status, sampleCount, hz }
}
