<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { createChart, CandlestickSeries, LineSeries, type ISeriesApi, type UTCTimestamp, type IPriceLine } from 'lightweight-charts'
import { chartOptions, candlestickSeriesOptions } from './chartOptions'
import type { Socket } from 'socket.io-client'

const props = defineProps<{
  socket: Socket
}>()

const chartContainer = ref<HTMLDivElement | null>(null)
const priceSeries = ref<ISeriesApi<"Candlestick"> | null>(null)
const extraSeries = ref<Record<string, ISeriesApi<"Line">>>({})
const lvnLines = ref<IPriceLine[]>([])

const formatCandle = (candle: any) => ({
  time: Math.floor(candle.timestamp / 1_000_000_000) as UTCTimestamp,
  open: candle.open / 1_000_000_000,
  high: candle.high / 1_000_000_000,
  low: candle.low / 1_000_000_000,
  close: candle.close / 1_000_000_000,
})

const formatExtra = (candle: any, key: string) => ({
  time: Math.floor(candle.timestamp / 1_000_000_000) as UTCTimestamp,
  value: candle[key],
})

onMounted(() => {
  const chart = createChart(chartContainer.value!, { ...chartOptions, autoSize: true })
  priceSeries.value = chart.addSeries(CandlestickSeries, candlestickSeriesOptions)

  props.socket.on('med_candle', (candle: any) => {
    priceSeries.value?.update(formatCandle(candle))
    for (const key of Object.keys(candle)) {
      if (key.startsWith('graph')) {
        const split_key = key.split(':')
        const pane = split_key[1]
        const color = split_key[2]
        if (extraSeries.value[key]) {
          extraSeries.value[key].update(formatExtra(candle, key))
        } else {
          extraSeries.value[key] = chart.addSeries(LineSeries, {
            color: color,
            lineWidth: 1,
          }, pane as unknown as number)
          extraSeries.value[key].update(formatExtra(candle, key))
        }
      }
    }
  })

  props.socket.on('lvn_update', (new_lvns: number[]) => {
    for (const line of lvnLines.value) {
      priceSeries.value?.removePriceLine(line)
    }
    lvnLines.value = []
    for (const lvn of new_lvns) {
      const line = priceSeries.value?.createPriceLine({
        price: lvn / 1_000_000_000,
        color: '#fbbf24',
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: 'LVN',
      })
      if (line) lvnLines.value.push(line)
    }
  })
})
</script>

<template>
  <div class="chart" ref="chartContainer" />
</template>

<style scoped>
.chart {
  width: 100%;
  height: 100%;
}
</style>
