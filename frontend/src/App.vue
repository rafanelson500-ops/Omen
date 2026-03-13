<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { io, Socket } from 'socket.io-client'
import type { IChartApi, ISeriesApi } from 'lightweight-charts'
import { createChart, CandlestickSeries } from 'lightweight-charts'
import { chartOptions, candlestickSeriesOptions, chartTheme } from './chartOptions'

let url = 'http://localhost:8000'
if (window.location.hostname === 'play.nukesmp.com') {
  url = 'http://play.nukesmp.com:8000'
}

const socket = ref<Socket>()
const chartContainer = ref<HTMLDivElement | null>(null)
const chart = ref<IChartApi>()
const candles = ref<ISeriesApi<'Candlestick'>>()
const connected = ref(false)

let resizeObserver: ResizeObserver | null = null

const formatCandle = (candle: any) => {
  return {
    time: candle.timestamp,
    open: candle.open * 1e-9,
    high: candle.high * 1e-9,
    low: candle.low * 1e-9,
    close: candle.close * 1e-9,
  }
}

onMounted(() => {
  if (!chartContainer.value) return

  // Create chart
  chart.value = createChart(chartContainer.value, {
    ...chartOptions,
    width: chartContainer.value.clientWidth,
    height: chartContainer.value.clientHeight,
  })

  candles.value = chart.value.addSeries(CandlestickSeries, candlestickSeriesOptions)

  // Keep chart sized to container
  resizeObserver = new ResizeObserver(() => {
    if (chartContainer.value && chart.value) {
      chart.value.resize(
        chartContainer.value.clientWidth,
        chartContainer.value.clientHeight
      )
    }
  })
  resizeObserver.observe(chartContainer.value)

  // Connect socket
  socket.value = io(url)

  socket.value.on('connect', () => { connected.value = true })
  socket.value.on('disconnect', () => { connected.value = false })

  socket.value.on('candle', (candle: any) => {
    console.log(candle)
    candles.value?.update(formatCandle(candle))
  })
  socket.value.on('update_candle', (candle: any) => {
    console.log("update_candle", candle)
    candles.value?.update(formatCandle(candle))
  })
})

onUnmounted(() => {
  resizeObserver?.disconnect()
  socket.value?.disconnect()
  chart.value?.remove()
})
</script>

<template>
  <div class="page">
    <header class="header">
      <div class="header-left">
        <span class="logo">🧀 Cheese Trading</span>
        <span class="timeframe">1s</span>
      </div>
      <div class="status" :class="connected ? 'status--live' : 'status--off'">
        <span class="status-dot" />
        {{ connected ? 'LIVE' : 'DISCONNECTED' }}
      </div>
    </header>

    <main class="main">
      <div ref="chartContainer" class="chart-container" />
    </main>
  </div>
</template>

<style scoped>
*,
*::before,
*::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

.page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100vw;
  background: #0f1923;
  color: #e2e8f0;
  font-family: 'Outfit', system-ui, sans-serif;
  overflow: hidden;
}

/* ── Header ── */
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  height: 48px;
  background: #1a2332;
  border-bottom: 1px solid rgba(148, 163, 184, 0.15);
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: #fbbf24;
}

.timeframe {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(251, 191, 36, 0.15);
  color: #fbbf24;
  letter-spacing: 0.05em;
}

/* ── Status badge ── */
.status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  padding: 4px 10px;
  border-radius: 20px;
}

.status--live {
  background: rgba(34, 197, 94, 0.12);
  color: #22c55e;
}

.status--off {
  background: rgba(239, 68, 68, 0.12);
  color: #ef4444;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
  animation: pulse 2s ease-in-out infinite;
}

.status--off .status-dot {
  animation: none;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.3; }
}

/* ── Chart ── */
.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 12px;
}

.chart-container {
  flex: 1;
  width: 100%;
  height: 100%;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, 0.15);
}
</style>
