import {
  createChart,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type Time,
} from 'lightweight-charts'

// Databento raw prices are fixed-point integers scaled by 1e9
export const PRICE_SCALE = 1_000_000_000

export interface RawCandle {
  second: number
  open: number
  high: number
  low: number
  close: number
  buy_vol: number
  sell_vol: number
  delta: number
  price_levels: Record<number, [number, number]>
}

export const useChart = () => {
  let series: ISeriesApi<'Line'> | null = null

  const initChart = (container: HTMLDivElement): IChartApi => {
    const chart = createChart(container, {
      width: container.clientWidth,
      height: container.clientHeight,
      layout: {
        background: { color: '#1a2332' },
        textColor: '#e2e8f0',
      },
      grid: {
        vertLines: { color: 'rgba(148, 163, 184, 0.08)' },
        horzLines: { color: 'rgba(148, 163, 184, 0.08)' },
      },
      crosshair: {
        vertLine: { color: '#fbbf24', labelBackgroundColor: '#fbbf24' },
        horzLine: { color: '#fbbf24', labelBackgroundColor: '#fbbf24' },
      },
      rightPriceScale: {
        borderColor: 'rgba(148, 163, 184, 0.15)',
      },
      timeScale: {
        borderColor: 'rgba(148, 163, 184, 0.15)',
        timeVisible: true,
        secondsVisible: true,
      },
    })

    series = chart.addSeries(LineSeries)

    return chart
  }

  const toChartData = (raw: RawCandle): LineData<Time> => ({
    time: raw.second as Time,
    value: raw.close / PRICE_SCALE,
  })

  // Upserts the candle at its timestamp (adds new or updates existing)
  const upsertCandle = (raw: RawCandle) => {
    if (!series) return
    series.update(toChartData(raw))
  }

  // Maps a real price (in dollars) to a canvas y-coordinate (logical px)
  const priceToCoord = (price: number): number | null => {
    if (!series) return null
    return series.priceToCoordinate(price) ?? null
  }

  return { initChart, upsertCandle, priceToCoord }
}
