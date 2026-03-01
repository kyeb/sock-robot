import { useEffect, useRef, useState } from 'react'

export function useSampleRate(sampleCount: number): number {
  const [hz, setHz] = useState(0)
  const prevCountRef = useRef(0)
  const prevTimeRef = useRef(performance.now())

  useEffect(() => {
    const interval = setInterval(() => {
      const now = performance.now()
      const dt = (now - prevTimeRef.current) / 1000
      const dCount = sampleCount - prevCountRef.current

      if (dt > 0) {
        setHz(Math.round(dCount / dt))
      }

      prevCountRef.current = sampleCount
      prevTimeRef.current = now
    }, 1000)

    return () => clearInterval(interval)
  }, [sampleCount])

  return hz
}
