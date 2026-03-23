<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import {
  createChart,
  LineSeries,
  CandlestickSeries,
  type IChartApi,
  type ISeriesApi,
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
  [key: string]: number
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
let savgolseries: ISeriesApi<'Line'> | null = null

let lastTimeLine = -Infinity
let lastTime10 = -Infinity
let lastTime100 = -Infinity

const TIME_EPS = 1e-6

function ensureMonotonic(t: number, last: number): number {
  return t > last ? t : last + TIME_EPS
}

function on1Tick(c: CandleMsg) {
  if (!seriesLine || !chartLine) return
  const t = ensureMonotonic(c.time, lastTimeLine)
  lastTimeLine = t
  seriesLine.update({ time: t as UTCTimestamp, value: c.close })
  chartLine.timeScale().scrollToRealTime()
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

function on100Tick(c: CandleMsg) {
  if (!series100 || !chart100 || !savgolseries) return
  const t = ensureMonotonic(c.time, lastTime100)
  lastTime100 = t
  series100.update({
    time: t as UTCTimestamp,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  })
  savgolseries.update({time: t as UTCTimestamp, value: c["savgol"]})
  chart100.timeScale().scrollToRealTime()
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

  savgolseries = chart100.addSeries(LineSeries, {
    color: chartTheme.accent,
    lineWidth: 2,
    crosshairMarkerVisible: true,
    lastValueVisible: true,
    priceLineVisible: true,
  })

  props.socket.on('1-tick', on1Tick)
  props.socket.on('10-tick', on10Tick)
  props.socket.on('100-tick', on100Tick)
})

onUnmounted(() => {
  props.socket.off('1-tick', on1Tick)
  props.socket.off('10-tick', on10Tick)
  props.socket.off('100-tick', on100Tick)
  chartLine?.remove()
  chart10?.remove()
  chart100?.remove()
  chartLine = null
  chart10 = null
  chart100 = null
  seriesLine = null
  series10 = null
  series100 = null
})
</script>

<template>
  <div class="charts-dashboard">
    <section class="panel panel--primary">
      <header class="panel-head">
        <span class="panel-title">Tick close</span>
        <span class="panel-hint">1-tick → line</span>
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
