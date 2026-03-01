import {
  createChart,
  LineSeries,
  BaselineSeries,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type Time,
  CandlestickSeries,
  type CandlestickData,
  HistogramSeries,
  type HistogramData,
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
  gravity: number
  delta_gravity: number
  average_gravity: number
  price_levels: Record<number, [number, number]>
  ha_open: number
  ha_high: number
  ha_low: number
  ha_close: number
}

export const useChart = () => {
  let series: ISeriesApi<any>[] = []
  let priceSeries: ISeriesApi<'Candlestick'> | null = null
  let haSeries: ISeriesApi<'Candlestick'> | null = null
  let returnSeries: ISeriesApi<'Line'> | null = null
  let benchmarkSeries: ISeriesApi<'Line'> | null = null
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

    return chart
  }

  const clearChart = (chart: IChartApi) => {
    if (!chart) return
    for (const s of series) {
      chart?.removeSeries(s)
    }
    series = []
    priceSeries = chart.addSeries(CandlestickSeries)
    haSeries = chart.addSeries(CandlestickSeries, { upColor: '#34d399', downColor: '#ef4444' }, 1)
    returnSeries = chart.addSeries(LineSeries, { color: '#fbbf24' }, 2)
    benchmarkSeries = chart.addSeries(LineSeries, { color: '#e2e8f0' }, 2)
    series.push(priceSeries, haSeries, returnSeries, benchmarkSeries)
  }


  const hydrateChart = (data: any) => {
    for (const candle of data) {
      upsertCandle(candle)
    }
  }

  const toReturnChartData = (data: any): LineData<Time> => ({
    time: data.second as Time,
    value: data.strategy_returns / PRICE_SCALE,
  })

  const toBenchmarkChartData = (data: any): LineData<Time> => ({
    time: data.second as Time,
    value: data.benchmark_returns / PRICE_SCALE,
  })

  const toPriceChartData = (raw: RawCandle): CandlestickData<Time> => ({
    time: raw.second as Time,
    open: raw.open / PRICE_SCALE,
    high: raw.high / PRICE_SCALE,
    low: raw.low / PRICE_SCALE,
    close: raw.close / PRICE_SCALE,
  })

  const toHaChartData = (raw: RawCandle): CandlestickData<Time> => ({
    time: raw.second as Time,
    open: raw.ha_open / PRICE_SCALE,
    high: raw.ha_high / PRICE_SCALE,
    low: raw.ha_low / PRICE_SCALE,
    close: raw.ha_close / PRICE_SCALE,
  })
  // Upserts the candle at its timestamp (adds new or updates existing)
  const upsertCandle = (raw: RawCandle) => {
    if (!priceSeries) return
    priceSeries.update(toPriceChartData(raw))
    haSeries?.update(toHaChartData(raw))
    if ("strategy_returns" in raw) {
      returnSeries?.update(toReturnChartData(raw))
      benchmarkSeries?.update(toBenchmarkChartData(raw))
    }
  }

  // Maps a real price (in dollars) to a canvas y-coordinate (logical px)
  const priceToCoord = (price: number): number | null => {
    if (!priceSeries) return null
    return priceSeries.priceToCoordinate(price) ?? null
  }

  return { initChart, upsertCandle, priceToCoord, hydrateChart, clearChart }
}
