import { useEffect, useRef, useState } from 'react'

export function useSampleRate(sampleCount: number): number {
  const [hz, setHz] = useState(0)
  const countRef = useRef(sampleCount)
  const prevCountRef = useRef(0)
  const prevTimeRef = useRef(performance.now())

  // Keep ref in sync with latest value
  countRef.current = sampleCount

  useEffect(() => {
    const interval = setInterval(() => {
      const now = performance.now()
      const dt = (now - prevTimeRef.current) / 1000
      const dCount = countRef.current - prevCountRef.current

      if (dt > 0) {
        setHz(Math.round(dCount / dt))
      }

      prevCountRef.current = countRef.current
      prevTimeRef.current = now
    }, 1000)

    return () => clearInterval(interval)
  }, [])

  return hz
}
