<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { io, type Socket } from 'socket.io-client'
import type { IChartApi } from 'lightweight-charts'
import { useChart, type RawCandle } from '../composables/useChart'
import { useVolumeProfile } from '../composables/useVolumeProfile'
import styles from './CandleChart.module.css'

const props = defineProps<{ backendUrl: string }>()

const containerRef = ref<HTMLDivElement | null>(null)
const connected = ref(false)
const mode = ref("live")
const availableData = ref([])
// Canvas is created programmatically *after* initChart so it sits on top
// of lightweight-charts' own canvas elements in the DOM stacking order.
let vpCanvas: HTMLCanvasElement | null = null
let chart: IChartApi | null = null
let socket: Socket | null = null
let unsubscribeRangeChange: (() => void) | null = null

const { initChart, upsertCandle, priceToCoord, hydrateChart, clearChart } = useChart()
const { addCandle, draw, clearProfile } = useVolumeProfile()

// Match canvas pixel dimensions to the container (DPR-aware)
const sizeCanvas = () => {
  const container = containerRef.value
  if (!vpCanvas || !container) return
  const dpr = window.devicePixelRatio || 1
  vpCanvas.width = container.clientWidth * dpr
  vpCanvas.height = container.clientHeight * dpr
  vpCanvas.style.width = `${container.clientWidth}px`
  vpCanvas.style.height = `${container.clientHeight}px`
}

const drawVP = () => {
  if (!vpCanvas || !chart) return
  // Fall back to 65px if the price scale width isn't available yet
  const rightOffset = chart.priceScale('right').width() || 65
  draw(vpCanvas, priceToCoord, rightOffset)
}

const handleResize = () => {
  if (chart && containerRef.value) {
    chart.applyOptions({
      width: containerRef.value.clientWidth,
      height: containerRef.value.clientHeight,
    })
  }
  sizeCanvas()
  drawVP()
}

const handleModeChange = () => {
  socket?.emit('mode_change', mode.value)
}

const handleBacktest = () => {
  socket?.emit('backtest', mode.value)
}

onMounted(() => {
  const container = containerRef.value
  if (container) {
    chart = initChart(container)

    // Append canvas AFTER the chart so it is on top in z/DOM order
    vpCanvas = document.createElement('canvas')
    vpCanvas.className = styles.vpCanvas as string
    container.appendChild(vpCanvas)

    sizeCanvas()

    // Redraw whenever the user pans or zooms (price range shifts)
    const handler = () => drawVP()
    chart.timeScale().subscribeVisibleLogicalRangeChange(handler)
    unsubscribeRangeChange = () =>
      chart!.timeScale().unsubscribeVisibleLogicalRangeChange(handler)
  }

  socket = io(props.backendUrl)

  socket.on('connect', () => {
    connected.value = true
  })

  socket.on('disconnect', () => {
    connected.value = false
  })

  socket.on('available_data', (data: any) => {
    availableData.value = data.sort()
  })

  socket.on('hydration_data', (data: any) => {
    console.log(data)
    clearChart(chart as IChartApi)
    clearProfile()
    hydrateChart(data)
    for (const candle of data) {
      addCandle(candle)
    }
    drawVP()
  })

  socket.on('candle_update', (candle: RawCandle) => {
    if (mode.value === "live") {
      upsertCandle(candle)
      addCandle(candle)
      drawVP()
    }
  })

  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  unsubscribeRangeChange?.()
  socket?.disconnect()
  chart?.remove()
  vpCanvas?.remove()
  window.removeEventListener('resize', handleResize)
})
</script>

<template>
  <div :class="styles.wrapper">
    <div :class="styles.header">
      <span :class="styles.symbol">ES.FUT</span>
      <span :class="styles.interval">1s</span>
      <span :class="[styles.statusDot, !connected && styles.statusDotOff]" />
      <select v-model="mode" @change="handleModeChange">
        <option value="live">Live</option>
        <option v-for="data in availableData" :value="data">{{ data }}</option>
      </select>
      <button @click="handleBacktest">Backtest</button>
    </div>
    <!-- vpCanvas is appended here programmatically after chart init -->
    <div ref="containerRef" :class="styles.chart" />
  </div>
</template>
