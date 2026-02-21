import { ref } from "vue"
import { createChart, ColorType, type IChartApi, type ISeriesApi, CandlestickSeries, LineSeries, BaselineSeries } from "lightweight-charts"

export const useChart = () => {
  const chart = ref<IChartApi | null>(null)
  const series = ref<ISeriesApi<any>[]>([])
  const backtestChart = ref<IChartApi | null>(null)
  const backtestSeries = ref<ISeriesApi<any>[]>([])

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
    baseValue: { type: 'price' as const, price: 0.5 },
    topLineColor: 'rgb(255, 166, 1)',
    topFillColor1: 'rgba( 255, 166, 1, 0.28)',
    topFillColor2: 'rgba( 255, 166, 1, 0.05)',
    bottomLineColor: 'rgb(0, 140, 255)',
    bottomFillColor1: 'rgba( 0, 140, 255, 0.05)',
    bottomFillColor2: 'rgba( 0, 140, 255, 0.28)',
  }

  const valueAreaSeriesOptions = {
    color: "rgb(0, 201, 252)",
    lineWidth: 2 as const,
  }

  const chopSignalSeriesOptions = {
    baseValue: { type: 'price' as const, price: 0 },
    topLineColor: 'rgb(255, 166, 1)',
    topFillColor1: 'rgba( 255, 166, 1, 0.28)',
    topFillColor2: 'rgba( 255, 166, 1, 0.05)',
    bottomLineColor: 'rgb(94, 61, 0)',
    bottomFillColor1: 'rgba( 136, 88, 0, 0.05)',
    bottomFillColor2: 'rgba( 136, 88, 0, 0.28)',
  }

  const trendSignalSeriesOptions = {
    baseValue: { type: 'price' as const, price: 0 },
    topLineColor: 'rgb(0, 140, 255)',
    topFillColor1: 'rgba( 0, 140, 255, 0.28)',
    topFillColor2: 'rgba( 0, 140, 255, 0.05)',
    bottomLineColor: 'rgb(0, 49, 88)',
    bottomFillColor1: 'rgba( 0, 49, 88, 0.05)',
    bottomFillColor2: 'rgba( 0, 49, 88, 0.28)',
  }

  const weightedSignalSeriesOptions = {
    baseValue: { type: 'price' as const, price: 0 },
    topLineColor: 'rgb(0, 255, 149)',
    topFillColor1: 'rgba( 0, 255, 149, 0.28)',
    topFillColor2: 'rgba( 0, 255, 149, 0.05)',
    bottomLineColor: 'rgb(255, 58, 58)',
    bottomFillColor1: 'rgba( 255, 58, 58, 0.05)',
    bottomFillColor2: 'rgba( 255, 58, 58, 0.28)',
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

  const addTrendSignalSeries = (data: any[]) => {
    if (!chart.value) return;
    const trendSignalSeries = chart.value.addSeries(BaselineSeries, trendSignalSeriesOptions, 1)
    const trendSignalData = data.map((row: any) => ({
      time: row.time,
      value: row.trend_signal,
    }))
    trendSignalSeries.setData(trendSignalData)
    series.value.push(trendSignalSeries)
  }

  const addWeightedSignalSeries = (data: any[]) => {
    if (!chart.value) return;
    const weightedSignalSeries = chart.value.addSeries(BaselineSeries, weightedSignalSeriesOptions, 3)
    const weightedSignalData = data.map((row: any) => ({
      time: row.time,
      value: row.weighted_signal,
    }))
    weightedSignalSeries.setData(weightedSignalData)
    series.value.push(weightedSignalSeries)
  }

  const addRegimeSeries = (data: any[]) => {
    if (!chart.value) return;
    const regimeSeries = chart.value.addSeries(BaselineSeries, regimeSeriesOptions, 2)
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

  // Backtest chart functions
  const initBacktestChart = (container: HTMLElement) => {
    backtestChart.value = createChart(container, chartOptions)
  }

  const addBacktestPriceSeries = (data: any[]) => {
    if (!backtestChart.value) return;
    const priceSeries = backtestChart.value.addSeries(CandlestickSeries, priceSeriesOptions, 0)
    const priceData = data.map((row: any) => ({
      time: row.time,
      open: row.open,
      high: row.high,
      low: row.low,
      close: row.close,
    }))
    priceSeries.setData(priceData)
    backtestSeries.value.push(priceSeries)
  }

  const strategySeriesOptions = {
    color: 'rgb(0, 255, 149)',
    lineWidth: 2 as const,
    priceFormat: {
      type: 'price' as const,
      precision: 4,
      minMove: 0.0001,
    },
  }

  const buyHoldSeriesOptions = {
    color: 'rgb(148, 163, 184)',
    lineWidth: 2 as const,
    priceFormat: {
      type: 'price' as const,
      precision: 4,
      minMove: 0.0001,
    },
  }

  const positionSeriesOptions = {
    baseValue: { type: 'price' as const, price: 0 },
    topLineColor: 'rgb(34, 197, 94)', // Green
    topFillColor1: 'rgba(34, 197, 94, 0.28)',
    topFillColor2: 'rgba(34, 197, 94, 0.05)',
    bottomLineColor: 'rgb(239, 68, 68)', // Red
    bottomFillColor1: 'rgba(239, 68, 68, 0.05)',
    bottomFillColor2: 'rgba(239, 68, 68, 0.28)',
  }

  const addBacktestCumulativeSeries = (data: any[]) => {
    if (!backtestChart.value) return;
    
    // Add strategy cumulative returns
    const strategySeries = backtestChart.value.addSeries(LineSeries, strategySeriesOptions, 1)
    const strategyData = data.map((row: any) => ({
      time: row.time,
      value: row.cum_strategy || 1.0,
    }))
    strategySeries.setData(strategyData)
    backtestSeries.value.push(strategySeries)

    // Add buy-and-hold cumulative returns
    const buyHoldSeries = backtestChart.value.addSeries(LineSeries, buyHoldSeriesOptions, 1)
    const buyHoldData = data.map((row: any) => ({
      time: row.time,
      value: row.cum_buy_hold || 1.0,
    }))
    buyHoldSeries.setData(buyHoldData)
    backtestSeries.value.push(buyHoldSeries)
  }

  const addBacktestPositionSeries = (data: any[]) => {
    if (!backtestChart.value) return;
    
    const positionSeries = backtestChart.value.addSeries(BaselineSeries, positionSeriesOptions, 2)
    const positionData = data.map((row: any) => ({
      time: row.time,
      value: row.position || 0,
    }))
    positionSeries.setData(positionData)
    backtestSeries.value.push(positionSeries)
  }

  const clearBacktestChart = () => {
    backtestSeries.value.forEach(series => {
      backtestChart.value?.removeSeries(series)
    })
    backtestSeries.value = []
  }

  return { 
    chart, 
    initChart, 
    addPriceSeries, 
    addRegimeSeries, 
    addValueAreaSeries, 
    addChopSignalSeries, 
    addTrendSignalSeries, 
    addWeightedSignalSeries, 
    clearChart,
    backtestChart,
    initBacktestChart,
    addBacktestPriceSeries,
    addBacktestCumulativeSeries,
    addBacktestPositionSeries,
    clearBacktestChart
  }
}