import type { InjectionKey } from 'vue'
import type { IChartApi, ISeriesApi, MouseEventParams, SeriesType, Time } from 'lightweight-charts'
import { MismatchDirection } from 'lightweight-charts'

export const chartSyncKey: InjectionKey<ChartSyncGroup> = Symbol('chartSync')

type MainSeries = ISeriesApi<SeriesType>

function priceAtCrosshair(data: unknown): number | null {
  if (!data || typeof data !== 'object') return null
  const o = data as Record<string, unknown>
  if (typeof o.value === 'number') return o.value
  if (typeof o.close === 'number') return o.close
  return null
}

/**
 * When `t` falls between two bar open times, `timeToIndex(t, true)` returns the *next* bar
 * (first index where bar.time >= t). For sync we need the bar that *contains* the tick:
 * last bar with bar.time <= t, i.e. step left once when the resolved bar opens after `t`.
 */
function barAtOrBeforeTime(series: MainSeries, chart: IChartApi, t: Time) {
  let idx = chart.timeScale().timeToIndex(t, true)
  if (idx === null) return null
  let bar = series.dataByIndex(idx, MismatchDirection.NearestLeft)
  if (!bar) return null
  const bt = bar.time
  if (typeof bt === 'number' && typeof t === 'number' && bt > t) {
    idx -= 1
    if (idx < 0) return null
    bar = series.dataByIndex(idx, MismatchDirection.NearestLeft)
  }
  return bar
}

/**
 * `setVisibleRange` throws if the interval does not map to a logical range on that chart
 * (no data yet, or window fully outside series bounds). Clamp to bar times and swallow errors.
 */
function safeSetVisibleRange(chart: IChartApi, series: MainSeries, range: { from: Time; to: Time }) {
  const rows = series.data()
  if (rows.length === 0) return

  const firstT = rows[0]!.time
  const lastT = rows[rows.length - 1]!.time
  let from = range.from
  let to = range.to

  if (
    typeof from === 'number' &&
    typeof to === 'number' &&
    typeof firstT === 'number' &&
    typeof lastT === 'number'
  ) {
    let lo = Math.min(from, to)
    let hi = Math.max(from, to)
    lo = Math.max(lo, firstT)
    hi = Math.min(hi, lastT)
    if (lo > hi) return
    from = lo as Time
    to = hi as Time
  }

  try {
    chart.timeScale().setVisibleRange({ from, to })
  } catch {
    /* scale not ready or non-numeric Time */
  }
}

/**
 * Keeps visible time range and crosshair time aligned across multiple charts (TradingView lightweight-charts).
 */
export class ChartSyncGroup {
  private readonly entries = new Map<
    IChartApi,
    { mainSeries: MainSeries; cleanups: (() => void)[] }
  >()

  private timeLock = false
  private crossLock = false

  /** When false, charts do not mirror time scale or crosshair. */
  constructor(private readonly isSyncEnabled: () => boolean = () => true) {}

  register(chart: IChartApi, mainSeries: MainSeries) {
    if (this.entries.has(chart)) return

    const cleanups: (() => void)[] = []

    const onVisibleTimeRangeChange = (range: { from: Time; to: Time } | null) => {
      if (this.timeLock || !range || !this.isSyncEnabled()) return
      this.timeLock = true
      try {
        for (const [c, { mainSeries: ms }] of this.entries) {
          if (c === chart) continue
          safeSetVisibleRange(c, ms, range)
        }
      } finally {
        this.timeLock = false
      }
    }
    chart.timeScale().subscribeVisibleTimeRangeChange(onVisibleTimeRangeChange)
    cleanups.push(() => chart.timeScale().unsubscribeVisibleTimeRangeChange(onVisibleTimeRangeChange))

    const onCrosshairMove = (param: MouseEventParams<Time>) => {
      if (this.crossLock) return
      if (!this.isSyncEnabled()) return

      if (param.point === undefined) {
        this.crossLock = true
        try {
          for (const c of this.entries.keys()) {
            c.clearCrosshairPosition()
          }
        } finally {
          this.crossLock = false
        }
        return
      }

      if (param.time === undefined) {
        this.crossLock = true
        try {
          for (const c of this.entries.keys()) {
            if (c !== chart) c.clearCrosshairPosition()
          }
        } finally {
          this.crossLock = false
        }
        return
      }

      const t = param.time
      this.crossLock = true
      try {
        for (const [c, { mainSeries: series }] of this.entries) {
          if (c === chart) continue
          const bar = barAtOrBeforeTime(series, c, t)
          const price = priceAtCrosshair(bar)
          if (price === null || !bar) {
            c.clearCrosshairPosition()
            continue
          }
          c.setCrosshairPosition(price, bar.time, series)
        }
      } finally {
        this.crossLock = false
      }
    }
    chart.subscribeCrosshairMove(onCrosshairMove)
    cleanups.push(() => chart.unsubscribeCrosshairMove(onCrosshairMove))

    this.entries.set(chart, { mainSeries, cleanups })
  }

  unregister(chart: IChartApi) {
    const entry = this.entries.get(chart)
    if (!entry) return
    for (const fn of entry.cleanups) fn()
    this.entries.delete(chart)
  }
}
