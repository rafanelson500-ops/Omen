<script setup lang="ts">
import type { Socket } from 'socket.io-client'
import {
  createChart,
  LineSeries,
  CandlestickSeries,
  ColorType,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type UTCTimestamp,
} from 'lightweight-charts'
import { ref, shallowRef, onMounted, onUnmounted } from 'vue'

const props = defineProps<{
  socket: Socket
  endpoint: string
  seriesType: string
}>()

const chartRef = ref<HTMLDivElement | null>(null)
let chart: IChartApi | null = null
const series = shallowRef<ISeriesApi<'Line'> | ISeriesApi<'Candlestick'> | null>(null)

let detachSocket: (() => void) | null = null

/** Backend sends `time` as integer microseconds since Unix epoch (JSON-safe). */
const toChartTime = (t: number): UTCTimestamp => (t / 1e6) as UTCTimestamp

const mapData = (data: any, map: Record<string, string>) => {
  return data.map((item: any) => {
    const newItem: Record<string, any> = {}
    for (const [key, value] of Object.entries(map)) {
      newItem[key] = item[value]
    }
    if (typeof newItem.time === 'number') {
      newItem.time = toChartTime(newItem.time)
    }
    return newItem
  })
}

onMounted(() => {
  if (!chartRef.value) return
  chart = createChart(chartRef.value, {
    autoSize: true,
    layout: {
      background: { type: ColorType.Solid, color: '#131722' },
      textColor: '#d1d4dc',
    },
    grid: {
      vertLines: { color: '#2B2B43' },
      horzLines: { color: '#2B2B43' },
    },
  })

  if (props.seriesType === 'line') {
    series.value = chart.addSeries(LineSeries, { color: '#2962FF', lineWidth: 2 })
  } else if (props.seriesType === 'candlestick') {
    series.value = chart.addSeries(CandlestickSeries, { upColor: '#2962FF', downColor: '#2962FF' })
  } else {
    throw new Error(`Invalid series type: ${props.seriesType}`)
  }

  const onBacktest = (payload: any) => {
    if (!payload || !Object.keys(payload).includes(props.endpoint)) return
    const data = payload[props.endpoint]
    if (props.seriesType === 'line') {
      const mapped = mapData(data, { time: 'time', value: 'close' }) as LineData[]
      ;(series.value as ISeriesApi<'Line'>).setData(mapped)
    } else {
      const mapped = mapData(data, {
        time: 'time',
        open: 'open',
        high: 'high',
        low: 'low',
        close: 'close',
      })
      ;(series.value as ISeriesApi<'Candlestick'>).setData(mapped)
    }
    chart?.timeScale().fitContent()
  }

  props.socket.on('backtest', onBacktest)
  detachSocket = () => props.socket.off('backtest', onBacktest)
})

onUnmounted(() => {
  detachSocket?.()
  detachSocket = null
  series.value = null
  chart?.remove()
  chart = null
})
</script>

<template>
  <div class="chart-shell">
    <div ref="chartRef" class="chart"></div>
  </div>
</template>

<style scoped>
/* Outer shell keeps App's .tick-chart dimensions (50vw × 50vh). Scoped .chart
   must NOT set height: 100% on the same node as .tick-chart — that overrides
   50vh and resolves against .app, which has no height → 0px chart. */
.chart-shell {
  box-sizing: border-box;
}
.chart {
  width: 100%;
  height: 100%;
  min-height: 0;
  position: relative;
}
</style>
