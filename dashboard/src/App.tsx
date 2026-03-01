import { useState, useCallback } from 'react'
import { useIMUSocket } from '~/hooks/useIMUSocket'
import { Chart } from '~/components/Chart'
import { CurrentValues } from '~/components/CurrentValues'
import { TabBar } from '~/components/TabBar'
import { StatusBar } from '~/components/StatusBar'
import { TimeWindowSelector } from '~/components/TimeWindowSelector'
import type { ChartTab } from '~/lib/types'

const VALID_TABS = new Set<string>(['all', 'accel', 'gyro', 'orientation'])

function getTabFromURL(): ChartTab {
  const params = new URLSearchParams(window.location.search)
  const tab = params.get('tab')
  return tab && VALID_TABS.has(tab) ? (tab as ChartTab) : 'all'
}

export function App() {
  const { dataRef, latest, status, sampleCount, hz } = useIMUSocket()
  const [tab, setTabState] = useState<ChartTab>(getTabFromURL)
  const [timeWindow, setTimeWindow] = useState(10)

  const setTab = useCallback((t: ChartTab) => {
    setTabState(t)
    const url = new URL(window.location.href)
    if (t === 'all') {
      url.searchParams.delete('tab')
    } else {
      url.searchParams.set('tab', t)
    }
    window.history.replaceState({}, '', url)
  }, [])

  return (
    <div className="flex flex-col h-screen bg-[#0a0a0f] text-[#c0c0c0] font-mono p-4 gap-2 scanlines">
      {/* Header */}
      <header className="flex items-center justify-between">
        <h1 className="text-xs tracking-[0.3em] uppercase text-[#444]">
          sock-robot // imu telemetry
        </h1>
        <TimeWindowSelector value={timeWindow} onChange={setTimeWindow} />
      </header>

      {/* Current values - always visible */}
      <CurrentValues sample={latest} />

      {/* Tab bar */}
      <TabBar active={tab} onChange={setTab} />

      {/* Charts */}
      {tab === 'all' ? (
        <div className="flex-1 min-h-0 flex flex-col gap-2">
          <div className="flex-1 min-h-0 relative">
            <Chart dataRef={dataRef} tab="accel" timeWindow={timeWindow} visible />
          </div>
          <div className="flex-1 min-h-0 relative">
            <Chart dataRef={dataRef} tab="gyro" timeWindow={timeWindow} visible />
          </div>
          <div className="flex-1 min-h-0 relative">
            <Chart dataRef={dataRef} tab="orientation" timeWindow={timeWindow} visible />
          </div>
        </div>
      ) : (
        <div className="flex-1 min-h-0 relative">
          <Chart dataRef={dataRef} tab="accel" timeWindow={timeWindow} visible={tab === 'accel'} />
          <Chart dataRef={dataRef} tab="gyro" timeWindow={timeWindow} visible={tab === 'gyro'} />
          <Chart dataRef={dataRef} tab="orientation" timeWindow={timeWindow} visible={tab === 'orientation'} />
        </div>
      )}

      {/* Bottom HUD */}
      <StatusBar status={status} hz={hz} samples={sampleCount} />
    </div>
  )
}
