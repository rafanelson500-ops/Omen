<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import {
  createChart,
  LineSeries,
  CandlestickSeries,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts'
import { chartOptions, compactChartOptions, candlestickSeriesOptions, chartTheme } from './chartOptions'
import type { Socket } from 'socket.io-client'

const props = defineProps<{
  socket: Socket
}>()

type CandleMsg = {
  time: number
  open: number
  high: number
  low: number
  close: number
  bar_delta?: number
  avg_delta?: number
}

const lineHost = ref<HTMLDivElement | null>(null)
const candle10Host = ref<HTMLDivElement | null>(null)
const candle100Host = ref<HTMLDivElement | null>(null)

let chartLine: IChartApi | null = null
let chart10: IChartApi | null = null
let chart100: IChartApi | null = null

let seriesLine: ISeriesApi<'Line'> | null = null
let series10: ISeriesApi<'Candlestick'> | null = null
let series100: ISeriesApi<'Candlestick'> | null = null
let seriesVWAP: ISeriesApi<'Line'> | null = null
let seriesVWAPsigplus1: ISeriesApi<'Line'> | null = null
let seriesVWAPsigminus1: ISeriesApi<'Line'> | null = null
let seriesVWAPsigplus2: ISeriesApi<'Line'> | null = null
let seriesVWAPsigminus2: ISeriesApi<'Line'> | null = null
let vwapLineSeeded = false

let lastTimeLine = -Infinity
let lastTime10 = -Infinity
let lastTime100 = -Infinity
const seriesMarkers: SeriesMarker<Time>[] = []
let markerPlugin: ISeriesMarkersPluginApi<Time> | null = null
let lastMarkerTime = -Infinity
let lastTradeSideForMarkers = 0

const TIME_EPS = 1e-6
const MAX_SERIES_MARKERS = 160

function ensureMonotonic(t: number, last: number): number {
  return t > last ? t : last + TIME_EPS
}

function pushMarkerTime(raw: number): Time {
  const t = raw > lastMarkerTime ? raw : lastMarkerTime + TIME_EPS
  lastMarkerTime = t
  return t as Time
}

function trimMarkers() {
  if (seriesMarkers.length > MAX_SERIES_MARKERS) {
    seriesMarkers.splice(0, seriesMarkers.length - MAX_SERIES_MARKERS)
  }
}

function applySeriesMarkers() {
  markerPlugin?.setMarkers(seriesMarkers)
}

type TickPayload = {
  tick: { time: number; value: number }
}

type HundredTickPayload = {
  c: CandleMsg
  vwap: number
  vwap_sigma: number
}

type StrategyStatusPayload = {
  time: number
  status: string
  side: number
}

function onStrategyStatus(payload: StrategyStatusPayload) {
  if (!seriesLine) return
  const { time, status, side } = payload
  if (status === 'IN_TRADE' && side !== 0) {
    lastTradeSideForMarkers = side
    seriesMarkers.push({
      time: pushMarkerTime(time),
      position: side === 1 ? 'belowBar' : 'aboveBar',
      color: side === 1 ? '#22c55e' : '#f87171',
      shape: side === 1 ? 'arrowUp' : 'arrowDown',
      text: 'Entry',
    })
    trimMarkers()
    applySeriesMarkers()
  } else if (status === 'COOLDOWN') {
    const exitedLong = lastTradeSideForMarkers === 1
    seriesMarkers.push({
      time: pushMarkerTime(time),
      position: exitedLong ? 'aboveBar' : 'belowBar',
      color: '#a78bfa',
      shape: 'circle',
      text: 'Exit',
    })
    trimMarkers()
    applySeriesMarkers()
  }
}

function onTickMessage(payload: TickPayload) {
  const c = payload.tick
  if (!seriesLine || !chartLine) return
  const t = ensureMonotonic(c.time, lastTimeLine)
  lastTimeLine = t
  seriesLine.update({ time: t as UTCTimestamp, value: c.value })
}

function on10Tick(c: CandleMsg) {
  if (!series10 || !chart10) return
  const t = ensureMonotonic(c.time, lastTime10)
  lastTime10 = t
  series10.update({
    time: t as UTCTimestamp,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  })
  chart10.timeScale().scrollToRealTime()
}

function on100Tick(payload: HundredTickPayload) {
  if (!series100 || !chart100 || !seriesVWAP || !seriesVWAPsigplus1 || !seriesVWAPsigminus1 || !seriesVWAPsigplus2 || !seriesVWAPsigminus2) return
  const { c, vwap, vwap_sigma } = payload
  const t = ensureMonotonic(c.time, lastTime100)
  lastTime100 = t
  series100.update({
    time: t as UTCTimestamp,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  })
  if (Number.isFinite(vwap)) {
    if (!vwapLineSeeded) {
      seriesVWAP.setData([{ time: t as UTCTimestamp, value: vwap }])
      seriesVWAPsigplus1.setData([{ time: t as UTCTimestamp, value: vwap + vwap_sigma }])
      seriesVWAPsigminus1.setData([{ time: t as UTCTimestamp, value: vwap - vwap_sigma }])
      seriesVWAPsigplus2.setData([{ time: t as UTCTimestamp, value: vwap + 2 * vwap_sigma }])
      seriesVWAPsigminus2.setData([{ time: t as UTCTimestamp, value: vwap - 2 * vwap_sigma }])
      vwapLineSeeded = true
    } else {
      seriesVWAP.update({ time: t as UTCTimestamp, value: vwap })
      seriesVWAPsigplus1.update({ time: t as UTCTimestamp, value: vwap + vwap_sigma })
      seriesVWAPsigminus1.update({ time: t as UTCTimestamp, value: vwap - vwap_sigma })
      seriesVWAPsigplus2.update({ time: t as UTCTimestamp, value: vwap + 2 * vwap_sigma })
      seriesVWAPsigminus2.update({ time: t as UTCTimestamp, value: vwap - 2 * vwap_sigma })
    }
  }
}

onMounted(() => {
  chartLine = createChart(lineHost.value!, { ...chartOptions, autoSize: true })
  seriesLine = chartLine.addSeries(LineSeries, {
    color: chartTheme.accent,
    lineWidth: 2,
    crosshairMarkerVisible: true,
    lastValueVisible: true,
    priceLineVisible: true,
  })

  chart10 = createChart(candle10Host.value!, { ...compactChartOptions, autoSize: true })
  series10 = chart10.addSeries(CandlestickSeries, {
    ...candlestickSeriesOptions,
  })

  chart100 = createChart(candle100Host.value!, { ...compactChartOptions, autoSize: true })
  series100 = chart100.addSeries(CandlestickSeries, {
    ...candlestickSeriesOptions,
  })


  seriesVWAP = chart100.addSeries(LineSeries, {
    color: "white",
    lineWidth: 2,
    crosshairMarkerVisible: true,
    lastValueVisible: true,
  })
  seriesVWAPsigplus1 = chart100.addSeries(LineSeries, {
    color: "yellow",
    lineWidth: 2,
    crosshairMarkerVisible: true,
    lastValueVisible: true,
  })
  seriesVWAPsigminus1 = chart100.addSeries(LineSeries, {
    color: "yellow",
    lineWidth: 2,
    crosshairMarkerVisible: true,
    lastValueVisible: true,
  })
  seriesVWAPsigplus2 = chart100.addSeries(LineSeries, {
    color: "orange",
    lineWidth: 2,
    crosshairMarkerVisible: true,
    lastValueVisible: true,
  })
  seriesVWAPsigminus2 = chart100.addSeries(LineSeries, {
    color: "orange",
    lineWidth: 2,
    crosshairMarkerVisible: true,
    lastValueVisible: true,
  })

  markerPlugin = createSeriesMarkers(seriesLine, seriesMarkers)

  props.socket.on('tick', onTickMessage)
  props.socket.on('10-tick', on10Tick)
  props.socket.on('100-tick', on100Tick)
  props.socket.on('strategy_status', onStrategyStatus)
})

onUnmounted(() => {
  props.socket.off('tick', onTickMessage)
  props.socket.off('10-tick', on10Tick)
  props.socket.off('100-tick', on100Tick)
  props.socket.off('strategy_status', onStrategyStatus)
  chartLine?.remove()
  chart10?.remove()
  chart100?.remove()
  chartLine = null
  chart10 = null
  chart100 = null
  seriesLine = null
  series10 = null
  series100 = null
  seriesVWAP = null
  seriesVWAPsigplus1 = null
  seriesVWAPsigminus1 = null
  seriesVWAPsigplus2 = null
  seriesVWAPsigminus2 = null
  vwapLineSeeded = false
  markerPlugin = null
  seriesMarkers.length = 0
  lastMarkerTime = -Infinity
  lastTradeSideForMarkers = 0
})
</script>

<template>
  <div class="charts-dashboard">
    <section class="panel panel--primary">
      <header class="panel-head">
        <span class="panel-title">1-tick</span>
        <span class="panel-hint">last close → line</span>
      </header>
      <div class="panel-chart" ref="lineHost" />
    </section>

    <div class="panel-row">
      <section class="panel panel--secondary">
        <header class="panel-head">
          <span class="panel-title">10-tick</span>
          <span class="panel-hint">OHLC</span>
        </header>
        <div class="panel-chart" ref="candle10Host" />
      </section>
      <section class="panel panel--secondary">
        <header class="panel-head">
          <span class="panel-title">100-tick</span>
          <span class="panel-hint">OHLC</span>
        </header>
        <div class="panel-chart" ref="candle100Host" />
      </section>
    </div>
  </div>
</template>

<style scoped>
.charts-dashboard {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
  min-height: 0;
  padding: 10px;
  background: linear-gradient(165deg, #141c2a 0%, #1a2332 45%, #151d2c 100%);
}

.panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  background: rgba(17, 29, 44, 0.65);
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.04) inset,
    0 12px 32px rgba(0, 0, 0, 0.22);
  overflow: hidden;
}

.panel--primary {
  flex: 1.35;
  min-height: 200px;
}

.panel-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  flex: 0.85;
  min-height: 160px;
}

.panel--secondary {
  min-height: 0;
}

.panel-head {
  flex-shrink: 0;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 12px 6px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
  background: rgba(15, 23, 42, 0.35);
}

.panel-title {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #f1f5f9;
}

.panel-hint {
  font-size: 10px;
  font-weight: 500;
  color: #64748b;
  letter-spacing: 0.04em;
}

.panel-chart {
  flex: 1;
  min-height: 0;
  width: 100%;
  position: relative;
}
</style>
