<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { createChart, LineSeries, LineStyle, type ISeriesApi, type UTCTimestamp, type IPriceLine } from 'lightweight-charts'
import { chartOptions } from './chartOptions'
import type { Socket } from 'socket.io-client'

const props = defineProps<{
  socket: Socket
}>()

const chartContainer = ref<HTMLDivElement | null>(null)
const tickSeries = ref<ISeriesApi<'Line'> | null>(null)

/** Map "bid|ask:price" -> PriceLine for idempotent updates */
const wallLines = new Map<string, IPriceLine>()

/** Active paper trade visualization */
const tradeLines = ref<{
  entry: IPriceLine
  takeProfit: IPriceLine
  stopLoss: IPriceLine
} | null>(null)

function wallKey(side: string, price: number): string {
  return `${side}:${price}`
}

const formatTick = (tick: { ts: number; price: number }) => ({
  time: tick.ts as UTCTimestamp,
  value: tick.price,
})

function onTick(tick: { ts: number; price: number; side?: number; size?: number }) {
  tickSeries.value?.update(formatTick(tick))
}

function onWallDelta(payload: {
  added?: Array<{ side: string; price: number; size: number }>
  removed?: Array<{ side: string; price: number }>
}) {
  const series = tickSeries.value
  if (!series) return

  for (const r of payload.removed ?? []) {
    const k = wallKey(r.side, r.price)
    const line = wallLines.get(k)
    if (line) {
      series.removePriceLine(line)
      wallLines.delete(k)
    }
  }

  for (const a of payload.added ?? []) {
    const k = wallKey(a.side, a.price)
    const existing = wallLines.get(k)
    if (existing) {
      series.removePriceLine(existing)
      wallLines.delete(k)
    }
    const color = a.side === 'bid' ? '#22c55e' : '#ef4444'
    const line = series.createPriceLine({
      price: a.price,
      color,
      lineWidth: 2,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: `${a.side} ${a.size}`,
    })
    wallLines.set(k, line)
  }
}

function clearTradeLines() {
  const series = tickSeries.value
  const t = tradeLines.value
  if (!series || !t) {
    tradeLines.value = null
    return
  }
  series.removePriceLine(t.entry)
  series.removePriceLine(t.takeProfit)
  series.removePriceLine(t.stopLoss)
  tradeLines.value = null
}

function onTradeOpened(p: {
  id: string
  side: string
  entry: number
  take_profit: number
  stop_loss: number
}) {
  const series = tickSeries.value
  if (!series) return
  clearTradeLines()
  const entryLine = series.createPriceLine({
    price: p.entry,
    color: '#60a5fa',
    lineWidth: 2,
    lineStyle: LineStyle.Solid,
    axisLabelVisible: true,
    title: `${p.side.toUpperCase()} #${p.id} entry`,
  })
  const tpLine = series.createPriceLine({
    price: p.take_profit,
    color: '#22c55e',
    lineWidth: 2,
    lineStyle: LineStyle.Dashed,
    axisLabelVisible: true,
    title: 'TP +4',
  })
  const slLine = series.createPriceLine({
    price: p.stop_loss,
    color: '#f97316',
    lineWidth: 2,
    lineStyle: LineStyle.Dashed,
    axisLabelVisible: true,
    title: 'SL -8',
  })
  tradeLines.value = {
    entry: entryLine,
    takeProfit: tpLine,
    stopLoss: slLine,
  }
}

function onTradeClosed() {
  clearTradeLines()
}

onMounted(() => {
  const chart = createChart(chartContainer.value!, { ...chartOptions, autoSize: true })
  tickSeries.value = chart.addSeries(LineSeries, { color: '#fbbf24', lineWidth: 1 })

  props.socket.on('tick', onTick)
  props.socket.on('wall_delta', onWallDelta)
  props.socket.on('trade_opened', onTradeOpened)
  props.socket.on('trade_closed', onTradeClosed)
})

onUnmounted(() => {
  props.socket.off('tick', onTick)
  props.socket.off('wall_delta', onWallDelta)
  props.socket.off('trade_opened', onTradeOpened)
  props.socket.off('trade_closed', onTradeClosed)
  wallLines.clear()
  clearTradeLines()
})
</script>

<template>
  <div class="chart-wrap-inner">
    <div class="chart" ref="chartContainer" />
  </div>
</template>

<style scoped>
.chart-wrap-inner {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 0;
}

.chart {
  width: 100%;
  height: 100%;
}
</style>
