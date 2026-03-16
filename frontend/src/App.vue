<script setup lang="ts">
import { onMounted, onUnmounted, ref, computed, nextTick } from 'vue'
import { io, Socket } from 'socket.io-client'
import type { IChartApi, ISeriesApi, UTCTimestamp, IPriceLine, SeriesMarker } from 'lightweight-charts'
import { createChart, CandlestickSeries, LineSeries, LineStyle, createSeriesMarkers } from 'lightweight-charts'
import { chartOptions, candlestickSeriesOptions } from './chartOptions'

let url = 'http://localhost:8000'
if (window.location.hostname === 'play.nukesmp.com') {
  url = 'http://play.nukesmp.com:8000'
}

// ── State ─────────────────────────────────────────────────────────────────────
const socket        = ref<Socket>()
const chartContainer = ref<HTMLDivElement | null>(null)
const chart         = ref<IChartApi>()
const auxSeries     = ref<{ [key: string]: ISeriesApi<'Line'> }>({})
const candles       = ref<ISeriesApi<'Candlestick'>>()

const connected  = ref(false)
const loading    = ref(false)
const mode       = ref<string>('live')   // 'live' | 'YYYY-MM-DD'
const csvDates   = ref<string[]>([])
const keyLevels  = ref<number[]>([])
const keyLevelLines = ref<IPriceLine[]>([])
const signalMarkers = ref<SeriesMarker<UTCTimestamp>[]>([])
const signalPriceLines = ref<IPriceLine[]>([])
const signalCount = ref<number>(0)
const totalCandles = ref<number>(0)
const markerPrimitive = ref<any>(null)

let resizeObserver: ResizeObserver | null = null

// ── Computed ──────────────────────────────────────────────────────────────────
const isLive = computed(() => mode.value === 'live')

const statusLabel = computed(() => {
  if (!isLive.value) return 'HIST'
  return connected.value ? 'LIVE' : 'DISCONNECTED'
})

const statusClass = computed(() => {
  if (!isLive.value) return 'status--hist'
  return connected.value ? 'status--live' : 'status--off'
})

// ── Chart helpers ─────────────────────────────────────────────────────────────
const clearChart = () => {
  Object.values(auxSeries.value).forEach(s => {
    try { chart.value?.removeSeries(s) } catch { /* already removed */ }
  })
  auxSeries.value = {}
  candles.value?.setData([])
  
  // Clear signal price lines
  if (candles.value) {
    signalPriceLines.value.forEach(line => {
      try { candles.value?.removePriceLine(line) } catch { /* already gone */ }
    })
    signalPriceLines.value = []
  }
  
  // Clear markers primitive
  if (markerPrimitive.value) {
    try {
      markerPrimitive.value.detach()
    } catch { /* already detached */ }
    markerPrimitive.value = null
  }
  
  signalMarkers.value = []
}

/**
 * Draw LVN key levels as horizontal price lines on pane 0 (the main price
 * pane). Price lines are attached to the candlestick series so they survive
 * setData() calls and remain visible across all mode switches.
 * Call once after series creation; re-call if levels change.
 */
const drawKeyLevels = () => {
  if (!candles.value) return
  // Remove any previously drawn lines before redrawing.
  keyLevelLines.value.forEach(line => {
    try { candles.value?.removePriceLine(line) } catch { /* already gone */ }
  })
  keyLevelLines.value = []

  keyLevels.value.forEach(price => {
    const line = candles.value!.createPriceLine({
      price,
      color:            '#f59e0b',
      lineWidth:        1,
      lineStyle:        LineStyle.LargeDashed,
      axisLabelVisible: true,
      title:            'LVN',
    })
    keyLevelLines.value.push(line)
  })
}

/**
 * Bulk-load an array of candles into the chart.
 *
 * @param data       Array of candle objects from the backend.
 * @param priceScale 1e-9 for live fixed-point prices, 1 for historical real-dollar prices.
 */
const loadCandles = (data: any[], priceScale: number) => {
  clearChart()

  // Annotate absorption as a graph series key (same as live to_graph_notation).
  // Note: backend now provides graph: keys directly, so we preserve them
  const annotated = data.map(c => ({ ...c }))

  // Set main OHLC series with markers included in data
  if (candles.value) {
    // Create signal markers array
    const signals = annotated.filter(c => c.signal != null)
    signalMarkers.value = signals.map(c => ({
      time:     c.timestamp as UTCTimestamp,
      position: c.signal === 'long' ? 'belowBar' as const : 'aboveBar' as const,
      color:    '#fbbf24',  // Yellow/amber for high visibility
      shape:    c.signal === 'long' ? 'arrowUp' as const : 'arrowDown' as const,
      text:     c.signal === 'long' ? 'LONG' : 'SHORT',
      size:     2,  // Larger size
    }))
    
    // Debug: log signals found with dates
    const signalsCount = signals.length
    console.log(`[Signals] Found ${signalsCount} signals out of ${annotated.length} candles`)
    if (signalsCount > 0) {
      console.log(`\n[Signals] ========== ALL SIGNAL TIMESTAMPS ==========`)
      signals.forEach((c, idx) => {
        const date = new Date(c.timestamp * 1000)
        const dateStr = date.toISOString().replace('T', ' ').substring(0, 19) + ' UTC'
        console.log(`  ${idx + 1}. ${c.signal.toUpperCase()} signal at ${dateStr} (timestamp: ${c.timestamp})`)
      })
      console.log(`[Signals] ===========================================\n`)
    } else {
      console.warn(`[Signals] NO SIGNALS FOUND - This indicates either:`)
      console.warn(`  1. Signal criteria are too strict (all 4 must be met)`)
      console.warn(`  2. Data is outside NY session hours (14:30-21:00 UTC)`)
      console.warn(`  3. TPO/absorption/delta conditions not met`)
    }
    
    // Build candlestick data (without markers - they're set separately)
    const candleData = annotated.map(c => ({
      time:  c.timestamp as UTCTimestamp,
      open:  c.open  * priceScale,
      high:  c.high  * priceScale,
      low:   c.low   * priceScale,
      close: c.close * priceScale,
    }))
    
    candles.value.setData(candleData)
    
    // Create/update markers using v5 plugin API
    if (markerPrimitive.value) {
      // Detach old primitive
      try {
        markerPrimitive.value.detach()
      } catch { /* already detached */ }
      markerPrimitive.value = null
    }
    
    if (signalsCount > 0 && candles.value) {
      // Create new markers primitive
      markerPrimitive.value = createSeriesMarkers(candles.value, signalMarkers.value)
      console.log(`[Markers] Created ${signalsCount} markers using createSeriesMarkers`)
      console.log('[Markers] First marker example:', signalMarkers.value[0])
    }
  }

  // Collect all graph: keys across the dataset, then create + populate aux series.
  const graphKeys = new Set<string>()
  annotated.forEach(c =>
    Object.keys(c)
      .filter(k => k.startsWith('graph:'))
      .forEach(k => graphKeys.add(k))
  )

  for (const key of graphKeys) {
    if (!chart.value) break
    const parts = key.split(':')
    const color = parts[2] ?? '#e2e8f0'
    const pane  = parseInt(parts[1] ?? '0')
    auxSeries.value[key] = chart.value.addSeries(LineSeries, { color }, pane)
    auxSeries.value[key].setData(
      annotated
        .filter(c => c[key] != null)
        .map(c => ({ time: c.timestamp as UTCTimestamp, value: c[key] }))
    )
  }
}

// ── Live update (socket) ───────────────────────────────────────────────────────
const handleUpdate = (candle: any) => {
  const updateData: any = {
    time:  candle.timestamp as UTCTimestamp,
    open:  candle.open  * 1e-9,
    high:  candle.high  * 1e-9,
    low:   candle.low   * 1e-9,
    close: candle.close * 1e-9,
  }
  
  candles.value?.update(updateData)
  
  // Add marker if signal exists (set separately via applyOptions)
  if (candle.signal != null) {
    const date = new Date(candle.timestamp * 1000)
    const dateStr = date.toISOString().replace('T', ' ').substring(0, 19) + ' UTC'
    console.log(`[Signals] ⚡ NEW ${candle.signal.toUpperCase()} SIGNAL at ${dateStr} (timestamp: ${candle.timestamp})`)
    
    const newMarker: SeriesMarker<UTCTimestamp> = {
      time:     candle.timestamp as UTCTimestamp,
      position: candle.signal === 'long' ? 'belowBar' as const : 'aboveBar' as const,
      color:    '#fbbf24',  // Yellow/amber for high visibility
      shape:    candle.signal === 'long' ? 'arrowUp' as const : 'arrowDown' as const,
      text:     candle.signal === 'long' ? 'LONG' : 'SHORT',
      size:     2,  // Larger size
    }
    
    // Add to existing markers and update using v5 plugin API
    signalMarkers.value.push(newMarker)
    if (candles.value) {
      if (markerPrimitive.value) {
        // Update existing markers
        markerPrimitive.value.setMarkers(signalMarkers.value)
      } else {
        // Create new markers primitive
        markerPrimitive.value = createSeriesMarkers(candles.value, signalMarkers.value)
      }
    }
  }
  
  Object.keys(candle).forEach(key => {
    if (!key.startsWith('graph:')) return
    if (auxSeries.value[key]) {
      auxSeries.value[key].update({ time: candle.timestamp as UTCTimestamp, value: candle[key] })
    } else {
      if (!chart.value) return
      const parts = key.split(':')
      const color = parts[2] ?? '#e2e8f0'
      const pane  = parseInt(parts[1] ?? '0')
      auxSeries.value[key] = chart.value.addSeries(LineSeries, { color }, pane)
      auxSeries.value[key].update({ time: candle.timestamp as UTCTimestamp, value: candle[key] })
    }
  })
}

// ── Mode switching ────────────────────────────────────────────────────────────
const loadMode = async (newMode: string) => {
  mode.value = newMode
  loading.value = true
  signalCount.value = 0
  totalCandles.value = 0

  try {
    if (newMode === 'live') {
      // Seed chart with whatever is already in the in-memory deque.
      const res = await fetch(`${url}/api/candles/live`)
      const liveCandles: any[] = await res.json()
      totalCandles.value = liveCandles.length
      // Count signals in live data
      signalCount.value = liveCandles.filter((c: any) => c.signal != null).length
      // Live prices are fixed-point integers → divide by 1e9.
      loadCandles(liveCandles, 1e-9)
    } else {
      // Historical CSV: prices are already real dollar values → scale = 1.
      const res = await fetch(`${url}/api/candles/historical/${newMode}`)
      const response = await res.json()
      
      // Handle both old format (array) and new format (object with metadata)
      let historicalCandles: any[]
      if (Array.isArray(response)) {
        historicalCandles = response
        totalCandles.value = historicalCandles.length
        signalCount.value = historicalCandles.filter((c: any) => c.signal != null).length
      } else {
        historicalCandles = response.candles || []
        totalCandles.value = response.metadata?.total_candles || historicalCandles.length
        signalCount.value = response.metadata?.signal_count || historicalCandles.filter((c: any) => c.signal != null).length
        
        // Log diagnostic information
        if (response.metadata?.diagnostics) {
          const diag = response.metadata.diagnostics
          const total = diag.total || totalCandles.value
          console.log(`[Diagnostics] Signal Criteria Breakdown:`)
          console.log(`  NY Session:        ${diag.ny_session || 0} (${((diag.ny_session || 0) / total * 100).toFixed(1)}%)`)
          console.log(`  TPO Bullish (+1):  ${diag.tpo_bullish || 0} (${((diag.tpo_bullish || 0) / total * 100).toFixed(1)}%)`)
          console.log(`  TPO Bearish (-1):  ${diag.tpo_bearish || 0} (${((diag.tpo_bearish || 0) / total * 100).toFixed(1)}%)`)
          console.log(`  LVN Tap:           ${diag.lvn_tap || 0} (${((diag.lvn_tap || 0) / total * 100).toFixed(1)}%)`)
          console.log(`  SP Tap:            ${diag.sp_tap || 0} (${((diag.sp_tap || 0) / total * 100).toFixed(1)}%)`)
          console.log(`  Absorption Signal: ${diag.absorption_signal || 0} (${((diag.absorption_signal || 0) / total * 100).toFixed(1)}%)`)
          console.log(`  Delta Spike:       ${diag.delta_spike || 0} (${((diag.delta_spike || 0) / total * 100).toFixed(1)}%)`)
          console.log(`  Long Criteria Met:  ${diag.long_criteria_met || 0}`)
          console.log(`  Short Criteria Met: ${diag.short_criteria_met || 0}`)
        }
      }
      
      console.log(`[Frontend] Loaded ${totalCandles.value} candles, ${signalCount.value} signals`)
      loadCandles(historicalCandles, 1)
    }
  } finally {
    loading.value = false
  }
}

const onModeChange = (e: Event) => {
  loadMode((e.target as HTMLSelectElement).value)
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────
onMounted(async () => {
  if (!chartContainer.value) return

  // Create chart.
  chart.value = createChart(chartContainer.value, {
    ...chartOptions,
    width:  chartContainer.value.clientWidth,
    height: chartContainer.value.clientHeight,
  })
  candles.value = chart.value.addSeries(CandlestickSeries, {
    ...candlestickSeriesOptions,
    // Enable markers support
    priceFormat: {
      type: 'price',
      precision: 2,
      minMove: 0.01,
    },
  })

  // Keep chart sized to container.
  resizeObserver = new ResizeObserver(() => {
    if (chartContainer.value && chart.value) {
      chart.value.resize(
        chartContainer.value.clientWidth,
        chartContainer.value.clientHeight,
      )
    }
  })
  resizeObserver.observe(chartContainer.value)

  // Fetch available CSV dates and key levels in parallel.
  try {
    const [datesRes, levelsRes] = await Promise.all([
      fetch(`${url}/api/csv-dates`),
      fetch(`${url}/api/key-levels`),
    ])
    csvDates.value  = await datesRes.json()
    keyLevels.value = await levelsRes.json()
  } catch { /* server may not be running yet */ }

  // Draw LVN lines on the price pane. These survive setData() so they stay
  // visible across all mode switches without needing to be redrawn.
  drawKeyLevels()

  // Connect socket (always connected; updates are gated by mode).
  socket.value = io(url)
  socket.value.on('connect',    () => { connected.value = true })
  socket.value.on('disconnect', () => { connected.value = false })
  socket.value.on('candle', (candle: any) => {
    // Only apply live updates when in live mode.
    if (isLive.value) handleUpdate(candle)
  })

  // Load default mode.
  await loadMode('live')
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

        <!-- Mode selector -->
        <div class="mode-wrapper">
          <select
            class="mode-select"
            :value="mode"
            :disabled="loading"
            @change="onModeChange"
          >
            <option value="live">⚡ Live</option>
            <optgroup v-if="csvDates.length" label="Historical">
              <option v-for="date in csvDates" :key="date" :value="date">
                {{ date }}
              </option>
            </optgroup>
          </select>
          <span v-if="loading" class="mode-spinner" />
        </div>
      </div>

      <div class="header-right">
        <div v-if="!isLive && totalCandles > 0" class="signal-info">
          <span class="signal-label">Signals:</span>
          <span class="signal-count" :class="{ 'signal-count--zero': signalCount === 0 }">
            {{ signalCount }} / {{ totalCandles }}
          </span>
        </div>
        <div class="status" :class="statusClass">
          <span class="status-dot" />
          {{ statusLabel }}
        </div>
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

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.signal-info {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 6px;
  background: rgba(148, 163, 184, 0.08);
  color: #e2e8f0;
}

.signal-label {
  color: #94a3b8;
}

.signal-count {
  color: #22c55e;
  font-weight: 700;
}

.signal-count--zero {
  color: #ef4444;
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

/* ── Mode selector ── */
.mode-wrapper {
  display: flex;
  align-items: center;
  gap: 6px;
}

.mode-select {
  appearance: none;
  background: rgba(148, 163, 184, 0.08);
  color: #e2e8f0;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 6px;
  padding: 4px 28px 4px 10px;
  font-size: 12px;
  font-family: inherit;
  font-weight: 600;
  letter-spacing: 0.03em;
  cursor: pointer;
  outline: none;
  /* custom arrow */
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%2394a3b8'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 9px center;
  transition: border-color 0.15s;
}

.mode-select:focus {
  border-color: rgba(251, 191, 36, 0.5);
}

.mode-select:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.mode-select option,
.mode-select optgroup {
  background: #1a2332;
  color: #e2e8f0;
}

.mode-spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid rgba(148, 163, 184, 0.3);
  border-top-color: #fbbf24;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
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

.status--hist {
  background: rgba(99, 102, 241, 0.12);
  color: #818cf8;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
  animation: pulse 2s ease-in-out infinite;
}

.status--off .status-dot,
.status--hist .status-dot {
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
  padding: 0 0 12px;
}

.chart-container {
  flex: 1;
  margin: 10px 12px 0;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, 0.15);
}
</style>
