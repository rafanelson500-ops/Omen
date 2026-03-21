<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { createChart, CandlestickSeries, LineSeries, type ISeriesApi, type UTCTimestamp, type IPriceLine } from 'lightweight-charts'
import { chartOptions, candlestickSeriesOptions } from './chartOptions'
import type { Socket } from 'socket.io-client'

const props = defineProps<{
  socket: Socket
}>()

const chartContainer = ref<HTMLDivElement | null>(null)
const tickSeries = ref<ISeriesApi<"Line"> | null>(null)
const rlLines = ref<IPriceLine[]>([])

const formatTick = (tick: any) => ({
  time: tick.ts as UTCTimestamp,
  value: tick.price,
})

onMounted(() => {
  const chart = createChart(chartContainer.value!, { ...chartOptions, autoSize: true })
  tickSeries.value = chart.addSeries(LineSeries, { color: '#fbbf24', lineWidth: 1 })

  props.socket.on('tick', (tick: any) => {
    tickSeries.value?.update(formatTick(tick))
  })

  props.socket.on('rl_update', (new_rl: Record<number, number>) => {
    // for (const line of lvnLines.value) {
    //   priceSeries.value?.removePriceLine(line)
    // }
    // lvnLines.value = []
    // for (const lvn of new_lvns) {
    //   const line = priceSeries.value?.createPriceLine({
    //     price: lvn / 1_000_000_000,
    //     color: '#fbbf24',
    //     lineWidth: 1,
    //     lineStyle: 2,
    //     axisLabelVisible: true,
    //     title: 'LVN',
    //   })
    //   if (line) lvnLines.value.push(line)
    // }
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
