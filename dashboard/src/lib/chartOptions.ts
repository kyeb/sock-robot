import uPlot from 'uplot'
import { CHART_COLORS, DIM } from './colors'
import type { ChartTab } from './types'

const FONT = '11px JetBrains Mono, monospace'

function baseAxes(): uPlot.Axis[] {
  return [
    {
      stroke: DIM,
      grid: { stroke: 'rgba(255,255,255,0.04)', width: 1 },
      ticks: { stroke: DIM, size: 4 },
      font: FONT,
      gap: 6,
      size: 50,
      values: (_u, vals) => vals.map(v => v.toFixed(1) + 's'),
    },
    {
      stroke: DIM,
      grid: { stroke: 'rgba(255,255,255,0.04)', width: 1 },
      ticks: { stroke: DIM, size: 4 },
      font: FONT,
      gap: 8,
      size: 60,
    },
  ]
}

function makeSeries(colors: readonly string[], labels: string[]): uPlot.Series[] {
  return [
    { label: 'Time' },
    ...colors.map((color, i) => ({
      label: labels[i],
      stroke: color,
      width: 1.5,
      points: { show: false } as uPlot.Series.Points,
    })),
  ]
}

const SERIES_CONFIG: Record<ChartTab, { labels: string[]; yRange: [number, number] }> = {
  accel: { labels: ['X', 'Y', 'Z'], yRange: [-20, 20] },
  gyro: { labels: ['X', 'Y', 'Z'], yRange: [-5, 5] },
  orientation: { labels: ['Roll', 'Pitch', 'Yaw'], yRange: [-180, 180] },
}

export function createChartOptions(
  tab: ChartTab,
  width: number,
  height: number,
  timeWindow: number,
): uPlot.Options {
  const { labels, yRange } = SERIES_CONFIG[tab]
  const colors = CHART_COLORS[tab]

  return {
    width,
    height,
    cursor: {
      show: true,
      drag: { x: false, y: false, setScale: false },
    },
    select: { show: false, left: 0, top: 0, width: 0, height: 0 },
    legend: { show: false },
    axes: baseAxes(),
    scales: {
      x: {
        time: false,
        auto: true,
        range: (_u: uPlot, dataMin: number, dataMax: number): uPlot.Range.MinMax => {
          if (dataMin == null || dataMax == null) return [0, timeWindow]
          return [dataMax - timeWindow, dataMax]
        },
      },
      y: {
        auto: false,
        range: yRange as uPlot.Range.MinMax,
      },
    },
    series: makeSeries(colors, labels),
  }
}
