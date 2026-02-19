import { ref } from "vue"
import { createChart, ColorType, type IChartApi, type ISeriesApi, CandlestickSeries, LineSeries, BaselineSeries } from "lightweight-charts"

export const useChart = () => {
  const chart = ref<IChartApi | null>(null)
  const series = ref<ISeriesApi<any>[]>([])

  // Match App.vue dark theme: --surface, --text, --muted, --border, --on (green), accent
  const chartTheme = {
    bg: '#1a2332',
    text: '#e2e8f0',
    muted: '#94a3b8',
    border: 'rgba(148, 163, 184, 0.22)',
    up: '#22c55e',
    down: '#ef4444',
    accent: '#fbbf24',
  }

  const chartOptions = {
    layout: {
      textColor: chartTheme.text,
      background: { type: ColorType.Solid, color: chartTheme.bg },
      fontFamily: '"Outfit", system-ui, sans-serif',
      fontSize: 11,
    },
    grid: {
      vertLines: { color: chartTheme.border },
      horzLines: { color: chartTheme.border },
    },
    crosshair: {
      vertLine: { color: chartTheme.muted, labelBackgroundColor: chartTheme.accent },
      horzLine: { color: chartTheme.muted, labelBackgroundColor: chartTheme.accent },
    },
    rightPriceScale: {
      borderColor: chartTheme.border,
      scaleMargins: { top: 0.08, bottom: 0.08 },
    },
    timeScale: {
      timeVisible: true,
      secondsVisible: true,
      borderColor: chartTheme.border,
    },
  }
  const priceSeriesOptions = {
    priceFormat: {
      type: 'price' as const,
      precision: 2,
      minMove: 0.25,
    },
    upColor: chartTheme.up,
    downColor: chartTheme.down,
    borderUpColor: chartTheme.up,
    borderDownColor: chartTheme.down,
    wickUpColor: chartTheme.up,
    wickDownColor: chartTheme.down,
  }

  const regimeSeriesOptions = {
    color: chartTheme.accent,
    lineWidth: 2 as const,
  }

  const valueAreaSeriesOptions = {
    color: "rgb(0, 201, 252)",
    lineWidth: 2 as const,
  }

  const chopSignalSeriesOptions = {
    baseValue: { type: 'price' as const, price: 0 },
    topLineColor: 'rgba( 38, 166, 154, 1)',
    topFillColor1: 'rgba( 38, 166, 154, 0.28)',
    topFillColor2: 'rgba( 38, 166, 154, 0.05)',
    bottomLineColor: 'rgba( 239, 83, 80, 1)',
    bottomFillColor1: 'rgba( 239, 83, 80, 0.05)',
    bottomFillColor2: 'rgba( 239, 83, 80, 0.28)',
  }

  const initChart = (container: HTMLElement) => {
    chart.value = createChart(container, chartOptions)
  }

  const addPriceSeries = (data: any[]) => {
    if (!chart.value) return;
    const priceSeries = chart.value.addSeries(CandlestickSeries, priceSeriesOptions)
    const priceData = data.map((row: any) => ({
      time: row.time,
      open: row.open,
      high: row.high,
      low: row.low,
      close: row.close,
    }))
    priceSeries.setData(priceData)
    series.value.push(priceSeries)
  }

  const addValueAreaSeries = (data: any[]) => {
    console.log("Adding value area series...")
    if (!chart.value) return;
    const valueAreaHighSeries = chart.value.addSeries(LineSeries, valueAreaSeriesOptions, 0)
    const valueAreaLowSeries = chart.value.addSeries(LineSeries, valueAreaSeriesOptions, 0)
    const valueAreaHighData = data.map((row: any) => ({
      time: row.time,
      value: row.vah,
    }))
    const valueAreaLowData = data.map((row: any) => ({
      time: row.time,
      value: row.val,
    }))
    valueAreaHighSeries.setData(valueAreaHighData)
    valueAreaLowSeries.setData(valueAreaLowData)
    series.value.push(valueAreaHighSeries, valueAreaLowSeries)
  }

  const addChopSignalSeries = (data: any[]) => {
    if (!chart.value) return;
    const chopSignalSeries = chart.value.addSeries(BaselineSeries, chopSignalSeriesOptions, 1)
    const chopSignalData = data.map((row: any) => ({
      time: row.time,
      value: row.chop_signal,
    }))
    chopSignalSeries.setData(chopSignalData)
    series.value.push(chopSignalSeries)
  }

  const addRegimeSeries = (data: any[]) => {
    if (!chart.value) return;
    const regimeSeries = chart.value.addSeries(LineSeries, regimeSeriesOptions, 2)
    const regimeData = data.map((row: any) => ({
      time: row.time,
      value: row.regime,
    }))
    regimeSeries.setData(regimeData)
    series.value.push(regimeSeries)
  }

  const clearChart = () => {
    series.value.forEach(series => {
      chart.value?.removeSeries(series)
    })
    series.value = []
  }

  return { chart, initChart, addPriceSeries, addRegimeSeries, addValueAreaSeries, addChopSignalSeries, clearChart }
}