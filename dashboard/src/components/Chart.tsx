import { useEffect, useRef } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { createChartOptions } from '~/lib/chartOptions'
import type { ChartTab } from '~/lib/types'
import { TAB_COLUMNS } from '~/lib/types'

interface ChartProps {
  dataRef: React.RefObject<number[][]>
  tab: ChartTab
  timeWindow: number
  visible: boolean
}

function extractSeries(buf: number[][], columns: number[]): uPlot.AlignedData {
  return columns.map(i => buf[i]) as uPlot.AlignedData
}

export function Chart({ dataRef, tab, timeWindow, visible }: ChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const uplotRef = useRef<uPlot | null>(null)
  const rafRef = useRef<number>(0)
  const columns = TAB_COLUMNS[tab]

  // Create uPlot on mount, update data via rAF
  useEffect(() => {
    if (!containerRef.current) return

    const el = containerRef.current

    // Use parent dimensions since hidden elements have 0 size
    const parent = el.parentElement!
    const w = Math.max(parent.clientWidth, 300)
    const h = Math.max(parent.clientHeight, 300)

    const opts = createChartOptions(tab, w, h, timeWindow)
    const data = extractSeries(dataRef.current, columns)
    const u = new uPlot(opts, data, el)
    uplotRef.current = u

    // rAF loop to push data into chart
    const tick = () => {
      const d = extractSeries(dataRef.current, columns)
      u.setData(d)
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)

    // Handle resize from parent
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        if (width > 0 && height > 0) {
          u.setSize({ width, height })
        }
      }
    })
    ro.observe(parent)

    return () => {
      cancelAnimationFrame(rafRef.current)
      ro.disconnect()
      u.destroy()
      uplotRef.current = null
    }
  }, [tab, timeWindow, columns, dataRef])

  return (
    <div
      ref={containerRef}
      className="chart-glow absolute inset-0"
      style={{ visibility: visible ? 'visible' : 'hidden' }}
    />
  )
}
