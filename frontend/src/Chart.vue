<script setup lang="ts">
import type { Socket } from 'socket.io-client'
import {
  createChart,
  LineSeries,
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type CandlestickData,
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

/** Price scale step: labels and grid align to 0.25 increments. */
const priceFormatQuarter = { type: 'price' as const, minMove: 0.25, precision: 2 }

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
      background: { type: ColorType.Solid, color: '#0a0d12' },
      textColor: '#94a3b8',
      fontSize: 11,
      fontFamily: "'JetBrains Mono', ui-monospace, system-ui, sans-serif",
    },
    grid: {
      vertLines: { color: 'rgba(30, 41, 59, 0.85)', style: LineStyle.Dotted },
      horzLines: { color: 'rgba(30, 41, 59, 0.85)', style: LineStyle.Dotted },
    },
    crosshair: {
      mode: CrosshairMode.Normal,
      vertLine: {
        color: 'rgba(125, 211, 252, 0.45)',
        width: 1,
        style: LineStyle.Dashed,
        labelBackgroundColor: '#1e293b',
      },
      horzLine: {
        color: 'rgba(167, 139, 250, 0.45)',
        width: 1,
        style: LineStyle.Dashed,
        labelBackgroundColor: '#1e293b',
      },
    },
    rightPriceScale: {
      borderColor: 'rgba(148, 163, 184, 0.15)',
      scaleMargins: { top: 0.08, bottom: 0.12 },
    },
    timeScale: {
      borderColor: 'rgba(148, 163, 184, 0.15)',
      timeVisible: true,
      secondsVisible: true,
    },
  })

  if (props.seriesType === 'line') {
    series.value = chart.addSeries(LineSeries, {
      priceFormat: priceFormatQuarter,
      color: '#38bdf8',
      lineWidth: 2,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 4,
      crosshairMarkerBorderColor: '#0ea5e9',
      crosshairMarkerBackgroundColor: '#0c4a6e',
      lastValueVisible: true,
      priceLineVisible: true,
      priceLineColor: 'rgba(56, 189, 248, 0.45)',
    })
  } else if (props.seriesType === 'candlestick') {
    const candleOpts =
      props.endpoint === '100-tick'
        ? {
            priceFormat: priceFormatQuarter,
            upColor: 'rgba(52, 211, 153, 0.92)',
            downColor: 'rgba(248, 113, 113, 0.92)',
            borderVisible: true,
            borderUpColor: '#34d399',
            borderDownColor: '#f87171',
            wickVisible: true,
            wickUpColor: '#6ee7b7',
            wickDownColor: '#fca5a5',
          }
        : {
            priceFormat: priceFormatQuarter,
            upColor: 'rgba(56, 189, 248, 0.95)',
            downColor: 'rgba(244, 114, 182, 0.95)',
            borderVisible: true,
            borderUpColor: '#0ea5e9',
            borderDownColor: '#ec4899',
            wickVisible: true,
            wickUpColor: '#7dd3fc',
            wickDownColor: '#f9a8d4',
          }
    series.value = chart.addSeries(CandlestickSeries, candleOpts)
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

  const onTick = (payload: any) => {
    if (!payload || !Object.keys(payload).includes(props.endpoint)) return
    const data = payload
    console.log(data)
    if (props.seriesType === 'line') {
      const mapped = mapData(data, { time: 'time', value: 'close' }) as LineData
      ;(series.value as ISeriesApi<'Line'>).update(mapped)
    } else if (props.seriesType === 'candlestick') {
      const mapped = mapData(data, { time: 'time', open: 'open', high: 'high', low: 'low', close: 'close' }) as CandlestickData
      ;(series.value as ISeriesApi<'Candlestick'>).update(mapped)
    }
  }

  props.socket.on('backtest', onBacktest)
  props.socket.on(props.endpoint, onTick)
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
.chart-shell {
  box-sizing: border-box;
  position: relative;
  border-radius: 8px;
  background: linear-gradient(180deg, rgba(15, 23, 42, 0.5) 0%, rgba(10, 13, 18, 0.95) 100%);
  border: 1px solid rgba(51, 65, 85, 0.45);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.03),
    0 4px 24px rgba(0, 0, 0, 0.25);
}
.chart {
  width: 100%;
  height: 100%;
  min-height: 0;
  position: relative;
}
</style>
