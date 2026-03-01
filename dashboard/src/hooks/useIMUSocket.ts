import { useEffect, useRef, useState, useCallback } from 'react'
import type { IMUSample, ConnectionStatus } from '~/lib/types'

const NUM_COLUMNS = 10 // t, ax, ay, az, gx, gy, gz, roll, pitch, yaw
const MAX_POINTS = 6000 // 2 minutes at 50Hz

function createEmptyBuffer(): number[][] {
  return Array.from({ length: NUM_COLUMNS }, () => [])
}

function appendToBuffer(buf: number[][], sample: IMUSample) {
  const values = [
    sample.t / 1000, // convert ms to seconds
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
  const sampleCountRef = useRef(0)
  const [sampleCount, setSampleCount] = useState(0)

  // Batch sample count updates at ~4Hz to avoid excessive re-renders
  const countIntervalRef = useRef<ReturnType<typeof setInterval>>(undefined)

  const connect = useCallback(() => {
    if (typeof window === 'undefined') return

    const ws = new WebSocket(`ws://${location.host}/ws`)

    ws.onopen = () => {
      setStatus('connected')
    }

    ws.onclose = () => {
      setStatus('disconnected')
      // Reconnect with backoff
      setTimeout(connect, 2000)
    }

    ws.onerror = () => {
      ws.close()
    }

    ws.onmessage = (e) => {
      const d: IMUSample = JSON.parse(e.data)
      appendToBuffer(dataRef.current, d)
      sampleCountRef.current++
      setLatest(d)
    }

    return ws
  }, [])

  useEffect(() => {
    const ws = connect()

    // Update sample count display at 4Hz
    countIntervalRef.current = setInterval(() => {
      setSampleCount(sampleCountRef.current)
    }, 250)

    return () => {
      ws?.close()
      if (countIntervalRef.current) clearInterval(countIntervalRef.current)
    }
  }, [connect])

  return { dataRef, latest, status, sampleCount }
}
